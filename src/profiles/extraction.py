"""Conservative dictionary-based CV claims, always unverified until reviewed."""

import re
import unicodedata

from src.ingestion.catalog import load_role_catalog
from src.ingestion.selection import Catalog
from src.profiles.cv_parser import ParsedCV
from src.profiles.intake import validate_profile
from src.profiles.skill_normalizer import skill_index
from src.schemas.profile import ProfileSkill, SkillsProfile

# Reject whole clauses conservatively; this may miss positive skills in a negative sentence.
NON_CLAIM = re.compile(
    r"\b(no|not|never|without|lack|lacking|want|wish|hope|aspire|interested|learning|plan)\b",
    re.IGNORECASE,
)
PERSONAL_LINE = re.compile(
    r"^\s*(name|age|gender|sex|nationality|ethnicity|religion|date of birth|interests?|desired role|target role)\s*:",
    re.IGNORECASE,
)


def extract_profile(
    parsed: ParsedCV, profile_id: str, *, catalog: Catalog | None = None
) -> SkillsProfile:
    catalog = catalog if catalog is not None else load_role_catalog()
    index = skill_index(catalog.taxonomy)
    patterns = [
        (
            re.compile(
                r"(?<!\w)" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?!\w)",
                re.IGNORECASE,
            ),
            skill,
        )
        for alias, skill in sorted(index.items())
    ]
    evidence = {}
    for page_number, page in enumerate(parsed.pages, 1):
        for line_number, line in enumerate(page.splitlines(), 1):
            line = unicodedata.normalize("NFKC", line).strip()
            if PERSONAL_LINE.match(line):
                continue
            for clause in re.split(r"[!?;]+|(?<!\w)\.|\.(?!\w)", line):
                # These catalog skill names are positive claims, not an
                # aspiration to learn another skill.
                claim_context = re.sub(r"\b(?:Active Learning|Learning Strategies)\b", "", clause, flags=re.IGNORECASE)
                if NON_CLAIM.search(claim_context):
                    continue
                hits = []
                for pattern, skill in patterns:
                    # A computing discipline name alone does not establish the
                    # catalog's scientific-methods skill. Preserve offsets.
                    candidate = re.sub(r"\b(?:computer|data)\s+science\b",
                        lambda match: " " * len(match.group()), clause,
                        flags=re.IGNORECASE) if skill.label == "Science" else clause
                    for match in pattern.finditer(candidate):
                        hits.append((match.end() - match.start(), match.start(), match.end(), skill))
                software_spans = []
                for _, start, end, skill in sorted(hits, key=lambda hit: (-hit[0], hit[1], hit[3].skill_id)):
                    # Do not invent an additional generic tool from text inside
                    # a longer, exact software name (e.g. SAP ERP Financials).
                    if getattr(skill, "kind", None) == "software":
                        if any(left <= start and end <= right for left, right in software_spans):
                            continue
                        software_spans.append((start, end))
                    spans = evidence.setdefault(skill.skill_id, [])
                    span = f"Page {page_number}, line {line_number}: {clause.strip()[:500]}"
                    if span not in spans and len(spans) < 5:
                        spans.append(span)

    skills = {s.skill_id: s for s in catalog.taxonomy.skills}
    return validate_profile(
        SkillsProfile(
            profile_id=profile_id,
            skills=[
                ProfileSkill(
                    skill_id=skill_id, label=skills[skill_id].label, evidence=spans
                )
                for skill_id, spans in sorted(evidence.items())
            ],
            warnings=[
                "CV claims are unverified. Review skills and any estimated levels before matching.",
                "Dictionary extraction may miss context, negation or unsupported skills; typed input is available.",
            ],
        ),
        catalog,
    )
