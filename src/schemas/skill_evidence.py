"""Reusable skill interpretations, separate from occupational effects and weights."""

from typing import Literal

from pydantic import Field, model_validator

from src.schemas.extraction import NonBlank
from src.schemas.role import Contract


class SkillNewsAssessment(Contract):
    news_id: NonBlank
    relevance: Literal["potentially_relevant", "not_relevant", "insufficient_evidence"]
    finding_indices: list[int] = Field(max_length=2)
    rationale: NonBlank = Field(max_length=300)
    applicability_conditions: list[NonBlank] = Field(max_length=3)
    human_checks: list[NonBlank] = Field(max_length=2)

    @model_validator(mode="after")
    def scoped_interpretation(self):
        if len(set(self.finding_indices)) != len(self.finding_indices):
            raise ValueError("Duplicate finding reference")
        if self.relevance == "potentially_relevant" and (
            not self.finding_indices or not self.applicability_conditions
        ):
            raise ValueError("Potential relevance requires findings and conditions")
        return self


class SkillAssessmentBatch(Contract):
    assessments: list[SkillNewsAssessment] = Field(min_length=1, max_length=8)


class SkillMappingChallenge(Contract):
    news_id: NonBlank
    supported: bool
    reason: NonBlank = Field(max_length=200)


class SkillChallengeBatch(Contract):
    assessments: list[SkillMappingChallenge] = Field(min_length=1, max_length=8)
