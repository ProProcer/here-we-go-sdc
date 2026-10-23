"""Complete alternative futures, provenance, caching and numeric-policy separation."""

import copy
import json
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ingestion.selection import real_catalog
from src.intelligence.futures import FutureBatch, FutureService, MODES
from src.profiles.intake import create_profile
from src.profiles.onet_matching import OnetMatcher

ROLE = "role:onet_13_1161_01"


class TestFutureScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 10, 24, tzinfo=UTC)
        self.path = Path(self.temp.name) / "stories.json"
        self.service = FutureService(self.catalog, path=self.path, now=lambda: self.now)
        self.addCleanup(self.service.close)

    def client(self, mutate=None):
        rows = self.service._default_stories(ROLE, self.service._emphasis(self.service._policy(ROLE)))
        if mutate:
            mutate(rows)
        return Mock(generate=Mock(return_value=SimpleNamespace(value=FutureBatch(stories=rows))))

    def test_two_complete_career_illustrations_without_ai_or_network(self):
        with patch("src.intelligence.models.ModelClient.from_environment", side_effect=AssertionError("Offline path must not call AI")):
            result = self.service.for_role(ROLE)
        self.assertEqual(result["origin"], "application_authored")
        self.assertEqual([r["scenario_id"] for r in result["stories"]], list(MODES))
        self.assertNotEqual(result["stories"][0]["narrative"], result["stories"][1]["narrative"])
        self.assertIn("Search Marketing Strategists", result["stories"][0]["narrative"])
        self.assertEqual(result["sources"], [])
        self.assertTrue(result["shared_preparation"])
        self.assertIn("Not forecasts", result["label"])
        for story in result["stories"]:
            self.assertGreaterEqual(len(story["uncertainties"]), 2)
            self.assertTrue(story["assumptions"])
            self.assertTrue(story["task_changes"][0]["task_label"])

    def test_comparison_matches_engine_and_never_changes_fit_or_catalog(self):
        catalog_before = self.catalog.model_dump_json()
        profile = create_profile("synthetic:futures", ["Python", "SQL"], catalog=self.catalog)
        matcher = OnetMatcher(self.catalog)
        fit = matcher.match_role(profile, ROLE).fit_score
        result = self.service.for_role(ROLE)
        policies = self.service._policy(ROLE)
        for row in result["skill_comparison"]:
            for name, mode in (("baseline", "baseline"), ("moderate", MODES[0]), ("rapid", MODES[1])):
                value = next(r.adjusted_priority for r in policies[mode].skill_priorities if r.skill_id == row["skill_id"])
                self.assertEqual(row[name], value)
        self.service.generate(ROLE, self.client())
        self.assertEqual(matcher.match_role(profile, ROLE).fit_score, fit)
        self.assertEqual(self.catalog.model_dump_json(), catalog_before)
        self.assertFalse(result["changes_personal_fit"])

    def test_valid_ai_pair_is_cached_and_reloads_with_same_source_dates(self):
        article = {"article_id": "research-one", "title": "AI assistance for information workflows", "source_url": "https://example.org/research", "publisher": "TEST source", "published_at": "2026-10-20", "fetched_at": "2026-10-23T12:00:00+00:00", "source_text": "Research on tools that help people prepare and check information workflows. " * 4}
        self.service.trends = SimpleNamespace(lock=threading.RLock(), _candidates=lambda role: [article])
        client = self.client(lambda rows: rows[0].update(source_ids=[article["article_id"]]))
        self.service.generate(ROLE, client)
        restored = FutureService(self.catalog, path=self.path, now=lambda: self.now)
        self.addCleanup(restored.close)
        result = restored.for_role(ROLE)
        self.assertEqual(result["origin"], "ai_generated")
        self.assertEqual(result["sources"][0]["published_at"], "2026-10-20")
        self.assertNotIn("source_text", json.dumps(result))
        client.generate.assert_called_once()
        self.assertEqual(len(result["stories"]), 2)

    def test_bad_generation_never_replaces_last_complete_pair(self):
        self.service.generate(ROLE, self.client())
        before = self.path.read_bytes()
        mutations = [lambda rows: rows[1].update(scenario_id=MODES[0]),
            lambda rows: rows[0].update(practice_skill_id="invented"),
            lambda rows: rows[0].update(source_ids=["invented"]),
            lambda rows: rows[0]["task_changes"][0].update(task_id="invented"),
            lambda rows: rows[0].update(narrative="AI will replace 80% of jobs."),
            lambda rows: rows[0].update(narrative="This outcome is guaranteed."),
            lambda rows: rows[0].update(narrative=rows[1]["narrative"])]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.service.generate(ROLE, self.client(mutate))
            self.assertEqual(self.path.read_bytes(), before)

    def test_background_failure_leaves_complete_fallback_instead_of_pending_page(self):
        self.service.generate = Mock(side_effect=RuntimeError("provider unavailable"))
        with patch("src.intelligence.futures.model_configuration", return_value=("test", [])):
            self.service.ensure(ROLE)
        self.service.pool.submit(lambda: None).result(timeout=5)
        result = self.service.for_role(ROLE)
        self.assertFalse(result["updating"])
        self.assertTrue(result["update_unavailable"])
        self.assertEqual(len(result["stories"]), 2)
        self.assertEqual(result["origin"], "application_authored")

    def test_yesterdays_stories_remain_visible_during_refresh(self):
        self.service.generate(ROLE, self.client())
        self.now += timedelta(days=1)
        self.service.ensure = Mock()
        result = self.service.for_role(ROLE, enhance=True)
        self.service.ensure.assert_called_once_with(ROLE)
        self.assertEqual(result["origin"], "ai_generated")
        self.assertTrue(result["generated_at"].startswith("2026-10-24"))
        self.assertEqual(len(result["stories"]), 2)

    def test_examples_for_distinct_occupations_use_their_own_tasks(self):
        first = self.service.for_role(ROLE)
        second = self.service.for_role("role:onet_15_2051_01")
        self.assertNotEqual(first["stories"][0]["narrative"], second["stories"][0]["narrative"])
        for story in second["stories"]:
            for task in story["task_changes"]:
                self.assertIn(task["task_id"], self.service.roles[second["role_id"]].task_ids)
