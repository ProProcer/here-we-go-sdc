"""Reviewed, bounded evidence adjustments to learning priorities; never personal fit.

Prepare an assessment, preview it, then explicitly approve its exact content.
Benchmarks alone cannot produce a numerical adjustment under policy v1.
"""

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from src.ingestion.selection import real_catalog
from src.intelligence.evidence import load_evidence
from src.intelligence.feeds import ROOT, ReviewedSource
from src.intelligence.storage import atomic_json
from src.schemas.approval import reviewed_definition_fingerprint
from src.schemas.extraction import Digest, EvidenceType, NonBlank
from src.schemas.role import Contract, RoleId, SkillId, TaskId
from src.schemas.trends import evidence_fingerprint

POLICY = ROOT / "data/sources/learning_priority_policy.json"
STORE = ROOT / "data/processed/onet/31.0/priority_assessments.json"
PLANS = ROOT / "data/review/priority_assessments"


class PriorityPolicy(Contract):
    version: Literal["reviewed-learning-priorities-v1"]
    maximum_adjustment: float = Field(gt=0, le=0.1, allow_inf_nan=False)
    minimum_independent_studies: int = Field(ge=2)
    minimum_publishers: int = Field(ge=2)
    half_life_days: int = Field(ge=1)
    maximum_age_days: int = Field(ge=1)
    conflict_ratio: float = Field(gt=0, le=0.5)
    evidence_factors: dict[EvidenceType, float]

    @model_validator(mode="after")
    def validate_factors(self):
        if any(not 0 <= v <= 1 for v in self.evidence_factors.values()):
            raise ValueError("Evidence factors must be finite in [0,1]")
        if any(
            self.evidence_factors.get(k, 0) != 0
            for k in ("benchmark", "author_projection", "other")
        ):
            raise ValueError(
                "Indirect evidence cannot independently set numerical priorities"
            )
        return self


class PriorityAssessment(Contract):
    assessment_id: Digest
    review_path: NonBlank
    reviewed_definition_sha256: Digest
    evidence_sha256: Digest
    policy_sha256: Digest
    role_id: RoleId
    task_id: TaskId
    skill_id: SkillId
    signal_id: NonBlank
    publisher: NonBlank
    published_at: date
    evidence_type: EvidenceType
    study_group: NonBlank
    direction: Literal["increase", "decrease"]
    quality: Literal["strong", "moderate"]
    relevance: Literal["direct", "indirect"]
    rationale: NonBlank


class ApprovedAssessment(Contract):
    assessment: PriorityAssessment
    reviewer: NonBlank
    approved_at: datetime

    @model_validator(mode="after")
    def validate_time(self):
        if self.approved_at.utcoffset() is None:
            raise ValueError("Approval must be timezone-aware")
        return self


