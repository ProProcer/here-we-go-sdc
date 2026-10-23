"""Check layout invariance using the real parser and CV skill extraction."""

import json
import time

from scripts.create_cv_examples import DESTINATION
from scripts.create_cv_layout_examples import OUTPUT
from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile_from_cv


def main():
    catalog = real_catalog()
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    results = []
    for case in manifest:
        start = time.monotonic()
        source = DESTINATION / case["source"]
        expected = create_profile_from_cv("synthetic:layout_source", source.read_bytes(), source.name, catalog=catalog)
        try:
            path = OUTPUT / case["file"]
            actual = create_profile_from_cv("synthetic:layout_actual", path.read_bytes(), path.name, catalog=catalog)
            missing = {s.label for s in expected.skills} - {s.label for s in actual.skills}
            extra = {s.label for s in actual.skills} - {s.label for s in expected.skills}
            row = {**case, "status": "passed" if not missing and not extra else "different",
                "missing": sorted(missing), "extra": sorted(extra), "skills": len(actual.skills)}
        except (ValueError, OSError) as error:
            row = {**case, "status": "failed", "error": str(error)}
        row["seconds"] = round(time.monotonic() - start, 2)
        results.append(row)
        print(json.dumps(row), flush=True)
        (OUTPUT / "test_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    save_readme(results)
    if any(row["status"] != "passed" for row in results):
        raise SystemExit(1)


def save_readme(results):
    lines = ["# CV composition and styling tests", "",
        "These fictional documents vary layout, section ordering and styling rather than just file extension.",
        "ATS-friendly describes the intended plain, single-column structure; no commercial ATS vendor was tested.", "",
        "Each variant is compared with its source CV in ../domain_examples. All skills must be retained",
        "and no extra skills introduced. The scan uses real local OCR; the other PDFs contain text.", "",
        "| CV | Composition | Extracted skills | Check |", "| --- | --- | --- | --- |"]
    for row in results:
        lines.append(f"| [{row['file']}]({row['file']}) | {row['composition']} | {row.get('skills', '-')} | {row['status']} |")
    lines.extend(["", "Run `python -m scripts.create_cv_layout_examples` to regenerate and",
        "`python -m scripts.verify_cv_layout_examples` to repeat the checks.",
        "Full differences and timings: [test_results.json](test_results.json).", ""])
    (OUTPUT / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
