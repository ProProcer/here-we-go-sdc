"""External-source refresh, grounding, persistence and safe cached fallback."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ingestion.selection import real_catalog
from src.intelligence.live_trends import LiveTrendService, TrendBatch, parse_articles
from src.profiles.intake import create_profile
from src.profiles.onet_matching import OnetMatcher

ROLE = "role:onet_15_2051_01"
NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)
QUOTE = "AI agents can create interactive visualizations from structured datasets"
TEXT = QUOTE + ". Analysts should check the generated views against original records and the intended question."


def feed(title="AI agents for data analysis", slug="visualization", text=TEXT):
    return f'''<rss><channel><item><title>{title}</title>
    <link>https://research.example.org/articles/{slug}</link>
    <pubDate>Thu, 22 Oct 2026 16:00:00 +0000</pubDate>
    <description><![CDATA[<p>{text}</p>]]></description></item></channel></rss>'''.encode()


class TestLiveTrends(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config = self.root / "feeds.json"
        config.write_text(json.dumps({"schema_version": "0.1.0", "lookback_days": 90,
            "max_items_per_feed": 10, "keywords": ["AI", "data"], "feeds": [{
            "feed_id": "test_research", "publisher": "TEST research", "url": "https://research.example.org/feed",
            "article_prefix": "https://research.example.org/articles/"}]}))
        self.fetcher = Mock(return_value=feed())
        self.clock = NOW
        self.service = LiveTrendService(self.catalog, path=self.root / "cache.json", seed=self.root / "absent.json",
            config_path=config, fetcher=self.fetcher, article_fetcher=Mock(return_value=TEXT),
            now=lambda: self.clock, analysis_interval=0)
        self.addCleanup(self.service.close)

    def client(self, **changes):
        article = next(a for a in self.service._candidates(ROLE) if len(a["source_text"]) >= 80)
        row = {"article_id": article["article_id"], "task_id": self.service.roles[ROLE].task_ids[0],
            "skill_ids": [self.service._skill_pool(ROLE)[0]],
            "what_changed": "The source describes AI-assisted visualization.",
            "role_relevance": "This may assist the occupation's reporting tasks, with human checks.",
            "learning_action": "Practice checking generated views against source records.", "evidence_quote": QUOTE}
        row.update(changes)
        assessments = [{"article_id": a["article_id"],
            "outcome": "connected" if a["article_id"] == article["article_id"] else "indirect_relevance",
            "reason": "This excerpt describes chart generation that may support reporting." if a["article_id"] == article["article_id"] else "The excerpt discusses analysis broadly, without a specific task example."}
            for a in self.service._candidates(ROLE) if len(a["source_text"]) >= 80]
        return Mock(generate=Mock(return_value=SimpleNamespace(value=TrendBatch(interpretations=[row], assessments=assessments),
            returned_model="test-model", provider="groq")))

    def test_publication_date_and_actual_fetch_time_remain_distinct(self):
        result = self.service.refresh()
        article = self.service.for_role(ROLE)["articles"][0]
        self.assertEqual(article["published_at"], "2026-10-22")
        self.assertEqual(article["fetched_at"], NOW.isoformat())
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["feeds"][0]["response_sha256"], __import__("hashlib").sha256(feed()).hexdigest())
        self.assertNotIn("source_text", article)

    def test_external_feed_changes_reach_the_same_store_without_duplicate_items(self):
        self.service.refresh()
        self.service.refresh()
        self.assertEqual(len(self.service.state["articles"]), 1)
        self.fetcher.return_value = feed("AI research on reporting", "reporting")
        self.clock += timedelta(hours=1)
        self.service.refresh()
        self.assertEqual(len(self.service.for_role(ROLE)["articles"]), 2)
        cached = json.loads(self.service.path.read_text())
        self.assertEqual(len(cached["articles"]), 2)

    def test_fetch_failure_preserves_last_good_sources_and_success_timestamp(self):
        self.service.refresh()
        before = json.loads(json.dumps(self.service.state["articles"]))
        self.clock += timedelta(days=100)
        self.fetcher.side_effect = OSError("offline")
        result = self.service.refresh()
        self.assertEqual(self.service.state["articles"], before)
        self.assertEqual(result["last_successful_at"], NOW.isoformat())
        self.assertEqual(result["last_attempted_at"], self.clock.isoformat())
        self.assertEqual(result["status"], "cached")

    def test_parser_rejects_untrusted_origins_future_dates_and_xml_entities(self):
        configured = self.service.config.feeds[0]
        body = feed().replace(b"research.example.org/articles/visualization", b"evil.example/articles/visualization")
        self.assertEqual(parse_articles(body, configured, self.service.config, NOW), [])
        future = feed().replace(b"22 Oct 2026", b"22 Oct 2027")
        self.assertEqual(parse_articles(future, configured, self.service.config, NOW), [])
        with self.assertRaises(ValueError):
            parse_articles(b'<!DOCTYPE x [<!ENTITY x "bad">]><rss/>', configured, self.service.config, NOW)

    def test_html_response_is_failed_refresh_and_preserves_last_good_sources(self):
        self.service.refresh()
        before = json.loads(json.dumps(self.service.state["articles"]))
        self.clock += timedelta(hours=1)
        self.fetcher.return_value = b"<html><body>Source maintenance</body></html>"
        status = self.service.refresh()
        self.assertEqual(status["status"], "cached")
        self.assertEqual(status["last_successful_at"], NOW.isoformat())
        self.assertEqual(self.service.state["articles"], before)

    def test_supported_interpretation_is_labelled_unreviewed_and_does_not_change_fit(self):
        matcher = OnetMatcher(self.catalog)
        profile = create_profile("synthetic:trend_fit", ["Python", "SQL"], catalog=self.catalog)
        before = matcher.match_role(profile, ROLE).fit_score
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        result = self.service.for_role(ROLE)
        self.assertEqual(result["analysis_status"], "ready")
        self.assertEqual(result["analysis_provider"], "groq")
        self.assertIn("not human reviewed", result["interpretations"][0]["label"])
        self.assertFalse(result["changes_personal_fit"])
        self.assertEqual(matcher.match_role(profile, ROLE).fit_score, before)

    def test_invalid_reference_or_invented_quote_never_becomes_a_card(self):
        self.service.refresh()
        for change in ({"article_id": "invented"}, {"task_id": "task:invented"},
                {"skill_ids": ["skill:invented"]}, {"what_changed": "AI will automate 90% of these jobs"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.analyze_role(ROLE, self.client(**change))
        self.assertFalse(self.service.state["analyses"])

    def test_last_valid_analysis_survives_failed_new_interpretation(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        good = json.loads(json.dumps(self.service.state["analyses"]))
        with self.assertRaises(ValueError):
            self.service.analyze_role(ROLE, self.client(skill_ids=["skill:invented"]))
        self.assertEqual(self.service.state["analyses"], good)
        self.assertEqual(len(self.service.for_role(ROLE)["interpretations"]), 1)

    def test_changed_sources_keep_the_previous_assessment_with_original_citations(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        self.fetcher.return_value = feed(text="AI agents can help summarize reports. New evidence changes the previously fetched article and its content fingerprint.")
        self.clock += timedelta(hours=1)
        self.service.refresh()
        result = self.service.for_role(ROLE)
        self.assertEqual(len(result["interpretations"]), 1)
        self.assertTrue(result["analysis_stale"])
        self.assertEqual(result["source_review"]["assessed_count"], 1)
        source = result["interpretations"][0]["source"]
        self.assertEqual(source["fetched_at"], NOW.isoformat())
        self.assertNotIn("source_text", source)
        self.assertEqual(result["interpretations"][0]["evidence_quote"], QUOTE)

    def test_snapshot_contains_short_supporting_excerpts_not_full_article_bodies(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        snapshot = self.root / "seed.json"
        self.service.export_seed(snapshot)
        value = json.loads(snapshot.read_text())
        self.assertEqual(value["articles"][0]["source_text"], QUOTE)
        self.assertNotIn("Analysts should check", snapshot.read_text())
        restored = LiveTrendService(self.catalog, path=self.root / "missing-cache.json", seed=snapshot,
            config_path=self.root / "feeds.json", now=lambda: NOW)
        self.addCleanup(restored.close)
        self.assertEqual(restored.for_role(ROLE)["analysis_status"], "ready")

    def test_duplicate_article_interpretations_are_rejected(self):
        self.service.refresh()
        client = self.client()
        row = client.generate.return_value.value.interpretations[0]
        client.generate.return_value.value = TrendBatch(interpretations=[row, row], assessments=client.generate.return_value.value.assessments)
        with self.assertRaises(ValueError):
            self.service.analyze_role(ROLE, client)

    def test_invalid_quote_withholds_card_without_discarding_completed_assessment(self):
        self.service.refresh()
        bad = self.client(evidence_quote="An invented claim about future careers")
        good = self.client()
        bad.generate.side_effect = [bad.generate.return_value, good.generate.return_value]
        rows = self.service.analyze_role(ROLE, bad)
        self.assertEqual(bad.generate.call_count, 1)
        self.assertEqual(rows, [])
        result = self.service.for_role(ROLE)
        self.assertEqual(result["analysis_status"], "ready")
        self.assertEqual(result["source_review"]["assessed_count"], 1)
        self.assertEqual(result["source_review"]["connection_count"], 0)
        item = result["source_review"]["articles"][0]
        self.assertEqual(item["outcome"], "connection_not_verified")
        self.assertEqual(item["reason_origin"], "validation")
        self.assertNotIn("An invented claim", json.dumps(result))

    def test_assessment_coverage_distinguishes_unselected_and_unreadable_sources(self):
        entries = [feed(slug=f"visualization-{n}").split(b"<channel>")[1].split(b"</channel>")[0] for n in range(8)]
        self.fetcher.return_value = b"<rss><channel>" + b"".join(entries) + b"</channel></rss>"
        self.service.refresh()
        self.service._candidates = Mock(return_value=self.service.state["articles"][:6])
        unreadable = self.service._candidates(ROLE)[1]
        unreadable["source_text"] = "AI"
        client = self.client()
        self.service.analyze_role(ROLE, client)
        review = self.service.for_role(ROLE)["source_review"]
        sent = client.generate.call_args.args[1]["sources"]
        self.assertEqual(review["stored_count"], 8)
        self.assertEqual(review["selected_count"], 6)
        self.assertEqual(review["assessed_count"], 5)
        self.assertEqual(review["assessed_count"], len(sent))
        self.assertEqual(review["connection_count"], 1)
        rows = review["articles"]
        self.assertEqual(sum(r["outcome"] == "not_selected" for r in rows), 2)
        self.assertEqual(sum(r["outcome"] == "insufficient_text" for r in rows), 1)
        for r in rows:
            self.assertEqual(r["assessed_by_ai"], r["source"]["article_id"] in {a["article_id"] for a in sent})
            self.assertNotIn("source_text", r["source"])

    def test_missing_duplicate_unknown_and_inconsistent_assessments_are_rejected(self):
        self.service.refresh()
        for mutation in ("missing", "duplicate", "unknown", "inconsistent", "blank"):
            client = self.client()
            batch = client.generate.return_value.value.model_dump()
            assessment = batch["assessments"][0]
            if mutation == "missing":
                batch["assessments"] = []
            elif mutation == "duplicate":
                batch["assessments"].append(dict(assessment))
            elif mutation == "unknown":
                assessment["article_id"] = "invented"
            elif mutation == "inconsistent":
                assessment["outcome"] = "indirect_relevance"
            else:
                assessment["reason"] = "   "
            client.generate.return_value.value = TrendBatch.model_validate(batch)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.service.analyze_role(ROLE, client)
        self.assertFalse(self.service.state["analyses"])

    def test_old_cache_keeps_cards_without_inventing_omission_reasons(self):
        self.service.refresh()
        self.fetcher.return_value = feed(slug="another-article")
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        del self.service.state["analyses"][ROLE]["assessments"]
        del self.service.state["analyses"][ROLE]["assessed_article_ids"]
        self.service.ensure_analysis = Mock()
        result = self.service.for_role(ROLE, analyze=True)
        self.service.ensure_analysis.assert_called_once_with(ROLE)
        self.assertEqual(len(result["interpretations"]), 1)
        self.assertTrue(result["source_review"]["legacy_analysis"])
        self.assertIsNone(result["source_review"]["assessed_count"])
        omitted = [a for a in result["source_review"]["articles"] if not a["assessed_by_ai"]]
        self.assertEqual(len(omitted), 1)
        self.assertEqual(omitted[0]["outcome"], "not_recorded")

    def test_completed_assessment_can_explain_articles_without_any_connections(self):
        self.service.refresh()
        client = self.client()
        batch = client.generate.return_value.value.model_dump()
        batch["interpretations"] = []
        batch["assessments"][0].update(outcome="insufficient_detail",
            reason="The excerpt describes chart generation but does not establish this occupation's task implications.")
        client.generate.return_value.value = TrendBatch.model_validate(batch)
        self.service.analyze_role(ROLE, client)
        result = self.service.for_role(ROLE)
        self.assertEqual(result["analysis_status"], "ready")
        self.assertEqual(result["source_review"]["assessed_count"], 1)
        self.assertEqual(result["source_review"]["connection_count"], 0)
        self.assertEqual(result["source_review"]["articles"][0]["outcome"], "insufficient_detail")

    def test_assessment_reasons_survive_cache_reload_and_remain_during_updates(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        stored = json.loads(self.service.path.read_text())
        self.assertIn("assessments", stored["analyses"][ROLE])
        restored = LiveTrendService(self.catalog, path=self.service.path, seed=self.root / "none.json",
            config_path=self.root / "feeds.json", now=lambda: NOW)
        self.addCleanup(restored.close)
        self.assertEqual(restored.for_role(ROLE)["source_review"]["assessed_count"], 1)
        self.fetcher.return_value = feed(text=TEXT + " AI research content update.")
        self.service.refresh()
        review = self.service.for_role(ROLE)["source_review"]
        self.assertEqual(review["assessed_count"], 1)
        self.assertEqual(review["articles"][0]["outcome"], "connected")

    def test_unselected_article_changes_do_not_invalidate_completed_assessment(self):
        entries = [feed(slug=f"visualization-{n}").split(b"<channel>")[1].split(b"</channel>")[0] for n in range(8)]
        self.fetcher.return_value = b"<rss><channel>" + b"".join(entries) + b"</channel></rss>"
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        before = self.service._key(ROLE)
        unselected = self.service.state["articles"][-1]
        unselected["source_text"] = "AI astronomy research on distant stars."
        self.assertNotIn(unselected["article_id"], {a["article_id"] for a in self.service._candidates(ROLE)})
        self.assertEqual(self.service._key(ROLE), before)
        self.assertFalse(self.service.for_role(ROLE)["analysis_stale"])

    def test_fetch_dates_and_text_beyond_supplied_excerpt_do_not_reset_assessment(self):
        self.service.refresh()
        article = self.service.state["articles"][0]
        article["source_text"] = TEXT.ljust(1500)
        self.service.analyze_role(ROLE, self.client())
        before = self.service._key(ROLE)
        article["source_text"] += "Changed text outside the excerpt given to the model."
        article["fetched_at"] = (NOW + timedelta(hours=1)).isoformat()
        self.assertEqual(self.service._key(ROLE), before)
        result = self.service.for_role(ROLE)
        self.assertFalse(result["analysis_stale"])
        self.assertEqual(result["interpretations"][0]["source"]["fetched_at"], NOW.isoformat())

    def test_failed_background_update_keeps_completed_result_and_allows_retry(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        self.fetcher.return_value = feed(text=TEXT + " Source update.")
        self.service.refresh()
        self.service.analyze_role = Mock(side_effect=RuntimeError("provider unavailable"))
        with patch("src.intelligence.live_trends.model_configuration", return_value=("test", [])):
            self.service.ensure_analysis(ROLE)
        self.service.ai_pool.submit(lambda: None).result(timeout=5)
        result = self.service.for_role(ROLE)
        self.assertEqual(result["analysis_status"], "failed")
        self.assertTrue(result["analysis_stale"])
        self.assertEqual(result["source_review"]["assessed_count"], 1)
        self.assertEqual(len(result["interpretations"]), 1)
        self.assertNotIn(ROLE, self.service.pending)
        self.assertIn(ROLE, self.service.retry_at)

    def test_long_rate_limit_wait_ends_in_retryable_failure_instead_of_pending(self):
        import time
        self.service.refresh()
        self.service.analysis_interval = 65
        self.service.last_analysis = time.monotonic()
        self.service.analyze_role = Mock()
        with patch("src.intelligence.live_trends.model_configuration", return_value=("test", [])):
            self.service.ensure_analysis(ROLE)
        self.service.ai_pool.submit(lambda: None).result(timeout=5)
        self.assertEqual(self.service.for_role(ROLE)["analysis_status"], "failed")
        self.assertNotIn(ROLE, self.service.pending)
        self.service.analyze_role.assert_not_called()

    def test_snapshot_export_redacts_archived_source_bodies_too(self):
        self.service.refresh()
        self.service.analyze_role(ROLE, self.client())
        snapshot = self.root / "seed.json"
        self.service.export_seed(snapshot)
        data = json.loads(snapshot.read_text())
        self.assertEqual(data["analyses"][ROLE]["source_articles"][0]["source_text"], QUOTE)
        self.assertNotIn("Analysts should check", snapshot.read_text())
