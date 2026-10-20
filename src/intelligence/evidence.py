"""Load the small, manually reviewed evidence ledger offline."""

from pathlib import Path

from src.ingestion.catalog import load_role_catalog
from src.schemas.trends import EvidenceLedger

DEFAULT_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "data/processed/trend_signals.json"
)


def validate_catalog_references(ledger: EvidenceLedger) -> EvidenceLedger:
    catalog = load_role_catalog()
    roles = {row.role_id: set(row.task_ids) for row in catalog.roles}
    for row in ledger.task_interpretations:
        if row.task_id not in roles.get(row.role_id, set()):
            raise ValueError("Evidence mapping references an unknown role/task pair")
    requirements = {(row.role_id, row.skill_id) for row in catalog.role_skills}
    tasks = {row.task_id: set(row.skill_ids) for row in catalog.taxonomy.tasks}
    for chain in ledger.evidence_chains:
        for implication in chain.skill_implications:
            if (chain.role_id, implication.skill_id) not in requirements:
                raise ValueError("Evidence chain skill must be a role requirement")
            if implication.skill_id not in tasks[chain.task_id]:
                raise ValueError("Evidence chain skill must belong to the mapped task")
    return ledger


def load_evidence(path: str | Path = DEFAULT_EVIDENCE) -> EvidenceLedger:
    ledger = EvidenceLedger.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return validate_catalog_references(ledger)
