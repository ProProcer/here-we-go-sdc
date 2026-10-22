import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import SecretStr

from src.intelligence.extractors import ExtractionError
from src.intelligence.gemini import GeminiClient
from src.intelligence.review_retrieval import collect_documents, fetch_research
from src.intelligence.source_review import (
    approve_review,
    review_one,
    role_context,
    run_reviews,
    validate_grounding,
)
from src.schemas.source_review import ReviewChallenge, ReviewDraft
from src.schemas.sources import ApprovedSource

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "tests/fixtures/extraction_report.html").read_bytes()
NOW = datetime(2026, 10, 22, tzinfo=UTC)
ROW = {
    "discovery_id": "a" * 24,
    "url": "https://research.google/blog/fictional-review-test/",
    "title": "Fictional AI study",
    "publisher": "Google Research",
    "published_at": "2026-01-15",
    "feed_id": "google_research",
    "metadata_changed": False,
    "source_review_status": "pending_review",
}
SOURCE = ApprovedSource(
    source_id="source:fixture",
    source_url=ROW["url"],
    publisher=ROW["publisher"],
    published_at=ROW["published_at"],
)


def draft_payload():
    reference = {"document_id": "primary", "passage_id": "p0001"}
    return {
        "summary": "A fictional study reports model-assessed outcomes; employment effects remain unknown.",
        "findings": [
            {
                "claim": "Longer tasks had lower model-assessed success in the fictional sample.",
                "evidence_type": "observed_usage",
                "reference": reference,
                "quote": "longer tasks had lower success",
            }
        ],
        "checks": [
            {
                "dimension": "authorship",
                "status": "unclear",
                "explanation": "Author credentials require a separate check.",
                "references": [],
            },
            {
                "dimension": "methods",
                "status": "supported",
                "explanation": "Dates and outcome assessment are described.",
                "references": [{"document_id": "primary", "passage_id": "p0002"}],
            },
            {
                "dimension": "limitations",
                "status": "supported",
                "explanation": "One platform; model-assessed outcomes.",
                "references": [{"document_id": "primary", "passage_id": "p0003"}],
            },
            {
                "dimension": "role_relevance",
                "status": "supported",
                "explanation": "Conditional analytical-task context only.",
                "references": [reference],
            },
        ],
        "cross_source_status": "not_established",
        "cross_source_explanation": "No independent corroboration was established.",
        "cross_source_references": [],
        "recommendation": "consider_approval",
        "human_checks": ["Check author credentials and the original sampling methods."],
    }


def metadata(url):
    return json.dumps(
        {
            "message": {
                "items": [
                    {
                        "title": ["Fictional report for extraction tests"],
                        "publisher": "Fictional publisher",
                        "DOI": "10.1234/fictional",
                    }
                ]
            }
        }
    ).encode()


class StubReviewer:
    model = "fictional-reviewer"

    def __init__(
        self, draft=None, verdict="supported", failure=False, cross_supported=True
    ):
        self.draft = draft or draft_payload()
        self.verdict = verdict
        self.failure = failure
        self.cross_supported = cross_supported
        self.calls = []

    def generate(self, instruction, packet, model):
        self.calls.append((instruction, packet))
        if self.failure:
            raise ExtractionError("Fictional model failure")
        if model is ReviewDraft:
            payload = copy.deepcopy(self.draft)
            if packet["role_context"].get("scope") == "shared_work_evidence":
                for check in payload["checks"]:
                    if check["dimension"] == "role_relevance":
                        check["dimension"] = "work_relevance"
                if payload["recommendation"] == "skip_for_role":
                    payload["recommendation"] = "skip_for_scope"
            result = ReviewDraft.model_validate(payload)
        else:
            result = ReviewChallenge.model_validate(
                {
                    "findings": [
                        {
                            "finding_index": 0,
                            "verdict": self.verdict,
                            "reason": "Checked against the supplied context.",
                        }
                    ],
                    "checks_supported": True,
                    "cross_source_supported": self.cross_supported,
                    "recommendation_supported": True,
                    "unresolved_issues": [],
                }
            )
        return SimpleNamespace(value=result, returned_model=self.model)


class TestSourceReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = role_context("role:onet_15_2051_01")

    def review(self, reviewer=None, **kwargs):
        return review_one(
            ROW,
            self.context,
            reviewer or StubReviewer(),
            article_fetcher=lambda url: HTML,
            research_fetcher=metadata,
            now=NOW,
            **kwargs,
        )

    def test_quote_presence_and_second_pass_are_required_before_candidates(self):
        client = StubReviewer()
        before = (ROOT / "data/processed/onet/31.0/trend_signals.json").read_bytes()
        record, candidates = self.review(client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(record["status"], "pending_human_review")
        self.assertEqual(len(candidates.findings), 1)
        self.assertEqual(candidates.review_status, "pending_review")
        self.assertFalse(record["human_signoff_claimed"])
        self.assertEqual(
            before, (ROOT / "data/processed/onet/31.0/trend_signals.json").read_bytes()
        )
        self.assertIn("UNTRUSTED DATA", client.calls[0][0])

    def test_shared_review_has_no_catalog_or_occupation_dependency(self):
        with patch(
            "src.intelligence.source_review.real_catalog", side_effect=AssertionError
        ):
            client = StubReviewer()
            record, _ = review_one(
                ROW,
                role_context(None),
                client,
                article_fetcher=lambda url: HTML,
                research_fetcher=metadata,
                now=NOW,
            )
        self.assertEqual(record["review_scope"], "shared_work_evidence")
        self.assertIn(
            "work_relevance", {c["dimension"] for c in record["draft"]["checks"]}
        )
        self.assertNotIn("tasks", client.calls[0][1]["role_context"])

    def test_semantically_overstated_finding_is_removed_even_with_matching_quote(self):
        record, candidates = self.review(StubReviewer(verdict="overstated"))
        self.assertEqual(record["recommendation"], "investigate")
        self.assertEqual(candidates.findings, [])
        self.assertIsNotNone(candidates.no_findings_reason)

    def test_unique_exact_quote_can_repair_an_adjacent_passage_locator(self):
        payload = draft_payload()
        payload["findings"][0]["reference"]["passage_id"] = "p0002"
        record, candidates = self.review(StubReviewer(draft=payload))
        self.assertEqual(candidates.findings[0].support.passage_id, "p0001")
        self.assertIn(
            "Corrected exact-quote locator", record["automatic_corrections"][0]
        )

    def test_invented_reference_is_rejected_before_second_call(self):
        payload = draft_payload()
        payload["findings"][0]["reference"] = {
            "document_id": "imaginary",
            "passage_id": "p0001",
        }
        client = StubReviewer(draft=payload)
        with self.assertRaises(ValueError):
            self.review(client)
        self.assertEqual(len(client.calls), 1)

    def test_unmatched_quote_is_flagged_and_blocks_every_candidate(self):
        payload = draft_payload()
        payload["findings"][0]["quote"] = "fabricated words absent from the source"
        record, candidates = self.review(StubReviewer(draft=payload))
        self.assertFalse(record["deterministic_checks"]["grounding_passed"])
        self.assertEqual(record["recommendation"], "investigate")
        self.assertEqual(candidates.findings, [])
        self.assertEqual(record["supported_finding_indices"], [])

    def test_metadata_title_match_is_not_corroboration(self):
        _, documents, _ = collect_documents(HTML, SOURCE, fetcher=metadata)
        payload = draft_payload()
        payload["cross_source_status"] = "possible_independent_support"
        payload["cross_source_references"] = [
            {"document_id": "related_1", "passage_id": "p0001"}
        ]
        with self.assertRaisesRegex(ValueError, "Metadata titles alone"):
            validate_grounding(ReviewDraft.model_validate(payload), documents)

    def test_metadata_overreach_is_downgraded_before_challenge(self):
        payload = draft_payload()
        payload["cross_source_status"] = "possible_independent_support"
        payload["cross_source_references"] = [
            {"document_id": "related_1", "passage_id": "p0001"}
        ]
        client = StubReviewer(draft=payload)
        record, _ = self.review(client)
        self.assertEqual(record["draft"]["cross_source_status"], "not_established")
        self.assertTrue(record["automatic_corrections"])
        self.assertEqual(
            client.calls[1][1]["untrusted_draft"]["cross_source_status"],
            "not_established",
        )

    def test_irrelevant_source_can_be_skipped_without_forcing_corroboration_work(self):
        payload = draft_payload()
        payload["recommendation"] = "skip_for_role"
        payload["checks"][-1]["status"] = "not_found"
        record, _ = self.review(StubReviewer(draft=payload, cross_supported=False))
        self.assertEqual(record["recommendation"], "skip_for_role")

    def test_contradictory_skip_and_supported_relevance_require_human_check(self):
        payload = draft_payload()
        payload["recommendation"] = "skip_for_role"
        record, _ = self.review(StubReviewer(draft=payload))
        self.assertEqual(record["recommendation"], "investigate")
        self.assertIn("conflicts", record["automatic_corrections"][-1])

    def test_unavailable_external_sources_remain_unknown(self):
        def unavailable(url):
            raise TimeoutError("Fictional outage")

        _, docs, attempts = collect_documents(HTML, SOURCE, fetcher=unavailable)
        self.assertEqual(len(docs), 1)
        self.assertEqual(attempts[-1]["status"], "unavailable")

    def test_linked_arxiv_study_is_traced_but_marked_abstract_only(self):
        html = HTML.replace(
            b"</main>",
            b'<a href="https://arxiv.org/html/2601.12345v1">Paper</a></main>',
        )
        calls = []

        def fetch(url):
            calls.append(url)
            if "arxiv.org" in url:
                return b'<h1 class="title">Fictional original paper</h1><blockquote class="abstract">Fictional study abstract.</blockquote>'
            return metadata(url)

        _, docs, _ = collect_documents(html, SOURCE, fetcher=fetch)
        self.assertEqual(calls[0], "https://arxiv.org/abs/2601.12345v1")
        self.assertEqual(docs[1]["coverage"], "abstract_only_not_full_paper")

    def test_research_fetcher_blocks_untrusted_hosts_and_paths(self):
        for url in (
            "https://127.0.0.1/works",
            "https://api.crossref.org.evil.test/works",
            "https://arxiv.org/admin",
            "http://arxiv.org/abs/2601.12345",
        ):
            with self.assertRaises(ValueError):
                fetch_research(url)

    def test_cached_reviews_avoid_calls_and_failed_refresh_preserves_old_review(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "queue.json"
            state.write_text(json.dumps({"items": [copy.deepcopy(ROW)]}))
            client = StubReviewer()
            run_reviews(
                state_path=state,
                client=client,
                article_fetcher=lambda url: HTML,
                research_fetcher=metadata,
                now=NOW,
            )
            queue = json.loads(state.read_text())
            saved = state.parent / queue["items"][0]["ai_review_path"]
            previous = saved.read_bytes()
            run_reviews(state_path=state, client=client, now=NOW + timedelta(hours=1))
            self.assertEqual(len(client.calls), 2)
            result = run_reviews(
                state_path=state,
                client=StubReviewer(failure=True),
                article_fetcher=lambda url: HTML,
                research_fetcher=metadata,
                now=NOW + timedelta(days=8),
            )
            self.assertEqual(result["failed_reviews"], 1)
            self.assertEqual(saved.read_bytes(), previous)
            brief = (state.parent / "REVIEW_BRIEF.md").read_text(encoding="utf-8")
            self.assertIn("previous review", brief)
            self.assertIn("<details>", brief)

    def test_restored_old_queue_recovers_committed_reviews_without_new_calls(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "queue.json"
            state.write_text(json.dumps({"items": [copy.deepcopy(ROW)]}))
            client = StubReviewer()
            run_reviews(
                state_path=state,
                client=client,
                article_fetcher=lambda url: HTML,
                research_fetcher=metadata,
                now=NOW,
            )
            # Simulate a previous Actions artifact overwriting the queue, while
            # newer immutable review files remain checked out from the repository.
            state.write_text(json.dumps({"items": [copy.deepcopy(ROW)]}))
            result = run_reviews(
                state_path=state, client=client, now=NOW + timedelta(hours=1)
            )
            self.assertEqual(result["review_attempts"], 0)
            self.assertEqual(len(client.calls), 2)
            self.assertTrue(json.loads(state.read_text())["items"][0]["ai_review_path"])
            review_files = list((state.parent / "ai_reviews").glob("*.json"))
            self.assertNotIn(b"\r\n", review_files[0].read_bytes())

    def test_schema_error_diagnostics_do_not_echo_model_input_or_key(self):
        secret = "fictional-api-key-must-never-be-printed"
        client = GeminiClient(SecretStr(secret), "gemini-test")
        response = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps({"summary": secret})}]},
                }
            ]
        }
        with self.assertRaises(ExtractionError) as caught:
            client._parse_response(json.dumps(response).encode(), ReviewDraft)
        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("validation", str(caught.exception))

    def test_approval_requires_human_action_exact_hash_and_current_article(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "queue.json"
            state.write_text(json.dumps({"items": [copy.deepcopy(ROW)]}))
            run_reviews(
                state_path=state,
                client=StubReviewer(),
                article_fetcher=lambda url: HTML,
                research_fetcher=metadata,
                now=NOW,
            )
            queue = json.loads(state.read_text())
            review = state.parent / queue["items"][0]["ai_review_path"]
            digest = hashlib.sha256(review.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "Explicit human"):
                approve_review(
                    ROW["discovery_id"],
                    reviewer="Fictional reviewer",
                    expected_sha256=digest,
                    state_path=state,
                )
            with self.assertRaisesRegex(ValueError, "review changed"):
                approve_review(
                    ROW["discovery_id"],
                    reviewer="Fictional reviewer",
                    expected_sha256="0" * 64,
                    approve=True,
                    state_path=state,
                )
            changed = HTML.replace(
                b"longer tasks had lower success", b"a different result was observed"
            )
            with (
                patch(
                    "src.intelligence.source_review.fetch_feed", return_value=changed
                ),
                self.assertRaisesRegex(ValueError, "Article changed"),
            ):
                approve_review(
                    ROW["discovery_id"],
                    reviewer="Fictional reviewer",
                    expected_sha256=digest,
                    approve=True,
                    state_path=state,
                )


if __name__ == "__main__":
    unittest.main()
