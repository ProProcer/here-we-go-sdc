"""Grounded AI source-review drafts; deliberately separate from human approval."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.schemas.extraction import NonBlank
from src.schemas.role import Contract


class ReviewReference(Contract):
    document_id: NonBlank
    passage_id: NonBlank


class ReviewFinding(Contract):
    claim: NonBlank = Field(max_length=300)
    evidence_type: Literal[
        "observed_usage",
        "benchmark",
        "adoption_survey",
        "labour_market_observation",
        "author_projection",
        "other",
    ]
    reference: ReviewReference
    quote: NonBlank = Field(max_length=100, pattern=r"^\S+(?:\s+\S+){0,7}$")

    @field_validator("quote")
    @classmethod
    def short_quote(cls, value):
        if len(value.split()) > 8:
            raise ValueError("At most eight supporting quote words")
        return value


class ReviewCheck(Contract):
    dimension: Literal[
        "authorship", "methods", "limitations", "role_relevance", "work_relevance"
    ]
    status: Literal["supported", "unclear", "not_found"]
    explanation: NonBlank = Field(max_length=180)
    references: list[ReviewReference] = Field(max_length=2)


class ReviewDraft(Contract):
    summary: NonBlank = Field(max_length=300)
    findings: list[ReviewFinding] = Field(max_length=2)
    checks: list[ReviewCheck] = Field(min_length=4, max_length=4)
    cross_source_status: Literal[
        "consistent_with_linked_study",
        "possible_independent_support",
        "conflicting",
        "not_established",
    ]
    cross_source_explanation: NonBlank = Field(max_length=240)
    cross_source_references: list[ReviewReference] = Field(max_length=3)
    recommendation: Literal[
        "consider_approval", "investigate", "skip_for_role", "skip_for_scope"
    ]
    human_checks: list[NonBlank] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def required_dimensions(self):
        dimensions = {r.dimension for r in self.checks}
        if not any(
            dimensions == {"authorship", "methods", "limitations", relevance}
            for relevance in ("role_relevance", "work_relevance")
        ):
            raise ValueError("Review must cover all four dimensions exactly once")
        text = " ".join(
            [
                self.summary,
                *[r.claim for r in self.findings],
                *[r.explanation for r in self.checks],
                self.cross_source_explanation,
                *self.human_checks,
            ]
        )
        if len(text.split()) > 180:
            raise ValueError("Review narrative exceeds the 180-word budget")
        return self


class FindingChallenge(Contract):
    finding_index: int = Field(ge=0, le=1)
    verdict: Literal["supported", "overstated", "unsupported"]
    reason: NonBlank = Field(max_length=180)


class ReviewChallenge(Contract):
    findings: list[FindingChallenge] = Field(max_length=2)
    checks_supported: bool
    cross_source_supported: bool
    recommendation_supported: bool
    unresolved_issues: list[NonBlank] = Field(max_length=3)

    @model_validator(mode="after")
    def unique_findings(self):
        ids = [r.finding_index for r in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate challenged finding")
        return self
