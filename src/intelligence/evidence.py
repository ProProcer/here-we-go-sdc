"""Load the small, manually reviewed evidence ledger offline."""

from pathlib import Path

from src.ingestion.catalog import load_role_catalog
from src.ingestion.selection import Catalog, real_catalog
from src.schemas.onet import OnetCatalog
from src.schemas.trends import EvidenceLedger

DEFAULT_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "data/processed/trend_signals.json"
)
ONET_EVIDENCE = DEFAULT_EVIDENCE.parent / "onet/31.0/trend_signals.json"


def validate_catalog_references(
    ledger: EvidenceLedger, catalog: Catalog | None = None
) -> EvidenceLedger:
    if catalog is None:
        role_ids = {r.role_id for r in ledger.task_interpretations} | {
            r.role_id for r in ledger.evidence_chains
        }
        if any(r.startswith("role:onet_") for r in role_ids):
            if not all(r.startswith("role:onet_") for r in role_ids):
                raise ValueError(
                    "Evidence must not mix mock and O*NET catalog mappings"
                )
            catalog = real_catalog()
        else:
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


def load_evidence(
    path: str | Path | None = None, *, catalog: Catalog | None = None
) -> EvidenceLedger:
    if path is None:
        path = ONET_EVIDENCE if isinstance(catalog, OnetCatalog) else DEFAULT_EVIDENCE
    ledger = EvidenceLedger.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return validate_catalog_references(ledger, catalog)
