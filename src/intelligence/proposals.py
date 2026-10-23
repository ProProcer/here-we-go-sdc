"""Generate review-only task/skill proposals from an admitted, approved finding."""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from src.ingestion.selection import Catalog, catalog_for_role
from src.intelligence.evidence import load_evidence
from src.intelligence.extractors import ExtractionError
from src.intelligence.feeds import ReviewedSource
from src.intelligence.proposers import (
    PROMPT_VERSION,
    ModelTaskSkillProposer,
    TaskSkillProposer,
)
from src.intelligence.storage import atomic_json
from src.schemas.approval import FindingApproval
from src.schemas.onet import OnetCatalog
from src.schemas.proposals import (
    TaskSkillProposal,
    TaskSkillProposalRecord,
    UnmappedRoleSkill,
)
from src.schemas.trends import EvidenceSource, evidence_fingerprint

DEFAULT_PROPOSALS = (
    Path(__file__).resolve().parents[2] / "data/review/task_skill_proposals"
)
MAX_REVIEW_BYTES = 256 * 1024
MAX_PROPOSAL_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 64 * 1024


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Proposal/review file exceeds its size limit")
    return body


@dataclass(frozen=True)
class ProposalContext:
    review_path: Path
    review_sha256: str
    review: ReviewedSource
    approval: FindingApproval
    source: EvidenceSource
    catalog: Catalog
    catalog_sha256: str
    packet: dict
    unmapped_skills: tuple[UnmappedRoleSkill, ...]


