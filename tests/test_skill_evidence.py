import copy
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from src.intelligence.extractors import ExtractionError
from src.intelligence.skill_evidence import (
    active_assessments,
    approve_mapping,
    build_plan,
    evidence_for_role,
    fingerprint,
    run_assessments,
    stored_news,
)
from src.intelligence.source_review import PROMPT_VERSION, SHARED_CONTEXT
from src.intelligence.storage import atomic_json
from src.schemas.role import Skill
from src.schemas.skill_evidence import SkillAssessmentBatch, SkillChallengeBatch

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def catalog():
    return SimpleNamespace(
        taxonomy=SimpleNamespace(
            skills=[
                Skill(
                    skill_id="skill:programming",
                    label="Programming",
                    aliases=["coding"],
                ),
                Skill(skill_id="skill:writing", label="Writing", aliases=[]),
            ]
        ),
        roles=[SimpleNamespace(role_id="role:first")],
        role_skills=[
            SimpleNamespace(role_id="role:first", skill_id="skill:programming")
        ],
        software_associations=[],
    )


def source_record(row):
    return {
        "review_scope": "shared_work_evidence",
        "context_sha256": fingerprint(SHARED_CONTEXT),
        "source_item_sha256": fingerprint(
            {
                k: row[k]
                for k in ("url", "publisher", "published_at", "title", "feed_id")
            }
        ),
        "prompt_version": PROMPT_VERSION,
        "requested_model": "fictional-source-reviewer",
        "source": {"source_url": row["url"], "publisher": "Fictional test"},
        "article_title": row["title"],
        "parsed_text_sha256": "a" * 64,
        "supported_finding_indices": [0],
        "deterministic_checks": {"grounding_passed": True},
        "challenge": {
            "findings": [{"finding_index": 0, "verdict": "supported"}],
            "unresolved_issues": [],
        },
        "draft": {
            "findings": [
                {
                    "claim": "Fictional benchmark evaluated generated code.",
                    "quote": "evaluated generated code",
                    "reference": {"document_id": "primary", "passage_id": "p0001"},
                    "evidence_type": "benchmark",
                }
            ],
            "checks": [],
            "human_checks": ["Check benchmark scope."],
            "cross_source_status": "not_established",
            "cross_source_explanation": "No independent replication established.",
        },
        "correction_notices": [],
    }


def seed(path, count=2):
    rows = []
    for i in range(count):
        row = {
            "discovery_id": f"news{i}",
            "url": f"https://example.org/test{i}",
            "title": f"Fictional study {i}",
            "publisher": "Fictional test",
            "published_at": "2026-01-01",
            "feed_id": "fictional",
            "source_review_status": "approve",
            "ai_review_path": f"ai_reviews/test{i}.json",
        }
        atomic_json(path.parent / row["ai_review_path"], source_record(row))
        rows.append(row)
    atomic_json(path, {"items": rows})


class StubMapper:
    model = "fictional-skill-mapper"

    def __init__(
        self,
        *,
        relevance="potentially_relevant",
        omit=False,
        invent=False,
        fail=False,
        supported=True,
    ):
        self.calls = []
        self.relevance = relevance
        self.omit = omit
        self.invent = invent
        self.fail = fail
        self.supported = supported

    def generate(self, instruction, packet, model):
        self.calls.append((instruction, copy.deepcopy(packet)))
        if self.fail:
            raise ExtractionError("Fictional failure")
        rows = packet["news"][:-1] if self.omit else packet["news"]
        if model is SkillAssessmentBatch:
            value = model.model_validate(
                {
                    "assessments": [
                        {
                            "news_id": row["news_id"],
                            "relevance": self.relevance,
                            "finding_indices": [99 if self.invent else 0]
                            if self.relevance == "potentially_relevant"
                            else [],
                            "rationale": "Conditional coding activity; demand effects remain unknown.",
                            "applicability_conditions": [
                                "Work involves the evaluated coding activity."
                            ],
                            "human_checks": [
                                "Check whether the activity matches actual work."
                            ],
                        }
                        for row in rows
                    ]
                }
            )
        else:
            value = SkillChallengeBatch.model_validate(
                {
                    "assessments": [
                        {
                            "news_id": row["news_id"],
                            "supported": self.supported,
                            "reason": "Checked only against the supplied findings.",
                        }
                        for row in rows
                    ]
                }
            )
        return SimpleNamespace(value=value, returned_model=self.model)


class TestIncrementalSkillEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "queue.json"
        self.decisions = self.path.parent / "decisions.json"
        seed(self.path)
        self.catalog = catalog()
        self.client = StubMapper()

    def run_mapping(self, **kwargs):
        return run_assessments(
            state_path=self.path,
            catalog=self.catalog,
            client=kwargs.pop("client", self.client),
            now=NOW,
            **kwargs,
        )

    def active(self):
        return active_assessments(
            state_path=self.path,
            catalog=self.catalog,
            model=self.client.model,
            decisions_path=self.decisions,
        )[0]

    def approve(self, digest, **kwargs):
        return approve_mapping(
            digest,
            reviewer="Fictional owner",
            approve=True,
            state_path=self.path,
            catalog=self.catalog,
            model=self.client.model,
            decisions_path=self.decisions,
            **kwargs,
        )

    def test_initial_pass_covers_all_news_then_reuses_positive_and_negative_results(
        self,
    ):
        first = self.run_mapping(client=StubMapper(relevance="not_relevant"))
        self.assertEqual(first["assessments_written"], 4)
        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=AssertionError("No source refetch"),
        ):
            second = self.run_mapping()
        self.assertEqual(second["batches_attempted"], 0)
        self.assertEqual(self.client.calls, [])

    def test_new_skill_backfills_only_that_skill_against_every_stored_article(self):
        self.run_mapping()
        self.client.calls.clear()
        self.catalog.taxonomy.skills.append(
            Skill(skill_id="skill:math", label="Mathematics", aliases=[])
        )
        result = self.run_mapping()
        self.assertEqual(result["assessments_written"], 2)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(
            {c[1]["skill"]["skill_id"] for c in self.client.calls}, {"skill:math"}
        )
        self.assertEqual(
            {n["news_id"] for n in self.client.calls[0][1]["news"]}, {"news0", "news1"}
        )

    def test_role_addition_and_membership_update_need_no_ai_and_reuse_approved_mapping(
        self,
    ):
        self.run_mapping()
        mapping = next(
            a
            for a in self.active()
            if a["record"]["skill"]["skill_id"] == "skill:programming"
        )
        self.approve(fingerprint(mapping["record"]))
        self.catalog.roles.append(SimpleNamespace(role_id="role:second"))
        self.catalog.role_skills.append(
            SimpleNamespace(role_id="role:second", skill_id="skill:programming")
        )
        self.client.calls.clear()
        self.assertEqual(self.run_mapping()["batches_attempted"], 0)
        result = evidence_for_role(
            "role:second",
            catalog=self.catalog,
            state_path=self.path,
            model=self.client.model,
            decisions_path=self.decisions,
        )
        self.assertEqual(len(result["approved_conditional_skill_evidence"]), 1)
        self.assertFalse(result["changes_weights"])
        self.assertEqual(self.client.calls, [])
        self.catalog.role_skills[-1].skill_id = "skill:writing"
        result = evidence_for_role(
            "role:second",
            catalog=self.catalog,
            state_path=self.path,
            model=self.client.model,
            decisions_path=self.decisions,
        )
        self.assertEqual(result["approved_conditional_skill_evidence"], [])

    def test_changed_definition_invalidates_only_that_skill_and_its_approval(self):
        self.run_mapping()
        record = self.active()[0]["record"]
        digest = fingerprint(record)
        self.approve(digest)
        skill_id = record["skill"]["skill_id"]
        next(
            s for s in self.catalog.taxonomy.skills if s.skill_id == skill_id
        ).label += " revised"
        self.client.calls.clear()
        with self.assertRaisesRegex(ValueError, "context changed"):
            self.approve(digest)
        self.assertEqual(self.run_mapping()["assessments_written"], 2)
        self.assertEqual(
            {c[1]["skill"]["skill_id"] for c in self.client.calls}, {skill_id}
        )

    def test_changed_source_invalidates_only_that_article_for_every_skill(self):
        self.run_mapping()
        self.client.calls.clear()
        review = self.path.parent / "ai_reviews/test0.json"
        payload = json.loads(review.read_text())
        payload["parsed_text_sha256"] = "b" * 64
        atomic_json(review, payload)
        result = self.run_mapping()
        self.assertEqual(result["assessments_written"], 2)
        for _, packet in self.client.calls:
            self.assertEqual([n["news_id"] for n in packet["news"]], ["news0"])

    def test_legacy_reviews_are_explicitly_waiting_not_assumed_globally_irrelevant(
        self,
    ):
        review = self.path.parent / "ai_reviews/test0.json"
        payload = json.loads(review.read_text())
        payload.pop("review_scope")
        atomic_json(review, payload)
        news, waiting = stored_news(self.path)
        self.assertEqual(set(news), {"news1"})
        self.assertEqual(waiting, ["news0"])

    def test_no_supported_findings_returns_insufficient_without_ai(self):
        for review in (self.path.parent / "ai_reviews").glob("*.json"):
            payload = json.loads(review.read_text())
            payload["deterministic_checks"]["grounding_passed"] = False
            atomic_json(review, payload)
        self.run_mapping()
        self.assertEqual(self.client.calls, [])
        self.assertTrue(
            all(
                a["record"]["assessment"]["relevance"] == "insufficient_evidence"
                for a in self.active()
            )
        )

    def test_invented_references_or_omitted_articles_do_not_enter_cache(self):
        for client in (StubMapper(invent=True), StubMapper(omit=True)):
            result = self.run_mapping(client=client)
            self.assertEqual(result["failed_batches"], 2)
            self.assertEqual(self.active(), [])
            self.assertEqual(len(client.calls), 2)  # One rejected first pass per skill.

    def test_skeptic_rejection_cannot_be_approved(self):
        self.run_mapping(client=StubMapper(supported=False))
        record = self.active()[0]["record"]
        with self.assertRaisesRegex(ValueError, "resolve flagged"):
            self.approve(fingerprint(record))

    def test_source_rejection_or_failed_refresh_hides_previous_approved_mapping(self):
        self.run_mapping()
        record = self.active()[0]["record"]
        self.approve(fingerprint(record))
        queue = json.loads(self.path.read_text())
        row = next(r for r in queue["items"] if r["discovery_id"] == record["news_id"])
        row["ai_review_error"] = "Fictional refresh failure"
        atomic_json(self.path, queue)
        self.assertFalse(any(a["approved"] for a in self.active()))

    def test_removed_skill_is_inactive_and_identical_reintroduction_reuses_cache(self):
        self.run_mapping()
        removed = self.catalog.taxonomy.skills.pop()
        self.assertEqual(len(self.active()), 2)
        self.catalog.taxonomy.skills.append(removed)
        self.client.calls.clear()
        self.assertEqual(self.run_mapping()["batches_attempted"], 0)
        self.assertEqual(len(self.active()), 4)

    def test_backlog_and_retry_are_visible_and_bounded(self):
        result = self.run_mapping(max_batches=1)
        self.assertEqual(result["pending_pairs"], 2)
        failed = self.run_mapping(client=StubMapper(fail=True), max_batches=1)
        self.assertEqual(failed["failed_batches"], 1)
        self.assertEqual(self.run_mapping(max_batches=1)["assessments_written"], 2)
        self.assertEqual(
            build_plan(
                state_path=self.path, catalog=self.catalog, model=self.client.model
            )[-1]["pending_pairs"],
            0,
        )

    def test_forced_skill_review_preserves_history_and_invalidates_old_approval(self):
        self.run_mapping()
        item = self.active()[0]
        digest = fingerprint(item["record"])
        self.approve(digest)
        skill_id = item["record"]["skill"]["skill_id"]
        result = run_assessments(
            state_path=self.path,
            catalog=self.catalog,
            client=StubMapper(relevance="insufficient_evidence"),
            skill_ids=[skill_id],
            force=True,
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(result["assessments_written"], 2)
        self.assertTrue(item["path"].exists())
        self.assertFalse(any(a["approved"] for a in self.active()))
        with self.assertRaisesRegex(ValueError, "context changed"):
            self.approve(digest)
        with self.assertRaisesRegex(ValueError, "explicit skill"):
            self.run_mapping(force=True)

    def test_tampered_assessment_and_escaping_source_reference_are_rejected(self):
        self.run_mapping()
        saved = self.active()[0]["path"]
        payload = json.loads(saved.read_text())
        payload["assessment"]["rationale"] = "Changed"
        atomic_json(saved, payload)
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            self.active()
        queue = json.loads(self.path.read_text())
        queue["items"][0]["ai_review_path"] = "../outside.json"
        atomic_json(self.path, queue)
        with self.assertRaisesRegex(ValueError, "escapes"):
            stored_news(self.path)


if __name__ == "__main__":
    unittest.main()
