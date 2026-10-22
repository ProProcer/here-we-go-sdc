"""Bounded RSS/Atom discovery, source review, and optional candidate extraction.

python -m src.intelligence.discovery run
python -m src.intelligence.discovery list
python -m src.intelligence.discovery review --id ID --decision approve --reviewer NAME --reason TEXT
Discovery never writes accepted findings or learning priorities.
"""

import argparse
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener
from xml.etree import ElementTree as ET

from pydantic import Field, HttpUrl, model_validator

from src.intelligence.feeds import ROOT, RejectRedirects, fetch_html
from src.intelligence.reports import parse_report
from src.intelligence.sources import DEFAULT_REGISTRY, load_registry
from src.intelligence.storage import atomic_json
from src.schemas.role import Contract
from src.schemas.sources import ApprovedSource, SourceRegistry

CONFIG = ROOT / "data/sources/discovery_feeds.json"
DECISIONS = ROOT / "data/sources/discovery_decisions.json"
STATE = ROOT / "data/review/discovery/queue.json"
MAX_BYTES = 2 * 1024 * 1024


class DiscoveryFeed(Contract):
    feed_id: str = Field(pattern=r"^[a-z0-9_]+$")
    publisher: str = Field(min_length=1)
    url: HttpUrl
    article_prefix: HttpUrl

    @model_validator(mode="after")
    def validate_urls(self):
        for url in (self.url, self.article_prefix):
            if url.scheme != "https" or url.username or url.password or url.fragment:
                raise ValueError("Feeds require public HTTPS URLs without credentials")
        if self.url.host != self.article_prefix.host:
            raise ValueError("Article and feed hosts must match")
        return self


class DiscoveryConfig(Contract):
    schema_version: str
    lookback_days: int = Field(ge=1, le=365)
    max_items_per_feed: int = Field(ge=1, le=500)
    feeds: list[DiscoveryFeed] = Field(min_length=1, max_length=10)
    keywords: list[str] = Field(min_length=1)


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or not parts.hostname
    ):
        raise ValueError("Discovery requires HTTPS without credentials or custom ports")
    return urlunsplit(("https", parts.hostname.lower(), parts.path, "", ""))


def fetch_feed(url: str) -> bytes:
    # The caller selects exact URLs from repository-owned feed configuration.
    request = Request(url, headers={"User-Agent": "FutureReadyAI/0.2 source discovery"})
    with build_opener(RejectRedirects()).open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("Feed must return HTTP 200")
        body = response.read(MAX_BYTES + 1)
    if not body or len(body) > MAX_BYTES:
        raise ValueError("Empty or oversized feed")
    return body


def _text(item, name):
    return next(
        (
            " ".join(node.itertext()).strip()
            for node in item
            if node.tag.rsplit("}", 1)[-1] == name
        ),
        "",
    )


def parse_feed(
    body: bytes, feed: DiscoveryFeed, config: DiscoveryConfig, now: datetime
):
    if len(body) > MAX_BYTES or re.search(
        rb"<!\s*(DOCTYPE|ENTITY)", body, re.IGNORECASE
    ):
        raise ValueError("Oversized feed or XML entity declarations")
    root = ET.fromstring(body)
    entries = [
        node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}
    ]
    if len(entries) > 5000:
        raise ValueError("Feed has too many entries")
    results = []
    for item in entries[: config.max_items_per_feed]:
        title = " ".join(_text(item, "title").split())[:300]
        if not any(word.casefold() in title.casefold() for word in config.keywords):
            continue
        link = _text(item, "link")
        if not link:
            link = next(
                (
                    n.get("href", "")
                    for n in item
                    if n.tag.rsplit("}", 1)[-1] == "link"
                    and n.get("rel", "alternate") == "alternate"
                ),
                "",
            )
        try:
            url = canonical_url(link)
            prefix = str(feed.article_prefix)
            if not url.startswith(prefix):
                continue
            raw_date = (
                _text(item, "pubDate")
                or _text(item, "published")
                or _text(item, "updated")
            )
            try:
                published = datetime.fromisoformat(raw_date)
            except ValueError:
                published = parsedate_to_datetime(raw_date)
            if published.utcoffset() is None:
                continue
            published_date = published.astimezone(UTC).date()
            if (
                not now.date() - timedelta(days=config.lookback_days)
                <= published_date
                <= now.date()
            ):
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        results.append(
            {
                "discovery_id": hashlib.sha256(url.encode()).hexdigest()[:24],
                "url": url,
                "title": title,
                "publisher": feed.publisher,
                "published_at": published_date.isoformat(),
                "feed_id": feed.feed_id,
            }
        )
    return results


