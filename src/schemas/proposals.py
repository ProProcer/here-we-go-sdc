"""Qualitative task/skill proposals, isolated from accepted evidence and weights."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from src.schemas.approval import FindingApproval
from src.schemas.extraction import Digest, NonBlank
from src.schemas.role import Contract, RoleId, SkillId, TaskId
from src.schemas.trends import EvidenceSource, TrendSignal

Explanation = Annotated[NonBlank, Field(max_length=1200)]
Aspect = Annotated[NonBlank, Field(max_length=350)]


class ProposedSkillImplication(Contract):
    skill_id: SkillId
    direction: Literal[
        "increase", "decrease", "mixed", "unchanged", "insufficient_evidence"
    ]
    less_emphasis: list[Aspect] = Field(max_length=3)
    more_emphasis: list[Aspect] = Field(max_length=3)
    rationale: Explanation
    employer_demand_direction: Literal["insufficient_evidence"]

    @model_validator(mode="after")
    def validate_aspects(self):
        needs_more = self.direction in {"increase", "mixed"}
        needs_less = self.direction in {"decrease", "mixed"}
        if (
            bool(self.more_emphasis) != needs_more
            or bool(self.less_emphasis) != needs_less
        ):
            raise ValueError(
                "Skill direction must match the explained learning aspects"
            )
        return self


class ProposedTaskImpact(Contract):
    task_id: TaskId
    assessment: Literal["conditional_interpretation", "insufficient_evidence"]
    finding_relevance: Explanation
    task_change: Explanation | None
    assumptions: list[Aspect] = Field(max_length=4)
    human_responsibilities: list[Aspect] = Field(max_length=4)
    limitations: list[Aspect] = Field(min_length=1, max_length=4)
    skill_implications: list[ProposedSkillImplication] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_assessment(self):
        if self.assessment == "insufficient_evidence":
            if (
                self.task_change is not None
                or self.assumptions
                or self.human_responsibilities
            ):
                raise ValueError(
                    "Insufficient evidence must not invent a future workflow"
                )
            if any(
                row.direction != "insufficient_evidence"
                for row in self.skill_implications
            ):
                raise ValueError("Unsupported task cannot establish a skill direction")
        elif (
            not self.task_change
            or not self.assumptions
            or not self.human_responsibilities
        ):
            raise ValueError(
                "Conditional task changes need assumptions and human responsibilities"
            )
        return self


class TaskSkillProposal(Contract):
    role_id: RoleId
    signal_id: str = Field(pattern=r"^signal:[a-z0-9_]+$")
    summary: Explanation
    tasks: list[ProposedTaskImpact] = Field(min_length=1, max_length=12)


class UnmappedRoleSkill(Contract):
    skill_id: SkillId
    label: NonBlank
    direction: Literal["insufficient_evidence"] = "insufficient_evidence"
    reason: NonBlank = "This role requirement has no task link in the current catalog; no task-level implication was inferred."


class TaskSkillProposalRecord(TaskSkillProposal):
    schema_version: Literal["0.1.0"] = "0.1.0"
    record_type: Literal["task_skill_proposal"] = "task_skill_proposal"
    review_status: Literal["pending_review"] = "pending_review"
    generated_at: datetime
    reviewed_source_path: NonBlank
    reviewed_source_sha256: Digest
    accepted_finding_sha256: Digest
    catalog_sha256: Digest
    input_sha256: Digest
    source: EvidenceSource
    finding: TrendSignal
    finding_approval: FindingApproval
    catalog_synthetic: bool
    unmapped_role_skills: list[UnmappedRoleSkill]
    provider: Literal["gemini"] = "gemini"
    requested_model: NonBlank
    returned_model: NonBlank
    prompt_version: NonBlank
    changes_skill_weights: Literal[False] = False
    status: Literal["proposed_interpretations", "insufficient_evidence"]
    limitations: list[NonBlank] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_record(self):
        if self.generated_at.utcoffset() is None:
            raise ValueError("Generation time must be timezone-aware")
        if self.generated_at < self.finding_approval.approved_at:
            raise ValueError("Proposal cannot precede finding approval")
        if (
            self.signal_id != self.finding.signal_id
            or self.source.source_id != self.finding.source_id
        ):
            raise ValueError("Proposal must identify its accepted finding and source")
        expected = (
            "insufficient_evidence"
            if all(row.assessment == "insufficient_evidence" for row in self.tasks)
            else "proposed_interpretations"
        )
        if self.status != expected:
            raise ValueError("Proposal status must reflect the task assessments")
        return self
