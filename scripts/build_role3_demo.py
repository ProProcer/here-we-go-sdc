"""Regenerate offline Role 3 examples from a verified live-refresh snapshot.

Run after refreshing the complexity review:
python -m scripts.build_role3_demo --snapshot data/snapshots/trends/<snapshot>.json
"""

import argparse
import json
from pathlib import Path

from src.intelligence.evidence import load_evidence
from src.intelligence.feeds import ROOT, atomic_json
from src.intelligence.impacts import get_evidence_chain_response
from src.intelligence.outlook import get_outlook_response
from src.schemas.trends import EvidenceLedger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    snapshot_path = args.snapshot.resolve()
    relative_snapshot = snapshot_path.relative_to(ROOT).as_posix()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ledger = load_evidence()
    if EvidenceLedger.model_validate(snapshot["ledger"]) != ledger:
        raise ValueError("Snapshot must describe the current validated ledger")
    if not ledger.evidence_chains:
        raise ValueError("Refresh the chain review before building the example")
    response = get_evidence_chain_response()
    for chain in response["chains"]:
        if chain["source"]["source_url"] != snapshot["source_url"]:
            raise ValueError("Snapshot must verify the chain's source")
    atomic_json(
        ROOT / "data/demo/data_analyst_evidence_chain.json",
        {
            "description": "Live-source refresh adds a proposed, conditional task-to-skill interpretation.",
            "live_snapshot": relative_snapshot,
            "before": get_evidence_chain_response(
                evidence_path=ROOT
                / "data/demo/data_analyst_evidence_before_refresh.json"
            ),
            "after": response,
        },
    )
    atomic_json(
        ROOT / "data/demo/data_analyst_outlooks.json",
        {
            scenario: get_outlook_response("role:data_analyst", scenario)
            for scenario in ("baseline", "moderate_ai_change", "rapid_ai_change")
        },
    )
    print("Regenerated the evidence-chain example and three outlook responses.")


if __name__ == "__main__":
    main()
