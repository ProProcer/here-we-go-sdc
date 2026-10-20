"""Version 0.1 role catalog contract shared by Persons 1–5."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RoleId = Annotated[str, Field(pattern=r"^role:[a-z0-9_]+$")]
SkillId = Annotated[str, Field(pattern=r"^skill:[a-z0-9_]+$")]
TaskId = Annotated[str, Field(pattern=r"^task:[a-z0-9_]+$")]
SourceId = Annotated[str, Field(pattern=r"^source:[a-z0-9_]+$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Skill(Contract):
    skill_id: SkillId
    label: str
    aliases: list[str]


class Task(Contract):
    task_id: TaskId
    label: str
    skill_ids: list[SkillId] = Field(min_length=1)


class Sector(Contract):
    sector_id: str = Field(pattern=r"^sector:[a-z0-9_]+$")
    label: str


class Taxonomy(Contract):
    version: Literal["0.1.0"]
    skills: list[Skill] = Field(min_length=1)
    tasks: list[Task] = Field(min_length=1)
    sectors: list[Sector] = Field(min_length=1)


class Source(Contract):
    source_id: SourceId
    synthetic: bool
    title: str
    source_url: str | None
    license: str
    created_at: date
    limitations: str


class Role(Contract):
    role_id: RoleId
    role_title: str
    sector_id: str
    task_ids: list[TaskId] = Field(min_length=1)
    source_ids: list[SourceId] = Field(min_length=1)
    updated_at: date
    synthetic: bool


class RoleSkill(Contract):
    role_id: RoleId
    skill_id: SkillId
    importance: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_ids: list[SourceId] = Field(min_length=1)
    synthetic: bool


class RoleCatalog(Contract):
    schema_version: Literal["0.1.0"]
    synthetic: bool
    taxonomy: Taxonomy
    sources: list[Source] = Field(min_length=1)
    roles: list[Role] = Field(min_length=1)
    role_skills: list[RoleSkill] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        def unique_ids(records, field):
            values = [getattr(record, field) for record in records]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {field}")
            return set(values)

        roles = unique_ids(self.roles, "role_id")
        skills = unique_ids(self.taxonomy.skills, "skill_id")
        tasks = unique_ids(self.taxonomy.tasks, "task_id")
        sectors = unique_ids(self.taxonomy.sectors, "sector_id")
        sources = unique_ids(self.sources, "source_id")

        def require(values, known, label):
            if not set(values) <= known:
                raise ValueError(f"Unknown {label}: {set(values) - known}")

        for task in self.taxonomy.tasks:
            require(task.skill_ids, skills, "task skill IDs")
        for role in self.roles:
            require([role.sector_id], sectors, "sector IDs")
            require(role.task_ids, tasks, "task IDs")
            require(role.source_ids, sources, "source IDs")
        pairs = set()
        covered_roles = set()
        for requirement in self.role_skills:
            require([requirement.role_id], roles, "role IDs")
            require([requirement.skill_id], skills, "skill IDs")
            require(requirement.evidence_ids, sources, "evidence IDs")
            pair = (requirement.role_id, requirement.skill_id)
            if pair in pairs:
                raise ValueError(f"Duplicate role/skill pair: {pair}")
            pairs.add(pair)
            covered_roles.add(requirement.role_id)
        if covered_roles != roles:
            raise ValueError("Every role must have skill requirements")
        if self.synthetic and not all(
            record.synthetic
            for record in [*self.roles, *self.role_skills, *self.sources]
        ):
            raise ValueError("Synthetic catalog must label all records synthetic")
        return self
