"""Generate a fictional, fully specified proficiency benchmark CV."""

import csv
import json
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.shared import Pt
from pypdf import PdfReader, PdfWriter

from scripts.create_cv_examples import pdf_bytes
from src.backend import CareerBackend
from src.profiles.proficiency import LEVEL_POINTS, UNKNOWN_TARGET, level_suitability
from src.profiles.samples import SAMPLE_PATH

OUTPUT = SAMPLE_PATH.parent / "high_match"
ROLE = "role:onet_13_1161_01"
EVIDENCE = {
    "Reading Comprehension": "Independently interpreted search documentation and campaign briefs.",
    "Active Listening": "Summarized client requirements and checked understanding during discovery calls.",
    "Writing": "Independently wrote landing-page briefs and monthly performance narratives.",
    "Speaking": "Presented campaign results and explained attribution limitations to clients.",
    "Mathematics": "Calculated conversion rates, percentage changes and acquisition costs.",
    "Critical Thinking": "Compared competing explanations for organic traffic changes before acting.",
    "Active Learning": "Applied a newly documented reporting method to an independent campaign review.",
    "Learning Strategies": "Selected exercises and practice datasets to improve reporting techniques.",
    "Monitoring": "Independently tracked ranking and conversion trends against campaign objectives.",
    "Social Perceptiveness": "Adapted explanations after observing stakeholder questions and confusion.",
    "Coordination": "Coordinated content, development and account teams for campaign releases.",
    "Persuasion": "Used campaign evidence to obtain agreement on revised content priorities.",
    "Negotiation": "Independently agreed delivery scope and deadlines with project stakeholders.",
    "Instructing": "Showed colleagues routine reporting steps using a prepared walkthrough.",
    "Service Orientation": "Resolved client reporting requests and checked that the response was useful.",
    "Complex Problem Solving": "Investigated a multistep indexing issue and verified the resulting fix.",
    "Operations Analysis": "Independently translated campaign needs into workflow and reporting requirements.",
    "Technology Design": "Independently configured a simple dashboard workflow to meet a client brief.",
    "Programming": "Independently maintained small scripts and web snippets for routine campaign tasks.",
    "Operations Monitoring": "Performed basic guided checks of scheduled campaign jobs using a checklist.",
    "Quality Control Analysis": "Performed basic guided checks of tracking tags against a prepared test sheet.",
    "Judgment and Decision Making": "Compared expected campaign benefit, cost and uncertainty before release.",
    "Systems Analysis": "Independently traced how tagging changes affected downstream campaign reports.",
    "Systems Evaluation": "Independently compared reporting outputs with agreed business objectives.",
    "Time Management": "Independently scheduled several concurrent campaign deliverables and reviews.",
    "Management of Financial Resources": "Tracked a small campaign allowance with supervisor approval.",
    "Management of Material Resources": "Organized shared campaign assets using a supervised checklist.",
    "Management of Personnel Resources": "Independently allocated routine campaign tasks and checked completion.",
}


def benchmark_profile(backend):
    requirements = backend.matcher.index.general[ROLE]
    general = {r.skill_id: r for r in requirements}
    affinity = backend.matcher.role_affinities[ROLE]
    targets = backend.matcher.level_targets[ROLE]
    tools = sorted((sid for sid, weight in affinity.items()
        if backend.matcher.skills[sid].kind == "software" and weight == 1
        and targets.get(sid, UNKNOWN_TARGET)["required_level_points"] is not None),
        key=lambda sid: -backend.matcher.distinctiveness[sid])
    ids = [*general, *tools]
    profile = backend.create_profile("synthetic:rina_search_marketing",
        [backend.matcher.skills[sid].label for sid in ids])
    total = sum(backend.matcher.distinctiveness[sid] for sid in ids)
    general_total = sum(row.importance for row in requirements)
    reviewed = []
    # This is an explicitly tailored synthetic test profile, not a model claim
    # about a real person. The score function itself is never modified here.
    for skill in profile.skills:
        def contribution(level):
            sid = skill.skill_id
            value = .65 * backend.matcher.distinctiveness[sid] / total * affinity[sid] * level_suitability(level, targets.get(sid, UNKNOWN_TARGET))
            requirement = general.get(sid)
            if requirement:
                required = requirement.source_level
                credit = 1 if required is None or required == 0 else min(1, LEVEL_POINTS[level] / required)
                value += .35 * requirement.importance / general_total * credit
            return value
        reviewed.append(skill.model_copy(update={"level": max(LEVEL_POINTS, key=contribution), "confirmation": "confirmed"}))
    return profile.model_copy(update={"skills": reviewed})


def main():
    backend = CareerBackend()
    profile = benchmark_profile(backend)
    general = [skill for skill in profile.skills if backend.matcher.skills[skill.skill_id].kind == "general"]
    tools = [skill for skill in profile.skills if backend.matcher.skills[skill.skill_id].kind == "software"]
    pages = ["\n".join([
        "RINA FARAH", "Search Marketing Strategist", "rina.farah@example.com | Kuala Lumpur, Malaysia",
        "FICTIONAL TEST CV - all people, employers and experience are invented.", "", "PROFILE",
        "Independent search-marketing practitioner with a deliberately comprehensive skill profile.",
        "This synthetic benchmark includes an explicit proficiency checklist for validation.", "",
        "EXPERIENCE", "Search Marketing Specialist | Fictional Cedar Digital | 2023 - 2026",
        "- Independently delivered technical site audits and routine content-priority reviews.",
        "- Maintained campaign reporting, tracking checks and client performance explanations.",
        "- Worked within agreed scope; complex strategic decisions remained with a supervisor.", "",
        "EDUCATION", "Diploma in Digital Marketing | Fictional Bay Institute | 2023", "",
        "TOOL PROFICIENCY AND EVIDENCE",
        *[f"{skill.label} - {skill.level.title()}: independently used in routine campaign work." for skill in tools], "",
        "PROJECT", "Fictional retail site audit and reporting refresh",
        "Delivered an audit log, content brief, reporting workbook and stakeholder walkthrough.",
    ])]
    for start in (0, 14):
        lines = ["RINA FARAH - SKILL EVIDENCE", "FICTIONAL TEST CV - continued", ""]
        for skill in general[start:start + 14]:
            lines.extend([skill.label + " - " + skill.level.title() + ": " + EVIDENCE[skill.label], ""])
        pages.append("\n".join(lines))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = OUTPUT / "rina_search_marketing"
    stem.with_suffix(".txt").write_text("\n\n".join(pages), encoding="utf-8")
    writer = PdfWriter()
    document = Document()
    document.styles["Normal"].font.size = Pt(9)
    document.styles["Normal"].paragraph_format.space_after = Pt(3)
    for index, page in enumerate(pages):
        writer.append(PdfReader(BytesIO(pdf_bytes(page))))
        if index:
            document.add_page_break()
        for line in page.splitlines():
            document.add_paragraph(line)
    with stem.with_suffix(".pdf").open("wb") as output:
        writer.write(output)
    document.save(stem.with_suffix(".docx"))
    with (OUTPUT / "proficiency_checklist.csv").open("w", newline="", encoding="utf-8") as output:
        rows = csv.writer(output)
        rows.writerow(["skill_id", "skill", "level"])
        rows.writerows((skill.skill_id, skill.label, skill.level) for skill in profile.skills)
    (OUTPUT / "reviewed_profile.json").write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    match = backend.matcher.match_role(profile, ROLE)
    print(json.dumps({"role": match.role_title, "score": match.fit_score, "skills": len(profile.skills), "pdf": str(stem.with_suffix('.pdf'))}))


if __name__ == "__main__":
    main()
