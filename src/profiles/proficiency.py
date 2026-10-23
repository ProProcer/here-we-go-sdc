"""Job-relative proficiency suitability with explicit occupational software proxies."""

# Conservative fallback strengths when a job has no usable level requirement.
# These are application weights, not inferred requirements.
ALIGNMENT_LEVEL_FACTORS = {"unknown": 0.4, "beginner": 0.6, "intermediate": 0.8, "advanced": 1.0}

# Application proxy, not an official crosswalk or measured individual rating.
LEVEL_POINTS = {"beginner": 2.0, "intermediate": 4.0, "advanced": 6.0}

# Product inference rules: software categories use a related occupational skill
# rating as a proxy. These are NEVER represented as published software ratings.
SOFTWARE_LEVEL_PROXIES = {
    "group:onet_2_e_6_f": "Programming",  # database/query
    "group:onet_2_e_7_b": "Programming",  # development environments
    "group:onet_2_e_7_d": "Programming",  # GUI development
    "group:onet_2_e_7_e": "Programming",  # object/component development
    "group:onet_2_e_7_h": "Programming",  # web development
    "group:onet_2_e_4_i": "Mathematics",  # spreadsheets
    "group:onet_2_e_9_d": "Mathematics",  # analytical/scientific
    "group:onet_2_e_9_c": "Operations Analysis",  # CAD
    "group:onet_2_e_9_m": "Operations Analysis",  # CAD/CAM
    "group:onet_2_e_9_i": "Monitoring",  # medical software
}
UNKNOWN_TARGET = {"required_level_points": None, "required_level_label": None,
    "requirement_basis": "unavailable", "proxy_skill_id": None,
    "proxy_skill_label": None, "proxy_source_level": None}


def level_label(points):
    return "beginner" if points <= 2 else "intermediate" if points <= 4 else "advanced"


def alignment_targets(requirements, associations, skills):
    """Keep published general levels separate from inferred software bands."""
    targets = {}
    by_label = {skills[row.skill_id].label: row for row in requirements}
    for row in requirements:
        if row.source_level is not None and not row.level_suppressed:
            targets[row.skill_id] = {**UNKNOWN_TARGET,
                "required_level_points": row.source_level,
                "required_level_label": level_label(row.source_level),
                "requirement_basis": "published_general"}
    for association in associations:
        proxy = by_label.get(SOFTWARE_LEVEL_PROXIES.get(association.group_id))
        if proxy is None or proxy.level_suppressed or proxy.source_level is None or proxy.source_level <= 0:
            continue
        label = level_label(proxy.source_level)
        points = LEVEL_POINTS[label]
        existing = targets.get(association.skill_id, UNKNOWN_TARGET)
        if existing["required_level_points"] is None or points > existing["required_level_points"]:
            targets[association.skill_id] = {"required_level_points": points,
                "required_level_label": label, "requirement_basis": "estimated_from_general",
                "proxy_skill_id": proxy.skill_id, "proxy_skill_label": skills[proxy.skill_id].label,
                "proxy_source_level": proxy.source_level}
    return targets


def level_suitability(level, target):
    """Reward level agreement, penalizing shortfalls more than surplus skill."""
    points = LEVEL_POINTS.get(level)
    required = target["required_level_points"]
    if points is None:
        return 0.2  # presence evidence without an assessed level
    if required is None:
        return 0.2 + 0.3 * ALIGNMENT_LEVEL_FACTORS[level]
    if points < required:
        suitability = (points / required) ** 2
    else:
        suitability = 1 / (1 + 0.35 * (points - required) / 2)
    return 0.2 + 0.8 * suitability


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
