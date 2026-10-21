"""Shared real-catalog backend for Persons 2–4; no UI or HTTP implementation.

Run ``python -m src.backend`` for a deterministic fictional-profile example.
"""

from datetime import UTC, datetime

from src.ingestion.onet import ROOT, write_json
from src.ingestion.selection import real_catalog
from src.intelligence.outlook import get_outlook
from src.profiles.intake import create_profile, create_profile_from_cv, review_profile
from src.profiles.onet_matching import OnetMatcher
from src.reskilling.planner import build_learning_plan
from src.schemas.onet import OnetCatalog


class CareerBackend:
    """Share one validated snapshot across intake, matching, outlook and planning."""

    def __init__(
        self,
        catalog: OnetCatalog | None = None,
        *,
        course_store=None,
        search_provider=None,
    ):
        self.catalog = catalog if catalog is not None else real_catalog()
        self.matcher = OnetMatcher(self.catalog)
        self.course_store = course_store
        self.search_provider = search_provider

    def create_profile(self, profile_id, entries, **kwargs):
        return create_profile(profile_id, entries, catalog=self.catalog, **kwargs)

    def extract_profile(self, profile_id, content, filename):
        return create_profile_from_cv(
            profile_id, content, filename, catalog=self.catalog
        )

    def review_profile(self, profile, skills):
        return review_profile(profile, skills, catalog=self.catalog)

    def match(self, profile, *, top_n=10, policy=None):
        return self.matcher.match(profile, top_n=top_n, policy=policy)

    def outlook(self, role_id, scenario_id="baseline"):
        return get_outlook(role_id, scenario_id, catalog=self.catalog)

    def learning_plan(
        self,
        profile,
        role_id,
        scenario_id="baseline",
        *,
        selected_software_skill_ids=None,
        country="Malaysia",
        preferred_language="English",
        generated_at=None,
        policy=None,
    ):
        match = self.matcher.match_role(profile, role_id, policy=policy)
        return build_learning_plan(
            profile,
            match,
            scenario_id,
            catalog=self.catalog,
            course_store=self.course_store,
            search_provider=self.search_provider,
            selected_software_skill_ids=selected_software_skill_ids,
            country=country,
            preferred_language=preferred_language,
            generated_at=generated_at,
        )


def example_response():
    backend = CareerBackend()
    profile = backend.create_profile(
        "synthetic:backend_demo",
        ["Python", "SQL", "Tableau", "Reading Comprehension"],
        desired_role_id="role:onet_15_2051_01",
    )
    role_id = profile.desired_role_id
    match = backend.matcher.match_role(profile, role_id)
    selected = (
        [match.software_learning_options[0].skill_id]
        if match.software_learning_options
        else []
    )
    when = datetime(2026, 10, 21, tzinfo=UTC)
    return {
        "schema_version": "0.2.0",
        "catalog_id": backend.catalog.catalog_id,
        "profile_is_synthetic": True,
        "generated_at_is_fixed_for_reproducibility": True,
        "profile": profile.model_dump(mode="json"),
        "matches": [r.model_dump(mode="json") for r in backend.match(profile, top_n=3)],
        "selected_role_match": match.model_dump(mode="json"),
        "baseline_outlook": backend.outlook(role_id).model_dump(mode="json"),
        "rapid_outlook": backend.outlook(role_id, "rapid_ai_change").model_dump(
            mode="json"
        ),
        "baseline_plan": backend.learning_plan(
            profile, role_id, selected_software_skill_ids=selected, generated_at=when
        ).model_dump(mode="json"),
        "rapid_plan": backend.learning_plan(
            profile,
            role_id,
            "rapid_ai_change",
            selected_software_skill_ids=selected,
            generated_at=when,
        ).model_dump(mode="json"),
    }


def main():
    result = example_response()
    path = ROOT / "data/demo/onet_backend.json"
    write_json(path, result)
    print(f"Wrote real-catalog / fictional-profile backend handoff: {path}")


if __name__ == "__main__":
    main()
