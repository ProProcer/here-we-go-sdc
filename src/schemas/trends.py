"""Dated evidence and task interpretations for the Role 3 example."""

from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from src.schemas.role import Contract, RoleId, SourceId, TaskId


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


class TaskInterpretation(Contract):
    role_id: RoleId
    task_id: TaskId
    signal_ids: list[str] = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    mapping_basis: Literal["team_interpretation"]
    evidence_scope: Literal["contextual_not_task_measurement"]


class EvidenceLedger(Contract):
    schema_version: Literal["0.1.0"]
    sources: list[EvidenceSource]
    signals: list[TrendSignal]
    task_interpretations: list[TaskInterpretation]

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
        return self
