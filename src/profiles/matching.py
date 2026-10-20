"""Coverage-only baseline: no transferability, preferences or outlook blending."""

from decimal import Decimal, ROUND_HALF_UP

from src.ingestion.catalog import load_role_catalog
from src.profiles.intake import validate_profile
from src.schemas.profile import RoleMatch, ScoreBreakdown, SkillContribution, SkillsProfile
from src.schemas.role import RoleCatalog


def match_roles(profile: SkillsProfile, catalog: RoleCatalog | None = None) -> list[RoleMatch]:
    """Rank by exact coverage, then role ID; round displayed scores half-up."""
    catalog = catalog if catalog is not None else load_role_catalog()
    # Revalidate incoming models because callers can mutate Pydantic instances.
    profile = validate_profile(SkillsProfile.model_validate(profile.model_dump()), catalog)
    available = {skill.skill_id: skill for skill in profile.skills}
    labels = {skill.skill_id: skill.label for skill in catalog.taxonomy.skills}
    sectors = {sector.sector_id: sector.label for sector in catalog.taxonomy.sectors}
    results = []
    for role in catalog.roles:
        matched, missing = [], []
        earned = Decimal(0)
        total = Decimal(0)
        requirements = sorted((row for row in catalog.role_skills if row.role_id == role.role_id),
                              key=lambda row: row.skill_id)
        for requirement in requirements:
            weight = Decimal(str(requirement.importance))
            total += weight
            skill = available.get(requirement.skill_id)
            covered = skill is not None and skill.confirmation in {"self_reported", "confirmed"}
            if covered:
                earned += weight
            reason = ("Supported by a self-reported or reviewed skill; proficiency is not assessed." if covered
                      else "Skill claim awaits review." if skill else "Not evidenced in the submitted profile.")
            item = SkillContribution(
                skill_id=requirement.skill_id, label=labels[requirement.skill_id],
                importance=requirement.importance, coverage=int(covered),
                weighted_contribution=float(weight) if covered else 0,
                evidence=skill.evidence if skill else [], reason=reason,
            )
            (matched if covered else missing).append(item)
        coverage = earned / total if total else Decimal(0)
        warnings = [*profile.warnings,
                    "Coverage-only heuristic; transferability and preferences are not scored.",
                    "Missing or unverified skills are unconfirmed, not proof of inability."]
        if catalog.synthetic:
            warnings.append("Role requirements and importance weights are synthetic.")
        if not total:
            warnings.append("No positive requirement weights; score defaults to zero.")
        if not profile.skills:
            warnings.append("No supported skills supplied; review or add skills before interpreting scores.")
        result = RoleMatch(
            role_id=role.role_id, role_title=role.role_title, sector_id=role.sector_id,
            sector=sectors[role.sector_id], catalog_synthetic=catalog.synthetic, rank=1,
            fit_score=float((coverage * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            score_breakdown=ScoreBreakdown(earned_weight=float(earned), total_weight=float(total),
                                           required_skill_coverage=float(coverage)),
            matched_skills=matched, missing_skills=missing,
            manually_selected=profile.desired_role_id == role.role_id, warnings=warnings,
        )
        results.append((coverage, result))
    results.sort(key=lambda item: (-item[0], item[1].role_id))
    return [result.model_copy(update={"rank": rank})
            for rank, (_, result) in enumerate(results, start=1)]
