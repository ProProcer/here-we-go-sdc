"""Build the offline real-catalog Role 3 handoff after a live evidence refresh.

python -m scripts.build_onet_role3_demo --snapshot data/snapshots/trends/onet/FILE.json
This command reads cached data only; it makes no network or paid model calls.
"""

import argparse
import hashlib
import json
from pathlib import Path

from src.ingestion.selection import real_catalog
from src.intelligence.evidence import load_evidence
from src.intelligence.feeds import ROOT, get_refresh_status
from src.intelligence.impacts import get_evidence_chain_response
from src.intelligence.outlook import get_outlook
from src.intelligence.storage import atomic_json
from src.schemas.trends import EvidenceLedger

ROLE_ID = "role:onet_15_2051_01"
REVIEW = ROOT / "data/sources/onet_bi_ds_star_2025.json"


def build_response(snapshot_path: Path) -> dict:
    snapshot_path = snapshot_path.resolve()
    relative_snapshot = snapshot_path.relative_to(ROOT).as_posix()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    catalog = real_catalog()
    ledger = load_evidence(catalog=catalog)
    if EvidenceLedger.model_validate(snapshot["ledger"]) != ledger:
        raise ValueError("Snapshot must describe the current real-catalog ledger")
    if snapshot["review_sha256"] != hashlib.sha256(REVIEW.read_bytes()).hexdigest():
        raise ValueError("Review changed since live verification; refresh it again")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    if snapshot["source_url"] != review["source"]["source_url"]:
        raise ValueError("Snapshot must verify the handoff's reviewed source")
    outlooks = {
        scenario: get_outlook(ROLE_ID, scenario, catalog=catalog).model_dump(
            mode="json"
        )
        for scenario in ("baseline", "moderate_ai_change", "rapid_ai_change")
    }
    refresh_status = get_refresh_status(
        ROOT / "data/snapshots/trends/onet/last_refresh.json"
    )
    return {
        "schema_version": "0.2.0",
        "role_id": ROLE_ID,
        "live_snapshot": relative_snapshot,
        "review_record": "data/review/research/onet_bi_evidence_review.json",
        "refresh_status": refresh_status.model_dump(mode="json")
        if refresh_status is not None
        else None,
        "outlooks": outlooks,
        "skill_implications": get_evidence_chain_response(ROLE_ID, catalog=catalog),
        "skill_implications_reason": "No reviewed task-to-skill links exist in this catalog.",
        "changes_personal_fit": False,
        "evidence_changes_skill_priorities": any(
            decision["adjustment"] != 0
            for decision in outlooks["baseline"]["learning_priority_evidence"][
                "decisions"
            ]
        ),
        "scenario_priorities_are_authored_assumptions": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    destination = ROOT / "data/demo/onet_role3_handoff.json"
    atomic_json(destination, build_response(args.snapshot))
    print(f"Wrote real-catalog Role 3 handoff: {destination}")


if __name__ == "__main__":
    main()
