"""Verify authored fictional CV files; --live also exercises the running app."""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.create_cv_examples import DESTINATION
from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile_from_cv
from src.profiles.onet_matching import OnetMatcher
from src.profiles.samples import SAMPLE_PATH

TARGETS = {
    "data_analytics": "Business Intelligence Analysts",
    "web_development": "Web Developers",
    "healthcare_nursing": "Registered Nurses",
    "finance_accounting": "Accountants and Auditors",
    "mechanical_engineering": "Mechanical Engineers",
}


def request(base, path, *, method="GET", body=None, headers=None):
    req = Request(base + "/api/v2" + path, data=body, method=method, headers=headers or {})
    with urlopen(req, timeout=210) as response:
        return json.load(response)



def live_check(example, base, matcher):
    filename = example["primary_file"]
    start = time.monotonic()
    row = {"domain": example["domain"], "file": filename}
    try:
        uploaded = request(base, "/profiles/upload", method="POST",
            body=(DESTINATION / filename).read_bytes(), headers={"X-Filename": filename})
        profile = uploaded["profile"]
        assessment = profile.get("assessment_status")
        skills = [{**skill, "confirmation": "confirmed"} for skill in profile["skills"]]
        reviewed = request(base, "/profiles/current", method="PATCH",
            body=json.dumps({"revision": uploaded["revision"], "skills": skills}).encode(),
            headers={"X-Session-ID": uploaded["session_id"], "Content-Type": "application/json"})
        matches = request(base, "/matches?revision=" + str(reviewed["revision"]),
            headers={"X-Session-ID": uploaded["session_id"]})["matches"]
        # Also inspect the domain occupation's full rank rather than just
        # reporting a favorable-looking shortlist.
        from src.schemas.profile import SkillsProfile
        all_matches = matcher.match(SkillsProfile.model_validate(reviewed["profile"]))
        target = next(r for r in all_matches if r.role_title == TARGETS[example["id"]])
        row.update(status="passed" if assessment and assessment["status"] == "completed" else "assessment_failed",
            extracted_skills=len(skills), assessment=assessment,
            top_five=[{"title": r["role_title"], "score": r["fit_score"]} for r in matches[:5]],
            domain_occupation=target.role_title, domain_occupation_rank=target.rank,
            domain_occupation_score=target.fit_score)
    except (HTTPError, URLError, ValueError, OSError) as error:
        row.update(status="failed", error=str(error))
    row["seconds"] = round(time.monotonic() - start, 2)
    return row


def verify(base=None):
    catalog = real_catalog()
    matcher = OnetMatcher(catalog)
    manifest = json.loads((DESTINATION / "manifest.json").read_text())
    report = {"fictional_documents_only": True, "format_checks": [], "live_checks": []}
    next_live = 0
    for example in manifest:
        canonical = create_profile_from_cv("synthetic:cv_format_check",
            (DESTINATION / (example["id"] + ".txt")).read_bytes(), "source.txt", catalog=catalog)
        expected = {s.skill_id for s in canonical.skills}
        for filename in example["files"]:
            start = time.monotonic()
            row = {"file": filename}
            try:
                profile = create_profile_from_cv("synthetic:cv_format_check",
                    (DESTINATION / filename).read_bytes(), filename, catalog=catalog)
                actual = {s.skill_id for s in profile.skills}
                row.update(status="passed" if actual == expected else "skill_difference",
                    skill_count=len(actual), missing_vs_txt=sorted(expected - actual),
                    extra_vs_txt=sorted(actual - expected))
            except (ValueError, OSError) as error:
                row.update(status="failed", error=str(error))
            row["seconds"] = round(time.monotonic() - start, 2)
            report["format_checks"].append(row)
            print(json.dumps(row), flush=True)
        if base:
            delay = max(0, next_live - time.monotonic())
            if delay:
                print(f"Waiting {delay:.0f}s to respect Groq's token-per-minute quota.", flush=True)
                time.sleep(delay)
            next_live = time.monotonic() + 65
            row = live_check(example, base, matcher)
            report["live_checks"].append(row)
            print(json.dumps(row), flush=True)

    original = create_profile_from_cv("synthetic:original_cv_check",
        SAMPLE_PATH.with_suffix(".pdf").read_bytes(), "graduate.pdf", catalog=catalog)
    report["original_sample_pdf"] = {"status": "passed", "skill_count": len(original.skills),
        "path": "../graduate.pdf", "download_url": "/api/v2/samples/graduate.pdf"}
    return report


