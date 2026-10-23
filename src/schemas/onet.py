"""Explicit 0.2 O*NET handoff; the synthetic 0.1 contract remains unchanged."""

import unicodedata
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from src.schemas.role import Contract, RoleId, Skill, SkillId, SourceId, TaskId


class InputFile(Contract):
    filename: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=0)
    documentation_url: str


class CatalogProvenance(Contract):
    release: Literal["31.0"] = "31.0"
    release_month: Literal["2026-08"] = "2026-08"
    verified_at: date
    downloaded_at: date | None = None
    geography: Literal["United States"] = "United States"
    license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    license_url: str = "https://creativecommons.org/licenses/by/4.0/"
    source_url: str = "https://www.onetcenter.org/database.html"
    attribution: str
    modifications: list[str]
    inputs: list[InputFile]


class CatalogSkill(Skill):
    kind: Literal["general", "software"]
    element_id: str | None = None
    description: str | None = None


class SoftwareGroup(Contract):
    group_id: str = Field(pattern=r"^group:onet_[a-z0-9_]+$")
    label: str
    element_id: str
    skill_ids: list[SkillId] = Field(min_length=1)
    meaning: Literal["category_familiarity_not_tool_equivalence"] = (
        "category_familiarity_not_tool_equivalence"
    )


class CatalogTask(Contract):
    task_id: TaskId
    label: str
    source_task_id: str
    task_type: str
    source_updated_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    skill_ids: list[SkillId] = Field(default_factory=list)
    mapping_status: Literal["unmapped"] = "unmapped"

    @model_validator(mode="after")
    def no_invented_links(self):
        if self.skill_ids:
            raise ValueError("Imported tasks have no source task-to-skill mapping")
        return self


class OccupationalFamily(Contract):
    family_id: str = Field(pattern=r"^family:soc_\d{2}$")
    label: str
    classification: Literal["SOC major occupational group"] = (
        "SOC major occupational group"
    )


class CatalogTaxonomy(Contract):
    version: Literal["0.2.0"] = "0.2.0"
    skills: list[CatalogSkill] = Field(min_length=1)
    tasks: list[CatalogTask] = Field(min_length=1)
    occupational_families: list[OccupationalFamily] = Field(min_length=1)
    software_groups: list[SoftwareGroup] = Field(min_length=1)


class CatalogRole(Contract):
    role_id: RoleId
    occupation_code: str = Field(pattern=r"^\d{2}-\d{4}\.\d{2}$")
    role_title: str
    description: str
    aliases: list[str]
    family_id: str
    task_ids: list[TaskId] = Field(min_length=1)
    source_ids: list[SourceId] = Field(min_length=1)
    latest_rating_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    synthetic: Literal[False] = False


class GeneralRequirement(Contract):
    role_id: RoleId
    skill_id: SkillId
    importance: float = Field(gt=0, le=1, allow_inf_nan=False)
    source_importance: float = Field(ge=1, le=5, allow_inf_nan=False)
    source_level: float | None = Field(default=None, ge=0, le=7, allow_inf_nan=False)
    level_suppressed: bool
    updated_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    evidence_ids: list[SourceId] = Field(min_length=1)
    weight_basis: Literal["source_importance_divided_by_5"] = (
        "source_importance_divided_by_5"
    )

    @model_validator(mode="after")
    def consistent_rating(self):
        if abs(self.importance - self.source_importance / 5) > 1e-9:
            raise ValueError("Importance must equal source importance / 5")
        if self.level_suppressed and self.source_level is not None:
            raise ValueError("Suppressed level must not be exposed as a usable rating")
        return self


class SoftwareAssociation(Contract):
    role_id: RoleId
    skill_id: SkillId
    group_id: str
    in_demand: bool
    hot_technology: bool
    evidence_ids: list[SourceId] = Field(min_length=1)
    meaning: Literal["occupation_example_not_universal_requirement"] = (
        "occupation_example_not_universal_requirement"
    )


class OnetSource(Contract):
    source_id: SourceId
    title: str
    url: str
    license: str
    synthetic: Literal[False] = False


class ExcludedOccupation(Contract):
    occupation_code: str
    title: str
    reasons: list[str] = Field(min_length=1)


