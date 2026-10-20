"""Provider-independent boundary for candidate finding extraction."""

from dataclasses import dataclass
from typing import Protocol

from src.intelligence.reports import ParsedReport
from src.schemas.extraction import ExtractionBatch
from src.schemas.sources import ApprovedSource


class ExtractionError(RuntimeError):
    """A safe provider failure message without credentials or response bodies."""


@dataclass(frozen=True)
class ModelExtraction:
    batch: ExtractionBatch
    returned_model: str


class FindingExtractor(Protocol):
    @property
    def model(self) -> str: ...

    def extract(
        self, report: ParsedReport, source: ApprovedSource
    ) -> ModelExtraction: ...
