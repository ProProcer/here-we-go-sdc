"""Dated evidence and task interpretations for the Role 3 example."""

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from src.schemas.role import Contract, RoleId, SkillId, SourceId, TaskId


class EvidenceSource(Contract):
    source_id: SourceId
    title: str
    publisher: str
    source_url: HttpUrl
    published_at: date
    retrieved_at: date
    synthetic: Literal[False]
    usage_note: str
    coverage: str
    limitations: str

    @model_validator(mode="after")
    def validate_dates(self):
        if self.retrieved_at < self.published_at:
            raise ValueError("Retrieval cannot precede publication")
        return self


class TrendSignal(Contract):
    signal_id: str = Field(pattern=r"^signal:[a-z0-9_]+$")
    source_id: SourceId
    claim: str = Field(min_length=1)
    synthetic: Literal[False]


def evidence_fingerprint(source: EvidenceSource, signal: TrendSignal) -> str:
    """Bind an interpretation to reviewed content, independently of fetch date."""
    payload = {
        "source": source.model_dump(mode="json", exclude={"retrieved_at"}),
        "signal": signal.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


class SkillImplication(Contract):
    skill_id: SkillId
    direction: Literal[
        "increase", "decrease", "mixed", "unchanged", "insufficient_evidence"
    ]
    less_emphasis: list[str]
    more_emphasis: list[str]
    rationale: str = Field(min_length=1)
    employer_demand_direction: Literal["insufficient_evidence"]

    @model_validator(mode="after")
    def validate_direction(self):
        if self.direction in {"increase", "mixed"} and not self.more_emphasis:
            raise ValueError("An increase needs an explained skill aspect")
        if self.direction in {"decrease", "mixed"} and not self.less_emphasis:
            raise ValueError("A decrease needs an explained skill aspect")
        return self


class EvidenceChain(Contract):
    """Proposed reasoning, never a measured forecast or a numerical adjustment."""

    chain_id: str = Field(pattern=r"^chain:[a-z0-9_]+$")
    role_id: RoleId
    task_id: TaskId
    signal_id: str = Field(pattern=r"^signal:[a-z0-9_]+$")
    reviewed_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_type: Literal["observed_usage_with_model_assessed_outcomes"]
    evidence_locator: str = Field(min_length=1)
    study_period_start: date
    study_period_end: date
    mapping_basis: Literal["team_interpretation"]
    evidence_scope: Literal["contextual_not_task_measurement"]
    interpretation_status: Literal["proposed_for_review"]
    temporal_scope: Literal["conditional_future_workflow_not_dated_forecast"]
    assumptions: list[str] = Field(min_length=1)
    task_change: str = Field(min_length=1)
    human_responsibilities: list[str] = Field(min_length=1)
    skill_implications: list[SkillImplication] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    changes_skill_weights: Literal[False]

    @model_validator(mode="after")
    def validate_period_and_skills(self):
        if self.study_period_end < self.study_period_start:
            raise ValueError("Study period ends before it starts")
        ids = [row.skill_id for row in self.skill_implications]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate skill implication")
        return self


class TaskInterpretation(Contract):
    role_id: RoleId
    task_id: TaskId
    signal_ids: list[str] = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    mapping_basis: Literal["team_interpretation"]
    evidence_scope: Literal["contextual_not_task_measurement"]


class EvidenceLedger(Contract):
    schema_version: Literal["0.1.0", "0.2.0"]
    sources: list[EvidenceSource]
    signals: list[TrendSignal]
    task_interpretations: list[TaskInterpretation]
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        source_ids = [row.source_id for row in self.sources]
        signal_ids = [row.signal_id for row in self.signals]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source IDs")
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("Duplicate signal IDs")
        if any(row.source_id not in source_ids for row in self.signals):
            raise ValueError("Signal needs an existing cited source")
        pairs = [(row.role_id, row.task_id) for row in self.task_interpretations]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate role/task interpretation")
        for row in self.task_interpretations:
            if not set(row.signal_ids) <= set(signal_ids):
                raise ValueError("Task interpretation needs existing signals")
        if self.evidence_chains and self.schema_version != "0.2.0":
            raise ValueError("Evidence chains require ledger schema 0.2.0")
        chain_ids = [row.chain_id for row in self.evidence_chains]
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError("Duplicate evidence chain IDs")
        sources = {row.source_id: row for row in self.sources}
        signals = {row.signal_id: row for row in self.signals}
        mappings = {
            (row.role_id, row.task_id): row for row in self.task_interpretations
        }
        for chain in self.evidence_chains:
            signal = signals.get(chain.signal_id)
            mapping = mappings.get((chain.role_id, chain.task_id))
            if (
                signal is None
                or mapping is None
                or chain.signal_id not in mapping.signal_ids
            ):
                raise ValueError("Evidence chain needs a cited role/task mapping")
            source = sources[signal.source_id]
            if chain.study_period_end > source.published_at:
                raise ValueError("Study period cannot end after source publication")
            if evidence_fingerprint(source, signal) != chain.reviewed_evidence_sha256:
                raise ValueError("Evidence changed; review the affected evidence chain")
        return self
