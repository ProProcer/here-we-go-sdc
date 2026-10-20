"""Read and resolve exact URLs in the trusted local source registry."""

from pathlib import Path

from src.schemas.sources import ApprovedSource, SourceRegistry

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[2] / "data/sources/approved_sources.json"
)


def load_registry(path: Path = DEFAULT_REGISTRY) -> SourceRegistry:
    return SourceRegistry.model_validate_json(path.read_bytes())


def resolve_source(url: str, registry: SourceRegistry) -> ApprovedSource:
    for source in registry.sources:
        if str(source.source_url) == url:
            return source
    raise ValueError("URL is not in the approved source registry")