def save_report(report):
    report["known_limits"] = [
        "HTML and CSS abbreviations now resolve to existing canonical database records, and dotted tool names such as Node.js are preserved during sentence parsing.",
        "Format consistency compares extracted skills with TXT; it does not establish that every claim was recognized.",
        "The verifier spaces live calls for the observed Groq token quota. Failed live cases can be retried after cooldown, preserving the original attempt.",
        "An intended domain occupation in the top five does not guarantee it is the top recommendation; full top-five lists are retained.",
    ]
    (DESTINATION / "test_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Fictional CV test files", "",
        "All people, employers, contact details and qualifications are fictional.", "",
        "Each domain has PDF, DOCX and TXT versions of the same CV.",
        "Accounting also includes PNG; mechanical engineering includes JPG.", "",
        "The original in-app sample is [graduate.pdf](../graduate.pdf), available at",
        "http://localhost:8000/api/v2/samples/graduate.pdf while the app runs.", "",
        "## Files", "", "| Domain | PDF | Word | Text | Image |", "| --- | --- | --- | --- | --- |"]
    manifest = json.loads((DESTINATION / "manifest.json").read_text())
    for example in manifest:
        stem = example["id"]
        image = next((name for name in example["files"] if name.endswith((".jpg", ".png"))), None)
        lines.append(f"| {example['domain']} | [PDF]({stem}.pdf) | [DOCX]({stem}.docx) | [TXT]({stem}.txt) | "
            + (f"[Image]({image})" if image else "-") + " |")
    checks = report["format_checks"]
    lines.extend(["", "## Actual verification", "",
        f"File parsing and skill consistency: {sum(r['status'] == 'passed' for r in checks)}/{len(checks)} passed.",
        "All formats were processed by the app's real document workers, including local OCR for images.",
        "Skill sets were compared with each domain's TXT source; AI is not involved in this comparison.", "",
        "Live tests uploaded one file per domain, called AI assessment, explicitly confirmed extracted",
        "skills for this automated test, and requested recommendations without target or interest boosts.", "",
        "| Domain / upload format | AI provider / status | Top recommendation | Domain occupation rank |", "| --- | --- | --- | --- |"])
    for row in report["live_checks"]:
        assessment = row.get("assessment") or {}
        top = row.get("top_five", [{}])[0].get("title", "Unavailable")
        lines.append(f"| {row['domain']} / {Path(row['file']).suffix} | {assessment.get('provider', '-')} / {assessment.get('status', row['status'])} | {top} | {row.get('domain_occupation_rank', '-')} |")
    lines.extend(["", "## Findings and limits", ""])
    lines.extend("- " + note for note in report["known_limits"])
    lines.extend(["", "Reproduce with `python -m scripts.create_cv_examples` and",
        "`python -m scripts.verify_cv_examples --live` (app running on port 8000).",
        "The verifier spaces live calls to respect the observed Groq quota;",
        "`--retry-failed` repeats only failed live cases after a cooldown."])
    lines.extend(["", "These tests distinguish successful upload/assessment from recommendation relevance.",
        "The named domain occupation rank is reported even when it is outside the top ten.",
        "A generated CV is test input, not evidence of qualification or licensure.",
        "Full scores, timings, differences and failures are in [test_results.json](test_results.json).", ""])
    (DESTINATION / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--retry-failed", action="store_true",
        help="Retry only failed live checks in the saved report, pacing calls for Groq quota.")
    args = parser.parse_args()
    if args.retry_failed:
        report = json.loads((DESTINATION / "test_results.json").read_text())
        matcher = OnetMatcher(real_catalog())
        manifest = json.loads((DESTINATION / "manifest.json").read_text())
        for index, previous in enumerate(report["live_checks"]):
            if previous["status"] == "passed":
                continue
            print("Waiting 65s before retry to respect Groq token quota.", flush=True)
            time.sleep(65)
            example = next(e for e in manifest if e["primary_file"] == previous["file"])
            updated = live_check(example, "http://127.0.0.1:8000", matcher)
            updated["previous_attempts"] = [*previous.get("previous_attempts", []),
                {key: value for key, value in previous.items() if key != "previous_attempts"}]
            report["live_checks"][index] = updated
            print(json.dumps(updated), flush=True)
    else:
        report = verify("http://127.0.0.1:8000" if args.live else None)
    save_report(report)
    print("Saved CV verification report.")
    if any(row["status"] != "passed" for row in report["format_checks"] + report["live_checks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
