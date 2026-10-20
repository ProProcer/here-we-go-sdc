"""Validated typed-form intake and replacement-based human review."""

from src.ingestion.catalog import load_role_catalog
from src.profiles.skill_normalizer import normalize_entries
from src.schemas.profile import ProfileSkill, SkillsProfile
from src.schemas.role import RoleCatalog


def validate_profile(profile: SkillsProfile, catalog: RoleCatalog) -> SkillsProfile:
    skills = {skill.skill_id: skill for skill in catalog.taxonomy.skills}
    if profile.desired_role_id is not None and profile.desired_role_id not in {r.role_id for r in catalog.roles}:
        raise ValueError("Unknown desired role ID")
    for skill in profile.skills:
        if skill.skill_id not in skills:
            raise ValueError(f"Unknown skill ID: {skill.skill_id}")
        if skill.label != skills[skill.skill_id].label:
            raise ValueError(f"Use the canonical label for {skill.skill_id}")
    return profile


def create_profile(profile_id: str, entries: list[str], *, desired_role_id: str | None = None,
                   interests: list[str] | None = None, catalog: RoleCatalog | None = None) -> SkillsProfile:
    """Explicit typed entries are self-reported; proficiency remains unknown."""
    catalog = catalog if catalog is not None else load_role_catalog()
    normalized, unknown = normalize_entries(entries, catalog.taxonomy)
    profile = SkillsProfile(
        profile_id=profile_id, desired_role_id=desired_role_id, interests=interests or [],
        skills=[ProfileSkill(skill_id=skill.skill_id, label=skill.label,
                             evidence=[f"Typed skill entry: {entry}" for entry in evidence],
                             confirmation="self_reported") for skill, evidence in normalized],
        warnings=[f"Unsupported skill entry: {entry}" for entry in unknown],
    )
    return validate_profile(profile, catalog)


def review_profile(profile: SkillsProfile, skills: list[ProfileSkill | dict], *,
                   catalog: RoleCatalog | None = None) -> SkillsProfile:
    """Replace the full reviewed skill list; supports additions, removals and edits.

    Revalidation is deliberate: model_copy(update=...) alone skips validation.
    The original profile is preserved so the UI can compare before and after.
    """
    payload = profile.model_dump()
    payload["skills"] = [row.model_dump() if isinstance(row, ProfileSkill) else row for row in skills]
    return validate_profile(SkillsProfile.model_validate(payload),
                            catalog if catalog is not None else load_role_catalog())


def create_profile_from_cv(profile_id: str, content: bytes, filename: str, *,
                           catalog: RoleCatalog | None = None) -> SkillsProfile:
    """Parse a fictional document and propose unverified skills for human review."""
    from src.profiles.cv_parser import parse_cv
    from src.profiles.extraction import extract_profile

    return extract_profile(parse_cv(content, filename), profile_id, catalog=catalog)
