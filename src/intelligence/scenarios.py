"""Apply additive adjustments from the spec to fresh baseline requirements."""

import json
from pathlib import Path

from src.schemas.role import RoleCatalog
from src.schemas.scenario import Scenario, ScenarioResult, SkillPriority

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "data/synthetic/scenarios.json"


def load_scenarios(path: str | Path = DEFAULT_SCENARIOS) -> list[Scenario]:
    rows = [Scenario.model_validate(row) for row in json.loads(Path(path).read_text(encoding="utf-8"))]
    if len({row.scenario_id for row in rows}) != len(rows):
        raise ValueError("Duplicate scenario IDs")
    return rows


def apply_scenario(catalog: RoleCatalog, role_id: str, scenario_id: str,
                   scenarios: list[Scenario]) -> ScenarioResult:
    roles = {role.role_id: role for role in catalog.roles}
    if role_id not in roles:
        raise KeyError(f"Unknown role: {role_id}")
    role = roles[role_id]
    requirements = {row.skill_id: row.importance for row in catalog.role_skills if row.role_id == role_id}
    scenario = None
    if scenario_id != "baseline":
        scenario = next((row for row in scenarios if row.scenario_id == scenario_id), None)
        if scenario is None:
            raise ValueError(f"Unknown scenario: {scenario_id}")
        if scenario.role_id != role_id:
            raise ValueError(f"Scenario {scenario_id} does not cover {role_id}")
        if not set(scenario.affected_task_ids) <= set(role.task_ids):
            raise ValueError("Scenario references tasks outside this role")
        if not set(scenario.skill_priority_adjustments) <= set(requirements):
            raise ValueError("Scenario references skills outside this role's requirements")
    adjustments = scenario.skill_priority_adjustments if scenario else {}
    priorities = []
    for skill_id, baseline in sorted(requirements.items()):
        adjusted = round(max(0, min(1, baseline + adjustments.get(skill_id, 0))), 6)
        priorities.append(SkillPriority(
            skill_id=skill_id, baseline_priority=baseline,
            adjusted_priority=adjusted, applied_adjustment=round(adjusted - baseline, 6),
        ))
    return ScenarioResult(
        scenario_id=scenario_id,
        name=scenario.name if scenario else "Baseline (synthetic role requirements)",
        synthetic=scenario is not None,
        assumptions=scenario.assumptions if scenario else [],
        affected_task_ids=scenario.affected_task_ids if scenario else [],
        skill_priorities=priorities,
        interpretation=scenario.interpretation if scenario else (
            "Unadjusted catalog weights; the role catalog is synthetic. These are not measured demand or proficiency."
        ),
    )
