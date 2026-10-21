"""Offline real-catalog / fictional-profile handoff example."""

import json

from src.ingestion.coverage import CoverageIndex
from src.ingestion.onet import ROOT, load_onet_catalog, write_json
from src.ingestion.onet_api import get_onet_role
from src.profiles.intake import create_profile


def example_response() -> dict:
    catalog = load_onet_catalog()
    profile = create_profile(
        "synthetic:onet_demo",
        ["Python", "SQL", "Tableau", "Critical Thinking", "Reading Comprehension"],
        catalog=catalog,
    )
    index = CoverageIndex(catalog)
    scores = [index.score_profile(r.role_id, profile) for r in catalog.roles]
    scores.sort(key=lambda r: (-r.score, r.role_id))
    role_id = "role:onet_15_2051_01"
    return {
        "schema_version": "0.2.0",
        "profile_is_synthetic": True,
        "catalog_is_synthetic": False,
        "profile": profile.model_dump(mode="json"),
        "selected_role": get_onet_role(catalog, role_id),
        "selected_coverage": index.score_profile(role_id, profile).model_dump(
            mode="json"
        ),
        "top_5_exploratory_coverage": [r.model_dump(mode="json") for r in scores[:5]],
        "ranking_warning": "Cross-occupation coverage is exploratory; it omits qualification, domain-knowledge and licensing checks and is not career eligibility.",
    }


def main():
    result = example_response()
    path = ROOT / "data/demo/onet_coverage.json"
    write_json(path, result)
    print(
        json.dumps(
            {
                "output": str(path),
                "selected_role": result["selected_role"]["role"]["role_title"],
                "coverage": result["selected_coverage"]["score"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
