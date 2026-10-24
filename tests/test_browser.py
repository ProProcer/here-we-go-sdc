"""Optional browser smoke test. Set RUN_BROWSER_TESTS=1; see README for setup."""

import os
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

import httpx


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "Opt-in browser test")
class TestBrowserJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen([
            sys.executable, "-m", "src.main"],
            env={**os.environ, "PORT": str(port), "WEB_CONCURRENCY": "4", "TREND_AUTO_REFRESH": "0", "GROQ_API": "", "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "RUNPOD_API_KEY": "", "RUNPOD_ENDPOINT_ID": ""},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.stop_server)
        for _ in range(150):
            try:
                if httpx.get(cls.url + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Browser test server did not start")
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        channel = os.getenv("BROWSER_CHANNEL")
        cls.browser = cls.playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
        cls.addClassCleanup(cls.browser.close)

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()

    def screenshot(self, page, name):
        directory = os.getenv("BROWSER_ARTIFACT_DIR")
        if directory:
            destination = Path(directory)
            destination.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(destination / (name + ".png")), full_page=True)

    def choose_roadmap_option(self, page, control_id, value):
        labels = {
            "baseline": "Baseline · current requirements",
            "moderate_ai_change": "Moderate AI adoption",
            "rapid_ai_change": "Rapid AI adoption",
        }
        label = labels[value] if control_id == "scenario-select" else f"{value} hours / week"
        page.locator(f"#{control_id}").click()
        page.locator(f"#{control_id}-options").get_by_role("option", name=label, exact=True).click()

    def test_live_trends_show_source_dates_labels_and_refresh_without_changing_fit(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        article = {"article_id": "test", "title": "TEST research on generated charts", "publisher": "TEST publisher",
            "source_url": "https://example.org/research/charts", "published_at": "2026-10-22",
            "fetched_at": "2026-10-23T12:00:00+00:00", "content_scope": "feed_excerpt"}
        payload = {"articles": [article], "interpretations": [{"article_id": "test", "task_label": "TEST reporting task",
            "what_changed": "TEST AI-assisted chart finding", "role_relevance": "May assist reporting with human checks.",
            "learning_action": "Practice validating chart outputs.", "evidence_quote": "AI can help create chart views", "source": article,
            "skills": [{"skill_id": "skill:python", "label": "Python"}]}],
            "refresh": {"status": "fresh", "last_attempted_at": "2026-10-23T12:00:00+00:00", "last_successful_at": "2026-10-23T12:00:00+00:00", "article_count": 1, "feeds": []},
            "analysis_status": "ready", "analyzed_at": "2026-10-23T12:00:00+00:00", "analysis_provider": "test", "analysis_error": None, "scope": "Test fixture only."}
        indirect = {**article, "article_id": "indirect", "title": "TEST broad research", "source_url": "https://example.org/research/broad"}
        unselected = {**article, "article_id": "unselected", "title": "TEST unselected research", "source_url": "https://example.org/research/unselected"}
        thin = {**article, "article_id": "thin", "title": "TEST short excerpt", "source_url": "https://example.org/research/short"}
        payload["interpretations"].append({**payload["interpretations"][0],
            "article_id": "indirect", "source": indirect,
            "task_label": "HIDDEN indirect task", "what_changed": "HIDDEN indirect finding"})
        payload["refresh"]["article_count"] = 4
        payload["source_review"] = {"stored_count": 4, "selected_count": 3, "assessed_count": 2,
            "connection_count": 1, "assessment_limit": 6, "connection_limit": 3,
            "legacy_analysis": False, "updating": False, "articles": [
                {"source": article, "outcome": "connected", "reason": "Chart generation may assist reporting.", "assessed_by_ai": True},
                {"source": indirect, "outcome": "indirect_relevance", "reason": "This excerpt describes general AI research without a specific reporting application.", "assessed_by_ai": True},
                {"source": unselected, "outcome": "not_selected", "reason": "Not sent to the AI: outside the selected articles. This does not mean it is unrelated.", "assessed_by_ai": False},
                {"source": thin, "outcome": "insufficient_text", "reason": "Not sent to the AI: too little source text was available.", "assessed_by_ai": False}]}
        first_fetch = []
        def trends(route):
            if not first_fetch:
                first_fetch.append(route)
                return
            if route.request.method == "POST":
                payload["refresh"]["last_successful_at"] = "2026-10-23T13:00:00+00:00"
            route.fulfill(json=payload)
        page.route("**/api/v2/roles/*/trends**", trends)
        page.goto(self.url)
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#target-search").fill("Business Intelligence Analysts")
        page.get_by_role("option", name="Business Intelligence Analysts", exact=True).click()
        page.locator("#find-matches").click()
        page.get_by_role("button", name="Explore Business Intelligence Analysts", exact=True).click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        fit = page.locator("#role-fit strong").inner_text()
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#news-loading .news-spinner")).to_be_visible()
        transform = page.locator("#news-loading .news-spinner").evaluate("el => getComputedStyle(el).transform")
        page.wait_for_timeout(150)
        self.assertNotEqual(transform, page.locator("#news-loading .news-spinner").evaluate("el => getComputedStyle(el).transform"))
        self.assertEqual(len(first_fetch), 1)
        first_fetch[0].fulfill(json=payload)
        expect(page.locator("#trend-interpretations .trend-card")).to_have_count(1)
        expect(page.locator(".news-spinner")).to_have_count(0)
        expect(page.locator("#outlook")).not_to_contain_text("HIDDEN indirect")
        expect(page.locator("#live-trend-status")).to_contain_text("12:00:00 UTC")
        expect(page.locator("#trend-interpretations")).to_contain_text("not human reviewed")
        page.get_by_text("Explore finding & evidence", exact=True).click()
        expect(page.locator(".trend-citation")).to_be_visible()
        expect(page.locator(".trend-citation")).to_contain_text("Published 2026-10-22")
        expect(page.locator(".trend-implications")).to_contain_text("What it could mean for this career")
        expect(page.locator(".trend-implications")).to_contain_text("Practice validating chart outputs.")
        page.get_by_text("Supporting source", exact=True).click()
        expect(page.locator("#trend-interpretations")).to_contain_text("Published 2026-10-22")
        expect(page.get_by_role("link", name="Read original research")).to_have_attribute("href", article["source_url"])
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        expect(page.locator("#live-trend-status")).to_contain_text("13:00:00 UTC")
        expect(page.locator("#trend-interpretations")).to_contain_text("Published 2026-10-22")
        page.locator("#back-to-role").click()
        expect(page.locator("#role-fit strong")).to_have_text(fit)
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#trend-review-summary")).to_contain_text("4 stored · 3 selected for this career · 2 assessed by AI · 1 career connection shown")
        page.locator("#trend-source-review > summary").click()
        expect(page.locator("#trend-source-review .help-mark")).to_have_text("?")
        self.assertEqual(page.locator("#trend-source-review > summary").evaluate("el => getComputedStyle(el).borderWidth"), "0px")
        self.assertTrue(page.evaluate("Boolean(document.querySelector('#build-roadmap').compareDocumentPosition(document.querySelector('#trend-source-review')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
        expect(page.locator("#live-source-list .source-card")).to_have_count(1)
        expect(page.locator("#live-source-list")).to_contain_text("Career connection shown")
        for hidden_title in ("TEST broad research", "TEST unselected research", "TEST short excerpt"):
            expect(page.locator("#outlook")).not_to_contain_text(hidden_title)
        expect(page.locator("#outlook")).not_to_contain_text("Indirect relevance")
        expect(page.locator("#outlook")).not_to_contain_text("Not selected for AI assessment")
        page.locator("#trend-review-summary").scroll_into_view_if_needed()
        self.screenshot(page, "trend-source-context")
        complete = json.loads(json.dumps(payload))
        payload["interpretations"] = []
        payload["analyzed_at"] = None
        payload["analysis_status"] = "queued"
        payload["source_review"].update(assessed_count=0, connection_count=0, updating=True)
        for item in payload["source_review"]["articles"]:
            item.update(outcome="not_assessed", assessed_by_ai=False)
        expect(page.locator("#trend-analysis-notice")).to_contain_text("Finding research relevant", timeout=10000)
        expect(page.locator("#trend-analysis-notice .news-spinner")).to_be_visible()
        expect(page.locator("#trend-review-summary")).to_have_count(0)
        expect(page.locator("#live-source-list")).to_have_count(0)
        expect(page.locator("#live-trends")).not_to_contain_text("AI assessment pending")
        payload["analysis_status"] = "failed"
        payload["analysis_error"] = "Provider unavailable"
        payload["source_review"]["updating"] = False
        expect(page.locator("#retry-trend-analysis")).to_be_visible(timeout=10000)
        expect(page.locator(".news-spinner")).to_have_count(0)
        expect(page.locator("#trend-analysis-notice")).to_contain_text("does not mean that no articles are relevant")
        payload.clear()
        payload.update(json.loads(json.dumps(complete)))
        page.locator("#retry-trend-analysis").click()
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        payload["analysis_status"] = "updating"
        payload["analysis_stale"] = True
        payload["source_review"]["updating"] = True
        expect(page.locator("#trend-analysis-notice")).to_contain_text("Updating career research", timeout=10000)
        expect(page.locator("#trend-analysis-notice .news-spinner")).to_be_visible()
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        expect(page.locator("#trend-interpretations")).to_contain_text("TEST AI-assisted chart finding")
        payload["analysis_status"] = "failed"
        payload["analysis_error"] = "Provider unavailable"
        payload["source_review"]["updating"] = False
        expect(page.locator("#trend-analysis-notice")).to_contain_text("Showing your last completed assessment", timeout=10000)
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        payload.clear()
        payload.update(json.loads(json.dumps(complete)))
        payload["interpretations"] = []
        payload["source_review"]["connection_count"] = 0
        payload["source_review"]["articles"][0]["outcome"] = "no_clear_connection"
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        expect(page.get_by_text("No career connections to show yet", exact=True)).to_be_visible()
        expect(page.locator(".news-spinner")).to_have_count(0)
        payload.clear()
        payload.update(json.loads(json.dumps(complete)))
        # A new frontend talking to an older server must explain how to recover.
        payload.pop("source_review")
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        expect(page.locator("#trend-version-notice")).to_contain_text("Restart the app server")

    def test_late_refresh_cannot_replace_another_careers_trends(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        held = []
        def payload(count):
            return {"articles": [], "interpretations": [],
                "refresh": {"status": "fresh", "last_successful_at": "2026-10-23T12:00:00+00:00", "article_count": count, "feeds": []},
                "source_review": {"stored_count": count, "selected_count": 0, "assessed_count": 0, "connection_count": 0, "assessment_limit": 6, "connection_limit": 3, "legacy_analysis": False, "updating": False, "articles": []},
                "analysis_status": "no_sources", "analyzed_at": None, "analysis_provider": None, "analysis_error": None, "scope": "TEST source response"}
        def trends(route):
            if route.request.method == "POST":
                held.append(route)
            else:
                route.fulfill(json=payload(111 if "onet_15_2051_01/" in route.request.url else 222))
        page.route("**/api/v2/roles/*/trends**", trends)
        page.goto(self.url)
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#target-search").fill("Business Intelligence Analysts")
        page.get_by_role("option", name="Business Intelligence Analysts", exact=True).click()
        page.locator("#find-matches").click()
        page.get_by_role("button", name="Explore Business Intelligence Analysts", exact=True).click()
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#live-trend-status")).to_contain_text("111 stored")
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        page.locator("#back-to-role").click()
        page.locator("#back-to-careers").click()
        page.locator('[data-role-id]:not([data-role-id="role:onet_15_2051_01"])').first.click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#live-trend-status")).to_contain_text("222 stored")
        self.assertEqual(len(held), 1)
        held[0].fulfill(json=payload(999))
        page.wait_for_timeout(100)
        expect(page.get_by_role("button", name="Refresh trends", exact=True)).to_be_enabled()
        expect(page.locator("#live-trend-status")).to_contain_text("222 stored")
        expect(page.locator("#live-trend-status")).not_to_contain_text("999")

    def test_search_marketing_sdg_and_scenario_control_spacing(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#target-search").fill("Search Marketing Strategists")
        page.get_by_role("option", name="Search Marketing Strategists", exact=True).click()
        page.locator("#find-matches").click()
        page.get_by_role("button", name="Explore Search Marketing Strategists", exact=True).click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        expect(page.locator("#role-sdg-connections")).to_contain_text("Target 8.2")
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        fit = page.locator("#detail-fit").inner_text()
        expect(page.locator("#scenario-select")).to_have_text("Baseline · current requirements")
        expect(page.locator(".future-story")).to_have_count(0)
        page.locator("#open-sdg").click()
        expect(page.locator("#sdg")).to_be_visible()
        expect(page.locator("#role-sdg-connections")).to_contain_text("Decent Work and Economic Growth")
        page.locator("#sdg-skill-filter").select_option("confirmed")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Python")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("In your profile")
        page.locator("#sdg-skill-filter").select_option("all")
        page.locator("#sdg-skill-search").fill("Critical Thinking")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("SDG 4")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("SDG 8")
        page.locator("#sdg-skill-search").fill("")
        page.locator("#back-to-roadmap").click()
        self.choose_roadmap_option(page, "scenario-select", "rapid_ai_change")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator(".future-story")).to_have_count(1)
        page.get_by_text("Compare all three scenarios", exact=True).click()
        buttons = page.locator(".future-actions button")
        expect(buttons).to_have_count(2)
        first, second = buttons.nth(0).bounding_box(), buttons.nth(1).bounding_box()
        gap = second["x"] - first["x"] - first["width"] if abs(second["y"] - first["y"]) < 5 else second["y"] - first["y"] - first["height"]
        self.assertGreaterEqual(gap, 12)
        buttons.first.click()
        expect(page.locator("#future-skill-comparison tbody tr")).to_have_count(10)
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        page.locator("#open-sdg").click()
        page.locator("#sdg-impact").scroll_into_view_if_needed()
        self.screenshot(page, "sdg-career-and-skills")

    def test_python_only_levels_change_best_matching_job(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        titles = []
        for index, level in enumerate(("Beginner", "Intermediate", "Advanced")):
            if index:
                page.locator('[data-screen="review"]').click()
            page.locator(".cv-evidence summary").first.click()
            page.locator("#level-0").click()
            page.get_by_role("option", name=level, exact=True).click()
            page.locator(".cv-evidence summary").first.click()
            page.locator("#confirm-all").check()
            page.locator("#review-next").click()
            with page.expect_response("**/api/v2/matches?*", timeout=30000) as response:
                page.locator("#find-matches").click()
            expect(page.locator("#explore")).to_be_visible(timeout=30000)
            expect(page.locator("#busy")).to_be_hidden(timeout=30000)
            target = response.value.json()["matches"][0]["score_breakdown"]["alignment_contributions"][0]
            self.assertEqual(target["required_level_label"], level.lower())
            self.assertEqual(target["requirement_basis"], "estimated_from_general")
            titles.append(page.locator("#featured-match h2").inner_text())
        self.assertEqual(len(set(titles)), 3, titles)

    def test_sample_cv_recommends_data_roles_with_score_explanation(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        page.locator("#sample").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#find-matches").click()
        expect(page.locator("#featured-match h2")).to_have_text("Data Scientists", timeout=30000)
        expect(page.locator("#match-rows")).to_contain_text("Business Intelligence Analysts")
        page.get_by_role("button", name="Explore Data Scientists", exact=True).first.click()
        expect(page.locator("#score-breakdown")).to_contain_text("CV skill alignment", timeout=30000)
        expect(page.locator("#role")).to_contain_text("65.0% CV skill alignment and 35.0% general requirement fulfilment")
        page.get_by_text("See score breakdown & proficiency", exact=True).click()
        page.get_by_text("Your proficiency vs job requirements", exact=True).click()
        expect(page.locator("#proficiency-comparison")).to_contain_text("Job requirement:")
        expect(page.locator("#proficiency-comparison")).to_contain_text("Your estimate: unknown")
        page.get_by_text("How your CV skills affect this score", exact=True).click()
        expect(page.locator("#role")).to_contain_text("Tableau")

    def test_career_pages_navigation_and_mobile_readability(self):
        from playwright.sync_api import expect

        for width, height in ((1440, 1080), (390, 844)):
            with self.subTest(width=width):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                trend_requests = []

                def trends(route):
                    trend_requests.append(route.request.url)
                    route.fulfill(json={
                        "articles": [], "interpretations": [], "analysis_status": "no_sources",
                        "analyzed_at": None, "analysis_provider": None, "analysis_error": None,
                        "refresh": {"status": "cached", "last_successful_at": None, "article_count": 0, "feeds": []},
                        "scope": "Test fixture only.",
                    })

                page.route("**/api/v2/roles/*/trends**", trends)
                page.goto(self.url)
                page.locator("#sample").click()
                page.locator("#confirm-all").check()
                page.locator("#review-next").click()
                page.locator("#find-matches").click()
                page.locator("[data-role-id]").first.click()
                expect(page.locator("#role")).to_be_visible(timeout=30000)
                expect(page.locator("#explore")).to_have_count(0)
                expect(page.locator("dialog")).to_have_count(0)
                expect(page).to_have_url(self.url + "/#role")
                expect(page.locator("#role h1")).to_be_focused()
                page.locator(".skip-link").focus()
                page.locator(".skip-link").click()
                expect(page.locator("#main")).to_be_focused()
                expect(page).to_have_url(self.url + "/#role")
                expect(page.locator('[data-screen="explore"]')).to_have_attribute("aria-current", "step")
                expect(page.locator("#score-breakdown")).to_be_hidden()
                expect(page.get_by_role("heading", name="Full occupation description", exact=True)).to_be_visible()
                expect(page.locator("#role-description")).to_be_visible()
                expect(page.locator(".role-overview details")).to_have_count(0)
                expect(page.locator(".career-page-steps")).to_have_count(0)
                matching_panel = page.locator("#matched-skills")
                gap_panel = page.locator("#skills-to-explore")
                card = page.locator(".role-skill-card").first
                card_height = card.bounding_box()["height"]
                panel_height = matching_panel.bounding_box()["height"]
                matching_panel.locator("summary").first.click()
                self.assertAlmostEqual(card.bounding_box()["height"], card_height, delta=1)
                self.assertAlmostEqual(matching_panel.bounding_box()["height"], panel_height, delta=1)
                self.assertEqual(gap_panel.evaluate("el => getComputedStyle(el).overflowY"), "auto")
                self.assertTrue(gap_panel.evaluate("el => el.scrollHeight > el.clientHeight"))
                gap_panel.focus()
                gap_panel.press("End")
                page.wait_for_function("() => document.querySelector('#skills-to-explore').scrollTop > 0")
                self.assertGreater(gap_panel.evaluate("el => el.scrollTop"), 0)
                help_control = gap_panel.locator(".help-disclosure > summary")
                self.assertEqual(help_control.evaluate("el => getComputedStyle(el).borderWidth"), "0px")
                help_control.click()
                self.assertAlmostEqual(page.locator(".role-skill-card").nth(1).bounding_box()["height"], card_height, delta=1)
                self.assertEqual(trend_requests, [])
                fit = page.locator("#role-fit strong").inner_text()
                self.screenshot(page, f"role-page-{width}")
                page.get_by_text("Choose software", exact=True).click()
                software = page.locator("#software-options input").first
                if software.count():
                    software.check()
                page.locator("#open-ai-outlook").click()
                expect(page.locator("#outlook")).to_be_visible()
                expect(page.locator("#role")).to_have_count(0)
                expect(page).to_have_url(self.url + "/#outlook")
                expect(page.locator("#outlook h1")).to_be_focused()
                expect(page.locator("#source-list")).to_have_count(0)
                expect(page.locator(".career-page-steps")).to_have_count(0)
                expect(page.get_by_role("button", name="Back to role", exact=False)).to_be_visible()
                expect(page.locator("#outlook .text-button")).to_have_count(0)
                expect(page.locator("#live-trend-status")).to_be_visible()
                health = page.locator("#trend-source-health")
                expect(health.locator(".help-mark")).to_have_text("?")
                self.assertEqual(health.locator("summary").evaluate("el => getComputedStyle(el).borderWidth"), "0px")
                self.assertTrue(page.evaluate("Boolean(document.querySelector('#build-roadmap').compareDocumentPosition(document.querySelector('#trend-source-health')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
                self.screenshot(page, f"outlook-page-{width}")
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                page.go_back()
                expect(page.locator("#role")).to_be_visible()
                expect(page.locator("#role-fit strong")).to_have_text(fit)
                if software.count():
                    page.get_by_text("Choose software · 1 selected", exact=True).click()
                    expect(software).to_be_checked()
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                page.go_forward()
                expect(page.locator("#outlook")).to_be_visible()
                expect(page.locator("#live-trend-status")).to_be_visible()
                self.assertEqual(len(trend_requests), 1, 'Returning to AI outlook should reuse the cached result')
                page.locator("#build-roadmap").click()
                expect(page.locator("#detail")).to_be_visible(timeout=30000)
                expect(page.locator("#detail-fit")).to_have_text(fit)
                page.locator("#open-role-details").click()
                expect(page.locator("#role")).to_be_visible()
                page.locator("#back-to-careers").click()
                expect(page.locator("#explore")).to_be_visible()
                page.locator('[data-screen="review"]').click()
                page.locator("#confirm-all").uncheck()
                page.go_back()
                expect(page.locator("#review")).to_be_visible()
                self.assertEqual(errors, [])
                context.close()

    def test_visual_roadmap_timing_and_pace(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        errors, held, map_requests = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        source_plan = {}

        def original_plan(route):
            response = route.fetch()
            source_plan.update(response.json()["plan"])
            route.fulfill(response=response)

        def dependency_plan(route):
            body = route.request.post_data_json
            map_requests.append(body)
            horizon, weekly = body["horizon"], body["weekly_hours"]
            count = {"short": 3, "standard": 5, "long": 7}[horizon]
            weeks = {"short": 12, "standard": 26, "long": 52}[horizon]
            labels = {item["skill_id"]: item["label"] for item in source_plan["prioritized_gaps"]}
            course = next(item for item in source_plan["selected_courses"] if "thinking" in item["course_id"])
            nodes = []
            titles = ["Inspect and validate a dataset", "Query business results", "Build a reporting dashboard", "Validate the pipeline", "Deliver an analysis brief", "Compare modelling approaches", "Complete a portfolio project"]
            for index in range(count):
                covered = course["skill_ids"] if index == 0 else [next(iter(labels))]
                skills = [{"skill_id": sid, "label": labels.get(sid, "Critical Thinking"), "course_covered": index == 0, "already_confirmed": False, "suggested_tool": False} for sid in covered]
                nodes.append({"node_id": f"node_{index}", "title": titles[index], "objective": "Prepare a checked work sample using a realistic business dataset.",
                    "deliverable": "A reproducible analysis, quality checks and a concise decision brief.", "task_id": "task:test",
                    "skill_ids": covered, "embedded_skill_ids": [], "skills": skills, "embedded_skills": [],
                    "course_ids": [course["course_id"]] if index == 0 else [], "course_hours": course["duration"]["hours"] if index == 0 else 0,
                    "practice_hours": 6, "hours": 12, "level": max(0, index - 1), "week_start": index + 1, "week_end": index + 2})
            graph = {"summary": "Start with two independent branches, then combine them into a practical project.", "origin": "ai_generated", "status": "ready", "model": "TEST model", "provider": "test",
                "horizon": horizon, "target_weeks": weeks, "weekly_hours": weekly, "budget_hours": weeks * weekly,
                "planned_hours": count * 12, "estimated_weeks": __import__('math').ceil(count * 12 / weekly),
                "nodes": nodes, "edges": [{"source": "node_0", "target": "node_2", "basis": "ai_suggested", "reason": "Use the checked dataset as input to the reporting project."},
                    {"source": "node_1", "target": "node_2", "basis": "course_prerequisite", "reason": "Use the tested queries to produce the reporting project."}],
                "deferred_skills": [], "changes_personal_fit": False}
            if horizon == "standard" and not held:
                held.append((route, graph))
                return
            route.fulfill(json={"revision": body["revision"], "roadmap": graph})

        page.route("**/api/v2/pathways", original_plan)
        page.route("**/api/v2/pathways/dependencies", dependency_plan)
        page.goto(self.url)
        page.locator("#sample").click()
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#find-matches").click()
        page.locator("[data-role-id]").first.click()
        page.locator("#build-roadmap").click()
        expect(page.locator(".module-card")).to_have_count(3)
        expect(page.get_by_text("AI-curated", exact=True)).to_be_visible()
        expect(page.locator("#roadmap-total-time")).to_have_text("About 8 weeks of learning")
        expect(page.locator("#module-detail-title")).to_have_text("Inspect and validate a dataset")
        expect(page.locator(".module-course")).to_have_count(1)
        expect(page.locator(".module-course .chip")).to_have_count(len(next(item for item in source_plan["selected_courses"] if "thinking" in item["course_id"])["skill_ids"]))
        expect(page.locator(".dependency-edges > path")).to_have_count(2)
        self.assertNotEqual(page.locator(".dependency-edges > path").first.get_attribute("d"), "")
        fit = page.locator("#detail-fit").inner_text()
        with page.expect_request("**/api/v2/pathways/dependencies"):
            page.get_by_role("button", name="Standard 6 months", exact=True).click()
        expect(page.locator(".dependency-loading")).to_be_visible()
        page.get_by_role("button", name="Long term 12 months", exact=True).click()
        expect(page.locator(".module-card")).to_have_count(7)
        self.assertEqual(len(held), 1)
        held[0][0].fulfill(json={"roadmap": held[0][1]})
        expect(page.locator(".curated-summary")).to_contain_text("12 MONTHS TARGET")
        expect(page.locator(".module-card")).to_have_count(7)
        self.choose_roadmap_option(page, "roadmap-pace", "10")
        expect(page.locator("#roadmap-total-time")).to_have_text("About 9 weeks of learning")
        expect(page.locator("#detail-fit")).to_have_text(fit)
        page.locator("#open-sdg").click()
        expect(page.locator("#sdg")).to_be_visible()
        calls_before_return = len(map_requests)
        page.locator("#back-to-roadmap").click()
        expect(page.locator("#roadmap-pace")).to_have_text("10 hours / week")
        expect(page.get_by_role("button", name="Long term 12 months", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".module-card")).to_have_count(7)
        self.assertEqual(len(map_requests), calls_before_return, 'Returning to the map must not generate it again')
        page.get_by_role("button", name="Short term 1–3 months", exact=True).click()
        expect(page.locator(".module-card")).to_have_count(3)
        for width, height in ((1440, 1080), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#milestones").scroll_into_view_if_needed()
            expect(page.locator(".dependency-edges > path")).to_have_count(2)
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self.screenshot(page, f"dependency-map-{width}")
            page.locator('[data-module="node_1"]').click()
            expect(page.locator("#module-detail-title")).to_have_text("Query business results")
            expect(page.locator(".course-source-option")).to_have_count(3)
            self.screenshot(page, f"dependency-module-{width}")
        self.assertTrue(page.evaluate("Boolean(document.querySelector('#milestones').compareDocumentPosition(document.querySelector('#future-scenarios')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
        with page.expect_download() as download:
            page.locator("#export-plan").click()
        exported = json.loads(Path(download.value.path()).read_text())
        self.assertEqual(exported["curated_roadmap"]["horizon"], "short")
        self.assertEqual(len(exported["curated_roadmap"]["nodes"]), 3)
        self.assertEqual(errors, [])

    def test_language_selector_persists_and_keeps_current_profile(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={'width': 390, 'height': 844})
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(self.url)
        def choose(value):
            page.locator('#language-select').click()
            page.locator(f'#language-select-option-{value}').click()
        choose(1)
        expect(page.locator('html')).to_have_attribute('lang', 'ms')
        expect(page.locator('#intake h1')).to_contain_text('kerjaya')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page.reload()
        expect(page.locator('html')).to_have_attribute('lang', 'ms')
        expect(page.locator('#intake h1')).to_contain_text('kerjaya')
        page.locator('#cv-file').set_input_files({'name': 'skills.txt', 'mimeType': 'text/plain', 'buffer': b'Skills: Python, SQL'})
        expect(page.locator('#review')).to_be_visible(timeout=30000)
        count = page.locator('#skill-list input[type=checkbox]').count()
        page.locator('#confirm-all').check()
        choose(2)
        expect(page.locator('html')).to_have_attribute('lang', 'zh-Hans')
        expect(page.locator('#review h1')).not_to_contain_text("Let's review")
        expect(page.locator('#confirm-all')).to_be_checked()
        self.assertEqual(page.locator('#skill-list input[type=checkbox]').count(), count)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.screenshot(page, 'mandarin-review-390')
        choose(0)
        expect(page.locator('#review h1')).to_have_text("Let's review your skills.")
        expect(page.locator('#confirm-all')).to_be_checked()
        self.assertEqual(page.evaluate('Object.keys(localStorage)'), ['ikiguy-language'])
        self.assertEqual(errors, [])

    def test_sample_core_level_editor_increases_general_requirement_bar(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={'width': 1440, 'height': 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(self.url)
        page.locator('#sample').click()
        page.locator('#confirm-all').check()
        expect(page.locator('#missing-levels-notice')).to_contain_text('9 confirmed skills still need a level.')
        page.locator('#review-next').click()
        page.locator('#target-search').fill('business intelligence')
        page.get_by_role('option', name='Business Intelligence Analysts', exact=True).click()
        page.locator('#find-matches').click()
        page.locator('[data-role-id="role:onet_15_2051_01"]').click()
        meter = page.get_by_role('meter', name='General requirement fulfilment', exact=True)
        expect(meter).to_have_attribute('value', '0')
        expect(page.locator('#general-fulfilment-help')).to_contain_text('confirmed core skills still need a level')
        page.get_by_role('button', name='Set core skill levels', exact=True).click()
        page.locator('#set-next-level').click()
        # The helper opens the first core skill, ahead of the Excel tool row.
        control = page.get_by_role('combobox', name='Your skill level', exact=True)
        expect(control).to_be_focused()
        control.click()
        page.get_by_role('option', name='Beginner', exact=True).click()
        expect(page.locator('#missing-levels-notice')).to_contain_text('8 confirmed skills still need a level.')
        expect(page.locator('#confirm-all')).to_be_checked()
        page.locator('#review-next').click()
        page.locator('#find-matches').click()
        page.locator('[data-role-id="role:onet_15_2051_01"]').click()
        self.assertGreater(float(meter.get_attribute('value')), 0)
        expect(page.locator('#general-fulfilment-help')).to_have_count(0)
        self.screenshot(page, 'sample-general-fulfilment-positive')
        self.assertEqual(errors, [])

    def test_ai_estimates_display_without_manual_level_input(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()

        def assessed_sample(route):
            response = route.fetch()
            payload = response.json()
            for skill in payload["profile"]["skills"]:
                skill.update(level="intermediate", level_assessment={
                    "method": "ai_estimate", "model": "test-model", "confidence": "medium",
                    "rationale": "Fictional independent project evidence.", "evidence_indices": [0]})
            payload["profile"]["assessment_status"] = {
                "status": "completed", "provider": "runpod", "error_code": None,
                "assessed_skill_count": len(payload["profile"]["skills"]),
                "message": "AI assessed your skills automatically."}
            route.fulfill(response=response, json=payload)

        page.route("**/api/v2/profiles/sample", assessed_sample)
        page.goto(self.url)
        page.locator("#sample").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#ai-assessment-status")).to_contain_text("automatically")
        expect(page.locator(".skill-name").first).to_contain_text("AI estimate: intermediate")
        page.locator(".cv-evidence summary").first.click()
        expect(page.locator("#level-0")).to_have_text("Intermediate")
        expect(page.locator("#level-0")).not_to_have_attribute("role", "combobox")
        page.locator("#correct-level-0").click()
        expect(page.locator("#level-0")).to_have_attribute("role", "combobox")
        page.locator("#level-0").click()
        page.get_by_role("option", name="Advanced", exact=True).click()
        expect(page.locator(".skill-name").first).not_to_contain_text("AI estimate")
        expect(page.locator("#level-0")).to_have_text("Advanced")
        self.screenshot(page, "ai-estimates-applied")

    def test_sidebar_animates_between_sizes(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 1440, "height": 1080}, reduced_motion="no-preference")
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        sidebar = page.locator('.sidebar')
        sample_frames = '''async el => {
            const widths = [];
            const start = performance.now();
            while (performance.now() - start < 260) {
                await new Promise(requestAnimationFrame);
                widths.push(el.getBoundingClientRect().width);
            }
            return widths;
        }'''
        page.get_by_role('button', name='Collapse sidebar', exact=True).click()
        collapsing = sidebar.evaluate(sample_frames)
        self.assertGreater(len({round(width) for width in collapsing}), 4)
        self.assertTrue(any(110 < width < 210 for width in collapsing))
        expect(sidebar).to_have_css('width', '84px')
        expect(page.locator('.sidebar>.brand')).to_be_visible()
        page.get_by_role('button', name='Expand sidebar', exact=True).click()
        expanding = sidebar.evaluate(sample_frames)
        self.assertGreater(len({round(width) for width in expanding}), 4)
        self.assertTrue(any(110 < width < 210 for width in expanding))
        expect(sidebar).to_have_css('width', '228px')
        expect(page.get_by_text('Fictional CV demo', exact=True)).to_have_count(0)
        page.emulate_media(reduced_motion='reduce')
        expect(sidebar).to_have_css('transition-duration', '0s')

    def test_complete_cv_review_matching_and_scenarios(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.url)
        expect(page.get_by_text("Drop your CV here", exact=True)).to_be_visible()
        expect(page.locator('.nav-item.completed')).to_have_count(0)
        expect(page.locator('#stage-label')).to_have_count(0)
        expect(page.get_by_role('link', name='FutureReady home')).to_have_count(0)
        expanded_width = page.locator('.sidebar').bounding_box()['width']
        page.get_by_role('button', name='Collapse sidebar', exact=True).click()
        expect(page.get_by_role('button', name='Expand sidebar', exact=True)).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('.sidebar')).to_have_css('width', '84px')
        self.assertLess(page.locator('.sidebar').bounding_box()['width'], expanded_width)
        expect(page.locator('.nav-full').first).to_be_hidden()
        expect(page.locator('[data-screen="intake"]')).to_be_visible()
        self.screenshot(page, 'sidebar-collapsed')
        page.get_by_role('button', name='Expand sidebar', exact=True).click()
        expect(page.locator('.nav-full').first).to_be_visible()
        self.screenshot(page, "intake")
        # Upload actual PDF bytes rather than passing a preconstructed profile.
        pdf = httpx.get(self.url + "/api/v2/samples/graduate.pdf").content
        page.locator("#cv-file").set_input_files({"name": "graduate.pdf", "mimeType": "application/pdf", "buffer": pdf})
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('[data-screen="intake"]')).to_have_attribute('data-complete', 'true')
        expect(page.locator('.nav-status .icon')).to_have_count(0)
        expect(page.locator('[data-screen="review"]')).to_have_attribute('data-complete', 'false')
        self.assertEqual(page.locator("#skill-list input:checked").count(), 0)
        expect(page.locator("#target-search")).to_be_hidden()
        page.locator('#skill-list input[type="checkbox"]').first.check()
        expect(page.locator("#confirmed-count")).to_have_text("1")
        expect(page.get_by_role("progressbar", name="Skill confirmation progress")).to_have_attribute("aria-valuenow", "1")
        self.assertTrue(page.locator("#confirm-all").evaluate("el => el.indeterminate"))
        self.assertLess(float(page.locator(".confirmation-ring").get_attribute("stroke-dashoffset")), 2 * 3.141593 * 34)
        circle = page.locator('.skill-count-circle').bounding_box()
        caption = page.locator('.skill-confirmation > span').bounding_box()
        self.assertGreaterEqual(caption['y'], circle['y'] + circle['height'])
        self.screenshot(page, "review")
        page.locator(".cv-evidence summary").first.click()
        expect(page.locator(".cv-evidence-content").first).to_be_visible()
        expect(page.locator(".cv-evidence summary").first).to_have_text("View CV evidence")
        expect(page.locator(".cv-evidence summary .icon").first).to_be_visible()
        page.locator("#correct-level-0").click()
        level = page.locator("#level-0")
        level.click()
        expect(page.locator("#level-0-options")).to_be_visible()
        self.screenshot(page, "skill-level-dropdown")
        page.get_by_role("option", name="Advanced", exact=True).click()
        expect(level).to_have_text("Advanced")
        expect(level).to_have_attribute("aria-expanded", "false")
        level.press("ArrowDown")
        level.press("Home")
        level.press("ArrowDown")
        level.press("Enter")
        expect(level).to_have_text("Beginner")
        level.click()
        level.press("Escape")
        expect(page.locator("#level-0-options")).to_be_hidden()
        self.assertEqual(page.locator("select").count(), 0)
        self.screenshot(page, "review-evidence")
        page.locator(".cv-evidence summary").first.click()
        page.locator("#confirm-all").click()
        expect(page.locator("#confirm-all")).to_be_checked()
        self.assertEqual(float(page.locator(".confirmation-ring").get_attribute("stroke-dashoffset")), 0)
        page.locator("#confirm-all").uncheck()
        expect(page.locator("#confirmed-count")).to_have_text("0")
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#target-search").fill("business intelligence")
        page.get_by_role("option", name="Business Intelligence Analysts", exact=True).click()
        page.locator("#learning-preferences summary").click()
        page.locator("#weekly-hours").fill("5")
        page.locator("#back-to-skills").click()
        expect(page.locator("#confirm-all")).to_be_checked()
        page.locator("#review-next").click()
        expect(page.locator("#selected-target")).to_have_text("Business Intelligence Analysts")
        expect(page.locator("#weekly-hours")).to_have_value("5")
        self.screenshot(page, "review-direction")
        page.locator("#find-matches").click()
        expect(page.locator("#explore")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('[data-screen="review"]')).to_have_attribute('data-complete', 'true')
        expect(page.locator('[data-screen="explore"]')).to_have_attribute('data-complete', 'false')
        self.screenshot(page, "matches")
        family = page.get_by_role("combobox", name="Occupational family", exact=True)
        family.click()
        family.press("End")
        family.press("Enter")
        expect(family).not_to_have_text("All occupational families")
        family.click()
        family.press("Home")
        family.press("Enter")
        expect(family).to_have_text("All occupational families")
        target = page.locator('[data-role-id="role:onet_15_2051_01"]')
        page.locator("#role-filter").fill("no matches for this filter")
        expect(target).to_be_visible()
        page.locator("#role-filter").fill("")
        page.locator('[data-role-id="role:onet_15_2051_01"]').click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.screenshot(page, "role-details")
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('.nav-item.completed')).to_have_count(4)
        expect(page.locator('[data-screen="detail"]')).to_have_attribute('aria-description', 'Roadmap ready')
        fit = page.locator("#detail-fit").inner_text()
        expect(page.locator(".module-card").first).to_be_visible()
        baseline = page.locator(".module-card > strong").all_text_contents()
        expect(page.locator("#scenario-select")).to_have_text("Baseline · current requirements")
        expect(page.locator("#future-disclaimer")).to_contain_text("hypothetical scenarios, not forecasts")
        expect(page.locator(".future-story")).to_have_count(0)
        page.get_by_text("Compare all three scenarios", exact=True).click()
        expect(page.locator("#future-skill-comparison")).to_contain_text("Baseline")
        expect(page.locator("#future-skill-comparison")).to_contain_text("Moderate")
        expect(page.locator("#future-skill-comparison")).to_contain_text("Rapid")
        expect(page.locator("#shared-future-preparation")).to_contain_text("capabilities you already have")
        self.choose_roadmap_option(page, "scenario-select", "moderate_ai_change")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('[data-future-scenario="moderate_ai_change"]')).to_be_visible()
        expect(page.locator(".future-story")).to_have_count(1)
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        page.locator("#future-baseline").click()
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator(".module-card").first).to_be_visible()
        self.assertEqual(page.locator(".module-card > strong").all_text_contents(), baseline)
        page.get_by_text("Compare all three scenarios", exact=True).click()
        page.locator("#open-sdg").click()
        expect(page.locator("#sdg-impact")).to_be_visible()
        expect(page.locator("#sdg-coverage")).to_contain_text("Career linked")
        page.locator("#sdg-skill-search").fill("Python")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Python")
        page.locator("#skill-sdg-connections summary").first.click()
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Quality Education")
        page.locator("#sdg-skill-search").fill("")
        page.locator("#back-to-roadmap").click()
        expect(page.locator("#milestones")).not_to_contain_text("skill:onet_")
        page.locator("#future-scenarios").scroll_into_view_if_needed()
        self.screenshot(page, "future-scenarios")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator(".future-story")).to_have_count(0)
        page.locator("#future-scenarios").scroll_into_view_if_needed()
        self.screenshot(page, "future-scenarios-mobile")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.evaluate("JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))})"))
        page.set_viewport_size({"width": 1440, "height": 1080})
        expect(page.locator("#course-availability")).to_contain_text("verified courses")
        page.locator("#detail summary").filter(has_text="Why these learning priorities?").click()
        expect(page.locator("#priority-evidence")).to_contain_text("No approved research adjustments")
        page.locator("#detail summary").filter(has_text="Plan details & limitations").click()
        expect(page.locator("#course-catalog-status")).to_contain_text("verified courses in the catalog")
        expect(page.locator('.plan-notes')).to_contain_text('Matches show skill coverage, not hiring chances')
        expect(page.locator('#plan-warnings')).to_be_hidden()
        expect(page.locator('.plan-notes')).not_to_contain_text('skill:onet_')
        page.locator('.plan-technical summary').click()
        expect(page.locator('#plan-warnings')).to_be_visible()
        expect(page.locator('#plan-warnings')).to_contain_text('No search provider configured')
        page.locator('.plan-technical summary').click()
        expect(page.locator("#module-detail .course-source-options")).to_be_visible()
        self.choose_roadmap_option(page, "scenario-select", "rapid_ai_change")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-note")).to_contain_text("HYPOTHETICAL")
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        expect(page.locator("#priority-comparison")).to_contain_text("How priorities change")
        self.screenshot(page, "roadmap")
        with page.expect_download() as download:
            page.locator("#export-plan").click()
        self.assertEqual(download.value.suggested_filename, "ikiguy-learning-plan.json")
        self.choose_roadmap_option(page, "scenario-select", "baseline")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator(".module-card").first).to_be_visible()
        self.assertEqual(page.locator(".module-card > strong").all_text_contents(), baseline)
        page.locator("#open-role-details").click()
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#source-list, #shared-skill-evidence, #reviewed-role-impacts")).to_have_count(0)
        page.locator('[data-screen="review"]').click()
        page.locator('#confirm-all').uncheck()
        expect(page.locator('.nav-item.completed')).to_have_count(1)
        expect(page.locator('[data-screen="detail"]')).to_be_disabled()
        page.reload()
        expect(page.locator("#intake")).to_be_visible(timeout=30000)
        self.assertEqual(errors, [])

    def test_mobile_sample_and_manual_fallback(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        self.screenshot(page, "mobile")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        page.locator("#sample").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        page.locator('[data-screen="intake"]').click()
        expect(page.locator(".upload-success-label")).to_have_text("Uploaded successfully", timeout=30000)
        expect(page.locator(".uploaded-filename")).to_have_text("graduate.pdf")
        page.locator("#cv-file").set_input_files({"name": "career-update.txt", "mimeType": "text/plain", "buffer": b"Skills: Python, SQL"})
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        page.locator('[data-screen="intake"]').click()
        expect(page.locator(".uploaded-filename")).to_have_text("career-update.txt", timeout=30000)
        page.locator("#cv-file").set_input_files({"name": "broken.pdf", "mimeType": "application/pdf", "buffer": b"not a PDF"})
        expect(page.locator("#feedback")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator(".uploaded-filename")).to_have_text("career-update.txt")
        self.screenshot(page, "mobile-upload-success")
        page.locator("#review-upload").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        page.reload()
        expect(page.locator("#intake")).to_be_visible(timeout=30000)
        page.locator(".upload-help summary").click()
        expect(page.locator(".upload-help .help-mark")).to_have_text("?")
        page.locator("#manual-fallback").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        page.locator("#skill-search").fill("Python")
        expect(page.get_by_role("option", name="Python", exact=True)).to_be_visible()
        page.locator("#skill-search").press("ArrowDown")
        expect(page.locator("#skill-search")).to_have_attribute("aria-activedescendant", "skill-results-0")
        self.screenshot(page, "mobile-autocomplete")
        page.locator("#skill-search").press("Escape")
        expect(page.locator("#skill-results")).to_be_hidden()
        page.locator("#skill-search").press("ArrowDown")
        page.locator("#skill-search").press("Enter")
        expect(page.locator(".skill-name .added")).to_have_text("Added by you")
        expect(page.locator(".skill-name label")).to_have_text("Python")
        page.locator(".cv-evidence summary").first.click()
        page.locator("#level-0").click()
        expect(page.get_by_role("option", name="Intermediate", exact=True)).to_be_visible()
        self.screenshot(page, "mobile-skill-level-dropdown")
        page.get_by_role("option", name="Intermediate", exact=True).click()
        expect(page.locator("#level-0")).to_have_text("Intermediate")
        page.locator(".cv-evidence summary").first.click()
        page.locator("#confirm-all").click()
        page.locator("#review-next").click()
        page.locator("#find-matches").click()
        expect(page.locator("#explore")).to_be_visible(timeout=30000)
        expect(page.locator("#feedback")).to_be_hidden()

    def test_upload_loading_reel_and_reduced_motion(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.addCleanup(context.close)
        page = context.new_page()
        held = []
        page.route("**/api/v2/profiles/sample", lambda route: held.append(route))
        page.goto(self.url)
        page.locator("#sample").click()
        expect(page.locator("#busy")).to_be_visible()
        self.assertEqual(page.locator("#processing-steps").count(), 0)
        first = page.locator("#upload-reel-track span").first.inner_text()
        transform = page.locator(".spinner").evaluate("el => getComputedStyle(el).transform")
        page.wait_for_timeout(150)
        self.assertNotEqual(transform, page.locator(".spinner").evaluate("el => getComputedStyle(el).transform"))
        # Check actual upward movement, not only the next message's text.
        page.wait_for_function("new DOMMatrix(getComputedStyle(document.querySelector('.reel-track')).transform).m42 < -2", timeout=1000)
        page.wait_for_timeout(2200)
        self.assertNotEqual(first, page.locator("#upload-reel-track span").first.inner_text())
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        page.emulate_media(reduced_motion="reduce")
        self.assertEqual(page.locator(".spinner").evaluate("el => getComputedStyle(el).animationName"), "spin")
        self.assertEqual(page.locator(".reel-track").evaluate("el => getComputedStyle(el).animationName"), "reel-turn")
        self.assertEqual(page.locator("#busy button").count(), 0)
        self.screenshot(page, "mobile-loading")
        self.assertEqual(len(held), 1)
        held[0].continue_()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden()
        page.wait_for_timeout(2400)
        self.assertEqual(page.locator("#upload-reel-track").count(), 0)

    def test_unfiltered_reviewed_evidence_is_hidden_and_optional_failure_allows_roadmap(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/v2/roles/*/skill-evidence", lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({
                "changes_weights": False, "pending_mapping_reviews": 0, "unassessed_pairs": 3,
                "articles_awaiting_shared_review": 0,
                "approved_conditional_skill_evidence": [{
                    "news_id": "fictional-browser-test", "skill_id": "skill:python", "skill_label": "Python",
                    "rationale": "Fictional test-only reviewed interpretation.",
                    "source": {"source_url": "https://example.org/test-research", "publisher": "Fictional research publisher", "published_at": "2026-10-01"},
                    "supporting_findings": [{"claim": "Fictional finding for browser validation.", "quote": "test-only supporting words", "evidence_type": "benchmark", "reference": {"document_id": "test", "passage_id": "p1"}}],
                    "applicability_conditions": ["Only the fictional test context."],
                    "human_checks": ["No real research result is claimed."],
                }],
            })))
        page.route("**/api/v2/roles/*/impacts", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"Temporarily unavailable"}'))
        page.goto(self.url)
        page.locator("#cv-file").set_input_files({"name": "fictional.txt", "mimeType": "text/plain", "buffer": b"Skills: Python, SQL"})
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        page.locator("#confirm-all").check()
        page.locator("#review-next").click()
        page.locator("#target-search").fill("business intelligence")
        page.get_by_role("option", name="Business Intelligence Analysts", exact=True).click()
        page.locator("#find-matches").click()
        expect(page.locator("#explore")).to_be_visible(timeout=30000)
        page.locator('[data-role-id="role:onet_15_2051_01"]').click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        fit = page.locator("#role-fit strong").inner_text()
        page.locator("#open-ai-outlook").click()
        expect(page.locator("#source-list, #shared-skill-evidence, #reviewed-role-impacts")).to_have_count(0)
        expect(page.locator("#outlook")).not_to_contain_text("Fictional test-only reviewed interpretation.")
        expect(page.locator("#feedback")).to_be_hidden()
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#detail-fit")).to_have_text(fit)

    def test_empty_profile_errors_and_skill_review_states(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.url)
        page.locator("#cv-file").set_input_files({"name": "broken.pdf", "mimeType": "application/pdf", "buffer": b"not a PDF"})
        expect(page.locator("#feedback")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.screenshot(page, "mobile-error")
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        expect(page.locator("#review")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        page.locator("#review-next").click()
        page.locator("#find-matches").click()
        expect(page.locator("#explore")).to_be_visible(timeout=30000)
        self.assertEqual(page.locator(".career-card, .featured-career").count(), 0)
        expect(page.get_by_text("Let's find your starting point", exact=True)).to_be_visible()
        self.screenshot(page, "mobile-empty")
        page.get_by_role("button", name="Review my skills", exact=True).click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        expect(page.locator(".skill-name .added")).to_have_text("Added by you")
        page.get_by_role("button", name="Remove Python", exact=True).click()
        expect(page.locator(".skill-row.removed")).to_be_visible()
        page.get_by_role("button", name="Restore Python", exact=True).click()
        page.locator("#confirm-all").click()
        expect(page.locator("#confirmed-count")).to_have_text("1")
        page.locator("#review-next").click()
        page.locator("#find-matches").click()
        expect(page.locator("#explore")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.screenshot(page, "mobile-matches")
        page.locator("[data-role-id]").first.click()
        expect(page.locator("#role")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_be_enabled()
        self.choose_roadmap_option(page, "scenario-select", "rapid_ai_change")
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_have_text("Rapid AI adoption")
        self.choose_roadmap_option(page, "scenario-select", "moderate_ai_change")
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_have_text("Moderate AI adoption")
        expect(page.locator("#future-disclaimer")).to_be_visible()
        expect(page.locator("#detail-fit")).to_be_visible()
        self.screenshot(page, "mobile-roadmap")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
