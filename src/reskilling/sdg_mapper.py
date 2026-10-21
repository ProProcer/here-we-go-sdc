"""Curated role-and-skill mappings to official UN SDG targets."""

import json
from pathlib import Path
from typing import Iterable, Literal
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, ValidationError, model_validator

from src.ingestion.catalog import load_role_catalog
from src.schemas.roadmap import SDGConnection
from src.schemas.role import Contract, RoleCatalog, RoleId, SkillId


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SDG_MAPPINGS = ROOT / "data/processed/sdg_mappings.json"


class SDGRule(Contract):
    rule_id: str = Field(pattern=r"^sdg_rule:[a-z0-9_]+$")
    role_ids: list[RoleId] = Field(default_factory=list)
    skill_ids: list[SkillId] = Field(min_length=1)
    match: Literal["any_skill", "all_skills"] = "any_skill"
    sdg_id: str = Field(pattern=r"^SDG ([1-9]|1[0-7])$")
    target_id: str = Field(pattern=r"^(?:[1-9]|1[0-7])\.[0-9a-z]+$")
    contribution: Literal["direct", "indirect"]
    rationale: str = Field(min_length=1)
    evidence_url: HttpUrl

    @model_validator(mode="after")
    def validate_rule(self):
        if len(self.role_ids) != len(set(self.role_ids)):
            raise ValueError("SDG rule role IDs must be unique")
        if len(self.skill_ids) != len(set(self.skill_ids)):
            raise ValueError("SDG rule skill IDs must be unique")

        sdg_number = self.sdg_id.removeprefix("SDG ")
        target_number = self.target_id.split(".", 1)[0]
        if sdg_number != target_number:
            raise ValueError("SDG and target numbers must agree")

        parsed = urlsplit(str(self.evidence_url))
        host = (parsed.hostname or "").rstrip(".").casefold()
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not (host == "un.org" or host.endswith(".un.org"))
        ):
            raise ValueError("SDG evidence must be an official UN HTTPS URL")
        return self


class SDGRuleSet(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    rules: list[SDGRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_rules(self):
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Duplicate SDG rule IDs")
        return self


class SDGMappingError(ValueError):
    """Raised when curated SDG data cannot be decoded or validated."""


def load_sdg_rules(path: str | Path = DEFAULT_SDG_MAPPINGS) -> SDGRuleSet:
    """Load curated rules; an absent file is an explicit empty mapping set."""

    path = Path(path)
    if not path.exists():
        return SDGRuleSet()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SDGRuleSet.model_validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise SDGMappingError(
            f"SDG mapping file is unavailable or invalid: {path.name}"
        ) from exc


def validate_sdg_catalog_references(
    rules: SDGRuleSet, catalog: RoleCatalog
) -> SDGRuleSet:
    """Reject stale role or skill IDs before mappings reach a learning plan."""

    known_roles = {role.role_id for role in catalog.roles}
    known_skills = {skill.skill_id for skill in catalog.taxonomy.skills}
    for rule in rules.rules:
        unknown_roles = set(rule.role_ids) - known_roles
        unknown_skills = set(rule.skill_ids) - known_skills
        if unknown_roles:
            raise SDGMappingError(
                f"SDG rule {rule.rule_id} references unknown roles: "
                f"{sorted(unknown_roles)}"
            )
        if unknown_skills:
            raise SDGMappingError(
                f"SDG rule {rule.rule_id} references unknown skills: "
                f"{sorted(unknown_skills)}"
            )
    return rules


def map_sdg_connections(
    role_id: RoleId,
    skill_ids: Iterable[SkillId],
    *,
    rules: SDGRuleSet | None = None,
    catalog: RoleCatalog | None = None,
) -> list[SDGConnection]:
    """Return only curated rules that match the selected role and planned skills."""

    catalog = catalog if catalog is not None else load_role_catalog()
    known_roles = {role.role_id for role in catalog.roles}
    known_skills = {skill.skill_id for skill in catalog.taxonomy.skills}
    if role_id not in known_roles:
        raise ValueError(f"Unknown role: {role_id}")

    requested = set(skill_ids)
    unknown_skills = requested - known_skills
    if unknown_skills:
        raise ValueError(f"Unknown planned skills: {sorted(unknown_skills)}")
    if not requested:
        return []

    rules = validate_sdg_catalog_references(
        rules if rules is not None else load_sdg_rules(), catalog
    )
    applicable = [
        rule
        for rule in rules.rules
        if (not rule.role_ids or role_id in rule.role_ids)
        and (
            set(rule.skill_ids) <= requested
            if rule.match == "all_skills"
            else bool(set(rule.skill_ids) & requested)
        )
    ]
    applicable.sort(
        key=lambda rule: (
            0 if role_id in rule.role_ids else 1,
            -len(rule.skill_ids),
            rule.rule_id,
        )
    )

    claimed: set[tuple[str, str]] = set()
    connections = []
    for rule in applicable:
        matched = set(rule.skill_ids) & requested
        unmatched = {
            skill_id
            for skill_id in matched
            if (rule.target_id, skill_id) not in claimed
        }
        if not unmatched:
            continue
        connections.append(
            SDGConnection(
                role_id=role_id,
                skill_ids=sorted(unmatched),
                sdg_id=rule.sdg_id,
                target_id=rule.target_id,
                contribution=rule.contribution,
                rationale=rule.rationale,
                evidence_url=rule.evidence_url,
                evidence_kind="inferred",
            )
        )
        claimed.update((rule.target_id, skill_id) for skill_id in unmatched)
    return connections
