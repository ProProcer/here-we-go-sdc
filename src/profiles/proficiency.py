"""Transparent application comparison with published O*NET general-skill levels."""

# Application proxy, not an official crosswalk or measured individual rating.
LEVEL_POINTS = {"beginner": 2.0, "intermediate": 4.0, "advanced": 6.0}


def compare_proficiency(requirements, supported, skills):
    comparisons = []
    earned = 0.0
    total = sum(row.importance for row in requirements)
    for requirement in requirements:
        skill = supported.get(requirement.skill_id)
        required = None if requirement.level_suppressed else requirement.source_level
        level = skill.level if skill else "unknown"
        points = LEVEL_POINTS.get(level)
        if skill is None:
            credit, status = 0.0, "skill_unconfirmed"
        elif required is None:
            credit, status = 1.0, "required_level_unavailable"
        elif required == 0:
            credit, status = 1.0, "compared"
        elif points is None:
            credit, status = 0.0, "profile_level_unassessed"
        else:
            credit = min(1.0, points / required) if required > 0 else 1.0
            status = "compared"
        earned += requirement.importance * credit
        comparisons.append({"skill_id": requirement.skill_id,
            "label": skills[requirement.skill_id].label,
            "importance": requirement.importance, "required_source_level": required,
            "profile_level": level, "profile_level_proxy": points,
            "fulfilment": credit, "status": status})
    return comparisons, earned / total if total else 0.0
