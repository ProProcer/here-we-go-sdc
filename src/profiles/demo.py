"""Reproduce Person 2's offline handoff: python -m src.profiles.demo."""

import json
from pathlib import Path

from src.profiles.intake import create_profile
from src.profiles.matching import match_roles

ROOT = Path(__file__).resolve().parents[2]


def example_responses() -> list[dict]:
    fixtures = json.loads(
        (ROOT / "data/synthetic/profiles/typed_inputs.json").read_text(encoding="utf-8")
    )
    responses = []
    for fixture in fixtures:
        profile = create_profile(
            fixture["profile_id"],
            fixture["entries"],
            desired_role_id=fixture.get("desired_role_id"),
            interests=fixture.get("interests"),
        )
        responses.append(
            {
                "profile": profile.model_dump(mode="json"),
                "matches": [
                    match.model_dump(mode="json") for match in match_roles(profile)
                ],
            }
        )
    return responses


if __name__ == "__main__":
    print(json.dumps(example_responses(), indent=2))
