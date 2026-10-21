"""Explicit real-catalog selection with per-worker caching."""

from functools import lru_cache

from src.ingestion.catalog import load_role_catalog
from src.ingestion.onet import load_onet_catalog
from src.schemas.onet import OnetCatalog
from src.schemas.role import RoleCatalog

Catalog = RoleCatalog | OnetCatalog


@lru_cache(maxsize=1)
def real_catalog() -> OnetCatalog:
    return load_onet_catalog()


def catalog_for_role(role_id: str, catalog: Catalog | None = None) -> Catalog:
    if catalog is not None:
        return catalog
    return real_catalog() if role_id.startswith("role:onet_") else load_role_catalog()
