import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from pydantic import SecretStr, ValidationError

from src.intelligence.evidence import DEFAULT_EVIDENCE
from src.intelligence.extraction import extract_candidates, ground_findings, main
from src.intelligence.extractors import ExtractionError, ModelExtraction
from src.intelligence.feeds import APPROVED_URL, ReviewedSource
from src.intelligence.gemini import (
    MAX_RESPONSE_BYTES,
    SYSTEM_INSTRUCTION,
    GeminiExtractor,
)
from src.intelligence.reports import MAX_HTML_BYTES, MAX_REPORT_CHARACTERS, parse_report
from src.intelligence.sources import load_registry
from src.schemas.extraction import ExtractionBatch, ExtractionRecord
from src.schemas.trends import EvidenceLedger

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "tests/fixtures/extraction_report.html").read_bytes()
SOURCE = load_registry().sources[0]
NOW = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)


def candidate_payload():
    return {
        "findings": [
            {
                "claim": "The fictional sample reports lower model-assessed success on longer tasks.",
                "evidence_type": "observed_usage",
                "support": {
                    "passage_id": "p0001",
                    "quote": "longer tasks had lower success",
                },
                "study_period": {
                    "start": "2025-11-13",
                    "end": "2025-11-20",
                    "passage_id": "p0002",
                },
                "limitations": [
                    "Fictional vendor sample; model-assessed outcomes do not establish employment effects."
                ],
            }
        ],
        "no_findings_reason": None,
    }


class StubExtractor:
    model = "test-model"

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else candidate_payload()
        self.calls = 0

    def extract(self, report, source):
        self.calls += 1
        return ModelExtraction(
            ExtractionBatch.model_validate(self.payload), "test-returned-model"
        )


class TestReportParser(unittest.TestCase):
    def test_paragraphs_have_sections_and_exclude_navigation_hidden_and_scripts(self):
        report = parse_report(HTML, SOURCE)
        self.assertEqual(report.title, "Synthetic report for extraction tests")
        self.assertEqual(
            [row.passage_id for row in report.passages], ["p0001", "p0002", "p0003"]
        )
        self.assertTrue(report.passages[0].section.endswith("Observed results"))
        self.assertTrue(report.passages[1].section.endswith("Methods"))
        text = " ".join(row.text for row in report.passages)
        for hidden in (
            "previous instructions",
            "Hidden fabricated",
            "Another hidden",
            "skill weights",
            "advertisements",
        ):
            self.assertNotIn(hidden, text)

    def test_inline_markup_entities_and_breaks_preserve_readable_text(self):
        changed = HTML.replace(
            b"longer tasks had lower success",
            b"longer <strong>tasks</strong> had<br>lower&nbsp;success",
        )
        self.assertIn(
            "longer tasks had lower success",
            parse_report(changed, SOURCE).passages[0].text,
        )

    def test_main_is_preferred_and_plain_article_fallback_is_supported(self):
        body = HTML.replace(b"<main>", b"<article>").replace(b"</main>", b"</article>")
        self.assertEqual(
            parse_report(body, SOURCE).passages, parse_report(HTML, SOURCE).passages
        )
        body = HTML.replace(b"<main>", b"<div>").replace(b"</main>", b"</div>")
        self.assertEqual(
            parse_report(body, SOURCE).passages, parse_report(HTML, SOURCE).passages
        )

    def test_bad_date_empty_oversized_and_unreadable_reports_are_rejected(self):
        cases = [
            b"",
            b"x" * (MAX_HTML_BYTES + 1),
            b"<h1>Empty</h1>Jan 15, 2026",
            HTML.replace(b"Jan 15, 2026", b"Jan 16, 2026"),
            HTML.replace(b"<h1>", b"<div>").replace(b"</h1>", b"</div>"),
            HTML.replace(b"longer tasks", b"x" * MAX_REPORT_CHARACTERS),
        ]
        for body in cases:
            with self.subTest(size=len(body)), self.assertRaises(ValueError):
                parse_report(body, SOURCE)

    def test_scripts_cannot_supply_the_missing_publication_marker(self):
        body = (
            HTML.replace(b"Jan 15, 2026", b"Jan 16, 2026")
            + b"<script>Jan 15, 2026</script>"
        )
        with self.assertRaises(ValueError):
            parse_report(body, SOURCE)

    def test_parser_hashes_are_stable_and_body_changes_remain_auditable(self):
        first = parse_report(HTML, SOURCE)
        repeated = parse_report(HTML, SOURCE)
        changed = parse_report(
            HTML.replace(b"national skill demand", b"local skill demand"), SOURCE
        )
        self.assertEqual(first, repeated)
        self.assertNotEqual(first.response_sha256, changed.response_sha256)
        self.assertNotEqual(first.text_sha256, changed.text_sha256)


