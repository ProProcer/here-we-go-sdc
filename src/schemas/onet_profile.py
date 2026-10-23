"""Versioned Person 2 result for the real occupational catalog."""

from typing import Literal

from pydantic import Field

from src.schemas.onet import CatalogCoverage
from src.schemas.profile import SkillContribution
from src.schemas.role import Contract, RoleId, SkillId


class AlignmentContribution(Contract):
    skill_id: SkillId
    label: str
    distinctiveness: float = Field(ge=1)
    role_affinity: float = Field(ge=0, le=1)
    profile_level: Literal["unknown", "beginner", "intermediate", "advanced"]
    level_factor: float = Field(ge=0, le=1)
    presence_contribution: float = Field(ge=0, le=1)
    normalized_weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)


class ProficiencyComparison(Contract):
    skill_id: SkillId
    label: str
    importance: float = Field(gt=0, le=1)
    required_source_level: float | None = Field(ge=0, le=7)
    profile_level: Literal["unknown", "beginner", "intermediate", "advanced"]
    profile_level_proxy: float | None = Field(ge=0, le=7)
    fulfilment: float = Field(ge=0, le=1)
    status: Literal["skill_unconfirmed", "required_level_unavailable", "profile_level_unassessed", "compared"]


class OnetScoreBreakdown(Contract):
    method: Literal["reviewed_onet_fit_v4"] = "reviewed_onet_fit_v4"
    general_fulfilment: float = Field(ge=0, le=1)
    proficiency_comparisons: list[ProficiencyComparison]
    profile_presence_alignment: float = Field(ge=0, le=1)
    profile_alignment: float = Field(ge=0, le=1)
    profile_alignment_weight: float = Field(ge=0, le=1)
    general_coverage_weight: float = Field(ge=0, le=1)
    evidence_breadth: float = Field(ge=0, le=1)
    supported_skill_count: int = Field(ge=0)
    alignment_contributions: list[AlignmentContribution]
    coverage: CatalogCoverage
    readiness: float = Field(ge=0, le=1)
    preferences: float | None = Field(default=None, ge=0, le=1)
    readiness_weight: float = Field(ge=0, le=1)
    preference_weight: float = Field(ge=0, le=1)
    transferability: Literal[0] = 0
    unrounded_score: float = Field(ge=0, le=100)


class SoftwareLearningOption(Contract):
    skill_id: SkillId
    label: str
    group_ids: list[str]
    group_familiarity_evidenced: bool
    meaning: Literal["optional_occupation_demand_signal"] = (
        "optional_occupation_demand_signal"
    )


class OnetRoleMatch(Contract):
    schema_version: Literal["0.2.0"] = "0.2.0"
    catalog_id: Literal["onet_31_0"] = "onet_31_0"
    catalog_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    role_id: RoleId
    role_title: str
    occupation_code: str
    family_id: str
    family: str
    catalog_synthetic: Literal[False] = False
    rank: int = Field(ge=1)
    fit_score: float = Field(ge=0, le=100)
    score_breakdown: OnetScoreBreakdown
    matched_skills: list[SkillContribution]
    missing_skills: list[SkillContribution]
    software_learning_options: list[SoftwareLearningOption]
    matched_interests: list[str]
    manually_selected: bool
    pinned: bool = False
    warnings: list[str]
