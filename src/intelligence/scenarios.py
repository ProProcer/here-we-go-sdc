"""Apply additive adjustments from the spec to fresh baseline requirements."""

import json
from pathlib import Path

from src.ingestion.selection import Catalog
from src.schemas.onet import OnetCatalog
from src.schemas.scenario import Scenario, ScenarioResult, SkillPriority

DEFAULT_SCENARIOS = (
    Path(__file__).resolve().parents[2] / "data/synthetic/scenarios.json"
)
ONET_SCENARIOS = DEFAULT_SCENARIOS.parent / "onet_scenarios.json"


def load_scenarios(path: str | Path = DEFAULT_SCENARIOS) -> list[Scenario]:
    rows = [
        Scenario.model_validate(row)
        for row in json.loads(Path(path).read_text(encoding="utf-8"))
    ]
    if len({(row.role_id, row.scenario_id) for row in rows}) != len(rows):
        raise ValueError("Duplicate scenario IDs")
    return rows


def available_scenarios(catalog: Catalog, role_id: str, scenarios: list[Scenario]) -> list[str]:
    if isinstance(catalog, OnetCatalog) and any(r.role_id == role_id for r in catalog.role_skills):
        return ["baseline", "moderate_ai_change", "rapid_ai_change"]
    return ["baseline", *[s.scenario_id for s in scenarios if s.role_id == role_id]]


def _general_scenario(catalog, role, scenario_id, requirements):
    """Transparent application policy, never an inferred occupational AI effect."""
    if scenario_id not in {"moderate_ai_change", "rapid_ai_change"}:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    delta = 0.08 if scenario_id == "moderate_ai_change" else 0.16
    # Prioritize human checking, adaptation and communication under the assumption
    # that AI assistance becomes more common. No imported task-to-skill mapping.
    emphasis = {"Critical Thinking", "Active Learning", "Learning Strategies",
                "Monitoring", "Judgment and Decision Making", "Complex Problem Solving",
                "Reading Comprehension", "Writing", "Speaking", "Active Listening"}
    labels = {s.skill_id: s.label for s in catalog.taxonomy.skills}
    adjustments = {sid: delta for sid in requirements if labels.get(sid) in emphasis}
    return Scenario(
        scenario_id=scenario_id,
        name=f"Illustrative {'moderate' if delta == 0.08 else 'rapid'} AI adoption",
        synthetic=True, role_id=role.role_id, affected_task_ids=role.task_ids[:1],
        assumptions=[
            f"Assume {'moderate' if delta == 0.08 else 'rapid'} adoption of AI assistance in {role.role_title} workflows.",
            f"Application policy adds {delta:.2f} (capped at 1.0) to required checking, learning and communication skill priorities.",
            "All other occupational priorities stay unchanged. This is a generic stress test, not reviewed role-specific evidence.",
            "The listed task provides occupational context only; no measured task-to-skill or automation effect is asserted.",
        ], skill_priority_adjustments=adjustments,
        interpretation="Compare learning emphasis under assumed AI adoption. No prediction of job losses, local demand or personal proficiency; personal fit is unchanged.",
    )


def apply_scenario(
    catalog: Catalog, role_id: str, scenario_id: str, scenarios: list[Scenario]
) -> ScenarioResult:
    roles = {role.role_id: role for role in catalog.roles}
    if role_id not in roles:
        raise KeyError(f"Unknown role: {role_id}")
    role = roles[role_id]
    requirements = {
        row.skill_id: row.importance
        for row in catalog.role_skills
        if row.role_id == role_id
    }
    scenario = None
    if scenario_id != "baseline":
        scenario = next(
            (row for row in scenarios if row.scenario_id == scenario_id and row.role_id == role_id), None
        )
        if scenario is None and isinstance(catalog, OnetCatalog) and requirements:
            scenario = _general_scenario(catalog, role, scenario_id, requirements)
        if scenario is None:
            raise ValueError(f"Unknown scenario: {scenario_id}")
        if scenario.role_id != role_id:
            raise ValueError(f"Scenario {scenario_id} does not cover {role_id}")
        if not set(scenario.affected_task_ids) <= set(role.task_ids):
            raise ValueError("Scenario references tasks outside this role")
        if not set(scenario.skill_priority_adjustments) <= set(requirements):
            raise ValueError(
                "Scenario references skills outside this role's requirements"
            )
    adjustments = scenario.skill_priority_adjustments if scenario else {}
    priorities = []
    for skill_id, baseline in sorted(requirements.items()):
        adjusted = round(max(0, min(1, baseline + adjustments.get(skill_id, 0))), 6)
        priorities.append(
            SkillPriority(
                skill_id=skill_id,
                baseline_priority=baseline,
                adjusted_priority=adjusted,
                applied_adjustment=round(adjusted - baseline, 6),
            )
        )
    return ScenarioResult(
        scenario_id=scenario_id,
        name=scenario.name
        if scenario
        else (
            "Baseline (synthetic role requirements)"
            if catalog.synthetic
            else "Baseline (O*NET occupational ratings)"
        ),
        synthetic=scenario is not None,
        assumptions=scenario.assumptions if scenario else [],
        affected_task_ids=scenario.affected_task_ids if scenario else [],
        skill_priorities=priorities,
        interpretation=scenario.interpretation
        if scenario
        else (
            "Unadjusted catalog weights; the role catalog is synthetic. These are not measured demand or proficiency."
            if catalog.synthetic
            else "Unadjusted O*NET Importance/5 weights; not measured local demand, proficiency, or an employment forecast."
        ),
    )
