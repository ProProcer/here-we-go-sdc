"""Conservative dictionary-based CV claims, always unverified until reviewed."""

import re
import unicodedata

from src.ingestion.catalog import load_role_catalog
from src.profiles.cv_parser import ParsedCV
from src.profiles.intake import validate_profile
from src.profiles.skill_normalizer import skill_index
from src.schemas.profile import ProfileSkill, SkillsProfile
from src.schemas.role import RoleCatalog

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
    parsed: ParsedCV, profile_id: str, *, catalog: RoleCatalog | None = None
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
            for clause in re.split(r"[.!?;]+", line):
                if NON_CLAIM.search(clause):
                    continue
                for pattern, skill in patterns:
                    if pattern.search(clause):
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
                "CV claims are unverified. Review skills before matching; levels remain unknown.",
                "Dictionary extraction may miss context, negation or unsupported skills; typed input is available.",
            ],
        ),
        catalog,
    )
