"""Curated role-and-skill mappings to official UN SDG targets."""

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, ValidationError, model_validator

from src.ingestion.catalog import load_role_catalog
from src.ingestion.selection import Catalog
from src.schemas.onet import OnetCatalog
from src.schemas.roadmap import SDGConnection
from src.schemas.role import Contract, RoleId, SkillId

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
    schema_version: Literal["0.1.0", "0.2.0"] = "0.1.0"
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


def validate_sdg_catalog_references(rules: SDGRuleSet, catalog: Catalog) -> SDGRuleSet:
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
    catalog: Catalog | None = None,
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

    default_path = (
        ROOT / "data/processed/onet/31.0/sdg_mappings.json"
        if isinstance(catalog, OnetCatalog)
        else DEFAULT_SDG_MAPPINGS
    )
    rules = validate_sdg_catalog_references(
        rules if rules is not None else load_sdg_rules(default_path), catalog
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


def map_role_sdg_connections(role_id, *, catalog, rules=None):
    """Role purpose depends on occupational requirements, including known skills."""
    if not isinstance(catalog, OnetCatalog):
        return []
    loaded = rules if rules is not None else load_sdg_rules(
        ROOT / "data/processed/onet/31.0/sdg_mappings.json")
    # Exclude broad learning rules: completing learning objectives and applying
    # a role to an SDG are distinct connections.
    role_rules = loaded.model_copy(update={"rules": [r for r in loaded.rules if r.role_ids]})
    role_skills = {row.skill_id for row in catalog.role_skills if row.role_id == role_id}
    connections = [connection.model_copy(update={"scope": "role_application"})
            for connection in map_sdg_connections(role_id, role_skills,
                rules=role_rules, catalog=catalog)]
    if connections or rules is not None:
        return connections
    # Where a sector-specific rule is absent, state a conditional opportunity
    # grounded in an actual task. This is an application inference, not a UN
    # classification or evidence of economic/educational impact.
    roles = {r.role_id: r for r in catalog.roles}
    role = roles[role_id]
    skills = {s.skill_id: s for s in catalog.taxonomy.skills}
    tasks = {t.task_id: t for t in catalog.taxonomy.tasks}
    analytical = {sid for sid in role_skills if skills[sid].label in {
        "Critical Thinking", "Complex Problem Solving", "Systems Analysis", "Systems Evaluation",
        "Programming", "Operations Analysis", "Monitoring", "Mathematics"}}
    task = next((tasks[tid] for tid in role.task_ids if re.search(
        r"\b(data|software|technolog\w*|systems?|process\w*|efficien\w*|productiv\w*|analy\w*)\b", tasks[tid].label, re.I)), None)
    if analytical and task:
        return [SDGConnection(role_id=role_id, skill_ids=sorted(analytical), sdg_id="SDG 8", target_id="8.2",
            contribution="indirect", scope="role_application", evidence_kind="inferred",
            rationale=f"In {role.role_title}, applying analytical skills to improve the quality or efficiency of work such as ‘{task.label}’ could support productivity through technological upgrading under target 8.2. The link depends on a demonstrated improvement; a job title alone does not establish an SDG impact.",
            evidence_url="https://sdgs.un.org/goals/goal8")]
    return [SDGConnection(role_id=role_id, skill_ids=sorted(role_skills), sdg_id="SDG 4", target_id="4.4",
        contribution="indirect", scope="career_preparation", evidence_kind="inferred",
        rationale=f"Preparing for or progressing in {role.role_title} by developing relevant occupational skills connects this career pathway to target 4.4. This is a career-preparation link, not a claim that every activity in this occupation advances an SDG.",
        evidence_url="https://sdgs.un.org/goals/goal4")]


GOALS = {"SDG 3": "Good Health and Well-being", "SDG 4": "Quality Education",
    "SDG 8": "Decent Work and Economic Growth", "SDG 9": "Industry, Innovation and Infrastructure",
    "SDG 16": "Peace, Justice and Strong Institutions"}
TARGETS = {"4.4": "Work-relevant skills", "8.2": "Productivity through technological upgrading",
    "3.c": "Health-workforce capability", "4.c": "Teacher capability", "9.5": "Research and technological capability",
    "16.3": "Access to justice"}


def build_sdg_summary(role_id, skill_ids, *, catalog, profile_skills=(), planned_skill_ids=(), rules=None):
    """Give every contextual skill an individual, explained SDG tag.

    General capabilities, confirmed skills, selected tools and prerequisites
    remain visible even when they are no longer learning gaps.
    """
    from src.schemas.sdg import ExplainedSDGConnection, SDGSummary, SkillSDGMapping

    role = next(r for r in catalog.roles if r.role_id == role_id)
    skills = {s.skill_id: s for s in catalog.taxonomy.skills}
    requested = set(skill_ids)
    if not requested <= set(skills):
        raise ValueError("Unknown SDG skill")
    required = {r.skill_id for r in catalog.role_skills if r.role_id == role_id}
    relevant = required | {r.skill_id for r in catalog.software_associations if r.role_id == role_id}
    confirmed = {r.skill_id for r in profile_skills if r.confirmation in {"confirmed", "self_reported"}}
    reviewed = {r.skill_id for r in profile_skills}
    planned = set(planned_skill_ids)
    loaded = rules if rules is not None else load_sdg_rules(ROOT / "data/processed/onet/31.0/sdg_mappings.json")
    connections = map_sdg_connections(role_id, requested, catalog=catalog, rules=loaded)
    role_connections = map_role_sdg_connections(role_id, catalog=catalog, rules=rules)

    def explain(connection, label=None):
        if label:
            example = (f"Demonstrate {label} in a work sample or portfolio: explain your approach, check the result, and record feedback. Use it to plan a first role, a career transition, or continued development at work."
                if connection.target_id == "4.4" else
                f"Use {label} in a relevant {role.role_title} task, document the result, and explain how that application supports the target.")
        elif connection.scope == "career_preparation":
            example = f"Agree a role-relevant learning goal for {role.role_title}, practise it in a realistic task, and keep evidence of the capability developed."
        else:
            example = f"Choose an actual {role.role_title} task, agree what a better outcome would look like, and document a small improvement with feedback from the people involved."
        condition = ("Relevant skill development or demonstrated capability is the link. No job offer, formal qualification or measured societal impact is claimed."
            if connection.target_id == "4.4" else
            "The contribution depends on where and how the skill is applied. Check service quality, access and worker wellbeing; the mapping does not establish a measured SDG outcome.")
        return ExplainedSDGConnection(**connection.model_dump(), goal_title=GOALS.get(connection.sdg_id, connection.sdg_id),
            target_label=TARGETS.get(connection.target_id, f"Target {connection.target_id}"), application_example=example, condition=condition)

    mappings = []
    for sid in sorted(requested, key=lambda s: (s not in confirmed, s not in planned, skills[s].label.casefold())):
        by_target = {c.target_id: c.model_copy(update={"skill_ids": [sid]}) for c in connections if sid in c.skill_ids}
        for connection in role_connections:
            if connection.scope == "role_application" and sid in connection.skill_ids:
                by_target[connection.target_id] = connection.model_copy(update={"skill_ids": [sid]})
        found = list(by_target.values())
        if not found and rules is None:
            found = [SDGConnection(role_id=role_id, skill_ids=[sid], sdg_id="SDG 4", target_id="4.4",
                contribution="indirect", evidence_kind="inferred", evidence_url="https://sdgs.un.org/goals/goal4",
                rationale=f"Developing, maintaining and demonstrating {skills[sid].label} as a work-relevant capability connects to target 4.4.")]
        if not found:
            continue
        mappings.append(SkillSDGMapping(skill_id=sid, label=skills[sid].label, kind=skills[sid].kind,
            status="confirmed" if sid in confirmed else "learning_goal" if sid in planned else "needs_review" if sid in reviewed else "role_requirement",
            role_relevant=sid in relevant, connections=[explain(c, skills[sid].label) for c in found]))
    return SDGSummary(role_id=role_id, role_title=role.role_title,
        role_connections=[explain(c) for c in role_connections], skills=mappings,
        mapped_skill_count=len(mappings), skill_count=len(requested),
        interpretation_note="These are application-authored, conditional connections to official UN targets. The UN defines the targets; it has not endorsed these role or skill mappings. A connection is a possible contribution, not evidence of impact or a hiring assessment.")
