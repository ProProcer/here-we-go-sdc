import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from pydantic import ValidationError

from src.intelligence.evidence import load_evidence
from src.intelligence.feeds import (
    DEFAULT_REVIEW,
    ReviewedSource,
    SourceRegistry,
    refresh_evidence,
)
from src.intelligence.impacts import get_evidence_chain_response
from src.intelligence.outlook import get_outlook
from src.schemas.trends import (
    EvidenceLedger,
    EvidenceSource,
    TrendSignal,
    evidence_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/sources/anthropic_task_complexity_2026.json"
BEFORE = ROOT / "data/demo/data_analyst_evidence_before_refresh.json"
NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


class TestEvidenceChains(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ledger = self.directory / "ledger.json"
        self.ledger.write_bytes(BEFORE.read_bytes())
        self.payload = json.loads(REVIEW.read_text(encoding="utf-8"))
        markers = [
            self.payload["publication_marker"],
            *self.payload["required_markers"],
        ]
        # Transport fixture only; never used to generate committed live artifacts.
        self.body = (
            "<h1>Economic primitives</h1><p>" + " ".join(markers) + "</p>"
        ).encode()

    def refresh(self, payload=None, **kwargs):
        path = self.directory / "review.json"
        path.write_text(json.dumps(payload or self.payload), encoding="utf-8")
        return refresh_evidence(
            review_path=path,
            ledger_path=self.ledger,
            snapshots_path=self.directory / "snapshots",
            now=kwargs.pop("now", NOW),
            fetcher=kwargs.pop("fetcher", lambda url: self.body),
            **kwargs,
        )

    def response(self):
        return get_evidence_chain_response(evidence_path=self.ledger)

    def test_refresh_builds_complete_chain_without_changing_scenario_priorities(self):
        before = get_outlook("role:data_analyst", evidence_path=self.ledger)
        self.assertEqual(self.response()["status"], "insufficient_evidence")
        self.assertEqual(self.refresh().status, "updated")
        response = self.response()
        chain = response["chains"][0]
        self.assertEqual(chain["reasoning"]["signal_id"], chain["finding"]["signal_id"])
        self.assertEqual(chain["finding"]["source_id"], chain["source"]["source_id"])
        self.assertEqual(chain["source"]["published_at"], "2026-01-15")
        self.assertEqual(chain["reasoning"]["study_period_start"], "2025-11-13")
        self.assertTrue(response["catalog_synthetic"])
        self.assertFalse(response["changes_skill_weights"])
        self.assertEqual(
            {row["direction"] for row in chain["reasoning"]["skill_implications"]},
            {"mixed"},
        )
        self.assertEqual(
            before.scenario,
            get_outlook("role:data_analyst", evidence_path=self.ledger).scenario,
        )
        self.assertNotEqual(
            before.signals,
            get_outlook("role:data_analyst", evidence_path=self.ledger).signals,
        )

    def test_next_day_refresh_preserves_mapping_binding_and_publication_date(self):
        self.refresh()
        before = self.response()
        self.assertEqual(self.refresh(now=NOW + timedelta(days=1)).status, "updated")
        after = self.response()
        self.assertEqual(after["chains"][0]["source"]["retrieved_at"], "2026-10-21")
        self.assertEqual(after["chains"][0]["source"]["published_at"], "2026-01-15")
        self.assertEqual(
            before["chains"][0]["reasoning"], after["chains"][0]["reasoning"]
        )
        self.assertNotEqual(before["ledger_sha256"], after["ledger_sha256"])
        self.assertEqual(self.refresh(now=NOW + timedelta(days=1)).status, "unchanged")

    def test_changed_finding_requires_revised_binding_before_fetch(self):
        self.refresh()
        original = self.ledger.read_bytes()
        revised = copy.deepcopy(self.payload)
        revised["signal"]["claim"] = (
            "TEST ONLY: revised candidate finding, not a real source observation."
        )
        fetcher = Mock(return_value=self.body)
        self.assertEqual(self.refresh(revised, fetcher=fetcher).status, "cached")
        fetcher.assert_not_called()
        self.assertEqual(self.ledger.read_bytes(), original)
        revised["evidence_chains"][0]["reviewed_evidence_sha256"] = (
            evidence_fingerprint(
                EvidenceSource.model_validate(revised["source"]),
                TrendSignal.model_validate(revised["signal"]),
            )
        )
        revised["evidence_chains"][0]["task_change"] = (
            "TEST ONLY: re-reviewed interpretation."
        )
        self.assertEqual(self.refresh(revised).status, "updated")
        chain = self.response()["chains"][0]
        self.assertEqual(chain["finding"]["claim"], revised["signal"]["claim"])
        self.assertEqual(
            chain["reasoning"]["task_change"],
            revised["evidence_chains"][0]["task_change"],
        )

    def test_page_failure_preserves_entire_evidence_chain(self):
        self.refresh()
        original = self.ledger.read_bytes()
        changed_body = self.body.replace(
            self.payload["required_markers"][0].encode(), b"Changed finding"
        )
        self.assertEqual(
            self.refresh(fetcher=lambda url: changed_body).status, "cached"
        )
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_rejects_uncited_invalid_or_forecast_like_chains(self):
        cases = []
        for field, value in (
            ("signal_id", "signal:missing"),
            ("role_id", "role:missing"),
            ("task_id", "task:missing"),
            ("changes_skill_weights", True),
            ("study_period_end", "2027-01-01"),
            ("interpretation_status", "observed_fact"),
        ):
            payload = copy.deepcopy(self.payload)
            payload["evidence_chains"][0][field] = value
            cases.append(payload)
        for skill in ("skill:missing", "skill:statistics"):
            payload = copy.deepcopy(self.payload)
            payload["evidence_chains"][0]["skill_implications"][0]["skill_id"] = skill
            cases.append(payload)
        payload = copy.deepcopy(self.payload)
        payload["evidence_chains"][0]["skill_implications"][0]["more_emphasis"] = []
        cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ReviewedSource.model_validate(payload)

    def test_direct_ledger_edits_cannot_silently_reuse_an_old_interpretation(self):
        self.refresh()
        payload = load_evidence(self.ledger).model_dump(mode="json")
        payload["signals"][-1]["claim"] = (
            "TEST ONLY: changed without reviewing the chain."
        )
        with self.assertRaisesRegex(ValidationError, "Evidence changed"):
            EvidenceLedger.model_validate(payload)

    def test_review_can_withdraw_a_chain_without_leaving_stale_output(self):
        self.refresh()
        revised = copy.deepcopy(self.payload)
        revised["evidence_chains"] = []
        self.assertEqual(self.refresh(revised).status, "updated")
        self.assertEqual(self.response()["status"], "insufficient_evidence")
        self.assertEqual(self.response()["chains"], [])

    def test_refreshing_another_finding_preserves_the_existing_chain(self):
        self.refresh()
        original = self.response()["chains"]
        review = json.loads(DEFAULT_REVIEW.read_text(encoding="utf-8"))
        markers = [review["publication_marker"], *review["required_markers"]]
        body = ("<h1>Economic primitives</h1><p>" + " ".join(markers) + "</p>").encode()
        self.assertEqual(
            self.refresh(review, fetcher=lambda url: body).status, "updated"
        )
        self.assertEqual(self.response()["chains"], original)

    def test_chain_id_cannot_be_reassigned_to_another_signal(self):
        self.refresh()
        previous = self.ledger.read_bytes()
        revised = copy.deepcopy(self.payload)
        revised["signal"]["signal_id"] = "signal:another_finding"
        revised["task_interpretations"][0]["signal_ids"] = ["signal:another_finding"]
        revised["evidence_chains"][0]["signal_id"] = "signal:another_finding"
        revised["evidence_chains"][0]["reviewed_evidence_sha256"] = (
            evidence_fingerprint(
                EvidenceSource.model_validate(revised["source"]),
                TrendSignal.model_validate(revised["signal"]),
            )
        )
        self.assertEqual(self.refresh(revised).status, "cached")
        self.assertEqual(self.ledger.read_bytes(), previous)

    def test_other_roles_never_receive_unrelated_chains(self):
        self.refresh()
        self.assertEqual(
            get_evidence_chain_response(
                "role:it_support_specialist", evidence_path=self.ledger
            )["chains"],
            [],
        )
        with self.assertRaises(KeyError):
            get_evidence_chain_response("role:missing", evidence_path=self.ledger)

    def test_reviewed_new_release_can_be_admitted_through_registry_without_code_changes(
        self,
    ):
        payload = copy.deepcopy(self.payload)
        payload["evidence_chains"] = []
        payload["source"].update(
            source_id="source:test_release",
            source_url="https://example.org/test-release",
        )
        payload["signal"]["source_id"] = "source:test_release"
        entry = {
            key: payload["source"][key]
            for key in ("source_id", "source_url", "publisher", "published_at")
        }
        registry = self.directory / "approved.json"
        registry.write_text(
            json.dumps({"schema_version": "0.1.0", "sources": [entry]}),
            encoding="utf-8",
        )
        with self.assertRaises(ValidationError):
            ReviewedSource.model_validate(payload)
        with patch("src.intelligence.feeds.APPROVED_SOURCES", registry):
            self.assertEqual(self.refresh(payload).status, "updated")
        for url in (
            "http://example.org",
            "https://user:password@example.org",
            "https://example.org/#fragment",
        ):
            entry["source_url"] = url
            with self.subTest(url=url), self.assertRaises(ValidationError):
                SourceRegistry.model_validate(
                    {"schema_version": "0.1.0", "sources": [entry]}
                )

    def test_committed_example_matches_offline_service_and_real_snapshot(self):
        artifact = json.loads(
            (ROOT / "data/demo/data_analyst_evidence_chain.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(artifact["before"]["chains"], [])
        snapshot = json.loads(
            (ROOT / artifact["live_snapshot"]).read_text(encoding="utf-8")
        )
        # Historical demo receipts describe their saved input, not today's
        # mutable ledger after additional findings have been approved.
        historical = self.directory / "historical.json"
        historical.write_text(json.dumps(snapshot["ledger"]), encoding="utf-8")
        self.assertEqual(
            artifact["after"], get_evidence_chain_response(evidence_path=historical)
        )
        self.assertGreater(snapshot["response_bytes"], 1000)
        self.assertEqual(
            snapshot["ledger"]["evidence_chains"][0],
            artifact["after"]["chains"][0]["reasoning"],
        )
        ReviewedSource.model_validate_json(REVIEW.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
