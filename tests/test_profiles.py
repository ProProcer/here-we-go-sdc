import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.ingestion.catalog import load_role_catalog
from src.profiles.demo import example_responses
from src.profiles.intake import create_profile, review_profile
from src.profiles.matching import match_roles
from src.profiles.skill_normalizer import skill_index
from src.schemas.profile import SkillsProfile

ROOT = Path(__file__).resolve().parents[1]


class TestProfiles(unittest.TestCase):
    def test_fictional_fixtures_have_expected_skills_and_rankings(self):
        fixtures = json.loads(
            (ROOT / "data/synthetic/profiles/typed_inputs.json").read_text()
        )
        for row in fixtures:
            with self.subTest(profile=row["profile_id"]):
                profile = create_profile(row["profile_id"], row["entries"])
                self.assertEqual(
                    [s.skill_id for s in profile.skills], row["expected_skill_ids"]
                )
                self.assertEqual(
                    [r.role_id for r in match_roles(profile)], row["expected_ranking"]
                )
                self.assertTrue(all(s.level == "unknown" for s in profile.skills))

    def test_hand_calculated_coverage_and_gaps(self):
        profile = create_profile("synthetic:example", ["Python", "SQL"])
        result = match_roles(profile)[0]
        self.assertEqual(result.fit_score, 42.11)  # (0.7 + 0.9) / 3.8 * 100
        self.assertEqual(result.score_breakdown.earned_weight, 1.6)
        self.assertEqual(result.score_breakdown.total_weight, 3.8)
        self.assertEqual(
            {s.skill_id for s in result.missing_skills},
            {"skill:statistics", "skill:data_visualization", "skill:communication"},
        )
        self.assertEqual(sum(s.weighted_contribution for s in result.missing_skills), 0)

    def test_aliases_duplicates_and_order_do_not_inflate_scores(self):
        first = create_profile("synthetic:example", ["Python", "SQL"])
        second = create_profile(
            "synthetic:example",
            ["SQL", "python3", "PYTHON", "structured query language"],
        )
        self.assertEqual(
            [(r.role_id, r.fit_score) for r in match_roles(first)],
            [(r.role_id, r.fit_score) for r in match_roles(second)],
        )
        self.assertEqual(len(second.skills), 2)
        self.assertEqual(len(second.skills[0].evidence), 2)

    def test_review_add_remove_confirmation_and_no_mutation(self):
        original = create_profile("synthetic:example", ["Python", "SQL"])
        skills = [original.skills[0].model_dump()]
        skills[0]["confirmation"] = "unverified"
        unverified = review_profile(original, skills)
        self.assertTrue(all(r.fit_score == 0 for r in match_roles(unverified)))
        skills[0]["confirmation"] = "confirmed"
        skills.append(
            {
                "skill_id": "skill:statistics",
                "label": "Statistics",
                "level": "unknown",
                "confirmation": "confirmed",
                "evidence": ["Human-reviewed fictional coursework"],
            }
        )
        reviewed = review_profile(original, skills)
        self.assertEqual(match_roles(reviewed)[0].fit_score, 39.47)  # 1.5 / 3.8
        self.assertEqual(
            [s.skill_id for s in original.skills], ["skill:python", "skill:sql"]
        )

    def test_empty_unknown_and_non_skill_text(self):
        profile = create_profile(
            "synthetic:empty", [" ", "Kubernetes", "No Python experience"]
        )
        self.assertEqual(profile.skills, [])
        self.assertEqual(len(profile.warnings), 2)
        self.assertTrue(
            all(r.fit_score == 0 and r.warnings for r in match_roles(profile))
        )

    def test_rejects_invalid_contracts_and_catalog_references(self):
        profile = create_profile("synthetic:example", ["Python"])
        for change in (
            {"skill_id": "skill:invented"},
            {"label": "Wrong label"},
            {"level": "expert"},
            {"confirmation": "invented"},
            {"evidence": [" "]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                review_profile(profile, [{**profile.skills[0].model_dump(), **change}])
        with self.assertRaises(ValueError):
            review_profile(profile, [profile.skills[0], profile.skills[0]])
        with self.assertRaises(ValueError):
            create_profile("synthetic:example", [], desired_role_id="role:unknown")

    def test_protected_attributes_rejected_and_metadata_not_scored(self):
        profile = create_profile("synthetic:example", ["Python", "SQL"])
        for attribute in ("age", "gender", "nationality", "ethnicity", "name"):
            with self.subTest(attribute=attribute), self.assertRaises(ValidationError):
                SkillsProfile.model_validate(
                    {**profile.model_dump(), attribute: "unused"}
                )
        changed = profile.model_dump()
        changed.update(
            interests=["different interest"],
            desired_role_id="role:it_support_specialist",
        )
        changed["skills"][0]["evidence"] = [
            "Fictional candidate; age 21; gender female"
        ]
        other = SkillsProfile.model_validate(changed)
        baseline = match_roles(profile)
        self.assertEqual(
            [(r.role_id, r.fit_score) for r in baseline],
            [(r.role_id, r.fit_score) for r in match_roles(other)],
        )
        self.assertTrue(match_roles(other)[-1].manually_selected)

    def test_determinism_and_zero_weight_catalog(self):
        profile = create_profile("synthetic:example", ["Python"])
        self.assertEqual(match_roles(profile), match_roles(profile))
        catalog = copy.deepcopy(load_role_catalog())
        for requirement in catalog.role_skills:
            requirement.importance = 0
        results = match_roles(profile, catalog)
        self.assertTrue(all(r.fit_score == 0 for r in results))
        self.assertEqual(
            [r.role_id for r in results], sorted(r.role_id for r in results)
        )

    def test_ambiguous_taxonomy_is_rejected(self):
        taxonomy = copy.deepcopy(load_role_catalog().taxonomy)
        taxonomy.skills[1].aliases.append("Python")
        with self.assertRaises(ValueError):
            skill_index(taxonomy)

    def test_handoff_snapshot_matches_code(self):
        expected = json.loads((ROOT / "data/demo/person_2_responses.json").read_text())
        self.assertEqual(example_responses(), expected)


if __name__ == "__main__":
    unittest.main()