def _load(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def run_discovery(
    *,
    state_path=STATE,
    config_path=CONFIG,
    decisions_path=DECISIONS,
    registry_path=DEFAULT_REGISTRY,
    fetcher=fetch_feed,
    now=None,
    extractor=None,
    max_extractions=3,
    article_fetcher=fetch_html,
) -> dict:
    now = now or datetime.now(UTC)
    if now.utcoffset() is None or not 0 <= max_extractions <= 10:
        raise ValueError("Timezone-aware time and extraction limit 0..10 required")
    now = now.astimezone(UTC)
    config = DiscoveryConfig.model_validate_json(Path(config_path).read_bytes())
    state_path = Path(state_path)
    state = _load(state_path, {"schema_version": "0.1.0", "items": []})
    items = {row["discovery_id"]: row for row in state["items"]}
    decisions = {
        row["discovery_id"]: row
        for row in _load(Path(decisions_path), {"decisions": []})["decisions"]
    }
    sources = {
        str(row.source_url): row for row in load_registry(Path(registry_path)).sources
    }
    receipts = []
    for feed in config.feeds:
        try:
            body = fetcher(str(feed.url))
            found = parse_feed(body, feed, config, now)
            for row in found:
                old = items.get(row["discovery_id"])
                if old:
                    old["last_seen_at"] = now.isoformat()
                    if any(
                        old[k] != row[k] for k in ("url", "publisher", "published_at")
                    ):
                        old["metadata_changed"] = True
                else:
                    items[row["discovery_id"]] = {
                        **row,
                        "first_seen_at": now.isoformat(),
                        "last_seen_at": now.isoformat(),
                        "metadata_changed": False,
                    }
            receipts.append(
                {
                    "feed_id": feed.feed_id,
                    "status": "ok",
                    "matches": len(found),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                }
            )
        except (OSError, ValueError, ET.ParseError, HTTPException) as error:
            receipts.append(
                {
                    "feed_id": feed.feed_id,
                    "status": "failed",
                    "error": type(error).__name__,
                }
            )
    extraction_count = 0
    for row in sorted(
        items.values(),
        key=lambda r: (r["published_at"], r["discovery_id"]),
        reverse=True,
    ):
        decision = decisions.get(row["discovery_id"])
        row["source_review_status"] = (
            decision["decision"] if decision else "pending_review"
        )
        source = sources.get(row["url"])
        if row["source_review_status"] == "approve" and (
            source is None
            or source.published_at.isoformat() != row["published_at"]
            or source.publisher != row["publisher"]
            or row["metadata_changed"]
        ):
            row["source_review_status"] = "needs_re_review"
        if (
            extractor is not None
            and extraction_count < max_extractions
            and row["source_review_status"] == "approve"
            and not row.get("extraction_path")
        ):
            extraction_count += 1
            try:
                from src.intelligence.extraction import extract_candidates
                from src.intelligence.extractors import ExtractionError

                _, path = extract_candidates(
                    row["url"],
                    extractor,
                    registry=load_registry(Path(registry_path)),
                    output_directory=state_path.parent / "findings",
                    now=now,
                    fetcher=article_fetcher,
                )
                row["extraction_path"] = path.relative_to(state_path.parent).as_posix()
                row.pop("extraction_error", None)
            except (OSError, ValueError, ExtractionError, HTTPException) as error:
                row["extraction_error"] = type(error).__name__
    result = {
        "schema_version": "0.1.0",
        "last_run_at": now.isoformat(),
        "feeds": receipts,
        "items": sorted(
            items.values(),
            key=lambda r: (r["published_at"], r["discovery_id"]),
            reverse=True,
        ),
    }
    atomic_json(state_path, result)
    return result


def review_source(
    discovery_id,
    *,
    decision,
    reviewer,
    reason,
    state_path=STATE,
    decisions_path=DECISIONS,
    registry_path=DEFAULT_REGISTRY,
    config_path=CONFIG,
    fetcher=None,
    now=None,
    expected_previous_decision=None,
):
    if (
        decision not in {"approve", "reject"}
        or not reviewer.strip()
        or not reason.strip()
    ):
        raise ValueError("Decision, actual reviewer label and review reason required")
    state = _load(Path(state_path), {"items": []})
    row = next(r for r in state["items"] if r["discovery_id"] == discovery_id)
    if row["metadata_changed"] and decision == "approve":
        raise ValueError(
            "Feed metadata changed; investigate before creating a fresh review"
        )
    decisions = _load(
        Path(decisions_path), {"schema_version": "0.1.0", "decisions": []}
    )
    prior = next(
        (
            d
            for d in reversed(decisions["decisions"])
            if d["discovery_id"] == discovery_id
        ),
        None,
    )
    if prior is not None and prior != expected_previous_decision:
        raise ValueError(
            "Source already has a review decision; revise explicitly in a reviewed change"
        )
    registry = load_registry(Path(registry_path))
    if decision == "approve":
        config = DiscoveryConfig.model_validate_json(Path(config_path).read_bytes())
        feed = next(f for f in config.feeds if f.feed_id == row["feed_id"])
        if row["publisher"] != feed.publisher or not canonical_url(
            row["url"]
        ).startswith(str(feed.article_prefix)):
            raise ValueError("Source does not match configured publisher scope")
        source = ApprovedSource(
            source_id="source:discovered_" + discovery_id,
            source_url=row["url"],
            publisher=row["publisher"],
            published_at=date.fromisoformat(row["published_at"]),
        )
        existing = next(
            (s for s in registry.sources if str(s.source_url) == row["url"]), None
        )
        if existing:
            if (
                existing.publisher != source.publisher
                or existing.published_at != source.published_at
            ):
                raise ValueError("Conflicting approved source metadata")
            source = existing
        # Exact reviewed URL only; independent of the existing article allowlist.
        page = (fetcher or fetch_feed)(row["url"])
        parse_report(page, source)
        if not existing:
            registry = SourceRegistry(
                schema_version="0.1.0", sources=[*registry.sources, source]
            )
            atomic_json(Path(registry_path), registry.model_dump(mode="json"))
    decisions["decisions"].append(
        {
            "discovery_id": discovery_id,
            "decision": decision,
            "reviewer": reviewer.strip(),
            "reason": reason.strip(),
            "reviewed_at": (now or datetime.now(UTC)).isoformat(),
        }
    )
    if prior is not None:
        decisions["decisions"][-1]["supersedes_sha256"] = hashlib.sha256(
            json.dumps(prior, sort_keys=True).encode()
        ).hexdigest()
    atomic_json(Path(decisions_path), decisions)
    return decisions["decisions"][-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument(
        "--extract",
        action="store_true",
        help="Use Gemini only for source-approved items",
    )
    run.add_argument("--max-extractions", type=int, default=3)
    commands.add_parser("list")
    review = commands.add_parser("review")
    for flag in ("id", "reviewer", "reason"):
        review.add_argument("--" + flag, required=True)
    review.add_argument("--decision", choices=["approve", "reject"], required=True)
    args = parser.parse_args()
    if args.command == "run":
        extractor = None
        if args.extract:
            from src.intelligence.gemini import GeminiExtractor

            extractor = GeminiExtractor.from_environment()
        result = run_discovery(
            extractor=extractor, max_extractions=args.max_extractions
        )
        print(
            json.dumps(
                {"items": len(result["items"]), "feeds": result["feeds"]}, indent=2
            )
        )
        return 0 if any(f["status"] == "ok" for f in result["feeds"]) else 1
    if args.command == "list":
        for row in _load(STATE, {"items": []})["items"]:
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in (
                            "discovery_id",
                            "title",
                            "url",
                            "published_at",
                            "source_review_status",
                            "extraction_path",
                        )
                    }
                )
            )
    else:
        print(
            json.dumps(
                review_source(
                    args.id,
                    decision=args.decision,
                    reviewer=args.reviewer,
                    reason=args.reason,
                ),
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
