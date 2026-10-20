"""Exercise live-source promotion in a temporary ledger, without application approval."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from src.intelligence.approval import approve_plan, prepare_approval
from src.intelligence.evidence import DEFAULT_EVIDENCE, load_evidence
from src.intelligence.storage import atomic_json
from src.schemas.extraction import ExtractionRecord


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--finding", type=int, default=1)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    record = ExtractionRecord.model_validate_json(args.candidate_file.read_bytes())
    if not 1 <= args.finding <= len(record.findings):
        raise ValueError("Finding number is outside this candidate file")
    original_digest = hashlib.sha256(DEFAULT_EVIDENCE.read_bytes()).hexdigest()
    with TemporaryDirectory(prefix="role3-approval-smoke-") as temporary:
        directory = Path(temporary)
        ledger = directory / "ledger.json"
        shutil.copyfile(DEFAULT_EVIDENCE, ledger)
        before = load_evidence(ledger)
        finding = record.findings[args.finding - 1]
        _, plan_path = prepare_approval(
            args.candidate_file,
            finding.candidate_id,
            output_directory=directory / "plans",
        )
        result = approve_plan(
            plan_path,
            reviewer="Integration smoke test; temporary ledger only",
            approve=True,
            ledger_path=ledger,
            snapshots_path=directory / "snapshots",
            definitions_directory=directory / "definitions",
        )
        if result.refresh.status not in {"updated", "unchanged"}:
            raise RuntimeError(
                "Isolated promotion did not complete; inspect refresh output"
            )
        after = load_evidence(ledger)
        snapshot = json.loads(Path(result.refresh.snapshot_path).read_bytes())
        production_digest = hashlib.sha256(DEFAULT_EVIDENCE.read_bytes()).hexdigest()
        if original_digest != production_digest:
            raise RuntimeError("Application ledger changed during the smoke test")
        receipt = {
            "record_type": "isolated_live_promotion_smoke_test",
            "tested_at": result.refresh.attempted_at.isoformat(),
            "source_url": result.refresh.source_url,
            "candidate_file_sha256": hashlib.sha256(
                args.candidate_file.read_bytes()
            ).hexdigest(),
            "candidate_id": finding.candidate_id,
            "source_response_sha256": result.refresh.response_sha256,
            "source_response_bytes": snapshot["response_bytes"],
            "parsed_text_sha256": record.parsed_text_sha256,
            "refresh_status": result.refresh.status,
            "temporary_ledger_signal_count_before": len(before.signals),
            "temporary_ledger_signal_count_after": len(after.signals),
            "application_ledger_sha256_before": original_digest,
            "application_ledger_sha256_after": production_digest,
            "accepted_application_evidence_changed": False,
            "human_review_performed": False,
            "finding_approved_for_application": False,
        }
    if args.receipt:
        atomic_json(args.receipt, receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
