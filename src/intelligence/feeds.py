"""Bounded refresh of an explicitly reviewed source; no arbitrary web crawling.

Run ``python -m src.intelligence.feeds``. Failed validation leaves the last
validated ledger untouched and returns an explicit cached/unavailable result.
"""

import argparse
import hashlib
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import Field, model_validator

from src.ingestion.selection import Catalog, real_catalog
from src.intelligence.evidence import (
    DEFAULT_EVIDENCE,
    ONET_EVIDENCE,
    load_evidence,
    validate_catalog_references,
)
from src.intelligence.reports import date_is_present, parse_report
from src.intelligence.sources import load_registry
from src.intelligence.storage import atomic_json
from src.schemas.approval import FindingApproval, reviewed_definition_fingerprint
from src.schemas.onet import OnetCatalog
from src.schemas.role import Contract
from src.schemas.sources import ApprovedSource, SourceRegistry
from src.schemas.trends import (
    EvidenceChain,
    EvidenceLedger,
    EvidenceSource,
    TaskInterpretation,
    TrendSignal,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW = ROOT / "data/sources/anthropic_january_2026.json"
DEFAULT_SNAPSHOTS = ROOT / "data/snapshots/trends"
# Retained for existing consumers; fetching uses the reviewed registry below.
APPROVED_URL = (
    "https://www.anthropic.com/research/anthropic-economic-index-january-2026-report"
)
APPROVED_SOURCES = ROOT / "data/sources/approved_sources.json"
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15


def load_source_registry() -> SourceRegistry:
    """Local reviewed allowlist: adding a release does not require code changes."""
    return load_registry(APPROVED_SOURCES)


class ReviewedSource(Contract):
    """Reviewed claim and proposed mapping, admitted if webpage checks pass."""

    synthetic: Literal[False]
    source: EvidenceSource
    title_marker: str = Field(min_length=1)
    publication_marker: str = Field(min_length=1)
    required_markers: list[str] = Field(min_length=1)
    signal: TrendSignal
    task_interpretations: list[TaskInterpretation] = Field(default_factory=list)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
    approval: FindingApproval | None = None

    @model_validator(mode="after")
    def validate_review(self):
        approved = {row.source_id: row for row in load_source_registry().sources}
        entry = approved.get(self.source.source_id)
        if entry is None or any(
            getattr(entry, field) != getattr(self.source, field)
            for field in ("source_url", "publisher", "published_at")
        ):
            raise ValueError("Source must match an explicitly approved registry entry")
        if self.signal.source_id != self.source.source_id:
            raise ValueError("Reviewed signal/source IDs disagree")
        if not date_is_present(self.source.published_at, self.publication_marker):
            raise ValueError(
                "Publication marker must match the reviewed publication date"
            )
        if any(not marker.strip() for marker in self.required_markers):
            raise ValueError("Review markers must not be blank")
        for mapping in self.task_interpretations:
            if mapping.signal_ids != [self.signal.signal_id]:
                raise ValueError("Reviewed mappings must cite the reviewed signal")
        if self.approval is not None:
            fingerprint = reviewed_definition_fingerprint(
                self.model_dump(mode="json", exclude={"approval"})
            )
            if fingerprint != self.approval.reviewed_definition_sha256:
                raise ValueError(
                    "Approved wording or mapping changed; prepare a new approval plan"
                )
            expected_id = "signal:approved_" + self.approval.candidate_id.split(":")[1]
            if self.signal.signal_id != expected_id:
                raise ValueError(
                    "Approval provenance must identify the admitted candidate signal"
                )
            if self.approval.approved_at.date() > self.source.retrieved_at:
                raise ValueError(
                    "Source retrieval date cannot precede finding approval"
                )
        # Validate the full chain before any network access or cache mutation.
        validate_catalog_references(
            EvidenceLedger(
                schema_version="0.2.0",
                sources=[self.source],
                signals=[self.signal],
                task_interpretations=self.task_interpretations,
                evidence_chains=self.evidence_chains,
            )
        )
        return self


class RefreshResult(Contract):
    status: Literal["updated", "unchanged", "cached", "unavailable"]
    attempted_at: datetime
    cache_available: bool
    message: str
    source_url: str
    snapshot_path: str | None = None
    response_sha256: str | None = None


class VisibleText(HTMLParser):
    """Ignore executable/style content and retain visible text plus h1 titles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.in_title = False
        self.parts = []
        self.titles = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag == "h1":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "h1":
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.in_title:
                self.titles.append(data)


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect rejected; review a changed source URL explicitly")


def fetch_html(url: str) -> bytes:
    """Exact approved HTTPS URLs, no redirects, bounded size and read time."""
    if url not in {str(row.source_url) for row in load_source_registry().sources}:
        raise ValueError("Unapproved source URL")
    request = Request(
        url,
        headers={
            "User-Agent": "Ikiguy/0.1 (public research source verification)",
            "Accept": "text/html",
            "Accept-Encoding": "identity",
        },
    )
    started = time.monotonic()
    with build_opener(RejectRedirects()).open(
        request, timeout=TIMEOUT_SECONDS
    ) as response:
        if response.status != 200 or response.headers.get_content_type() != "text/html":
            raise ValueError("Source must return HTTP 200 text/html")
        chunks = []
        size = 0
        while True:
            if time.monotonic() - started > TIMEOUT_SECONDS:
                raise TimeoutError("Source exceeded refresh time budget")
            chunk = response.read(min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Source exceeds maximum response size")
        return b"".join(chunks)


def validate_page(body: bytes, review: ReviewedSource) -> None:
    if not body or len(body) > MAX_BYTES:
        raise ValueError("Empty or oversized source response")
    parser = VisibleText()
    parser.feed(body.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    title = " ".join(" ".join(parser.titles).split())
    if review.title_marker.casefold() not in title.casefold():
        raise ValueError("Reviewed report title missing from page heading")
    if any(
        marker.casefold() not in text.casefold()
        for marker in [review.publication_marker, *review.required_markers]
    ):
        raise ValueError(
            "Publication date or reviewed claim marker missing; manual review needed"
        )
    if review.approval is not None:
        source = ApprovedSource.model_validate(
            {
                key: getattr(review.source, key)
                for key in ("source_id", "source_url", "publisher", "published_at")
            }
        )
        report = parse_report(body, source)
        if report.text_sha256 != review.approval.parsed_text_sha256:
            raise ValueError(
                "Approved report text changed; re-extract and review before refresh"
            )


def merge_review(
    ledger: EvidenceLedger,
    review: ReviewedSource,
    retrieved_at: datetime,
    *,
    catalog: Catalog | None = None,
) -> EvidenceLedger:
    """Append the new dated claim; preserve the previous report and scenario data."""
    source = review.source.model_copy(update={"retrieved_at": retrieved_at.date()})
    # Revalidate copied fields, including the publication/retrieval relationship.
    source = EvidenceSource.model_validate(source.model_dump())
    sources = {row.source_id: row for row in ledger.sources}
    signals = {row.signal_id: row for row in ledger.signals}
    sources[source.source_id] = source
    signals[review.signal.signal_id] = review.signal
    mappings = {(row.role_id, row.task_id): row for row in ledger.task_interpretations}
    for row in review.task_interpretations:
        old = mappings.get((row.role_id, row.task_id))
        ids = list(dict.fromkeys([*(old.signal_ids if old else []), *row.signal_ids]))
        mappings[(row.role_id, row.task_id)] = row.model_copy(
            update={"signal_ids": ids}
        )
    # A review owns all chains for its signal. Explicitly removing a chain from
    # that review also withdraws it from future responses.
    chains = {
        row.chain_id: row
        for row in ledger.evidence_chains
        if row.signal_id != review.signal.signal_id
    }
    for row in review.evidence_chains:
        if row.chain_id in chains:
            raise ValueError("An evidence chain ID is already owned by another signal")
        chains[row.chain_id] = row
    candidate = EvidenceLedger(
        schema_version="0.2.0" if chains else ledger.schema_version,
        sources=list(sources.values()),
        signals=list(signals.values()),
        task_interpretations=list(mappings.values()),
        evidence_chains=list(chains.values()),
    )
    return validate_catalog_references(candidate, catalog)


def get_refresh_status(
    path: str | Path = DEFAULT_SNAPSHOTS / "last_refresh.json",
) -> RefreshResult | None:
    """Person 5 should show cached/unavailable messages beside the outlook."""
    path = Path(path)
    if not path.exists():
        return None
    return RefreshResult.model_validate_json(path.read_text(encoding="utf-8"))


def refresh_evidence(
    *,
    review_path: str | Path = DEFAULT_REVIEW,
    ledger_path: str | Path | None = None,
    snapshots_path: str | Path | None = None,
    fetcher=fetch_html,
    now: datetime | None = None,
    catalog: Catalog | None = None,
) -> RefreshResult:
    now = now or datetime.now(UTC)
    is_onet = isinstance(catalog, OnetCatalog)
    ledger_path = Path(ledger_path or (ONET_EVIDENCE if is_onet else DEFAULT_EVIDENCE))
    snapshots_path = Path(
        snapshots_path or (DEFAULT_SNAPSHOTS / "onet" if is_onet else DEFAULT_SNAPSHOTS)
    )
    url = APPROVED_URL
    cached = None
    try:
        if ledger_path.exists():
            cached = load_evidence(ledger_path, catalog=catalog)
        review_bytes = Path(review_path).read_bytes()
        review = ReviewedSource.model_validate_json(review_bytes)
        if (
            any(r.role_id.startswith("role:onet_") for r in review.task_interpretations)
            and not is_onet
        ):
            raise ValueError(
                "Refreshing O*NET mappings requires an explicitly selected real catalog"
            )
        url = str(review.source.source_url)
        body = fetcher(url)
        validate_page(body, review)
        base = cached or EvidenceLedger(
            schema_version="0.1.0", sources=[], signals=[], task_interpretations=[]
        )
        candidate = merge_review(base, review, now, catalog=catalog)
        digest = hashlib.sha256(body).hexdigest()
        snapshot = (
            snapshots_path / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}_{digest[:12]}.json"
        )
        # Store reviewed structured data and provenance, not copyrighted page text.
        snapshot_payload = {
            "fetched_at": now.isoformat(),
            "source_url": url,
            "response_sha256": digest,
            "response_bytes": len(body),
            "review_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "validation": "Reviewed heading, publication date and claim markers present",
            "ledger": candidate.model_dump(mode="json"),
        }
        if review.approval is not None:
            snapshot_payload["approval"] = review.approval.model_dump(mode="json")
        atomic_json(snapshot, snapshot_payload)
        changed = cached != candidate
        if changed:
            atomic_json(ledger_path, candidate.model_dump(mode="json"))
        try:
            snapshot_reference = snapshot.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            snapshot_reference = str(snapshot)
        result = RefreshResult(
            status="updated" if changed else "unchanged",
            attempted_at=now,
            cache_available=True,
            source_url=url,
            snapshot_path=snapshot_reference,
            response_sha256=digest,
            message="Reviewed source verified. Historical evidence is not a current labor-market forecast.",
        )
    except (OSError, URLError, HTTPException, ValueError) as error:
        result = RefreshResult(
            status="cached" if cached is not None else "unavailable",
            attempted_at=now,
            cache_available=cached is not None,
            source_url=url,
            message=f"Refresh failed; cached evidence was not changed: {error}",
        )
    atomic_json(snapshots_path / "last_refresh.json", result.model_dump(mode="json"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--catalog", choices=["mock", "onet"], default="mock")
    args = parser.parse_args()
    result = refresh_evidence(
        review_path=args.review,
        ledger_path=args.ledger,
        snapshots_path=args.snapshots,
        catalog=real_catalog() if args.catalog == "onet" else None,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.status in {"updated", "unchanged"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
