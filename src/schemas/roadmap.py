"""Typed contracts for verified courses and personalized learning plans."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from src.schemas.profile import ProfileSkill
from src.schemas.role import Contract, RoleId, SkillId


CourseId = Annotated[str, Field(pattern=r"^course:[a-z0-9_]+$")]
ScenarioId = Literal["baseline", "moderate_ai_change", "rapid_ai_change"]
MilestoneStage = Literal[
    "foundations", "core_skills", "applied_practice", "role_readiness"
]


class CourseCost(Contract):
    """One verified access route; unknown prices never become zero-cost routes."""

    access: Literal["free", "free_to_audit", "paid"]
    amount: float = Field(ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    includes_certificate: bool

    @model_validator(mode="after")
    def validate_amount_and_currency(self):
        if self.access == "paid" and (self.amount <= 0 or self.currency is None):
            raise ValueError("Paid access requires a positive amount and currency")
        if self.access != "paid" and self.amount != 0:
            raise ValueError("Free access routes must have zero cost")
        return self


class CourseDuration(Contract):
    hours: float = Field(gt=0, allow_inf_nan=False)
    display_text: str = Field(min_length=1)
    basis: Literal["provider_stated", "clearly_estimated"]


class VerifiedCourse(Contract):
    """A course that passed every gate required for recommendation."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    course_id: CourseId
    title: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    course_url: HttpUrl
    evidence_url: HttpUrl
    source_tier: Literal["trusted", "wider_web"]
    skill_ids: list[SkillId] = Field(min_length=1)
    coverage_strength: dict[SkillId, float]
    cost: CourseCost
    duration: CourseDuration
    prerequisite_skill_ids: list[SkillId] = Field(default_factory=list)
    delivery_mode: Literal["online", "hybrid", "in_person"]
    language: str = Field(min_length=1)
    country_codes: list[str] = Field(default_factory=list)
    enrollment_status: Literal["open"] = "open"
    last_verified_at: datetime
    verification_status: Literal["verified"] = "verified"
    validation_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_coverage_and_availability(self):
        if set(self.coverage_strength) != set(self.skill_ids):
            raise ValueError("Coverage strengths must match course skill IDs exactly")
        if any(not 0 < score <= 1 for score in self.coverage_strength.values()):
            raise ValueError("Coverage strengths must be finite and within (0, 1]")
        if self.delivery_mode == "in_person" and not self.country_codes:
            raise ValueError("In-person courses require at least one country code")
        if len(self.skill_ids) != len(set(self.skill_ids)):
            raise ValueError("Course skill IDs must be unique")
        if len(self.prerequisite_skill_ids) != len(set(self.prerequisite_skill_ids)):
            raise ValueError("Prerequisite skill IDs must be unique")
        return self


class ValidationCheck(Contract):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)
    evidence_url: HttpUrl | None = None


class CourseValidationLog(Contract):
    """Audit record for accepted and withheld course candidates."""

    candidate_url: HttpUrl
    final_url: HttpUrl | None = None
    checked_at: datetime
    status: Literal["verified", "withheld", "rejected"]
    checks: list[ValidationCheck] = Field(min_length=1)
    course_id: CourseId | None = None
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "verified":
            if self.course_id is None or self.reasons:
                raise ValueError("Verified results need a course ID and no failure reasons")
            if not all(check.passed for check in self.checks):
                raise ValueError("Verified results cannot contain failed checks")
        elif not self.reasons:
            raise ValueError("Withheld or rejected results require a reason")
        return self


class PrioritizedGap(Contract):
    """A Person 2 gap joined to Person 3's already-adjusted priority."""

    skill_id: SkillId
    label: str = Field(min_length=1)
    gap_reason: str = Field(min_length=1)
    person2_importance: float = Field(ge=0, le=1, allow_inf_nan=False)
    baseline_priority: float = Field(ge=0, le=1, allow_inf_nan=False)
    applied_adjustment: float = Field(ge=-1, le=1, allow_inf_nan=False)
    adjusted_priority: float = Field(ge=0, le=1, allow_inf_nan=False)


