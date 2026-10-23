"""Person 2 contracts for reviewed skills and explainable role matching."""

from typing import Literal

from pydantic import Field, model_validator

from src.schemas.role import Contract, RoleId, SkillId


class LevelAssessment(Contract):
    method: Literal["ai_estimate"] = "ai_estimate"
    model: str
    provider: str | None = Field(default=None, exclude_if=lambda value: value is None)
    confidence: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=1, max_length=1000)
    evidence_indices: list[int] = Field(min_length=1)


class ProfileSkill(Contract):
    skill_id: SkillId
    label: str = Field(min_length=1)
    level: Literal["unknown", "beginner", "intermediate", "advanced"] = "unknown"
    evidence: list[str] = Field(min_length=1)
    confirmation: Literal["unverified", "self_reported", "confirmed"] = "unverified"
    level_assessment: LevelAssessment | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def nonblank_evidence(self):
        if any(not item.strip() for item in self.evidence):
            raise ValueError("Evidence must not be blank")
        return self


class ProfileConstraints(Contract):
    budget_myr: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    hours_per_week: float | None = Field(
        default=None, gt=0, le=168, allow_inf_nan=False
    )


class AssessmentStatus(Contract):
    status: Literal["completed", "failed", "not_configured"]
    provider: str
    message: str
    assessed_skill_count: int = Field(default=0, ge=0)
    error_code: str | None = None
    primary_provider: str = "groq"
    used_backup: bool = False


class SkillsProfile(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    profile_id: str = Field(pattern=r"^synthetic:[a-z0-9_]+$")
    synthetic: Literal[True] = True
    desired_role_id: RoleId | None = None
    skills: list[ProfileSkill] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)
    warnings: list[str] = Field(default_factory=list)
    assessment_status: AssessmentStatus | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def unique_skills(self):
        ids = [skill.skill_id for skill in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate profile skill IDs")
        return self


class SkillContribution(Contract):
    skill_id: SkillId
    label: str
    importance: float = Field(ge=0, le=1)
    coverage: Literal[0, 1]
    weighted_contribution: float = Field(ge=0, le=1)
    evidence: list[str]
    reason: str


class ScoreBreakdown(Contract):
    method: Literal["reviewed_fit_v2"] = "reviewed_fit_v2"
    earned_weight: float
    total_weight: float
    required_skill_coverage: float
    transferability: float = Field(ge=0, le=1)
    preferences: float | None = Field(default=None, ge=0, le=1)
    readiness: float = Field(ge=0, le=1)
    readiness_weight: float
    preference_weight: float


class TransferContribution(Contract):
    source_skill_id: SkillId
    target_skill_id: SkillId
    task_id: str
    partial_credit: float
    weighted_contribution: float
    evidence: list[str]
    reason: str


class RoleMatch(Contract):
    role_id: RoleId
    role_title: str
    sector_id: str
    sector: str
    catalog_synthetic: bool
    rank: int = Field(ge=1)
    fit_score: float = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    matched_skills: list[SkillContribution]
    missing_skills: list[SkillContribution]
    manually_selected: bool
    warnings: list[str]
    transferable_skills: list[TransferContribution] = Field(default_factory=list)
    matched_interests: list[str] = Field(default_factory=list)
    pinned: bool = False
