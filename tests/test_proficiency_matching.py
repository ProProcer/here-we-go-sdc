"""Required levels change fit without inventing requirements for software."""

import unittest
from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile
from src.profiles.onet_matching import OnetMatcher

BI = "role:onet_15_2051_01"


class TestProficiencyMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()
        cls.matcher = OnetMatcher(cls.catalog)

    def profile(self, level):
        profile = create_profile("synthetic:proficiency", ["Critical Thinking", "Reading Comprehension",
            "Writing", "Python"], catalog=self.catalog)
        return profile.model_copy(update={"skills": [s.model_copy(update={"level": level}) for s in profile.skills]})

    def test_proficiency_increases_capability_while_suitability_tracks_job_level(self):
        rows = [self.matcher.match_role(self.profile(level), BI)
            for level in ("unknown", "beginner", "intermediate", "advanced")]
        self.assertEqual([row.score_breakdown.general_fulfilment for row in rows], sorted({row.score_breakdown.general_fulfilment for row in rows}))
        self.assertEqual(len({row.score_breakdown.coverage.general_coverage for row in rows}), 1)
        self.assertEqual(len({row.score_breakdown.profile_presence_alignment for row in rows}), 1)

    def test_higher_required_level_reduces_credit_for_same_person(self):
        profile = self.profile("beginner")
        sid = next(s.skill_id for s in profile.skills if s.label == "Critical Thinking")
        scores = []
        for required in (2, 6):
            requirements = [r.model_copy(update={"source_level": required, "level_suppressed": False})
                if r.role_id == BI and r.skill_id == sid else r for r in self.catalog.role_skills]
            catalog = self.catalog.model_copy(update={"role_skills": requirements})
            scores.append(OnetMatcher(catalog).match_role(profile, BI))
        self.assertGreater(scores[0].fit_score, scores[1].fit_score)
        self.assertEqual(scores[0].score_breakdown.profile_presence_alignment, scores[1].score_breakdown.profile_presence_alignment)

    def test_suppressed_levels_stay_unavailable(self):
        profile = self.profile("beginner")
        requirements = [r.model_copy(update={"source_level": None, "level_suppressed": True})
            if r.role_id == BI else r for r in self.catalog.role_skills]
        row = OnetMatcher(self.catalog.model_copy(update={"role_skills": requirements})).match_role(profile, BI)
        compared = [c for c in row.score_breakdown.proficiency_comparisons if c.status != "skill_unconfirmed"]
        self.assertTrue(compared)
        self.assertTrue(all(c.required_source_level is None and c.status == "required_level_unavailable" for c in compared))
        self.assertEqual(row.score_breakdown.general_fulfilment, row.score_breakdown.coverage.general_coverage)

    def test_software_level_changes_alignment_without_fabricated_requirement(self):
        profile = create_profile("synthetic:software_level", ["Python", "SQL", "Tableau"], catalog=self.catalog)
        scores = []
        for level in ("beginner", "advanced"):
            updated = profile.model_copy(update={"skills": [s.model_copy(update={"level": level}) for s in profile.skills]})
            row = self.matcher.match_role(updated, BI)
            scores.append(row.fit_score)
            self.assertFalse({s.skill_id for s in profile.skills} & {c.skill_id for c in row.score_breakdown.proficiency_comparisons})
        self.assertLess(*scores)


    def test_python_level_prefers_the_corresponding_occupational_requirement(self):
        roles = ("role:onet_47_4011_01", BI, "role:onet_15_1251_00")
        profile = create_profile("synthetic:only_python", ["Python"], catalog=self.catalog)
        matrix = []
        for index, level in enumerate(("beginner", "intermediate", "advanced")):
            updated = profile.model_copy(update={"skills": [s.model_copy(update={"level": level}) for s in profile.skills]})
            matches = [self.matcher.match_role(updated, role) for role in roles]
            scores = [row.fit_score for row in matches]
            matrix.append(scores)
            self.assertEqual(scores.index(max(scores)), index)
            for row in matches:
                target = row.score_breakdown.alignment_contributions[0]
                self.assertEqual(target.requirement_basis, "estimated_from_general")
                self.assertEqual(target.proxy_skill_label, "Programming")
        self.assertEqual(matrix, [[16.25, 6.5, 4.69], [12.88, 16.25, 9.03], [10.9, 12.88, 16.25]])

    def test_suppressed_programming_rating_does_not_create_a_python_requirement(self):
        profile = create_profile("synthetic:suppressed_python", ["Python"], catalog=self.catalog)
        row = self.matcher.match_role(profile, "role:onet_15_2051_00")
        target = row.score_breakdown.alignment_contributions[0]
        self.assertEqual(target.requirement_basis, "unavailable")
        self.assertIsNone(target.required_level_points)
        self.assertIsNone(target.proxy_source_level)

    def test_representative_general_and_software_skills_respond_to_levels(self):
        for label in ("Python", "SQL", "Microsoft Excel", "Reading Comprehension", "Critical Thinking"):
            with self.subTest(skill=label):
                profile = create_profile("synthetic:one_skill", [label], catalog=self.catalog)
                scores = []
                for level in ("beginner", "intermediate", "advanced"):
                    updated = profile.model_copy(update={"skills": [s.model_copy(update={"level": level}) for s in profile.skills]})
                    row = self.matcher.match_role(updated, BI)
                    scores.append(row.fit_score)
                    self.assertAlmostEqual(sum(c.contribution for c in row.score_breakdown.alignment_contributions), row.score_breakdown.profile_alignment)
                self.assertGreater(len(set(scores)), 1, scores)