class TestCandidateGrounding(unittest.TestCase):
    def setUp(self):
        self.report = parse_report(HTML, SOURCE)

    def ground(self, payload):
        return ground_findings(
            ExtractionBatch.model_validate(payload), self.report, SOURCE
        )

    def test_quotes_offsets_period_and_hashes_resolve_to_source_passages(self):
        result = self.ground(candidate_payload())[0]
        passage = self.report.passages[0]
        self.assertEqual(
            passage.text[result.support.quote_start : result.support.quote_end],
            result.support.quote,
        )
        self.assertEqual(result.support.passage_sha256, passage.sha256)
        self.assertEqual(
            result.study_period_passage_sha256, self.report.passages[1].sha256
        )
        self.assertEqual(result.review_status, "pending_review")

    def test_invented_quotes_wrong_locators_and_unsupported_dates_are_rejected(self):
        for mutation in (
            "quote",
            "passage",
            "period_passage",
            "period_date",
            "future_date",
        ):
            payload = candidate_payload()
            finding = payload["findings"][0]
            if mutation == "quote":
                finding["support"]["quote"] = (
                    "a fabricated result absent from the report"
                )
            elif mutation == "passage":
                finding["support"]["passage_id"] = "p9999"
            elif mutation == "period_passage":
                finding["study_period"]["passage_id"] = "p0001"
            elif mutation == "period_date":
                finding["study_period"]["start"] = "2025-11-12"
            else:
                finding["study_period"].update(start="2027-01-01", end="2027-01-02")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.ground(payload)

    def test_unknown_study_dates_remain_unknown(self):
        payload = candidate_payload()
        payload["findings"][0]["study_period"] = {
            "start": None,
            "end": None,
            "passage_id": None,
        }
        result = self.ground(payload)[0]
        self.assertIsNone(result.study_period.start)
        self.assertIsNone(result.study_period_passage_sha256)

    def test_duplicates_are_collapsed_and_ids_are_stable(self):
        payload = candidate_payload()
        original = self.ground(payload)[0]
        payload["findings"].append(copy.deepcopy(payload["findings"][0]))
        self.assertEqual(self.ground(payload), [original])

    def test_schema_rejects_promotion_unknown_fields_long_quotes_and_partial_periods(
        self,
    ):
        cases = []
        for key, value in (("review_status", "accepted"), ("skill_adjustment", 0.2)):
            payload = candidate_payload()
            payload["findings"][0][key] = value
            cases.append(payload)
        payload = candidate_payload()
        payload["findings"][0]["support"]["quote"] = (
            "one two three four five six seven eight nine"
        )
        cases.append(payload)
        payload = candidate_payload()
        payload["findings"][0]["study_period"]["end"] = None
        cases.append(payload)
        payload = candidate_payload()
        payload["findings"][0]["claim"] = " "
        cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ExtractionBatch.model_validate(payload)

    def test_paraphrase_and_limitations_word_budgets_are_enforced(self):
        for field, value in (("claim", "word " * 36), ("limitations", ["word " * 21])):
            payload = candidate_payload()
            payload["findings"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.ground(payload)


class TestExtractionWorkflow(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "candidates"
        self.fetcher = Mock(return_value=HTML)

    def run_extraction(self, extractor=None, **kwargs):
        return extract_candidates(
            APPROVED_URL,
            extractor or StubExtractor(),
            output_directory=self.output,
            fetcher=self.fetcher,
            now=NOW,
            **kwargs,
        )

    def test_complete_workflow_writes_pending_candidates_without_touching_accepted_evidence(
        self,
    ):
        accepted_before = DEFAULT_EVIDENCE.read_bytes()
        extractor = StubExtractor()
        record, path = self.run_extraction(extractor)
        self.assertEqual(extractor.calls, 1)
        self.fetcher.assert_called_once_with(APPROVED_URL)
        self.assertEqual(
            ExtractionRecord.model_validate_json(path.read_bytes()), record
        )
        self.assertEqual(DEFAULT_EVIDENCE.read_bytes(), accepted_before)
        payload = json.loads(path.read_bytes())
        for accepted_contract in (ReviewedSource, EvidenceLedger):
            with self.assertRaises(ValidationError):
                accepted_contract.model_validate(payload)
        self.assertEqual(payload["review_status"], "pending_review")
        self.assertNotIn("raw_html", payload)
        self.assertNotIn(HTML.decode(), path.read_text(encoding="utf-8"))

    def test_unapproved_urls_are_blocked_before_fetch_or_model_use(self):
        extractor = Mock()
        with self.assertRaises(ValueError):
            extract_candidates(
                "https://example.org/unapproved", extractor, fetcher=self.fetcher
            )
        self.fetcher.assert_not_called()
        extractor.extract.assert_not_called()

    def test_failed_fetch_or_model_or_grounding_preserves_previous_candidates(self):
        _, path = self.run_extraction()
        previous = path.read_bytes()
        self.fetcher.side_effect = URLError("offline")
        extractor = Mock(model="test")
        with self.assertRaises(URLError):
            self.run_extraction(extractor)
        extractor.extract.assert_not_called()
        self.fetcher.side_effect = None
        extractor.extract.side_effect = ExtractionError("provider failed")
        with self.assertRaises(ExtractionError):
            self.run_extraction(extractor)
        payload = candidate_payload()
        payload["findings"][0]["support"]["quote"] = "made up evidence"
        with self.assertRaises(ValueError):
            self.run_extraction(StubExtractor(payload))
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.output.glob("*.json")), [path])

    def test_repeated_runs_preserve_history_and_content_ids(self):
        first, first_path = self.run_extraction()
        second, second_path = self.run_extraction()
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first.findings, second.findings)
        self.assertTrue(first_path.exists())

    def test_injected_fetch_times_are_normalized_to_utc_and_naive_times_fail(self):
        local_time = datetime(2026, 10, 20, 23, tzinfo=timezone(timedelta(hours=8)))
        record, _ = extract_candidates(
            APPROVED_URL,
            StubExtractor(),
            output_directory=self.output,
            fetcher=self.fetcher,
            now=local_time,
        )
        self.assertEqual(record.fetched_at.isoformat(), "2026-10-20T15:00:00+00:00")
        with self.assertRaises(ValueError):
            extract_candidates(
                APPROVED_URL,
                StubExtractor(),
                fetcher=self.fetcher,
                now=datetime(2026, 10, 20, 15),
            )

    def test_no_findings_is_saved_explicitly_without_fabricated_records(self):
        record, _ = self.run_extraction(
            StubExtractor(
                {"findings": [], "no_findings_reason": "No supported work findings."}
            )
        )
        self.assertEqual(record.findings, [])
        self.assertIsNotNone(record.no_findings_reason)
        with self.assertRaises(ValidationError):
            ExtractionBatch.model_validate({"findings": [], "no_findings_reason": None})

    def test_cli_missing_key_fails_with_actionable_message_without_fetching(self):
        stream = io.StringIO()
        with (
            patch.dict("os.environ", {}, clear=True),
            redirect_stderr(stream),
            patch("src.intelligence.extraction.fetch_html") as fetcher,
        ):
            self.assertEqual(main(["--url", APPROVED_URL]), 1)
        self.assertIn("GEMINI_API_KEY", stream.getvalue())
        fetcher.assert_not_called()

    def test_cli_success_reports_candidate_path_and_no_accepted_changes(self):
        record, path = self.run_extraction()
        output = io.StringIO()
        with (
            patch("src.intelligence.extraction.GeminiExtractor.from_environment"),
            patch(
                "src.intelligence.extraction.extract_candidates",
                return_value=(record, path),
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["--url", APPROVED_URL]), 0)
        self.assertFalse(json.loads(output.getvalue())["accepted_evidence_changed"])


