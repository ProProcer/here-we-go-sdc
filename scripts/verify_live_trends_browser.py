"""Verify real source cards and an external refresh through the running UI."""

import json
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROLE = "role:onet_15_2051_01"
OUTPUT = Path("docs/verification")


def outlook():
    with urlopen(f"http://127.0.0.1:8000/api/v2/roles/{ROLE}/trends", timeout=10) as response:
        return json.load(response)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = outlook()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1080})
            page.goto("http://127.0.0.1:8000")
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
            expect(page.locator("#live-trend-status")).to_be_visible(timeout=30000)
            # A successful source refresh does not require the model to find
            # a career connection. Zero supported cards is a valid assessment.
            expect(page.get_by_role("button", name="Refresh trends", exact=True)).to_be_enabled(timeout=90000)
            before = outlook()
            old_time = page.locator("#live-trend-status time").inner_text()
            page.get_by_role("button", name="Refresh trends", exact=True).click()
            expect(page.locator("#live-trend-status time")).not_to_have_text(old_time, timeout=180000)
            expect(page.locator("#live-trend-status")).to_contain_text("Feeds up to date", timeout=180000)
            expect(page.locator("#drawer-fit strong")).to_have_text(fit)
            page.locator("#live-trend-status").scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT / "live-trends-refresh.png"))
            if page.locator("#trend-interpretations .trend-card").count():
                page.get_by_text("Supporting source", exact=True).first.click()
                expect(page.locator("#trend-interpretations")).to_contain_text("Published")
                expect(page.locator("#trend-interpretations")).to_contain_text("Fetched")
                page.locator("#trend-interpretations .disclosure-content").first.scroll_into_view_if_needed()
            elif page.locator("#trend-source-review").count():
                page.locator("#trend-source-review > summary").click()
                expect(page.locator("#live-source-list")).to_contain_text("Published")
                expect(page.locator("#live-source-list")).to_contain_text("Fetched")
            else:
                page.get_by_text("Browse dated research sources", exact=True).click()
                expect(page.locator("#live-trends")).to_contain_text("Published")
            page.screenshot(path=str(OUTPUT / "live-trends-citation.png"))
            after = outlook()
            assert after["refresh"]["last_successful_at"] != before["refresh"]["last_successful_at"]
            assert all(feed["status"] == "ok" and len(feed["response_sha256"]) == 64 for feed in after["refresh"]["feeds"])
            assert after["articles"] and all(a["published_at"] and a["fetched_at"] for a in after["articles"])
            proof = {"role_id": ROLE, "source_count": after["refresh"]["article_count"],
                "before_successful_fetch": before["refresh"]["last_successful_at"],
                "after_successful_fetch": after["refresh"]["last_successful_at"],
                "feeds": after["refresh"]["feeds"], "interpretation_count": len(after["interpretations"]),
                "analysis_provider": after["analysis_provider"], "fit_unchanged": True,
                "source_dates": [{"title": a["title"], "source_url": a["source_url"],
                    "published_at": a["published_at"], "fetched_at": a["fetched_at"]} for a in after["articles"]]}
            (OUTPUT / "live-trends.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"external_sources": len(proof["feeds"]), "articles": proof["source_count"],
                "ai_cards": proof["interpretation_count"], "refresh_verified": True, "fit_unchanged": True}), flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