def load_proposal_context(
    review_path: Path,
    role_id: str,
    *,
    evidence_path: Path | None = None,
    catalog: Catalog | None = None,
) -> ProposalContext:
    """Accept approved AND admitted findings; a saved definition alone is insufficient."""
    review_path = Path(review_path).resolve()
    body = _read(review_path, MAX_REVIEW_BYTES)
    catalog = catalog_for_role(role_id, catalog)
    review = ReviewedSource.model_validate_json(body)
    if review.approval is None:
        raise ValueError(
            "Select a finding admitted through the explicit approval command"
        )
    ledger = load_evidence(evidence_path, catalog=catalog)
    signal = next(
        (row for row in ledger.signals if row.signal_id == review.signal.signal_id),
        None,
    )
    source = next(
        (row for row in ledger.sources if row.source_id == review.source.source_id),
        None,
    )
    if signal != review.signal or source is None:
        raise ValueError(
            "Reviewed finding is not present unchanged in the accepted evidence ledger"
        )
    if evidence_fingerprint(source, signal) != evidence_fingerprint(
        review.source, review.signal
    ):
        raise ValueError(
            "Accepted source metadata changed; review it before generating implications"
        )
    role = next((row for row in catalog.roles if row.role_id == role_id), None)
    if role is None:
        raise ValueError("Unknown catalog role")
    if len(role.task_ids) != len(set(role.task_ids)):
        raise ValueError("Role catalog contains duplicate task references")
    tasks = {row.task_id: row for row in catalog.taxonomy.tasks}
    skills = {row.skill_id: row for row in catalog.taxonomy.skills}
    requirements = {
        row.skill_id for row in catalog.role_skills if row.role_id == role_id
    }
    linked = set()
    task_packet = []
    selected_task_ids = role.task_ids
    if isinstance(catalog, OnetCatalog):
        reviewed_tasks = {
            r.task_id for r in review.task_interpretations if r.role_id == role_id
        }
        if not reviewed_tasks:
            raise ValueError(
                "No reviewed task mapping exists for this O*NET role; approve a contextual task mapping before generating a proposal"
            )
        selected_task_ids = sorted(reviewed_tasks)
    for task_id in selected_task_ids:
        task = tasks[task_id]
        allowed = [skill_id for skill_id in task.skill_ids if skill_id in requirements]
        linked.update(allowed)
        task_packet.append(
            {
                "task_id": task_id,
                "label": task.label,
                "allowed_skills": [
                    {"skill_id": skill_id, "label": skills[skill_id].label}
                    for skill_id in allowed
                ],
            }
        )
    if len(task_packet) > 12 or any(
        len(row["allowed_skills"]) > 12 for row in task_packet
    ):
        raise ValueError("Selected role exceeds the bounded proposal task/skill scope")
    unmapped = tuple(
        UnmappedRoleSkill(skill_id=skill_id, label=skills[skill_id].label)
        for skill_id in sorted(requirements - linked)
    )
    packet = {
        "accepted_finding": {
            "signal_id": signal.signal_id,
            "claim": signal.claim,
            "evidence_type": review.approval.evidence_type,
            "study_period": review.approval.study_period.model_dump(mode="json"),
            "reviewed_limitations": review.approval.reviewed_limitations,
            "reviewed_task_links": [
                {"task_id": row.task_id, "interpretation": row.interpretation}
                for row in review.task_interpretations
                if row.role_id == role_id
            ],
        },
        "source": source.model_dump(
            mode="json", exclude={"retrieved_at", "usage_note"}
        ),
        "role": {
            "role_id": role.role_id,
            "title": role.role_title,
            "catalog_synthetic": catalog.synthetic,
            "tasks": task_packet,
        },
    }
    if len(json.dumps(packet, ensure_ascii=False).encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError(
            "Proposal input exceeds its size limit; no input was truncated"
        )
    return ProposalContext(
        review_path,
        hashlib.sha256(body).hexdigest(),
        review,
        review.approval,
        source,
        catalog,
        _digest(catalog.model_dump(mode="json")),
        packet,
        unmapped,
    )


def validate_proposed_scope(
    proposal: TaskSkillProposal, context: ProposalContext
) -> None:
    """Check exact task/skill coverage, not semantic correctness of model reasoning."""
    role = context.packet["role"]
    if (
        proposal.role_id != role["role_id"]
        or proposal.signal_id != context.review.signal.signal_id
    ):
        raise ValueError("Proposal refers to a different role or accepted finding")
    expected = {
        row["task_id"]: {skill["skill_id"] for skill in row["allowed_skills"]}
        for row in role["tasks"]
    }
    task_ids = [row.task_id for row in proposal.tasks]
    if len(task_ids) != len(set(task_ids)) or set(task_ids) != set(expected):
        raise ValueError("Proposal must cover every selected role task exactly once")
    for task in proposal.tasks:
        skill_ids = [row.skill_id for row in task.skill_implications]
        if (
            len(skill_ids) != len(set(skill_ids))
            or set(skill_ids) != expected[task.task_id]
        ):
            raise ValueError(
                "Proposal must cover only the allowed task/role skills, exactly once"
            )


def generate_task_skill_proposal(
    review_path: Path,
    role_id: str,
    proposer: TaskSkillProposer,
    *,
    evidence_path: Path | None = None,
    catalog: Catalog | None = None,
    output_directory: Path = DEFAULT_PROPOSALS,
    now: datetime | None = None,
) -> tuple[TaskSkillProposalRecord, Path]:
    context = load_proposal_context(
        review_path, role_id, evidence_path=evidence_path, catalog=catalog
    )
    generated_at = now or datetime.now(UTC)
    if generated_at.utcoffset() is None:
        raise ValueError("Generation time must be timezone-aware")
    generated_at = generated_at.astimezone(UTC)
    if generated_at < context.approval.approved_at:
        raise ValueError("Generation cannot precede finding approval")
    input_digest = _digest(context.packet)
    # Give providers an independent packet so they cannot mutate validation scope.
    result = proposer.propose(json.loads(json.dumps(context.packet)))
    validate_proposed_scope(result.proposal, context)
    current = load_proposal_context(
        review_path, role_id, evidence_path=evidence_path, catalog=catalog
    )
    if (
        current.review_sha256 != context.review_sha256
        or current.catalog_sha256 != context.catalog_sha256
        or _digest(current.packet) != input_digest
    ):
        raise ValueError(
            "Accepted inputs changed during generation; regenerate the proposal"
        )
    status = (
        "insufficient_evidence"
        if all(
            row.assessment == "insufficient_evidence" for row in result.proposal.tasks
        )
        else "proposed_interpretations"
    )
    record = TaskSkillProposalRecord(
        **result.proposal.model_dump(),
        generated_at=generated_at,
        reviewed_source_path=str(context.review_path),
        reviewed_source_sha256=context.review_sha256,
        accepted_finding_sha256=evidence_fingerprint(
            context.source, context.review.signal
        ),
        catalog_sha256=context.catalog_sha256,
        input_sha256=input_digest,
        source=context.source,
        finding=context.review.signal,
        finding_approval=context.approval,
        catalog_synthetic=context.catalog.synthetic,
        unmapped_role_skills=list(context.unmapped_skills),
        requested_model=proposer.model,
        returned_model=result.returned_model,
        provider=result.provider,
        prompt_version=PROMPT_VERSION,
        status=status,
        limitations=[
            "These are AI-generated interpretations awaiting review, not findings measured by the source.",
            "This stage uses the accepted finding and catalog; it does not reread the full source report.",
            "Skill directions concern conditional learning emphasis, not employer demand, job survival or personal fit.",
            "Numerical priorities remain authored scenario assumptions and are not modified by these proposals.",
        ],
    )
    name = f"{role_id.split(':')[1]}_{context.review.signal.signal_id.split(':')[1]}_{uuid4().hex[:12]}.json"
    path = Path(output_directory) / name
    atomic_json(path, record.model_dump(mode="json"))
    return record, path


def load_current_proposal(
    path: Path,
    *,
    evidence_path: Path | None = None,
    catalog: Catalog | None = None,
) -> TaskSkillProposalRecord:
    """Fail visibly when the approved input or catalog no longer matches a proposal."""
    record = TaskSkillProposalRecord.model_validate_json(
        _read(Path(path), MAX_PROPOSAL_BYTES)
    )
    context = load_proposal_context(
        Path(record.reviewed_source_path),
        record.role_id,
        evidence_path=evidence_path,
        catalog=catalog,
    )
    checks = (
        record.reviewed_source_sha256 == context.review_sha256,
        record.accepted_finding_sha256
        == evidence_fingerprint(context.source, context.review.signal),
        record.catalog_sha256 == context.catalog_sha256,
        record.input_sha256 == _digest(context.packet),
        record.finding == context.review.signal,
        record.finding_approval == context.approval,
        record.catalog_synthetic == context.catalog.synthetic,
        record.unmapped_role_skills == list(context.unmapped_skills),
        record.prompt_version == PROMPT_VERSION,
        record.source.model_dump(exclude={"retrieved_at"})
        == context.source.model_dump(exclude={"retrieved_at"}),
    )
    if not all(checks):
        raise ValueError("Proposal inputs changed; regenerate and review the proposal")
    validate_proposed_scope(record, context)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "inspect"):
        command = commands.add_parser(name)
        command.add_argument("--review", type=Path, required=True)
        command.add_argument("--role", default="role:data_analyst")
        command.add_argument("--ledger", type=Path)
        if name == "generate":
            command.add_argument("--model")
            command.add_argument("--output-dir", type=Path, default=DEFAULT_PROPOSALS)
    checking = commands.add_parser("check")
    checking.add_argument("--proposal", type=Path, required=True)
    checking.add_argument("--ledger", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            context = load_proposal_context(
                args.review, args.role, evidence_path=args.ledger
            )
            result = {
                "input": context.packet,
                "unmapped_role_skills": [
                    row.model_dump() for row in context.unmapped_skills
                ],
                "model_called": False,
                "accepted_evidence_changed": False,
            }
        elif args.command == "check":
            record = load_current_proposal(args.proposal, evidence_path=args.ledger)
            result = {
                "status": "current",
                "review_status": record.review_status,
                "assessment": record.status,
                "changes_skill_weights": False,
            }
        else:
            record, path = generate_task_skill_proposal(
                args.review,
                args.role,
                ModelTaskSkillProposer.from_environment(args.model),
                evidence_path=args.ledger,
                output_directory=args.output_dir,
            )
            result = {
                "status": "pending_review",
                "assessment": record.status,
                "proposal_path": str(path),
                "task_count": len(record.tasks),
                "model": record.returned_model,
                "accepted_evidence_changed": False,
                "changes_skill_weights": False,
            }
        print(json.dumps(result, indent=2))
        return 0
    except ExtractionError as error:
        message = str(error)
    except ValidationError:
        message = "Finding or proposal data failed schema validation; no proposal was published."
    except OSError:
        message = (
            "Finding/proposal I/O failed; inspect paths and storage before retrying."
        )
    except ValueError as error:
        message = str(error)
    print(json.dumps({"status": "failed", "message": message}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
