"""Hypothetical priority adjustments; these are never evidence records."""

from typing import Literal

from pydantic import Field, model_validator

from src.schemas.role import Contract, RoleId, SkillId, TaskId


class Scenario(Contract):
    scenario_id: Literal["moderate_ai_change", "rapid_ai_change"]
    name: str
    synthetic: Literal[True]
    role_id: RoleId
    affected_task_ids: list[TaskId] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    skill_priority_adjustments: dict[SkillId, float]
    interpretation: str

    @model_validator(mode="after")
    def bounded_adjustments(self):
        if any(
            not -1 <= value <= 1 for value in self.skill_priority_adjustments.values()
        ):
            raise ValueError("Priority adjustments must be finite and within [-1, 1]")
        return self


class SkillPriority(Contract):
    skill_id: SkillId
    baseline_priority: float = Field(ge=0, le=1)
    adjusted_priority: float = Field(ge=0, le=1)
    applied_adjustment: float = Field(ge=-1, le=1)


class ScenarioResult(Contract):
    scenario_id: Literal["baseline", "moderate_ai_change", "rapid_ai_change"]
    name: str
    synthetic: bool
    assumptions: list[str]
    affected_task_ids: list[TaskId]
    skill_priorities: list[SkillPriority]
    interpretation: str
