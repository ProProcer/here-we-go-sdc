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
            env={**os.environ, "PORT": str(port), "WEB_CONCURRENCY": "4", "GROQ_API": "", "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "RUNPOD_API_KEY": "", "RUNPOD_ENDPOINT_ID": ""},
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

    def test_python_only_level_changes_update_visible_fit(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1440, "height": 1080})
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.url)
        page.locator(".upload-help summary").click()
        page.locator("#manual-fallback").click()
        page.locator("#skill-search").fill("Python")
        page.get_by_role("option", name="Python", exact=True).click()
        scores = []
        for index, level in enumerate(("Beginner", "Intermediate", "Advanced")):
            if index:
                page.locator('[data-screen="review"]').click()
            page.locator(".cv-evidence summary").first.click()
            page.locator("#level-0").click()
            page.get_by_role("option", name=level, exact=True).click()
            page.locator(".cv-evidence summary").first.click()
            page.locator("#confirm-all").check()
            page.locator("#review-next").click()
            page.locator("#find-matches").click()
            expect(page.locator("#explore")).to_be_visible(timeout=30000)
            expect(page.locator("#busy")).to_be_hidden(timeout=30000)
            scores.append(float(page.locator("#featured-match .fit-orbit strong").inner_text()))
        self.assertTrue(scores[0] < scores[1] < scores[2], scores)

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
        page.locator('[data-scenario="rapid_ai_change"]').click()
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        expect(page.locator("#scenario-note")).to_contain_text("HYPOTHETICAL")
        self.assertEqual(page.locator("#detail-fit").inner_text(), fit)
        expect(page.locator("#priority-comparison")).to_contain_text("How priorities change")
        self.screenshot(page, "roadmap")
        with page.expect_download() as download:
            page.locator("#export-plan").click()
        self.assertEqual(download.value.suggested_filename, "ikiguy-learning-plan.json")
        page.locator('[data-scenario="baseline"]').click()
        expect(page.locator("#busy")).to_be_hidden(timeout=30000)
        self.assertEqual(page.locator(".step-preview h3:visible").all_text_contents(), baseline)
        page.locator("#open-role-details").click()
        page.locator("#role-drawer summary").filter(has_text="AI outlook & evidence").click()
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
        expect(page.locator('[data-scenario="rapid_ai_change"]')).to_be_enabled()
        page.locator('[data-scenario="rapid_ai_change"]').click()
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator('[data-scenario="rapid_ai_change"]')).to_have_attribute('aria-pressed', 'true')
        page.locator('[data-scenario="moderate_ai_change"]').click()
        expect(page.locator('#busy')).to_be_hidden(timeout=30000)
        expect(page.locator('[data-scenario="moderate_ai_change"]')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator("#scenario-support")).to_be_visible()
        expect(page.locator("#detail-fit")).to_be_visible()
        self.screenshot(page, "mobile-roadmap")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
