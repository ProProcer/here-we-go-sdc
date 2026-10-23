"""Real catalog checks across skill review, resources, SDGs and scenarios."""

import unittest

from src.backend import CareerBackend
from src.reskilling.course_catalog import CourseCatalogStore
from src.ingestion.onet import ROOT


class TestUserFlowIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = CareerBackend(course_store=CourseCatalogStore(
            ROOT / "data/processed/onet/31.0/courses.json"))

    def test_confirmed_reading_disappears_from_gaps(self):
        backend = self.backend
        role = "role:onet_15_2051_01"
        profile = backend.create_profile("synthetic:gap_review", ["Python"])
        initial = backend.matcher.match_role(profile, role)
        self.assertIn("Reading Comprehension", {s.label for s in initial.missing_skills})
        addition = backend.create_profile("synthetic:added", ["Reading Comprehension"]).skills[0]
        addition.confirmation = "confirmed"
        updated = backend.review_profile(profile, [*profile.skills, addition])
        revised = backend.matcher.match_role(updated, role)
        self.assertNotIn("Reading Comprehension", {s.label for s in revised.missing_skills})
        self.assertGreater(revised.fit_score, initial.fit_score)

    def test_nurse_resources_sdgs_and_three_scenarios(self):
        backend = self.backend
        role = "role:onet_29_1141_00"
        profile = backend.create_profile("synthetic:nurse_flow", [])
        baseline = backend.learning_plan(profile, role).plan
        moderate = backend.learning_plan(profile, role, "moderate_ai_change").plan
        rapid = backend.learning_plan(profile, role, "rapid_ai_change").plan
        self.assertEqual(baseline.fit_score, rapid.fit_score)
        self.assertNotEqual(baseline.prioritized_gaps, moderate.prioritized_gaps)
        self.assertNotEqual(moderate.prioritized_gaps, rapid.prioritized_gaps)
        self.assertEqual(baseline.prioritized_gaps,
                         backend.learning_plan(profile, role).plan.prioritized_gaps)
        self.assertTrue(baseline.selected_courses)
        self.assertIn("3.c", {c.target_id for c in baseline.sdg_connections})
        bi = backend.learning_plan(profile, "role:onet_15_2051_01").plan
        self.assertIn("9.5", {c.target_id for c in bi.sdg_connections})
        self.assertNotIn("3.c", {c.target_id for c in bi.sdg_connections})

    def test_role_sdg_survives_confirmation_of_its_skills(self):
        backend = self.backend
        role = "role:onet_15_2051_01"
        # These are all the skill triggers in the BI innovation rule.
        profile = backend.create_profile("synthetic:known_innovation_skills", [
            "Critical Thinking", "Complex Problem Solving", "Science", "Programming", "Systems Analysis"])
        plan = backend.learning_plan(profile, role).plan
        connections = [c for c in plan.sdg_connections if c.target_id == "9.5"]
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0].scope, "role_application")
        self.assertFalse(set(connections[0].skill_ids) & {g.skill_id for g in plan.prioritized_gaps})


if __name__ == "__main__":
    unittest.main()
