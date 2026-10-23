"""Measure automatic upload separately from the explicit reviewed benchmark."""

import argparse
import json

from scripts.create_high_match_cv import OUTPUT, ROLE
from scripts.verify_cv_examples import request
from src.backend import CareerBackend
from src.profiles.intake import create_profile_from_cv
from src.schemas.profile import SkillsProfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    backend = CareerBackend()
    specified = SkillsProfile.model_validate_json((OUTPUT / "reviewed_profile.json").read_text())
    levels = {s.skill_id: s.level for s in specified.skills}
    report = {"fictional": True, "role_id": ROLE, "role_title": "Search Marketing Strategists",
        "score_method": "reviewed_onet_fit_v5", "format_checks": []}
    for extension in ("pdf", "docx", "txt"):
        path = OUTPUT / ("rina_search_marketing." + extension)
        profile = create_profile_from_cv("synthetic:rina_search_marketing", path.read_bytes(), path.name, catalog=backend.catalog)
        assert {s.skill_id for s in profile.skills} == set(levels), "Document skill set differs from checklist"
        profile = profile.model_copy(update={"skills": [s.model_copy(update={
            "level": levels[s.skill_id], "confirmation": "confirmed"}) for s in profile.skills]})
        match = backend.matcher.match_role(profile, ROLE)
        assert match.fit_score > 90
        report["format_checks"].append({"file": path.name, "skills": len(profile.skills), "reviewed_fit": match.fit_score})
        if extension == "pdf":
            (OUTPUT / "reviewed_profile.json").write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
            report["reviewed_score"] = match.fit_score
            report["reviewed_rank"] = next(r.rank for r in backend.matcher.match(profile) if r.role_id == ROLE)
    if args.live:
        base = "http://127.0.0.1:8000"
        path = OUTPUT / "rina_search_marketing.pdf"
        data = request(base, "/profiles/upload", method="POST", body=path.read_bytes(), headers={"X-Filename": path.name})
        headers = {"X-Session-ID": data["session_id"], "Content-Type": "application/json"}
        report["automatic_assessment"] = data["profile"].get("assessment_status")
        skills = [{**s, "confirmation": "confirmed"} for s in data["profile"]["skills"]]
        for label, explicit_levels in (("automatic_levels", False), ("checklist_levels", True)):
            if explicit_levels:
                skills = [{**s, "level": levels[s["skill_id"]], "level_assessment": None} for s in skills]
            reviewed = request(base, "/profiles/current", method="PATCH", headers=headers,
                body=json.dumps({"revision": data["revision"], "skills": skills, "desired_role_id": ROLE}).encode())
            data["revision"] = reviewed["revision"]
            rows = request(base, "/matches?revision=" + str(data["revision"]), headers=headers)["matches"]
            match = next(row for row in rows if row["role_id"] == ROLE)
            report[label] = {"score": match["fit_score"], "rank": match["rank"], "skill_count": len(skills)}
        assert report["checklist_levels"]["score"] > 90
    (OUTPUT / "test_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
