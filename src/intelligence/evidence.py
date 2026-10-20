"""Load the small, manually reviewed evidence ledger offline."""

from pathlib import Path

from src.ingestion.catalog import load_role_catalog
from src.schemas.trends import EvidenceLedger

DEFAULT_EVIDENCE = Path(__file__).resolve().parents[2] / "data/processed/trend_signals.json"


def validate_catalog_references(ledger: EvidenceLedger) -> EvidenceLedger:
    roles = {row.role_id: set(row.task_ids) for row in load_role_catalog().roles}
    for row in ledger.task_interpretations:
        if row.task_id not in roles.get(row.role_id, set()):
            raise ValueError("Evidence mapping references an unknown role/task pair")
    return ledger


def load_evidence(path: str | Path = DEFAULT_EVIDENCE) -> EvidenceLedger:
    ledger = EvidenceLedger.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return validate_catalog_references(ledger)
