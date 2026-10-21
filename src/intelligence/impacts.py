"""Resolve source -> finding -> task -> skill chains offline.

Run ``python -m src.intelligence.impacts`` for the Data Analyst example.
Numerical priorities, the shared catalog, and personal fit are never modified.
"""

import argparse
import hashlib
import json
from pathlib import Path

from src.ingestion.selection import Catalog, catalog_for_role
from src.intelligence.evidence import load_evidence


def get_evidence_chain_response(
    role_id: str = "role:data_analyst",
    *,
    evidence_path: str | Path | None = None,
    catalog: Catalog | None = None,
) -> dict:
    catalog = catalog_for_role(role_id, catalog)
    roles = {row.role_id: row for row in catalog.roles}
    if role_id not in roles:
        raise KeyError(role_id)
    ledger = load_evidence(evidence_path, catalog=catalog)
    sources = {row.source_id: row for row in ledger.sources}
    signals = {row.signal_id: row for row in ledger.signals}
    tasks = {row.task_id: row for row in catalog.taxonomy.tasks}
    skills = {row.skill_id: row.label for row in catalog.taxonomy.skills}
    chains = []
    for chain in ledger.evidence_chains:
        if chain.role_id != role_id:
            continue
        signal = signals[chain.signal_id]
        chains.append(
            {
                "reasoning": chain.model_dump(mode="json"),
                "finding": signal.model_dump(mode="json"),
                "source": sources[signal.source_id].model_dump(mode="json"),
                "task_label": tasks[chain.task_id].label,
                "skill_labels": {
                    row.skill_id: skills[row.skill_id]
                    for row in chain.skill_implications
                },
            }
        )
    canonical = json.dumps(
        ledger.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "0.1.0" if catalog.synthetic else "0.2.0",
        "role_id": role_id,
        "role_title": roles[role_id].role_title,
        "catalog_synthetic": catalog.synthetic,
        "status": "proposed_interpretations" if chains else "insufficient_evidence",
        "changes_skill_weights": False,
        "ledger_sha256": hashlib.sha256(canonical).hexdigest(),
        "chains": chains,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", default="role:data_analyst")
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            get_evidence_chain_response(args.role, evidence_path=args.ledger), indent=2
        )
    )


if __name__ == "__main__":
    main()
