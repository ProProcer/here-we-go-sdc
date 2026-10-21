"""Prepare a candidate review plan, then explicitly approve it for admission.

This command does not invoke an AI model or infer a role/task mapping.
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import get_args
from urllib.error import URLError
from uuid import uuid4

from pydantic import ValidationError

from src.ingestion.selection import catalog_for_role
from src.intelligence.evidence import DEFAULT_EVIDENCE, ONET_EVIDENCE, load_evidence
from src.intelligence.extraction import candidate_identity, ground_findings
from src.intelligence.feeds import (
    DEFAULT_SNAPSHOTS,
    ROOT,
    RefreshResult,
    ReviewedSource,
    fetch_html,
    merge_review,
    refresh_evidence,
    validate_page,
)
from src.intelligence.reports import ParsedReport, parse_report
from src.intelligence.sources import load_registry, resolve_source
from src.intelligence.storage import atomic_json
from src.schemas.approval import (
    ApprovalPlan,
    ApprovedTaskMapping,
    FindingApproval,
    reviewed_definition_fingerprint,
)
from src.schemas.extraction import (
    CandidateFinding,
    EvidenceType,
    ExtractionBatch,
    ExtractionRecord,
    GroundedFinding,
    PassageQuote,
)
from src.schemas.trends import (
    EvidenceLedger,
    EvidenceSource,
    TaskInterpretation,
    TrendSignal,
)

DEFAULT_PLANS = ROOT / "data/review/approvals"
DEFAULT_DEFINITIONS = ROOT / "data/sources/approved_candidates"
MAX_ARTIFACT_BYTES = 256 * 1024
EVIDENCE_LABELS = {
    "observed_usage": "Observed platform usage (not an employment outcome)",
    "benchmark": "Benchmark finding (not demonstrated workplace adoption)",
    "adoption_survey": "Adoption survey finding (sample-limited)",
    "labour_market_observation": "Labour-market observation (causality not established)",
    "author_projection": "Author projection (not an observed future outcome)",
    "other": "Reviewed report finding (scope-limited)",
}


@dataclass(frozen=True)
class ApprovalResult:
    reviewed_source_path: Path
    refresh: RefreshResult


def _read_artifact(path: Path) -> bytes:
    with path.open("rb") as stream:
        body = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ValueError("Review artifact exceeds the size limit")
    return body


def _utc(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.utcoffset() is None:
        raise ValueError("Review time must be timezone-aware")
    return value.astimezone(UTC)


def _candidate_input(finding: GroundedFinding) -> CandidateFinding:
    return CandidateFinding(
        claim=finding.claim,
        evidence_type=finding.evidence_type,
        support=PassageQuote(
            passage_id=finding.support.passage_id, quote=finding.support.quote
        ),
        study_period=finding.study_period,
        limitations=finding.limitations,
    )


def _select_finding(record: ExtractionRecord, candidate_id: str) -> GroundedFinding:
    matches = [row for row in record.findings if row.candidate_id == candidate_id]
    if len(matches) != 1:
        raise ValueError("Select exactly one existing candidate ID")
    finding = matches[0]
    expected = candidate_identity(
        record.source.source_id, record.parsed_text_sha256, _candidate_input(finding)
    )
    if expected != finding.candidate_id:
        raise ValueError("Candidate content does not match its extraction identity")
    return finding


def _validate_mapping(mapping: ApprovedTaskMapping | None) -> None:
    if mapping is None:
        return
    role = next(
        (
            row
            for row in catalog_for_role(mapping.role_id).roles
            if row.role_id == mapping.role_id
        ),
        None,
    )
    if role is None or mapping.task_id not in role.task_ids:
        raise ValueError("Task mapping must reference an existing role/task pair")


def _validate_source(record: ExtractionRecord) -> None:
    if resolve_source(str(record.source.source_url), load_registry()) != record.source:
        raise ValueError(
            "Candidate source metadata no longer matches the source registry"
        )


def prepare_approval(
    candidate_path: Path,
    candidate_id: str,
    *,
    reviewed_claim: str | None = None,
    reviewed_limitations: list[str] | None = None,
    reviewed_evidence_type: EvidenceType | None = None,
    task_mapping: ApprovedTaskMapping | None = None,
    output_directory: Path = DEFAULT_PLANS,
    now: datetime | None = None,
) -> tuple[ApprovalPlan, Path]:
    """Prepare a reviewable plan offline; no accepted evidence or candidate is edited."""
    candidate_path = Path(candidate_path).resolve()
    body = _read_artifact(candidate_path)
    record = ExtractionRecord.model_validate_json(body)
    finding = _select_finding(record, candidate_id)
    _validate_source(record)
    _validate_mapping(task_mapping)
    prepared_at = _utc(now)
    if record.fetched_at.utcoffset() is None or record.fetched_at > prepared_at:
        raise ValueError("Candidate fetch time must precede the review plan")
    plan = ApprovalPlan(
        prepared_at=prepared_at,
        candidate_path=str(candidate_path),
        candidate_file_sha256=hashlib.sha256(body).hexdigest(),
        candidate_id=finding.candidate_id,
        parsed_text_sha256=record.parsed_text_sha256,
        source=record.source,
        reviewed_evidence_type=reviewed_evidence_type
        if reviewed_evidence_type is not None
        else finding.evidence_type,
        reviewed_claim=reviewed_claim if reviewed_claim is not None else finding.claim,
        reviewed_limitations=reviewed_limitations
        if reviewed_limitations is not None
        else finding.limitations,
        task_mapping=task_mapping,
    )
    path = (
        Path(output_directory)
        / f"plan_{candidate_id.split(':')[1]}_{uuid4().hex[:12]}.json"
    )
    atomic_json(path, plan.model_dump(mode="json"))
    return plan, path


def _build_review(
    plan: ApprovalPlan,
    record: ExtractionRecord,
    finding: GroundedFinding,
    report: ParsedReport,
    ledger: EvidenceLedger,
    reviewer: str,
    now: datetime,
    plan_sha256: str,
) -> ReviewedSource:
    existing_source = next(
        (row for row in ledger.sources if row.source_id == plan.source.source_id), None
    )
    if existing_source is not None:
        for key in ("source_url", "published_at", "publisher"):
            if getattr(existing_source, key) != getattr(plan.source, key):
                raise ValueError(
                    "Existing evidence source conflicts with the approved source"
                )
        # Preserve source metadata already bound to earlier reasoning chains.
        source = existing_source.model_copy(update={"retrieved_at": now.date()})
    else:
        source = EvidenceSource(
            **plan.source.model_dump(),
            title=record.report_title,
            retrieved_at=now.date(),
            synthetic=False,
            usage_note="Approved original paraphrase and citation only; full article is not redistributed. Source reuse terms require owner review.",
            coverage="Scope is limited to the cited report; sample details and study dates are recorded in the finding approval.",
            limitations="No broader geographic representativeness or job-survival conclusion is established. See the finding's reviewed limitations.",
        )
    signal = TrendSignal(
        signal_id="signal:approved_" + finding.candidate_id.split(":")[1],
        source_id=source.source_id,
        synthetic=False,
        claim=f"{EVIDENCE_LABELS[plan.reviewed_evidence_type]}: {plan.reviewed_claim} Limitations: {' '.join(plan.reviewed_limitations)}",
    )
    previous = next(
        (row for row in ledger.signals if row.signal_id == signal.signal_id), None
    )
    if previous is not None and previous != signal:
        raise ValueError(
            "This candidate already has different approved wording; do not silently overwrite it"
        )
    mappings = []
    if plan.task_mapping is not None:
        mappings.append(
            TaskInterpretation(
                **plan.task_mapping.model_dump(),
                signal_ids=[signal.signal_id],
                mapping_basis="team_interpretation",
                evidence_scope="contextual_not_task_measurement",
            )
        )
    finding_json = json.dumps(finding.model_dump(mode="json"), sort_keys=True).encode(
        "utf-8"
    )
    definition = {
        "synthetic": False,
        "source": source.model_dump(mode="json"),
        "title_marker": report.title,
        "publication_marker": report.publication_marker,
        "required_markers": [finding.support.quote],
        "signal": signal.model_dump(mode="json"),
        "task_interpretations": [row.model_dump(mode="json") for row in mappings],
        "evidence_chains": [],
    }
    approval = FindingApproval(
        reviewer=reviewer,
        approved_at=now,
        plan_sha256=plan_sha256,
        reviewed_definition_sha256=reviewed_definition_fingerprint(definition),
        candidate_id=finding.candidate_id,
        candidate_file_sha256=plan.candidate_file_sha256,
        candidate_finding_sha256=hashlib.sha256(finding_json).hexdigest(),
        parsed_text_sha256=report.text_sha256,
        support=finding.support,
        study_period=finding.study_period,
        study_period_passage_sha256=finding.study_period_passage_sha256,
        evidence_type=plan.reviewed_evidence_type,
        extracted_evidence_type=finding.evidence_type,
        reviewed_limitations=plan.reviewed_limitations,
        extraction_provider=record.provider,
        extraction_model=record.returned_model,
    )
    return ReviewedSource(**definition, approval=approval)


def approve_plan(
    plan_path: Path,
    *,
    reviewer: str,
    approve: bool = False,
    expected_plan_sha256: str | None = None,
    ledger_path: Path | None = None,
    snapshots_path: Path | None = None,
    definitions_directory: Path = DEFAULT_DEFINITIONS,
    fetcher: Callable[[str], bytes] = fetch_html,
    now: datetime | None = None,
) -> ApprovalResult:
    """Recheck the source and route an explicitly approved plan through refresh."""
    if not approve:
        raise ValueError(
            "Explicit approval is required; pass --approve after reviewing the plan"
        )
    reviewer = reviewer.strip()
    if not reviewer or len(reviewer) > 120:
        raise ValueError("Provide a nonblank reviewer name of at most 120 characters")
    plan_bytes = _read_artifact(Path(plan_path))
    digest = hashlib.sha256(plan_bytes).hexdigest()
    if expected_plan_sha256 is not None and digest != expected_plan_sha256:
        raise ValueError("Plan file changed after review; inspect it before approving")
    plan = ApprovalPlan.model_validate_json(plan_bytes)
    candidate_bytes = _read_artifact(Path(plan.candidate_path))
    if hashlib.sha256(candidate_bytes).hexdigest() != plan.candidate_file_sha256:
        raise ValueError("Candidate file changed after preparation; prepare a new plan")
    record = ExtractionRecord.model_validate_json(candidate_bytes)
    finding = _select_finding(record, plan.candidate_id)
    if (
        plan.source != record.source
        or plan.parsed_text_sha256 != record.parsed_text_sha256
    ):
        raise ValueError("Plan and candidate source fingerprints disagree")
    _validate_source(record)
    _validate_mapping(plan.task_mapping)
    catalog = catalog_for_role(plan.task_mapping.role_id) if plan.task_mapping else None
    approved_at = _utc(now)
    if record.fetched_at.utcoffset() is None or record.fetched_at > plan.prepared_at:
        raise ValueError("Candidate fetch time must precede plan preparation")
    if approved_at < plan.prepared_at:
        raise ValueError("Approval cannot precede plan preparation")
    is_onet = catalog is not None and not catalog.synthetic
    ledger_path = Path(ledger_path or (ONET_EVIDENCE if is_onet else DEFAULT_EVIDENCE))
    snapshots_path = snapshots_path or (
        DEFAULT_SNAPSHOTS / "onet" if is_onet else DEFAULT_SNAPSHOTS
    )
    ledger = (
        load_evidence(ledger_path, catalog=catalog)
        if ledger_path.exists()
        else EvidenceLedger(
            schema_version="0.1.0",
            sources=[],
            signals=[],
            task_interpretations=[],
        )
    )
    body = fetcher(str(record.source.source_url))
    report = parse_report(body, record.source)
    if report.text_sha256 != record.parsed_text_sha256:
        raise ValueError(
            "Report text changed since extraction; re-extract and review again"
        )
    rebuilt = ground_findings(
        ExtractionBatch(findings=[_candidate_input(finding)], no_findings_reason=None),
        report,
        record.source,
    )
    if rebuilt != [finding]:
        raise ValueError("Saved candidate references do not match the current report")
    review = _build_review(
        plan, record, finding, report, ledger, reviewer, approved_at, digest
    )
    validate_page(body, review)
    merge_review(ledger, review, approved_at, catalog=catalog)
    review_path = (
        Path(definitions_directory) / f"approved_{digest[:24]}_{uuid4().hex[:12]}.json"
    )
    atomic_json(review_path, review.model_dump(mode="json"))
    # Reuse the verified bytes; refresh performs its own validation and writes
    # the approval provenance into the same snapshot as the proposed ledger.
    refresh = refresh_evidence(
        review_path=review_path,
        ledger_path=ledger_path,
        snapshots_path=snapshots_path,
        fetcher=lambda url: body,
        now=approved_at,
        catalog=catalog,
    )
    return ApprovalResult(review_path, refresh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="Show findings available for review")
    listing.add_argument("--candidate-file", type=Path, required=True)
    preparing = commands.add_parser(
        "prepare", help="Create an offline review plan without accepting evidence"
    )
    preparing.add_argument("--candidate-file", type=Path, required=True)
    selection = preparing.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--finding", type=int, help="One-based finding number from list"
    )
    selection.add_argument("--candidate-id")
    preparing.add_argument(
        "--claim", help="Corrected, reviewed wording; defaults to the candidate claim"
    )
    preparing.add_argument(
        "--limitation",
        action="append",
        help="Reviewed limitation; repeat to replace candidate limitations",
    )
    preparing.add_argument(
        "--evidence-type",
        choices=get_args(EvidenceType),
        help="Correct the generated evidence classification",
    )
    preparing.add_argument("--role")
    preparing.add_argument("--task")
    preparing.add_argument(
        "--interpretation", help="Your separately reviewed role/task interpretation"
    )
    preparing.add_argument("--output-dir", type=Path, default=DEFAULT_PLANS)
    accepting = commands.add_parser(
        "approve", help="Admit an explicitly reviewed plan through refresh"
    )
    accepting.add_argument("--plan", type=Path, required=True)
    accepting.add_argument("--reviewer", required=True)
    accepting.add_argument("--approve", action="store_true", required=True)
    accepting.add_argument("--expected-plan-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command in {"list", "prepare"}:
            record = ExtractionRecord.model_validate_json(
                _read_artifact(args.candidate_file)
            )
        if args.command == "list":
            result = {
                "source": record.source.model_dump(mode="json"),
                "findings": [
                    {
                        "finding": index,
                        "candidate_id": row.candidate_id,
                        "claim": row.claim,
                        "evidence_type": row.evidence_type,
                        "limitations": row.limitations,
                    }
                    for index, row in enumerate(record.findings, 1)
                ],
                "accepted_evidence_changed": False,
            }
        elif args.command == "prepare":
            candidate_id = args.candidate_id
            if args.finding is not None:
                if not 1 <= args.finding <= len(record.findings):
                    raise ValueError("Finding number is outside this candidate file")
                candidate_id = record.findings[args.finding - 1].candidate_id
            mapping_values = (args.role, args.task, args.interpretation)
            if any(value is not None for value in mapping_values) and not all(
                mapping_values
            ):
                raise ValueError(
                    "Supply --role, --task and --interpretation together, or omit all three"
                )
            mapping = (
                ApprovedTaskMapping(
                    role_id=args.role,
                    task_id=args.task,
                    interpretation=args.interpretation,
                )
                if all(mapping_values)
                else None
            )
            plan, path = prepare_approval(
                args.candidate_file,
                candidate_id,
                reviewed_claim=args.claim,
                reviewed_limitations=args.limitation,
                task_mapping=mapping,
                reviewed_evidence_type=args.evidence_type,
                output_directory=args.output_dir,
            )
            result = {
                "status": "prepared",
                "plan_path": str(path),
                "plan_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "plan": plan.model_dump(mode="json"),
                "accepted_evidence_changed": False,
            }
        else:
            admission = approve_plan(
                args.plan,
                reviewer=args.reviewer,
                approve=args.approve,
                expected_plan_sha256=args.expected_plan_sha256,
            )
            accepted = admission.refresh.status in {"updated", "unchanged"}
            result = {
                "status": "approved" if accepted else "not_admitted",
                "reviewed_source_path": str(admission.reviewed_source_path),
                "refresh": admission.refresh.model_dump(mode="json"),
                "accepted_evidence_changed": admission.refresh.status == "updated",
            }
            print(json.dumps(result, indent=2))
            return 0 if accepted else 1
        print(json.dumps(result, indent=2))
        return 0
    except ValidationError:
        message = "Candidate, plan or source failed validation; inspect the selected review data."
    except (OSError, URLError, HTTPException):
        message = "Review I/O or source fetch failed. Inspect the ledger/refresh status before retrying."
    except ValueError as error:
        message = str(error)
    print(json.dumps({"status": "failed", "message": message}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
