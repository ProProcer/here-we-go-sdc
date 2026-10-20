"""Small auditable task-based partial-credit policy, not proof of another skill."""

from decimal import Decimal

from src.schemas.profile import SkillsProfile, TransferContribution
from src.schemas.role import RoleCatalog

PARTIAL_CREDIT = Decimal("0.25")


def transferable_requirements(
    profile: SkillsProfile, catalog: RoleCatalog, role_id: str, covered: set[str]
) -> list[TransferContribution]:
    requirements = {r.skill_id: r for r in catalog.role_skills if r.role_id == role_id}
    # Directly required skills are already scored in coverage and cannot earn a second contribution.
    sources = {
        s.skill_id: s
        for s in profile.skills
        if s.confirmation in {"self_reported", "confirmed"}
        and s.skill_id not in requirements
    }
    role = next(r for r in catalog.roles if r.role_id == role_id)
    tasks = sorted(
        (t for t in catalog.taxonomy.tasks if t.task_id in role.task_ids),
        key=lambda t: t.task_id,
    )
    used = set()
    contributions = []
    for target in sorted(set(requirements) - covered):
        candidates = [
            (source, task.task_id)
            for task in tasks
            if target in task.skill_ids
            for source in sorted(sources)
            if source in task.skill_ids and source not in used
        ]
        if not candidates or requirements[target].importance == 0:
            continue
        source, task_id = min(candidates)
        used.add(source)
        contributions.append(
            TransferContribution(
                source_skill_id=source,
                target_skill_id=target,
                task_id=task_id,
                partial_credit=float(PARTIAL_CREDIT),
                weighted_contribution=float(
                    Decimal(str(requirements[target].importance)) * PARTIAL_CREDIT
                ),
                evidence=sources[source].evidence,
                reason="Related skill in the same catalog task; illustrative 25% credit, target remains a gap.",
            )
        )
    return contributions
