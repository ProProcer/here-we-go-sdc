import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.intelligence.discovery import (
    CONFIG,
    DiscoveryConfig,
    parse_feed,
    review_source,
    run_discovery,
)
from src.intelligence.extractors import ModelExtraction
from src.schemas.extraction import MAX_FINDINGS, ExtractionBatch

NOW = datetime(2026, 10, 22, tzinfo=UTC)
URL = "https://research.google/blog/test-ai-analysis/"


def rss(
    url=URL,
    published="Thu, 22 Oct 2026 00:00:00 GMT",
    title="AI agent for data analysis",
):
    return f"<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate></item></channel></rss>".encode()


class NoFindingsExtractor:
    model = "fictional-test-only"
    calls = 0

    def extract(self, report, source):
        self.calls += 1
        return ModelExtraction(
            ExtractionBatch(
                findings=[],
                no_findings_reason="No supported findings in fictional fixture.",
            ),
            self.model,
        )


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / "queue.json"
        self.registry = root / "registry.json"
        self.decisions = root / "decisions.json"
        self.config = DiscoveryConfig.model_validate_json(CONFIG.read_bytes())
        self.config.feeds = self.config.feeds[:1]
        self.config_path = root / "config.json"
        self.config_path.write_text(self.config.model_dump_json())
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": "0.1.0",
                    "sources": [
                        {
                            "source_id": "source:fixture",
                            "source_url": "https://example.edu/fixture",
                            "publisher": "Fixture",
                            "published_at": "2026-01-01",
                        }
                    ],
                }
            )
        )

    def run_job(self, **kwargs):
        return run_discovery(
            state_path=self.state,
            registry_path=self.registry,
            decisions_path=self.decisions,
            config_path=self.config_path,
            now=NOW,
            fetcher=kwargs.pop("fetcher", lambda url: rss()),
            **kwargs,
        )

    def review(self, row, **kwargs):
        return review_source(
            row["discovery_id"],
            decision=kwargs.pop("decision", "approve"),
            reviewer="Fictional test reviewer",
            reason="Fictional test review; not real evidence.",
            state_path=self.state,
            registry_path=self.registry,
            decisions_path=self.decisions,
            config_path=self.config_path,
            now=NOW,
            **kwargs,
        )

    def test_unreviewed_discovery_is_deduplicated_and_cannot_call_model(self):
        before = self.registry.read_bytes()
        extractor = NoFindingsExtractor()
        first = self.run_job(extractor=extractor)
        second = self.run_job(extractor=extractor)
        self.assertEqual(len(second["items"]), 1)
        self.assertEqual(
            first["items"][0]["discovery_id"], second["items"][0]["discovery_id"]
        )
        self.assertEqual(extractor.calls, 0)
        self.assertEqual(second["items"][0]["source_review_status"], "pending_review")
        self.assertEqual(self.registry.read_bytes(), before)

    def test_out_of_scope_stale_future_and_unsafe_links_are_excluded(self):
        for body in (
            rss(url="https://research.google.evil.test/blog/test"),
            rss(url="https://research.google/blogish/test"),
            rss(url="https://research.google:secret@evil.test/blog/test"),
            rss(published="Tue, 01 Jan 2019 00:00:00 GMT"),
            rss(published="Fri, 23 Oct 2026 00:00:00 GMT"),
        ):
            self.assertEqual(
                parse_feed(body, self.config.feeds[0], self.config, NOW), []
            )
        with self.assertRaises(ValueError):
            parse_feed(
                b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>',
                self.config.feeds[0],
                self.config,
                NOW,
            )

    def test_atom_feed_and_tracking_link_canonicalization(self):
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Data science agent</title><link href="https://research.google/blog/test-ai-analysis/?utm_source=feed"/><published>2026-10-22T00:00:00Z</published></entry></feed>'
        rows = parse_feed(body, self.config.feeds[0], self.config, NOW)
        self.assertEqual(rows[0]["url"], URL)

    def test_failed_refresh_preserves_queue_and_records_failure(self):
        first = self.run_job()

        def failed(url):
            raise TimeoutError("Fictional outage")

        second = self.run_job(fetcher=failed)
        self.assertEqual(second["items"], first["items"])
        self.assertEqual(second["feeds"][0]["status"], "failed")

    def test_source_approval_checks_page_then_extraction_is_review_only(self):
        row = self.run_job()["items"][0]
        page = (
            b"<html><main><h1>Fictional report</h1><p>October 22, 2026</p><p>"
            + b"This is fictional test data, not a real finding. " * 12
            + b"</p></main></html>"
        )
        self.review(row, fetcher=lambda url: page)
        extractor = NoFindingsExtractor()
        result = self.run_job(extractor=extractor, article_fetcher=lambda url: page)
        self.assertEqual(extractor.calls, 1)
        path = self.state.parent / result["items"][0]["extraction_path"]
        record = json.loads(path.read_text())
        self.assertEqual(record["review_status"], "pending_review")
        self.assertLessEqual(len(record["findings"]), MAX_FINDINGS)
        self.run_job(extractor=extractor, article_fetcher=lambda url: page)
        self.assertEqual(extractor.calls, 1)

    def test_rejection_prevents_extraction_and_duplicate_decision_is_read_only(self):
        row = self.run_job()["items"][0]
        self.review(row, decision="reject")
        before = self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError, "already has a review"):
            self.review(row, fetcher=lambda url: self.fail("Must not fetch"))
        self.assertEqual(self.registry.read_bytes(), before)
        extractor = NoFindingsExtractor()
        self.run_job(extractor=extractor)
        self.assertEqual(extractor.calls, 0)

    def test_failed_page_validation_does_not_approve_source(self):
        row = self.run_job()["items"][0]
        before = self.registry.read_bytes()
        with self.assertRaises(ValueError):
            self.review(row, fetcher=lambda url: b"<html>no date</html>")
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertFalse(self.decisions.exists())


if __name__ == "__main__":
    unittest.main()
