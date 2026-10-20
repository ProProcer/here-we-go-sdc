"""Explicit illustrative interest labels; never infer interests from CV prose."""

from src.profiles.skill_normalizer import normalize_key

ROLE_INTERESTS = {
    "role:data_analyst": {"analytics", "data analysis", "statistics"},
    "role:business_analyst": {"business analysis", "business", "requirements analysis"},
    "role:it_support_specialist": {
        "it support",
        "technical support",
        "troubleshooting",
    },
}


def preference_alignment(
    role_id: str, interests: list[str]
) -> tuple[float | None, list[str]]:
    recognized = set().union(*ROLE_INTERESTS.values())
    supplied = {normalize_key(value) for value in interests} & recognized
    if not supplied:
        return None, []
    matched = sorted(supplied & ROLE_INTERESTS.get(role_id, set()))
    return len(matched) / len(supplied), matched
