"""Load the synthetic Person 1 handoff without a server or external API."""

import json
from pathlib import Path

from src.schemas.role import RoleCatalog

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "data/synthetic/role_catalog"


def load_role_catalog(directory: str | Path = DEFAULT_DIRECTORY) -> RoleCatalog:
    """Validate split fixture files and return the shared typed catalog."""
    directory = Path(directory)
    payload = {"schema_version": "0.1.0", "synthetic": True}
    for name in ("taxonomy", "sources", "roles", "role_skills"):
        payload[name] = json.loads((directory / f"{name}.json").read_text())
    return RoleCatalog.model_validate(payload)


def get_roles() -> dict:
    """JSON-compatible response body for Person 5's GET /api/roles route."""
    return load_role_catalog().model_dump(mode="json")


if __name__ == "__main__":
    print(json.dumps(get_roles(), indent=2))
