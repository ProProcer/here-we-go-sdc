"""Deterministic reviewed fit with separately explained partial transfer credit."""

from decimal import ROUND_HALF_UP, Decimal

from src.ingestion.catalog import load_role_catalog
from src.profiles.intake import validate_profile
from src.profiles.preferences import preference_alignment
from src.profiles.transferability import transferable_requirements
from src.schemas.profile import (
    RoleMatch,
    ScoreBreakdown,
    SkillContribution,
    SkillsProfile,
)
from src.schemas.role import RoleCatalog


def match_roles(
    profile: SkillsProfile,
    catalog: RoleCatalog | None = None,
    *,
    top_n: int | None = None,
) -> list[RoleMatch]:
    """Rank by full precision fit; append a target outside top_n with its original rank."""
    if top_n is not None and (
        isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1
    ):
        raise ValueError("top_n must be a positive integer")
    catalog = catalog if catalog is not None else load_role_catalog()
    # Revalidate incoming models because callers can mutate Pydantic instances.
    profile = validate_profile(
        SkillsProfile.model_validate(profile.model_dump()), catalog
    )
    available = {skill.skill_id: skill for skill in profile.skills}
    labels = {skill.skill_id: skill.label for skill in catalog.taxonomy.skills}
    sectors = {sector.sector_id: sector.label for sector in catalog.taxonomy.sectors}
    results = []
    for role in catalog.roles:
        matched, missing = [], []
        earned = Decimal(0)
        total = Decimal(0)
        requirements = sorted(
            (row for row in catalog.role_skills if row.role_id == role.role_id),
            key=lambda row: row.skill_id,
        )
        for requirement in requirements:
            weight = Decimal(str(requirement.importance))
            total += weight
            skill = available.get(requirement.skill_id)
            covered = skill is not None and skill.confirmation in {
                "self_reported",
                "confirmed",
            }
            if covered:
                earned += weight
            reason = (
                "Supported by a self-reported or reviewed skill; proficiency is not assessed."
                if covered
                else "Skill claim awaits review."
                if skill
                else "Not evidenced in the submitted profile."
            )
            item = SkillContribution(
                skill_id=requirement.skill_id,
                label=labels[requirement.skill_id],
                importance=requirement.importance,
                coverage=int(covered),
                weighted_contribution=float(weight) if covered else 0,
                evidence=skill.evidence if skill else [],
                reason=reason,
            )
            (matched if covered else missing).append(item)
        coverage = earned / total if total else Decimal(0)
        transfers = transferable_requirements(
            profile, catalog, role.role_id, {s.skill_id for s in matched}
        )
        transfer_weight = sum(
            (Decimal(str(t.weighted_contribution)) for t in transfers), Decimal(0)
        )
        transfer = transfer_weight / total if total else Decimal(0)
        readiness = coverage + transfer
        preference, matched_interests = preference_alignment(
            role.role_id, profile.interests
        )
        readiness_weight = Decimal("0.9") if preference is not None else Decimal(1)
        preference_weight = 1 - readiness_weight
        score = (
            (
                readiness_weight * readiness
                + preference_weight * Decimal(str(preference or 0))
            )
            if total
            else Decimal(0)
        )
        warnings = [
            *profile.warnings,
            "Illustrative fit heuristic, not a hiring probability or proficiency assessment.",
            "Missing or unverified skills are unconfirmed, not proof of inability.",
        ]
        if preference is None:
            warnings.append("No recognized interests; readiness receives 100% weight.")
        if catalog.synthetic:
            warnings.append("Role requirements and importance weights are synthetic.")
        if not total:
            warnings.append("No positive requirement weights; score defaults to zero.")
        if not profile.skills:
            warnings.append(
                "No supported skills supplied; review or add skills before interpreting scores."
            )
        result = RoleMatch(
            role_id=role.role_id,
            role_title=role.role_title,
            sector_id=role.sector_id,
            sector=sectors[role.sector_id],
            catalog_synthetic=catalog.synthetic,
            rank=1,
            fit_score=float(
                (score * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ),
            score_breakdown=ScoreBreakdown(
                earned_weight=float(earned),
                total_weight=float(total),
                required_skill_coverage=float(coverage),
                transferability=float(transfer),
                readiness=float(readiness),
                preferences=preference,
                readiness_weight=float(readiness_weight),
                preference_weight=float(preference_weight),
            ),
            matched_skills=matched,
            missing_skills=missing,
            manually_selected=profile.desired_role_id == role.role_id,
            warnings=warnings,
            transferable_skills=transfers,
            matched_interests=matched_interests,
        )
        results.append((score, result))
    results.sort(key=lambda item: (-item[0], item[1].role_id))
    ranked = [
        result.model_copy(update={"rank": rank})
        for rank, (_, result) in enumerate(results, start=1)
    ]
    if top_n is None:
        return ranked
    selected = ranked[:top_n]
    target = next((r for r in ranked[top_n:] if r.manually_selected), None)
    if target:
        selected.append(target.model_copy(update={"pinned": True}))
    return selected
