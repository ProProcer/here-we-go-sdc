"""Explicit finding approval plans and the provenance saved on admission."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from src.schemas.extraction import (
    Digest,
    EvidenceType,
    GroundedPassage,
    NonBlank,
    StudyPeriod,
)
from src.schemas.role import Contract, RoleId, TaskId
from src.schemas.sources import ApprovedSource

CandidateId = Annotated[str, Field(pattern=r"^candidate:[a-f0-9]{24}$")]


def reviewed_definition_fingerprint(definition: dict) -> str:
    """Bind approved wording/mapping while allowing a later retrieval date."""
    payload = {
        **definition,
        "source": {
            key: value
            for key, value in definition["source"].items()
            if key != "retrieved_at"
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


class ApprovedTaskMapping(Contract):
    role_id: RoleId
    task_id: TaskId
    interpretation: NonBlank = Field(max_length=2000)


class ApprovalPlan(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    record_type: Literal["finding_approval_plan"] = "finding_approval_plan"
    status: Literal["prepared"] = "prepared"
    prepared_at: datetime
    candidate_path: NonBlank
    candidate_file_sha256: Digest
    candidate_id: CandidateId
    parsed_text_sha256: Digest
    source: ApprovedSource
    reviewed_evidence_type: EvidenceType
    reviewed_claim: NonBlank = Field(max_length=600)
    reviewed_limitations: list[Annotated[NonBlank, Field(max_length=350)]] = Field(
        min_length=1, max_length=4
    )
    task_mapping: ApprovedTaskMapping | None = None

    @model_validator(mode="after")
    def validate_timestamp(self):
        if self.prepared_at.utcoffset() is None:
            raise ValueError("Plan timestamp must be timezone-aware")
        return self


class FindingApproval(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    review_status: Literal["approved"] = "approved"
    reviewer: NonBlank = Field(max_length=120)
    approved_at: datetime
    plan_sha256: Digest
    reviewed_definition_sha256: Digest
    candidate_id: CandidateId
    candidate_file_sha256: Digest
    candidate_finding_sha256: Digest
    parsed_text_sha256: Digest
    support: GroundedPassage
    study_period: StudyPeriod
    study_period_passage_sha256: Digest | None
    evidence_type: EvidenceType
    extracted_evidence_type: EvidenceType
    reviewed_limitations: list[NonBlank] = Field(min_length=1, max_length=4)
    extraction_provider: Literal["gemini"]
    extraction_model: NonBlank

    @model_validator(mode="after")
    def validate_timestamp(self):
        if self.approved_at.utcoffset() is None:
            raise ValueError("Approval timestamp must be timezone-aware")
        return self