class OnetCatalog(Contract):
    schema_version: Literal["0.2.0"] = "0.2.0"
    catalog_id: Literal["onet_31_0"] = "onet_31_0"
    synthetic: Literal[False] = False
    provenance: CatalogProvenance
    taxonomy: CatalogTaxonomy
    sources: list[OnetSource] = Field(min_length=1)
    roles: list[CatalogRole] = Field(min_length=1)
    role_skills: list[GeneralRequirement] = Field(min_length=1)
    software_associations: list[SoftwareAssociation] = Field(min_length=1)
    excluded_occupations: list[ExcludedOccupation]
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        def unique(rows, attribute):
            keys = [getattr(row, attribute) for row in rows]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {attribute}")
            return {getattr(row, attribute): row for row in rows}

        def require(ids, known, label):
            unknown = {value for value in ids if value not in known}
            if unknown:
                raise ValueError(f"Unknown {label}: {unknown}")

        roles = unique(self.roles, "role_id")
        unique(self.roles, "occupation_code")
        skills = unique(self.taxonomy.skills, "skill_id")
        tasks = unique(self.taxonomy.tasks, "task_id")
        families = unique(self.taxonomy.occupational_families, "family_id")
        groups = unique(self.taxonomy.software_groups, "group_id")
        sources = unique(self.sources, "source_id")
        unique(self.excluded_occupations, "occupation_code")
        if {r.occupation_code for r in self.roles} & {
            r.occupation_code for r in self.excluded_occupations
        }:
            raise ValueError("Included and excluded occupations overlap")
        aliases = {}
        for skill in skills.values():
            for alias in [skill.skill_id, skill.label, *skill.aliases]:
                key = " ".join(unicodedata.normalize("NFKC", alias).casefold().split())
                if key in aliases and aliases[key] != skill.skill_id:
                    raise ValueError(f"Ambiguous skill alias: {alias}")
                aliases[key] = skill.skill_id
        for group in groups.values():
            require(group.skill_ids, skills, "group skills")
            if len(group.skill_ids) != len(set(group.skill_ids)):
                raise ValueError("Duplicate group member")
            if any(skills[s].kind != "software" for s in group.skill_ids):
                raise ValueError("Software group contains a general skill")
        for role in roles.values():
            require(role.task_ids, tasks, "role tasks")
            require([role.family_id], families, "occupational family")
            require(role.source_ids, sources, "role sources")
        covered = set()
        pairs = set()
        for row in self.role_skills:
            require([row.role_id], roles, "requirement role")
            require([row.skill_id], skills, "requirement skill")
            require(row.evidence_ids, sources, "requirement sources")
            if skills[row.skill_id].kind != "general":
                raise ValueError("role_skills contains a software observation")
            key = (row.role_id, row.skill_id)
            if key in pairs:
                raise ValueError("Duplicate role/skill pair")
            pairs.add(key)
            covered.add(row.role_id)
        if covered != set(roles):
            raise ValueError("Every role must have relevant general requirements")
        associations = set()
        for row in self.software_associations:
            require([row.role_id], roles, "software role")
            require([row.skill_id], skills, "software skill")
            require([row.group_id], groups, "software group")
            require(row.evidence_ids, sources, "software sources")
            if row.skill_id not in groups[row.group_id].skill_ids:
                raise ValueError("Software association is outside its group")
            key = (row.role_id, row.skill_id, row.group_id)
            if key in associations:
                raise ValueError("Duplicate software association")
            associations.add(key)
        return self


class CoveragePolicy(Contract):
    profile_alignment_share: float = Field(default=0.65, gt=0, lt=1, allow_inf_nan=False)
    general_share: float = Field(default=0.5, gt=0, lt=1, allow_inf_nan=False)
    group_share: float = Field(default=0.5, gt=0, lt=1, allow_inf_nan=False)
    basis: Literal["exploratory_not_empirically_calibrated"] = (
        "exploratory_not_empirically_calibrated"
    )


class CatalogCoverage(Contract):
    method: Literal["onet_grouped_coverage_v1"] = "onet_grouped_coverage_v1"
    role_id: RoleId
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    general_coverage: float = Field(ge=0, le=1)
    software_group_coverage: float | None = Field(default=None, ge=0, le=1)
    software_exact_coverage: float | None = Field(default=None, ge=0, le=1)
    software_coverage: float | None = Field(default=None, ge=0, le=1)
    effective_general_share: float = Field(ge=0, le=1)
    policy: CoveragePolicy
    matched_general_skill_ids: list[SkillId]
    unconfirmed_general_skill_ids: list[SkillId]
    matched_software_skill_ids: list[SkillId]
    software_learning_options: list[SkillId]
    group_matches: dict[str, list[SkillId]]
    warnings: list[str]
