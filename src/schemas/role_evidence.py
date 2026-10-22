"""Conditional role/task relevance, separate from measured employment effects."""

from pydantic import Field, model_validator

from src.schemas.role import Contract, TaskId
from src.schemas.skill_evidence import SkillNewsAssessment


class RoleNewsAssessment(SkillNewsAssessment):
    task_ids: list[TaskId] = Field(max_length=3)

    @model_validator(mode="after")
    def task_support(self):
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("Duplicate task reference")
        if self.relevance == "potentially_relevant" and not self.task_ids:
            raise ValueError("Role relevance requires specific supplied tasks")
        return self


class RoleAssessmentBatch(Contract):
    assessments: list[RoleNewsAssessment] = Field(min_length=1, max_length=8)
