"""Explained role and individual-skill links; application interpretations of UN targets."""

from typing import Literal

from pydantic import Field

from src.schemas.roadmap import SDGConnection
from src.schemas.role import Contract


class ExplainedSDGConnection(SDGConnection):
    goal_title: str
    target_label: str
    application_example: str
    condition: str


class SkillSDGMapping(Contract):
    skill_id: str
    label: str
    kind: str
    status: Literal["confirmed", "learning_goal", "role_requirement", "needs_review"]
    role_relevant: bool
    connections: list[ExplainedSDGConnection] = Field(min_length=1)


class SDGSummary(Contract):
    role_id: str
    role_title: str
    role_connections: list[ExplainedSDGConnection] = Field(min_length=1)
    skills: list[SkillSDGMapping]
    mapped_skill_count: int
    skill_count: int
    interpretation_note: str
