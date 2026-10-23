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
        payload["refresh"]["article_count"] = 4
        payload["source_review"] = {"stored_count": 4, "selected_count": 3, "assessed_count": 2,
            "connection_count": 1, "assessment_limit": 6, "connection_limit": 3,
            "legacy_analysis": False, "updating": False, "articles": [
                {"source": article, "outcome": "connected", "reason": "Chart generation may assist reporting.", "assessed_by_ai": True},
                {"source": indirect, "outcome": "indirect_relevance", "reason": "This excerpt describes general AI research without a specific reporting application.", "assessed_by_ai": True},
                {"source": unselected, "outcome": "not_selected", "reason": "Not sent to the AI: outside the selected articles. This does not mean it is unrelated.", "assessed_by_ai": False},
                {"source": thin, "outcome": "insufficient_text", "reason": "Not sent to the AI: too little source text was available.", "assessed_by_ai": False}]}
        def trends(route):
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
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        fit = page.locator("#drawer-fit strong").inner_text()
        page.get_by_text("AI outlook & evidence", exact=True).click()
        expect(page.locator("#live-trend-status")).to_contain_text("12:00:00 UTC")
        expect(page.locator("#trend-interpretations")).to_contain_text("not human reviewed")
        expect(page.locator(".trend-citation")).to_be_visible()
        expect(page.locator(".trend-citation")).to_contain_text("Published 2026-10-22")
        expect(page.locator(".trend-implications")).to_contain_text("What it could mean for this career")
        expect(page.locator(".trend-implications")).to_contain_text("Practice validating chart outputs.")
        page.get_by_text("Supporting source", exact=True).click()
        expect(page.locator("#trend-interpretations")).to_contain_text("Published 2026-10-22")
        expect(page.get_by_role("link", name="TEST research on generated charts")).to_have_attribute("href", article["source_url"])
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        expect(page.locator("#live-trend-status")).to_contain_text("13:00:00 UTC")
        expect(page.locator("#trend-interpretations")).to_contain_text("Published 2026-10-22")
        expect(page.locator("#drawer-fit strong")).to_have_text(fit)
        expect(page.locator("#trend-review-summary")).to_contain_text("4 stored · 3 selected for this career · 2 assessed by AI · 1 career connection shown")
        page.get_by_text("How sources were assessed", exact=True).click()
        expect(page.locator("#live-source-list .source-card")).to_have_count(4)
        expect(page.locator("#live-source-list")).to_contain_text("Indirect relevance")
        expect(page.locator("#live-source-list")).to_contain_text("without a specific reporting application")
        expect(page.locator("#live-source-list")).to_contain_text("Not selected for AI assessment")
        expect(page.locator("#live-source-list")).to_contain_text("too little source text")
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
        expect(page.locator("#trend-review-summary")).to_have_count(0)
        expect(page.locator("#live-source-list")).to_have_count(0)
        expect(page.locator("#live-trends")).not_to_contain_text("AI assessment pending")
        payload["analysis_status"] = "failed"
        payload["analysis_error"] = "Provider unavailable"
        payload["source_review"]["updating"] = False
        expect(page.locator("#retry-trend-analysis")).to_be_visible(timeout=10000)
        expect(page.locator("#trend-analysis-notice")).to_contain_text("does not mean that no articles are relevant")
        payload.clear()
        payload.update(json.loads(json.dumps(complete)))
        page.locator("#retry-trend-analysis").click()
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        payload["analysis_status"] = "updating"
        payload["analysis_stale"] = True
        payload["source_review"]["updating"] = True
        expect(page.locator("#trend-analysis-notice")).to_contain_text("Updating career research", timeout=10000)
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        expect(page.locator("#trend-interpretations")).to_contain_text("TEST AI-assisted chart finding")
        payload["analysis_status"] = "failed"
        payload["analysis_error"] = "Provider unavailable"
        payload["source_review"]["updating"] = False
        expect(page.locator("#trend-analysis-notice")).to_contain_text("Showing your last completed assessment", timeout=10000)
        expect(page.locator("#trend-review-summary")).to_contain_text("2 assessed by AI")
        payload.clear()
        payload.update(complete)
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
        page.get_by_text("AI outlook & evidence", exact=True).click()
        expect(page.locator("#live-trend-status")).to_contain_text("111 stored")
        page.get_by_role("button", name="Refresh trends", exact=True).click()
        page.locator("#close-drawer").click()
        page.locator('[data-role-id]:not([data-role-id="role:onet_15_2051_01"])').first.click()
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        page.get_by_text("AI outlook & evidence", exact=True).click()
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
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        expect(page.locator("#drawer-sdg-connections")).to_contain_text("Target 8.2")
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        fit = page.locator("#detail-fit").inner_text()
        expect(page.locator("#scenario-select")).to_have_value("baseline")
        expect(page.locator(".future-story")).to_have_count(0)
        expect(page.locator("#role-sdg-connections")).to_contain_text("Decent Work and Economic Growth")
        page.locator("#sdg-skill-filter").select_option("confirmed")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Python")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("In your profile")
        page.locator("#sdg-skill-filter").select_option("all")
        page.locator("#sdg-skill-search").fill("Critical Thinking")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("SDG 4")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("SDG 8")
        page.locator("#sdg-skill-search").fill("")
        page.locator("#scenario-select").select_option("rapid_ai_change")
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
        expect(page.locator("#role-drawer")).to_contain_text("65.0% CV skill alignment and 35.0% general requirement fulfilment")
        page.get_by_text("Your proficiency vs job requirements", exact=True).click()
        expect(page.locator("#proficiency-comparison")).to_contain_text("Job requirement:")
        expect(page.locator("#proficiency-comparison")).to_contain_text("Your estimate: unknown")
        page.get_by_text("How your CV skills affect this score", exact=True).click()
        expect(page.locator("#role-drawer")).to_contain_text("Tableau")

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
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.screenshot(page, "role-details")
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('.nav-item.completed')).to_have_count(4)
        expect(page.locator('[data-screen="detail"]')).to_have_attribute('aria-description', 'Roadmap ready')
        fit = page.locator("#detail-fit").inner_text()
        baseline = page.locator(".step-preview h3:visible").all_text_contents()
        expect(page.locator("#scenario-select")).to_have_value("baseline")
        expect(page.locator("#future-disclaimer")).to_contain_text("hypothetical scenarios, not forecasts")
        expect(page.locator(".future-story")).to_have_count(0)
        page.get_by_text("Compare all three scenarios", exact=True).click()
        expect(page.locator("#future-skill-comparison")).to_contain_text("Baseline")
        expect(page.locator("#future-skill-comparison")).to_contain_text("Moderate")
        expect(page.locator("#future-skill-comparison")).to_contain_text("Rapid")
        expect(page.locator("#shared-future-preparation")).to_contain_text("capabilities you already have")
        page.locator("#scenario-select").select_option("moderate_ai_change")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator('[data-future-scenario="moderate_ai_change"]')).to_be_visible()
        expect(page.locator(".future-story")).to_have_count(1)
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        page.locator("#future-baseline").click()
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.assertEqual(page.locator(".step-preview h3:visible").all_text_contents(), baseline)
        page.get_by_text("Compare all three scenarios", exact=True).click()
        expect(page.locator("#sdg-impact")).to_be_visible()
        expect(page.locator("#sdg-coverage")).to_contain_text("Career linked")
        page.locator("#sdg-skill-search").fill("Python")
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Python")
        page.locator("#skill-sdg-connections summary").first.click()
        expect(page.locator("#skill-sdg-connections")).to_contain_text("Quality Education")
        page.locator("#sdg-skill-search").fill("")
        expect(page.locator("#milestones")).not_to_contain_text("skill:onet_")
        page.locator("#future-scenarios").scroll_into_view_if_needed()
        self.screenshot(page, "future-scenarios")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator(".future-story")).to_have_count(0)
        page.locator("#future-scenarios").scroll_into_view_if_needed()
        self.screenshot(page, "future-scenarios-mobile")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.evaluate("JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))})"))
        page.set_viewport_size({"width": 1440, "height": 1080})
        expect(page.locator("#course-availability")).to_contain_text("Verified courses unavailable")
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
        page.locator(".learning-step summary").first.click()
        expect(page.locator(".step-content").first).to_contain_text("OpenLearn")
        page.locator(".learning-step summary").first.click()
        page.locator("#scenario-select").select_option("rapid_ai_change")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-note")).to_contain_text("HYPOTHETICAL")
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        expect(page.locator("#priority-comparison")).to_contain_text("How priorities change")
        self.screenshot(page, "roadmap")
        with page.expect_download() as download:
            page.locator("#export-plan").click()
        self.assertEqual(download.value.suggested_filename, "ikiguy-learning-plan.json")
        page.locator("#scenario-select").select_option("baseline")
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.assertEqual(page.locator(".step-preview h3:visible").all_text_contents(), baseline)
        page.locator("#open-role-details").click()
        page.locator("#role-drawer summary").filter(has_text="AI outlook & evidence").click()
        page.get_by_text("Human-reviewed research", exact=True).click()
        expect(page.locator("#outlook-label")).to_have_text("Contextual AI evidence; employment impact unknown")
        expect(page.locator("#source-list")).to_contain_text("DS-STAR")
        page.locator("#role-drawer summary").filter(has_text="Reviewed skill connections").click()
        expect(page.locator("#shared-skill-evidence")).to_contain_text("No approved skill connections yet")
        page.locator("#role-drawer summary").filter(has_text="Reviewed role impacts").click()
        expect(page.locator("#reviewed-role-impacts")).to_contain_text("No approved role impacts yet")
        page.keyboard.press("Escape")
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

    def test_reviewed_evidence_display_and_optional_service_failure(self):
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
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        fit = page.locator("#drawer-fit strong").inner_text()
        page.locator("#role-drawer summary").filter(has_text="AI outlook & evidence").click()
        page.get_by_text("Human-reviewed research", exact=True).click()
        page.locator("#role-drawer summary").filter(has_text="Reviewed skill connections").click()
        expect(page.locator("#shared-skill-evidence")).to_contain_text("Fictional test-only reviewed interpretation.")
        page.locator("#shared-skill-evidence summary").filter(has_text="Evidence & conditions").click()
        expect(page.locator("#shared-skill-evidence blockquote")).to_have_text("test-only supporting words")
        expect(page.get_by_role("link", name="Fictional research publisher")).to_have_attribute("href", "https://example.org/test-research")
        page.locator("#role-drawer summary").filter(has_text="Reviewed role impacts").click()
        expect(page.locator("#reviewed-role-impacts")).to_contain_text("temporarily unavailable")
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
        expect(page.locator("#role-drawer")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        page.locator("#build-roadmap").click()
        expect(page.locator("#detail")).to_be_visible(timeout=30000)
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_be_enabled()
        page.locator("#scenario-select").select_option("rapid_ai_change")
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_have_value("rapid_ai_change")
        page.locator("#scenario-select").select_option("moderate_ai_change")
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-select")).to_have_value("moderate_ai_change")
        expect(page.locator("#future-disclaimer")).to_be_visible()
        expect(page.locator("#detail-fit")).to_be_visible()
        self.screenshot(page, "mobile-roadmap")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
