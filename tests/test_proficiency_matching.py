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

    def test_proficiency_increases_fit_without_changing_skill_presence(self):
        rows = [self.matcher.match_role(self.profile(level), BI)
            for level in ("unknown", "beginner", "intermediate", "advanced")]
        self.assertEqual([row.fit_score for row in rows], sorted({row.fit_score for row in rows}))
        self.assertEqual(len({row.score_breakdown.coverage.general_coverage for row in rows}), 1)
        self.assertEqual(len({row.score_breakdown.profile_alignment for row in rows}), 1)

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
        self.assertEqual(scores[0].score_breakdown.profile_alignment, scores[1].score_breakdown.profile_alignment)

    def test_suppressed_levels_stay_unavailable(self):
        profile = self.profile("beginner")
        requirements = [r.model_copy(update={"source_level": None, "level_suppressed": True})
            if r.role_id == BI else r for r in self.catalog.role_skills]
        row = OnetMatcher(self.catalog.model_copy(update={"role_skills": requirements})).match_role(profile, BI)
        compared = [c for c in row.score_breakdown.proficiency_comparisons if c.status != "skill_unconfirmed"]
        self.assertTrue(compared)
        self.assertTrue(all(c.required_source_level is None and c.status == "required_level_unavailable" for c in compared))
        self.assertEqual(row.score_breakdown.general_fulfilment, row.score_breakdown.coverage.general_coverage)

    def test_no_fabricated_software_requirement(self):
        profile = create_profile("synthetic:software_level", ["Python", "SQL", "Tableau"], catalog=self.catalog)
        scores = []
        for level in ("beginner", "advanced"):
            updated = profile.model_copy(update={"skills": [s.model_copy(update={"level": level}) for s in profile.skills]})
            row = self.matcher.match_role(updated, BI)
            scores.append(row.fit_score)
            self.assertFalse({s.skill_id for s in profile.skills} & {c.skill_id for c in row.score_breakdown.proficiency_comparisons})
        self.assertEqual(*scores)
