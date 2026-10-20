"""Extract findings from an approved report into an isolated review queue.

python -m src.intelligence.extraction --url https://approved.example/report
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from uuid import uuid4

from pydantic import ValidationError

from src.intelligence.extractors import ExtractionError, FindingExtractor
from src.intelligence.feeds import fetch_html
from src.intelligence.gemini import PROMPT_VERSION, GeminiExtractor
from src.intelligence.reports import (
    ParsedReport,
    date_is_present,
    normalize_text,
    parse_report,
)
from src.intelligence.sources import load_registry, resolve_source
from src.intelligence.storage import atomic_json
from src.schemas.extraction import (
    CandidateFinding,
    ExtractionBatch,
    ExtractionRecord,
    GroundedFinding,
    GroundedPassage,
)
from src.schemas.sources import ApprovedSource, SourceRegistry

DEFAULT_CANDIDATES = Path(__file__).resolve().parents[2] / "data/review/candidates"


def candidate_identity(
    source_id: str, text_sha256: str, finding: CandidateFinding
) -> str:
    """Stable identity shared by extraction and the later approval boundary."""
    content = json.dumps(
        {
            "source_id": source_id,
            "text_sha256": text_sha256,
            "finding": finding.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    return "candidate:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


def ground_findings(
    batch: ExtractionBatch, report: ParsedReport, source: ApprovedSource
) -> list[GroundedFinding]:
    """Verify locators/quotes/dates, not whether a claim is true or entailed."""
    passages = {row.passage_id: row for row in report.passages}
    findings = []
    seen = set()
    for finding in batch.findings:
        passage = passages.get(finding.support.passage_id)
        quote = normalize_text(finding.support.quote)
        if passage is None or quote not in passage.text:
            raise ValueError(
                "Candidate supporting quote does not match its report passage"
            )
        if (
            len(finding.claim.split()) > 35
            or sum(len(row.split()) for row in finding.limitations) > 20
        ):
            raise ValueError(
                "Candidate paraphrase or limitations exceed the word budget"
            )
        period = finding.study_period
        period_passage = passages.get(period.passage_id) if period.passage_id else None
        if period.start is not None and period.end is not None:
            if period.end > source.published_at or period_passage is None:
                raise ValueError(
                    "Study dates need a valid passage and cannot follow publication"
                )
            if not all(
                date_is_present(value, period_passage.text)
                for value in (period.start, period.end)
            ):
                raise ValueError(
                    "Study endpoints are not explicitly present in the cited passage"
                )
        identity = (normalize_text(finding.claim).casefold(), passage.passage_id, quote)
        if identity in seen:
            continue
        seen.add(identity)
        offset = passage.text.index(quote)
        findings.append(
            GroundedFinding(
                **finding.model_dump(exclude={"support"}),
                candidate_id=candidate_identity(
                    source.source_id, report.text_sha256, finding
                ),
                support=GroundedPassage(
                    passage_id=passage.passage_id,
                    quote=quote,
                    section=passage.section,
                    passage_sha256=passage.sha256,
                    quote_start=offset,
                    quote_end=offset + len(quote),
                ),
                study_period_passage_sha256=period_passage.sha256
                if period_passage
                else None,
            )
        )
    return findings


def extract_candidates(
    url: str,
    extractor: FindingExtractor,
    *,
    output_directory: Path = DEFAULT_CANDIDATES,
    registry: SourceRegistry | None = None,
    fetcher: Callable[[str], bytes] = fetch_html,
    now: datetime | None = None,
) -> tuple[ExtractionRecord, Path]:
    """All validation precedes the sole write; accepted evidence is never loaded."""
    source = resolve_source(url, registry or load_registry())
    fetched_at = now or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("Fetch time must be timezone-aware")
    fetched_at = fetched_at.astimezone(timezone.utc)
    if fetched_at.date() < source.published_at:
        raise ValueError("Fetch time must be timezone-aware and follow publication")
    report = parse_report(fetcher(url), source)
    result = extractor.extract(report, source)
    findings = ground_findings(result.batch, report, source)
    record = ExtractionRecord(
        source=source,
        report_title=report.title,
        fetched_at=fetched_at,
        response_sha256=report.response_sha256,
        parsed_text_sha256=report.text_sha256,
        passage_count=len(report.passages),
        parsed_characters=report.character_count,
        requested_model=extractor.model,
        returned_model=result.returned_model,
        prompt_version=PROMPT_VERSION,
        findings=findings,
        no_findings_reason=result.batch.no_findings_reason,
        limitations=[
            "AI-generated candidates require source and semantic review before acceptance.",
            "Exact-quote checks establish text presence, not support for every part of a paraphrase.",
            "Extraction does not create task mappings, skill adjustments or employment forecasts.",
        ],
    )
    # Fresh names preserve earlier candidates even when a later attempt fails.
    name = f"{source.source_id.split(':')[1]}_{fetched_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:12]}.json"
    path = Path(output_directory) / name
    atomic_json(path, record.model_dump(mode="json"))
    return record, path


def inspect_source(url: str) -> dict:
    """Verify fetch/parser without credentials, model use or persistent writes."""
    source = resolve_source(url, load_registry())
    report = parse_report(fetch_html(url), source)
    return {
        "source_id": source.source_id,
        "title": report.title,
        "published_at": source.published_at.isoformat(),
        "passage_count": len(report.passages),
        "parsed_characters": report.character_count,
        "response_sha256": report.response_sha256,
        "model_called": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--model",
        help="Gemini model ID; defaults to GEMINI_MODEL or the configured default",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument(
        "--inspect-source",
        action="store_true",
        help="Fetch and parse only; no AI call or saved article",
    )
    args = parser.parse_args(argv)
    try:
        if args.inspect_source:
            print(json.dumps(inspect_source(args.url), indent=2))
            return 0
        extractor = GeminiExtractor.from_environment(args.model)
        record, path = extract_candidates(
            args.url, extractor, output_directory=args.output_dir
        )
        print(
            json.dumps(
                {
                    "status": "pending_review",
                    "findings_count": len(record.findings),
                    "candidate_path": str(path),
                    "model": record.returned_model,
                    "accepted_evidence_changed": False,
                },
                indent=2,
            )
        )
        return 0
    except ExtractionError as error:
        message = str(error)
    except ValidationError:
        message = (
            "Candidate/source data failed schema validation; no candidates were saved."
        )
    except (OSError, URLError, HTTPException):
        message = "Source fetch or candidate storage failed; accepted evidence was not changed."
    except ValueError as error:
        message = str(error)
    print(
        json.dumps(
            {"status": "failed", "message": message, "accepted_evidence_changed": False}
        ),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
