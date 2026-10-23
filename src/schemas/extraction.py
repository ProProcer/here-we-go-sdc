"""Candidate findings are deliberately incompatible with accepted evidence."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from src.schemas.role import Contract
from src.schemas.sources import ApprovedSource

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PassageId = Annotated[str, Field(pattern=r"^p[0-9]{4,}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MAX_FINDINGS = 3
MAX_QUOTE_WORDS = 8
EvidenceType = Literal[
    "observed_usage",
    "benchmark",
    "adoption_survey",
    "labour_market_observation",
    "author_projection",
    "other",
]


class StudyPeriod(Contract):
    start: date | None
    end: date | None
    passage_id: PassageId | None

    @model_validator(mode="after")
    def validate_period(self):
        if self.start is None and self.end is None and self.passage_id is None:
            return self
        if self.start is None or self.end is None or self.passage_id is None:
            raise ValueError("Study dates need both endpoints and a supporting passage")
        if self.end < self.start:
            raise ValueError("Study period ends before it starts")
        return self


class PassageQuote(Contract):
    passage_id: PassageId
    quote: NonBlank = Field(max_length=240)

    @field_validator("quote")
    @classmethod
    def validate_quote_length(cls, value: str) -> str:
        if len(value.split()) > MAX_QUOTE_WORDS:
            raise ValueError("Supporting quote must contain at most eight words")
        return value


class CandidateFinding(Contract):
    claim: NonBlank = Field(
        max_length=600, description="Original paraphrase, not a copied passage."
    )
    evidence_type: EvidenceType
    support: PassageQuote
    study_period: StudyPeriod
    limitations: list[Annotated[NonBlank, Field(max_length=350)]] = Field(
        min_length=1, max_length=4
    )


class ExtractionBatch(Contract):
    findings: list[CandidateFinding] = Field(max_length=MAX_FINDINGS)
    no_findings_reason: NonBlank | None

    @model_validator(mode="after")
    def validate_empty_result(self):
        if not self.findings and self.no_findings_reason is None:
            raise ValueError("An empty extraction needs an explanation")
        if self.findings and self.no_findings_reason is not None:
            raise ValueError(
                "A nonempty extraction must not claim that no findings exist"
            )
        return self


class GroundedPassage(PassageQuote):
    section: NonBlank
    passage_sha256: Digest
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.quote_end - self.quote_start != len(self.quote):
            raise ValueError("Quote offsets must describe the stored normalized quote")
        return self


class GroundedFinding(CandidateFinding):
    candidate_id: str = Field(pattern=r"^candidate:[a-f0-9]{24}$")
    support: GroundedPassage
    study_period_passage_sha256: Digest | None
    review_status: Literal["pending_review"] = "pending_review"


class ExtractionRecord(ExtractionBatch):
    schema_version: Literal["0.1.0"] = "0.1.0"
    record_type: Literal["candidate_extraction"] = "candidate_extraction"
    review_status: Literal["pending_review"] = "pending_review"
    source: ApprovedSource
    report_title: NonBlank
    fetched_at: datetime
    response_sha256: Digest
    parsed_text_sha256: Digest
    passage_count: int = Field(gt=0)
    parsed_characters: int = Field(gt=0)
    provider: Literal["gemini", "runpod", "groq"] = "gemini"
    request_attempts: list[dict] = Field(default_factory=list, exclude_if=lambda value: not value)
    requested_model: NonBlank
    returned_model: NonBlank
    prompt_version: NonBlank
    findings: list[GroundedFinding] = Field(max_length=MAX_FINDINGS)
    no_findings_reason: NonBlank | None
    limitations: list[NonBlank] = Field(min_length=1)
