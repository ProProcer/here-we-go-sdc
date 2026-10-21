"""Offline Data Analyst example. Run python -m src.intelligence.outlook."""

import json
from pathlib import Path
from typing import Literal

from src.ingestion.selection import Catalog, catalog_for_role
from src.intelligence.evidence import load_evidence
from src.intelligence.scenarios import (
    DEFAULT_SCENARIOS,
    ONET_SCENARIOS,
    apply_scenario,
    load_scenarios,
)
from src.schemas.onet import OnetCatalog
from src.schemas.role import Contract, RoleId, TaskId
from src.schemas.scenario import ScenarioResult
from src.schemas.trends import EvidenceSource, TrendSignal


class TaskOutlook(Contract):
    task_id: TaskId
    label: str
    evidence_status: Literal["contextual_evidence", "insufficient_evidence"]
    interpretation: str
    mapping_basis: Literal["team_interpretation"] | None
    evidence_scope: Literal["contextual_not_task_measurement"] | None
    signal_ids: list[str]


class RoleOutlook(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    role_id: RoleId
    role_title: str
    catalog_synthetic: bool
    baseline_label: Literal[
        "Contextual AI evidence; employment impact unknown", "Insufficient evidence"
    ]
    tasks: list[TaskOutlook]
    signals: list[TrendSignal]
    sources: list[EvidenceSource]
    scenario: ScenarioResult
    limitations: list[str]


class OnetRoleOutlook(RoleOutlook):
    schema_version: Literal["0.2.0"] = "0.2.0"
    catalog_id: Literal["onet_31_0"] = "onet_31_0"
    available_scenarios: list[str]


def get_outlook(
    role_id: str,
    scenario_id: str = "baseline",
    *,
    evidence_path: str | Path | None = None,
    scenarios_path: str | Path | None = None,
    catalog: Catalog | None = None,
) -> RoleOutlook | OnetRoleOutlook:
    catalog = catalog_for_role(role_id, catalog)
    ledger = load_evidence(evidence_path, catalog=catalog)
    if scenarios_path is None:
        scenarios_path = (
            ONET_SCENARIOS if isinstance(catalog, OnetCatalog) else DEFAULT_SCENARIOS
        )
    scenarios = load_scenarios(scenarios_path)
    scenario = apply_scenario(catalog, role_id, scenario_id, scenarios)
    roles = {role.role_id: role for role in catalog.roles}
    tasks = {task.task_id: task for task in catalog.taxonomy.tasks}
    role = roles[role_id]
    mappings = {
        row.task_id: row
        for row in ledger.task_interpretations
        if row.role_id == role_id
    }
    task_outlooks = []
    for task_id in role.task_ids:
        mapping = mappings.get(task_id)
        task_outlooks.append(
            TaskOutlook(
                task_id=task_id,
                label=tasks[task_id].label,
                evidence_status="contextual_evidence"
                if mapping
                else "insufficient_evidence",
                interpretation=mapping.interpretation
                if mapping
                else "No reviewed evidence mapping is available.",
                mapping_basis=mapping.mapping_basis if mapping else None,
                evidence_scope=mapping.evidence_scope if mapping else None,
                signal_ids=mapping.signal_ids if mapping else [],
            )
        )
    used_signals = {
        signal_id for task in task_outlooks for signal_id in task.signal_ids
    }
    signals = [row for row in ledger.signals if row.signal_id in used_signals]
    used_sources = {row.source_id for row in signals}
    result_type = OnetRoleOutlook if isinstance(catalog, OnetCatalog) else RoleOutlook
    extra = (
        {
            "available_scenarios": [
                "baseline",
                *[s.scenario_id for s in scenarios if s.role_id == role_id],
            ]
        }
        if isinstance(catalog, OnetCatalog)
        else {}
    )
    return result_type(
        **extra,
        role_id=role_id,
        role_title=role.role_title,
        catalog_synthetic=catalog.synthetic,
        baseline_label="Contextual AI evidence; employment impact unknown"
        if signals
        else "Insufficient evidence",
        tasks=task_outlooks,
        signals=signals,
        sources=[row for row in ledger.sources if row.source_id in used_sources],
        scenario=scenario,
        limitations=[
            "Role requirements and task assignments come from Person 1's synthetic integration catalog."
            if catalog.synthetic
            else "Role/task records come from O*NET 31.0. Unmapped tasks and unreviewed evidence are not AI-impact findings.",
            "Task mappings are team interpretations, not measured task automation rates.",
            "Scenario adjustments are illustrative learning priorities, not employment forecasts or changes to personal fit.",
            "Outlook reads validated cached evidence. Run python -m src.intelligence.feeds to refresh the reviewed source; source publication dates may still be historical.",
        ],
    )


def get_outlook_response(
    role_id: str, scenario_id: str = "baseline", *, catalog: Catalog | None = None
) -> dict:
    """JSON adapter for Person 5; no HTTP server is started here."""
    return get_outlook(role_id, scenario_id, catalog=catalog).model_dump(mode="json")


if __name__ == "__main__":
    print(
        json.dumps(
            {
                scenario_id: get_outlook_response("role:data_analyst", scenario_id)
                for scenario_id in ("baseline", "moderate_ai_change", "rapid_ai_change")
            },
            indent=2,
        )
    )