class TestGeminiAdapter(unittest.TestCase):
    def setUp(self):
        self.extractor = GeminiExtractor(
            SecretStr("sentinel-test-secret"), "gemini-test"
        )
        self.report = parse_report(HTML, SOURCE)
        self.opener_patch = patch("src.intelligence.gemini.build_opener")
        self.opener = self.opener_patch.start()
        self.addCleanup(self.opener_patch.stop)
        self.response = (
            self.opener.return_value.open.return_value.__enter__.return_value
        )
        self.response.status = 200
        self.response.headers.get_content_type.return_value = "application/json"
        self.envelope = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(candidate_payload())}]},
                }
            ],
            "modelVersion": "gemini-test-version",
        }
        self.set_response(self.envelope)

    def set_response(self, payload):
        self.response.read.return_value = json.dumps(payload).encode()

    def test_structured_request_keeps_secret_out_of_url_body_repr_and_result(self):
        result = self.extractor.extract(self.report, SOURCE)
        request = self.opener.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            payload["systemInstruction"]["parts"][0]["text"], SYSTEM_INSTRUCTION
        )
        self.assertIn("responseJsonSchema", payload["generationConfig"])
        self.assertNotIn("tools", payload)
        self.assertIn(
            "untrusted_report_passages", payload["contents"][0]["parts"][0]["text"]
        )
        self.assertEqual(request.get_header("X-goog-api-key"), "sentinel-test-secret")
        for public in (
            request.full_url,
            request.data.decode(),
            repr(self.extractor),
            repr(result),
        ):
            self.assertNotIn("sentinel-test-secret", public)
        self.assertEqual(result.returned_model, "gemini-test-version")
        self.response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        self.opener.return_value.open.assert_called_once()

    def test_rate_limits_auth_and_network_errors_are_sanitized_without_retries(self):
        for error in (
            HTTPError("url", 429, "sentinel-test-secret", {}, None),
            HTTPError("url", 403, "sentinel-test-secret", {}, None),
            URLError("sentinel-test-secret"),
        ):
            self.opener.return_value.open.side_effect = error
            with (
                self.subTest(error=type(error).__name__),
                self.assertRaises(ExtractionError) as context,
            ):
                self.extractor.extract(self.report, SOURCE)
            self.assertNotIn("sentinel-test-secret", str(context.exception))

    def test_malformed_blocked_and_truncated_responses_are_rejected(self):
        cases = [
            {},
            [],
            {"candidates": []},
            {"candidates": ["invalid"]},
            {"candidates": [{"finishReason": "MAX_TOKENS"}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": ["bad"]}}]},
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": 1}]}}
                ]
            },
        ]
        invalid = copy.deepcopy(self.envelope)
        invalid["candidates"][0]["content"]["parts"][0]["text"] = "not JSON"
        cases.append(invalid)
        for payload in cases:
            self.set_response(payload)
            with self.subTest(payload=payload), self.assertRaises(ExtractionError):
                self.extractor.extract(self.report, SOURCE)
        self.response.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(ExtractionError):
            self.extractor.extract(self.report, SOURCE)

    def test_empty_credentials_and_path_like_model_ids_are_rejected(self):
        for key, model in (
            ("", "gemini-test"),
            ("key", "../../other"),
            ("key", "https://example.org"),
        ):
            with self.subTest(model=model), self.assertRaises(ExtractionError):
                GeminiExtractor(SecretStr(key), model)


if __name__ == "__main__":
    unittest.main()