class PriorityStore(Contract):
    schema_version: Literal["0.1.0"]
    assessments: list[ApprovedAssessment]

    @model_validator(mode="after")
    def unique(self):
        ids = [r.assessment.assessment_id for r in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate priority assessment")
        return self


def digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def load_policy(path=POLICY):
    return PriorityPolicy.model_validate_json(Path(path).read_bytes())


def load_store(path=STORE):
    return PriorityStore.model_validate_json(Path(path).read_bytes())


def _review_context(path, role_id, task_id, skill_id, *, catalog, ledger):
    review = ReviewedSource.model_validate_json(Path(path).read_bytes())
    if review.approval is None:
        raise ValueError("Numerical assessment requires an explicitly approved finding")
    if review.signal not in ledger.signals:
        raise ValueError("Finding must be admitted to the selected ledger")
    source = next(
        (s for s in ledger.sources if s.source_id == review.source.source_id), None
    )
    if source is None or evidence_fingerprint(
        source, review.signal
    ) != evidence_fingerprint(review.source, review.signal):
        raise ValueError("Accepted evidence changed since finding approval")
    if (role_id, skill_id) not in {
        (s.role_id, s.skill_id) for s in catalog.role_skills
    }:
        raise ValueError("Select an existing general role-skill requirement")
    if not any(
        m.role_id == role_id
        and m.task_id == task_id
        and review.signal.signal_id in m.signal_ids
        for m in ledger.task_interpretations
    ):
        raise ValueError("Assessment requires an admitted role/task interpretation")
    return review, source


def prepare_assessment(
    review_path,
    *,
    role_id,
    task_id,
    skill_id,
    direction,
    study_group,
    quality,
    relevance,
    rationale,
    catalog=None,
    evidence_path=None,
    policy_path=POLICY,
    output_directory=PLANS,
):
    catalog = catalog or real_catalog()
    ledger = load_evidence(evidence_path, catalog=catalog)
    path = Path(review_path).resolve()
    review, source = _review_context(
        path, role_id, task_id, skill_id, catalog=catalog, ledger=ledger
    )
    policy = load_policy(policy_path)
    try:
        reference = path.relative_to(ROOT).as_posix()
    except ValueError:
        reference = str(path)
    payload = {
        "review_path": reference,
        "role_id": role_id,
        "task_id": task_id,
        "skill_id": skill_id,
        "reviewed_definition_sha256": reviewed_definition_fingerprint(
            review.model_dump(mode="json", exclude={"approval"})
        ),
        "evidence_sha256": evidence_fingerprint(source, review.signal),
        "policy_sha256": digest(policy.model_dump(mode="json")),
        "signal_id": review.signal.signal_id,
        "publisher": source.publisher,
        "published_at": source.published_at.isoformat(),
        "evidence_type": review.approval.evidence_type,
        "study_group": study_group,
        "direction": direction,
        "quality": quality,
        "relevance": relevance,
        "rationale": rationale,
    }
    plan = PriorityAssessment(assessment_id="0" * 64, **payload)
    plan = plan.model_copy(
        update={
            "assessment_id": digest(
                plan.model_dump(mode="json", exclude={"assessment_id"})
            )
        }
    )
    destination = Path(output_directory) / (plan.assessment_id + ".json")
    atomic_json(destination, plan.model_dump(mode="json"))
    return plan, destination


def validate_assessment(row, *, catalog, ledger, policy):
    review, source = _review_context(
        ROOT / row.review_path,
        row.role_id,
        row.task_id,
        row.skill_id,
        catalog=catalog,
        ledger=ledger,
    )
    expected = row.model_dump(mode="json", exclude={"assessment_id"})
    if row.assessment_id != digest(expected):
        raise ValueError("Assessment content does not match its identity")
    if row.policy_sha256 != digest(policy.model_dump(mode="json")):
        raise ValueError("Policy changed; re-review this assessment")
    if row.reviewed_definition_sha256 != reviewed_definition_fingerprint(
        review.model_dump(mode="json", exclude={"approval"})
    ):
        raise ValueError("Reviewed definition changed")
    if (
        row.evidence_sha256 != evidence_fingerprint(source, review.signal)
        or row.publisher != source.publisher
        or row.published_at != source.published_at
        or row.evidence_type != review.approval.evidence_type
        or row.signal_id != review.signal.signal_id
    ):
        raise ValueError("Assessment provenance differs from approved evidence")


def approve_assessment(
    path,
    *,
    reviewer,
    expected_sha256,
    approve=False,
    store_path=STORE,
    catalog=None,
    evidence_path=None,
    policy_path=POLICY,
    now=None,
):
    if not approve or not reviewer.strip():
        raise ValueError("Explicit approval and actual reviewer label required")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("Prepared assessment changed; inspect it before approval")
    row = PriorityAssessment.model_validate_json(payload)
    catalog = catalog or real_catalog()
    validate_assessment(
        row,
        catalog=catalog,
        ledger=load_evidence(evidence_path, catalog=catalog),
        policy=load_policy(policy_path),
    )
    store = load_store(store_path)
    if any(r.assessment.assessment_id == row.assessment_id for r in store.assessments):
        raise ValueError("Assessment already approved")
    approved = ApprovedAssessment(
        assessment=row, reviewer=reviewer.strip(), approved_at=now or datetime.now(UTC)
    )
    store.assessments.append(approved)
    atomic_json(Path(store_path), store.model_dump(mode="json"))
    return approved


def aggregate_assessments(assessments, policy, as_of):
    """Pure policy calculation; inputs must already have passed provenance checks."""
    groups = {}
    for row in assessments:
        age = (as_of - row.published_at).days
        factor = policy.evidence_factors.get(row.evidence_type, 0)
        if (
            factor == 0
            or row.relevance != "direct"
            or not 0 <= age <= policy.maximum_age_days
        ):
            continue
        strength = (
            factor
            * (1 if row.quality == "strong" else 0.5)
            * 2 ** (-age / policy.half_life_days)
        )
        groups.setdefault(row.study_group.casefold().strip(), []).append(
            (row, strength)
        )
    independent = []
    for members in groups.values():
        if len({r.direction for r, _ in members}) > 1:
            continue
        independent.append(max(members, key=lambda p: (p[1], p[0].assessment_id)))
    # Cap one contribution per publisher even if multiple studies are reviewed.
    publishers = {}
    for row, strength in independent:
        key = row.publisher.casefold().strip()
        if key not in publishers or strength > publishers[key][1]:
            publishers[key] = (row, strength)
    contributors = list(publishers.values())
    positive = sum(w for r, w in contributors if r.direction == "increase")
    negative = sum(w for r, w in contributors if r.direction == "decrease")
    status = "applied"
    delta = 0.0
    if (
        len(independent) < policy.minimum_independent_studies
        or len(contributors) < policy.minimum_publishers
    ):
        status = "insufficient_independent_evidence"
    elif min(positive, negative) >= policy.conflict_ratio * max(positive, negative):
        status = "conflicting_evidence"
    else:
        total = positive + negative
        delta = round(
            policy.maximum_adjustment
            * (positive - negative)
            / total
            * min(1, total / 2),
            6,
        )
    return {
        "status": status,
        "adjustment": delta,
        "contributing_assessment_ids": sorted(r.assessment_id for r, _ in contributors),
        "excluded_assessment_ids": sorted(
            {r.assessment_id for r in assessments}
            - {r.assessment_id for r, _ in contributors}
        ),
        "independent_studies": len(independent),
        "publishers": len(contributors),
    }


def evaluate_priorities(
    role_id,
    *,
    catalog=None,
    ledger=None,
    store_path=STORE,
    policy_path=POLICY,
    as_of=None,
):
    catalog = catalog or real_catalog()
    ledger = ledger or load_evidence(catalog=catalog)
    policy = load_policy(policy_path)
    grouped = {}
    rejected = []
    for entry in load_store(store_path).assessments:
        row = entry.assessment
        if row.role_id != role_id:
            continue
        try:
            if entry.approved_at.date() > (as_of or datetime.now(UTC).date()):
                raise ValueError("Assessment approval is in the future")
            validate_assessment(row, catalog=catalog, ledger=ledger, policy=policy)
            grouped.setdefault(row.skill_id, []).append(row)
        except (OSError, ValueError) as error:
            rejected.append({"assessment_id": row.assessment_id, "reason": str(error)})
    return {
        "policy_version": policy.version,
        "maximum_adjustment": policy.maximum_adjustment,
        "basis": "reviewed_application_policy_not_empirically_calibrated",
        "decisions": [
            {
                "skill_id": skill,
                **aggregate_assessments(
                    rows, policy, as_of or datetime.now(UTC).date()
                ),
            }
            for skill, rows in sorted(grouped.items())
        ],
        "rejected_assessments": rejected,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for flag in ("review", "role", "task", "skill", "study-group", "rationale"):
        prepare.add_argument("--" + flag, required=True)
    prepare.add_argument("--direction", choices=["increase", "decrease"], required=True)
    prepare.add_argument("--quality", choices=["strong", "moderate"], required=True)
    prepare.add_argument("--relevance", choices=["direct", "indirect"], required=True)
    approve = commands.add_parser("approve")
    for flag in ("plan", "reviewer", "expected-sha256"):
        approve.add_argument("--" + flag, required=True)
    approve.add_argument("--approve", action="store_true")
    preview = commands.add_parser("preview")
    preview.add_argument("--role", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        row, path = prepare_assessment(
            args.review,
            role_id=args.role,
            task_id=args.task,
            skill_id=args.skill,
            study_group=args.study_group,
            direction=args.direction,
            quality=args.quality,
            relevance=args.relevance,
            rationale=args.rationale,
        )
        print(
            json.dumps(
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "plan": row.model_dump(mode="json"),
                },
                indent=2,
            )
        )
    elif args.command == "approve":
        print(
            approve_assessment(
                args.plan,
                reviewer=args.reviewer,
                expected_sha256=args.expected_sha256,
                approve=args.approve,
            ).model_dump_json(indent=2)
        )
    else:
        print(json.dumps(evaluate_priorities(args.role), indent=2))


if __name__ == "__main__":
    main()
