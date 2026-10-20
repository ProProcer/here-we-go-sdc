import copy
import json
import unittest
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError

from src.intelligence.evidence import load_evidence
from src.intelligence.feeds import (
    APPROVED_URL,
    DEFAULT_REVIEW,
    MAX_BYTES,
    ReviewedSource,
    fetch_html,
    get_refresh_status,
    refresh_evidence,
)
from src.intelligence.outlook import get_outlook

ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "data/demo/data_analyst_evidence_before_refresh.json"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_page(review):
    """Synthetic HTTP fixture only, never written to the real evidence ledger."""
    markers = " ".join([review.publication_marker, *review.required_markers])
    return f"<html><h1>{review.title_marker}</h1><p>{markers}</p></html>".encode()


class TestTrendRefresh(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ledger = self.directory / "ledger.json"
        self.ledger.write_bytes(BEFORE.read_bytes())
        self.snapshots = self.directory / "snapshots"
        self.review = ReviewedSource.model_validate_json(
            DEFAULT_REVIEW.read_text(encoding="utf-8")
        )

    def refresh(self, **kwargs):
        return refresh_evidence(
            ledger_path=self.ledger,
            snapshots_path=self.snapshots,
            now=NOW,
            **kwargs,
        )

    def test_real_dated_release_changes_cited_outlook_and_not_scenarios(self):
        # The HTTP bytes here are synthetic. A separate saved live-fetch receipt
        # records verification of the actual public page.
        before = get_outlook("role:data_analyst", evidence_path=self.ledger)
        result = self.refresh(fetcher=lambda url: test_page(self.review))
        after = get_outlook("role:data_analyst", evidence_path=self.ledger)
        self.assertEqual(result.status, "updated")
        self.assertEqual(len(before.sources), 1)
        self.assertEqual(len(after.sources), 2)
        self.assertEqual(str(after.sources[-1].published_at), "2026-01-15")
        self.assertNotEqual(before.tasks, after.tasks)
        self.assertNotEqual(before.signals, after.signals)
        self.assertEqual(before.scenario, after.scenario)
        self.assertEqual(before.sources[0], after.sources[0])
        snapshot = json.loads(Path(result.snapshot_path).read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot["response_sha256"]), 64)
        self.assertEqual(
            snapshot["ledger"], load_evidence(self.ledger).model_dump(mode="json")
        )
        self.assertNotIn("html", snapshot)
        repeat = self.refresh(fetcher=lambda url: test_page(self.review))
        self.assertEqual(repeat.status, "unchanged")
        self.assertEqual(
            get_refresh_status(self.snapshots / "last_refresh.json"), repeat
        )

    def test_fetch_failure_preserves_cache_byte_for_byte_and_reports_warning(self):
        previous = self.ledger.read_bytes()

        def fail(url):
            raise URLError("offline")

        result = self.refresh(fetcher=fail)
        self.assertEqual(result.status, "cached")
        self.assertTrue(result.cache_available)
        self.assertIn("offline", result.message)
        self.assertEqual(previous, self.ledger.read_bytes())
        self.assertEqual(
            list(self.snapshots.glob("*.json")), [self.snapshots / "last_refresh.json"]
        )

    def test_first_run_offline_is_unavailable_not_empty_success(self):
        ledger = self.directory / "missing.json"

        def fail(url):
            raise TimeoutError("deadline")

        result = refresh_evidence(
            ledger_path=ledger, snapshots_path=self.snapshots, fetcher=fail, now=NOW
        )
        self.assertEqual(result.status, "unavailable")
        self.assertFalse(result.cache_available)
        self.assertFalse(ledger.exists())

    def test_interrupted_http_response_preserves_cache(self):
        previous = self.ledger.read_bytes()

        def fail(url):
            raise IncompleteRead(b"partial", 100)

        result = self.refresh(fetcher=fail)
        self.assertEqual(result.status, "cached")
        self.assertEqual(previous, self.ledger.read_bytes())

    def test_catalog_invalid_cache_is_not_reported_as_usable(self):
        payload = json.loads(self.ledger.read_text(encoding="utf-8"))
        payload["task_interpretations"][0]["role_id"] = "role:missing"
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        previous = self.ledger.read_bytes()
        result = self.refresh(fetcher=lambda url: test_page(self.review))
        self.assertEqual(result.status, "unavailable")
        self.assertFalse(result.cache_available)
        self.assertEqual(previous, self.ledger.read_bytes())

    def test_changed_or_misleading_page_is_withheld(self):
        body = test_page(self.review)
        cases = [b"", b"x" * (MAX_BYTES + 1), b"<h1>Unrelated report</h1>"]
        cases.append(
            body.replace(self.review.publication_marker.encode(), b"Jan 16, 2026")
        )
        cases.append(
            body.replace(self.review.required_markers[0].encode(), b"Different finding")
        )
        cases.append(b"<h1>Economic primitives</h1><script>" + body + b"</script>")
        previous = self.ledger.read_bytes()
        for page in cases:
            with self.subTest(size=len(page)):
                result = self.refresh(fetcher=lambda url, page=page: page)
                self.assertEqual(result.status, "cached")
                self.assertEqual(previous, self.ledger.read_bytes())

    def test_synthetic_or_unapproved_review_never_fetches_or_enters_ledger(self):
        original = self.review.model_dump(mode="json")
        cases = []
        changed = copy.deepcopy(original)
        changed["synthetic"] = True
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["source"]["source_url"] = "http://127.0.0.1/private"
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["signal"]["synthetic"] = True
        cases.append(changed)
        previous = self.ledger.read_bytes()
        for payload in cases:
            path = self.directory / "review.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("src.intelligence.feeds.fetch_html") as fetcher:
                result = self.refresh(review_path=path, fetcher=fetcher)
                self.assertEqual(result.status, "cached")
                fetcher.assert_not_called()
                self.assertEqual(previous, self.ledger.read_bytes())

    def test_unknown_task_mapping_does_not_replace_cache(self):
        payload = self.review.model_dump(mode="json")
        payload["task_interpretations"][0]["task_id"] = "task:missing"
        path = self.directory / "review.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        previous = self.ledger.read_bytes()
        result = self.refresh(
            review_path=path, fetcher=lambda url: test_page(self.review)
        )
        self.assertEqual(result.status, "cached")
        self.assertEqual(previous, self.ledger.read_bytes())

    def test_transport_blocks_arbitrary_urls_redirects_and_large_responses(self):
        with self.assertRaises(ValueError):
            fetch_html("https://example.com")
        from src.intelligence.feeds import RejectRedirects

        with self.assertRaises(ValueError):
            RejectRedirects().redirect_request(None, None, 302, "", {}, APPROVED_URL)
        with patch("src.intelligence.feeds.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.headers.get_content_type.return_value = "application/json"
            with self.assertRaises(ValueError):
                fetch_html(APPROVED_URL)
            response.headers.get_content_type.return_value = "text/html"
            response.read.side_effect = lambda size: b"x" * size
            with self.assertRaises(ValueError):
                fetch_html(APPROVED_URL)

    def test_live_receipt_records_real_fetch_and_new_dated_source(self):
        receipt_path = ROOT / "data/demo/evidence_refresh_comparison.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        snapshot = json.loads(
            (ROOT / receipt["live_snapshot"]).read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["source_url"], APPROVED_URL)
        self.assertGreater(snapshot["response_bytes"], 1000)
        self.assertEqual(
            receipt["before_source_ids"], ["source:anthropic_economic_index_2025_09"]
        )
        self.assertIn(
            "source:anthropic_economic_index_2026_01", receipt["after_source_ids"]
        )
        self.assertEqual(
            receipt["after_signal_ids"],
            [row["signal_id"] for row in snapshot["ledger"]["signals"]],
        )


if __name__ == "__main__":
    unittest.main()
