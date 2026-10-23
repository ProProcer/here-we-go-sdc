"""Verify Rina through the real UI and live AI, without editing any level."""

import hashlib
import json
import os
import sys
import time

from playwright.sync_api import expect, sync_playwright

from scripts.create_high_match_cv import OUTPUT, ROLE


def main():
    # Leave headroom after another live inference on the same free-tier account.
    from pathlib import Path
    prior = Path(".role3-review/rina_browser_last_attempt.txt")
    if not prior.exists():
        prior.write_text("Live UI retry quota checkpoint.")
    delay = max(0, 65 - (time.time() - prior.stat().st_mtime)) if prior.exists() else 0
    if delay:
        print(f"Waiting {delay:.0f}s for Groq token quota before live UI verification.", flush=True)
        time.sleep(delay)
    path = OUTPUT / "rina_search_marketing.pdf"
    with sync_playwright() as playwright:
        channel = os.getenv("BROWSER_CHANNEL") or ("msedge" if sys.platform == "win32" else None)
        browser = playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1080})
            page.goto("http://127.0.0.1:8000")
            page.locator("#cv-file").set_input_files(str(path))
            expect(page.locator("#review")).to_be_visible(timeout=180000)
            expect(page.locator("#ai-assessment-status")).to_contain_text("39 skills")
            expect(page.locator("#ai-assessment-status")).to_contain_text("Groq")
            expect(page.locator(".skill-name").filter(has_text="AI estimate:")).to_have_count(39)
            page.locator("#confirm-all").check()
            page.locator("#review-next").click()
            page.locator("#find-matches").click()
            expect(page.locator("#featured-match h2")).to_have_text("Search Marketing Strategists", timeout=30000)
            expect(page.locator("#busy")).to_be_hidden(timeout=30000)
            displayed_fit = float(page.locator("#featured-match .fit-orbit strong").inner_text())
            assert displayed_fit > 90, displayed_fit
            page.screenshot(path=str(OUTPUT / "automatic_upload.png"), full_page=True)
            proof = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "provider": "groq", "assessed_skills": 39,
                "extracted_skills": 39, "displayed_score": displayed_fit,
                "rank": 1, "manual_level_overrides": 0, "target_role_boost": False,
                "flow": "Upload unchanged PDF; confirm all skills; explore without a goal"}
            (OUTPUT / "automatic_upload_verification.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(proof), flush=True)
        finally:
            browser.close()
            prior.touch()


if __name__ == "__main__":
    main()