class LearningStep(Contract):
    order: int = Field(ge=1)
    skill_ids: list[SkillId] = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    course_id: CourseId | None = None
    estimated_hours: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    prerequisite_skill_ids: list[SkillId] = Field(default_factory=list)
    practice_activity: str = Field(min_length=1)
    completion_evidence: str = Field(min_length=1)
    resource_status: Literal["verified", "verified_resource_not_found"]

    @model_validator(mode="after")
    def validate_resource_reference(self):
        if self.resource_status == "verified" and self.course_id is None:
            raise ValueError("Verified learning steps require a course ID")
        if self.resource_status == "verified_resource_not_found" and self.course_id:
            raise ValueError("Resource-not-found steps cannot reference a course")
        if len(self.skill_ids) != len(set(self.skill_ids)):
            raise ValueError("Learning-step skill IDs must be unique")
        return self


class Milestone(Contract):
    stage: MilestoneStage
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    steps: list[LearningStep] = Field(min_length=1)


class SDGConnection(Contract):
    role_id: RoleId
    skill_ids: list[SkillId] = Field(min_length=1)
    sdg_id: str = Field(pattern=r"^SDG ([1-9]|1[0-7])$")
    target_id: str = Field(pattern=r"^(?:[1-9]|1[0-7])\.[0-9a-z]+$")
    contribution: Literal["direct", "indirect"]
    rationale: str = Field(min_length=1)
    evidence_url: HttpUrl
    evidence_kind: Literal["observed", "inferred"]
    scope: Literal["learning", "role_application", "career_preparation"] = Field(
        default="learning", exclude_if=lambda value: value == "learning"
    )


class CostTotal(Contract):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: float = Field(ge=0, allow_inf_nan=False)


class LearningPlan(Contract):
    """Planner output consumed directly by the containing application."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    generated_at: datetime
    profile_id: str = Field(min_length=1)
    role_id: RoleId
    scenario_id: ScenarioId
    fit_score: float = Field(ge=0, le=100, allow_inf_nan=False)
    reviewed_skills: list[ProfileSkill]
    prioritized_gaps: list[PrioritizedGap]
    selected_courses: list[VerifiedCourse]
    milestones: list[Milestone]
    uncovered_skill_ids: list[SkillId] = Field(default_factory=list)
    total_estimated_hours: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    cost_totals: list[CostTotal] = Field(default_factory=list)
    sdg_connections: list[SDGConnection]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan_references(self):
        gap_ids = [gap.skill_id for gap in self.prioritized_gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Prioritized gap IDs must be unique")

        course_ids = [course.course_id for course in self.selected_courses]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("Selected course IDs must be unique")
        known_courses = set(course_ids)

        stages = [milestone.stage for milestone in self.milestones]
        if len(stages) != len(set(stages)):
            raise ValueError("Each milestone stage may appear only once")

        steps = [step for milestone in self.milestones for step in milestone.steps]
        orders = [step.order for step in steps]
        if orders != list(range(1, len(steps) + 1)):
            raise ValueError("Learning-step order must be unique, contiguous, and sorted")
        for step in steps:
            if step.course_id is not None and step.course_id not in known_courses:
                raise ValueError(f"Unknown selected course: {step.course_id}")

        gap_set = set(gap_ids)
        if not set(self.uncovered_skill_ids) <= gap_set:
            raise ValueError("Uncovered skills must be actual prioritized gaps")
        if len(self.uncovered_skill_ids) != len(set(self.uncovered_skill_ids)):
            raise ValueError("Uncovered skill IDs must be unique")

        currencies = [total.currency for total in self.cost_totals]
        if len(currencies) != len(set(currencies)):
            raise ValueError("Cost totals must contain at most one row per currency")
        return self
