"""Recommendation acceptance tests against the real catalog and authored CV."""

import unittest
from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile, create_profile_from_cv
from src.profiles.onet_matching import OnetMatcher
from src.profiles.samples import sample_cv_pdf

BI = "role:onet_15_2051_01"


class TestCVRecommendations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()
        cls.matcher = OnetMatcher(cls.catalog)
        cls.extracted = create_profile_from_cv("synthetic:recommendation_sample",
            sample_cv_pdf(), "graduate.pdf", catalog=cls.catalog)
        cls.reviewed = cls.extracted.model_copy(update={"skills": [
            skill.model_copy(update={"confirmation": "confirmed"}) for skill in cls.extracted.skills]})

    def profile(self, entries):
        return create_profile("synthetic:recommendation_test", entries, catalog=self.catalog)

    def test_sample_cv_recommends_data_careers_without_target_or_interest_boosts(self):
        rows = self.matcher.match(self.reviewed, top_n=10)
        titles = [row.role_title for row in rows]
        self.assertEqual(titles[0], "Data Scientists")
        for title in ("Data Warehousing Specialists", "Business Intelligence Analysts", "Statisticians"):
            self.assertIn(title, titles)
        for title in ("Ophthalmic Medical Technicians", "Audiologists", "Parking Enforcement Workers"):
            self.assertNotIn(title, titles)
        self.assertFalse(any(row.manually_selected for row in rows))
        self.assertTrue(all(row.score_breakdown.preferences is None for row in rows))
        self.assertTrue(all(0 <= row.fit_score <= 100 for row in rows))

    def test_distinctive_tools_improve_data_fit_over_excel_alone(self):
        excel = self.matcher.match_role(self.profile(["Microsoft Excel"]), BI)
        data = self.matcher.match_role(self.profile(["Python", "SQL", "Tableau", "Microsoft Excel"]), BI)
        self.assertGreater(data.fit_score, excel.fit_score + 30)
        # One common tool is insufficient evidence for a confident career match.
        self.assertLess(excel.fit_score, 25)
        contributions = {row.label: row for row in data.score_breakdown.alignment_contributions}
        self.assertGreater(contributions["Tableau"].normalized_weight,
            contributions["Microsoft Excel"].normalized_weight)

    def test_web_development_profile_gets_development_recommendations(self):
        rows = self.matcher.match(self.profile(["Programming", "JavaScript", "HTML", "CSS"]), top_n=5)
        self.assertIn("Web Developers", [row.role_title for row in rows])
        self.assertTrue(all("Develop" in row.role_title or "Programmer" in row.role_title or "Web" in row.role_title for row in rows))

    def test_unreviewed_cv_and_interests_cannot_create_skill_fit(self):
        profile = self.extracted.model_copy(update={"interests": ["Business Intelligence Analysts"]})
        rows = self.matcher.match(profile, top_n=3)
        self.assertTrue(all(row.fit_score == 0 for row in rows))

    def test_goal_pinning_does_not_promote_or_change_fit(self):
        original = self.matcher.match(self.reviewed)
        target = original[-1]
        pinned = self.reviewed.model_copy(update={"desired_role_id": target.role_id})
        row = next(row for row in self.matcher.match(pinned, top_n=3) if row.role_id == target.role_id)
        self.assertEqual(row.fit_score, target.fit_score)
        self.assertEqual(row.rank, target.rank)
        self.assertTrue(row.pinned)

    def test_explanation_reconciles_to_final_score(self):
        row = self.matcher.match_role(self.reviewed, BI)
        score = row.score_breakdown
        self.assertAlmostEqual(sum(part.contribution for part in score.alignment_contributions), score.profile_alignment)
        self.assertAlmostEqual(sum(part.normalized_weight for part in score.alignment_contributions), 1)
        expected = 100 * score.evidence_breadth * (
            score.readiness_weight * (score.profile_alignment_weight * score.profile_alignment
                + score.general_coverage_weight * score.general_fulfilment)
            + score.preference_weight * (score.preferences or 0))
        self.assertAlmostEqual(expected, score.unrounded_score)
        self.assertAlmostEqual(row.fit_score, expected, places=2)

    def test_computing_degree_does_not_claim_scientific_methods(self):
        self.assertNotIn("Science", [skill.label for skill in self.extracted.skills])
        explicit = create_profile_from_cv("synthetic:science_example",
            b"Skills: Science. Used scientific methods in laboratory experiments.", "science.txt", catalog=self.catalog)
        self.assertIn("Science", [skill.label for skill in explicit.skills])

    def test_ranking_is_deterministic_and_deduplicates_repeated_evidence(self):
        repeated = self.reviewed.model_copy(update={"skills": [skill.model_copy(update={
            "evidence": skill.evidence * 3}) for skill in reversed(self.reviewed.skills)]})
        before = self.matcher.match(self.reviewed, top_n=10)
        after = self.matcher.match(repeated, top_n=10)
        self.assertEqual([(row.role_id, row.fit_score) for row in before],
            [(row.role_id, row.fit_score) for row in after])
