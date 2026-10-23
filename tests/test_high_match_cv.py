"""The downloadable benchmark exceeds 90 using real parsed CV evidence."""

import unittest

from scripts.create_high_match_cv import OUTPUT, ROLE
from src.backend import CareerBackend
from src.profiles.intake import create_profile_from_cv
from src.schemas.profile import SkillsProfile


class TestHighMatchCV(unittest.TestCase):
    def test_pdf_with_confirmed_checklist_levels_exceeds_ninety(self):
        backend = CareerBackend()
        specified = SkillsProfile.model_validate_json((OUTPUT / "reviewed_profile.json").read_text())
        levels = {skill.skill_id: skill.level for skill in specified.skills}
        path = OUTPUT / "rina_search_marketing.pdf"
        profile = create_profile_from_cv("synthetic:benchmark_test", path.read_bytes(), path.name, catalog=backend.catalog)
        self.assertEqual({skill.skill_id for skill in profile.skills}, set(levels))
        reviewed = profile.model_copy(update={"skills": [skill.model_copy(update={
            "level": levels[skill.skill_id], "confirmation": "confirmed"}) for skill in profile.skills]})
        match = backend.matcher.match_role(reviewed, ROLE)
        self.assertGreater(match.fit_score, 90)
        self.assertIsNone(match.score_breakdown.preferences)
        self.assertFalse(match.manually_selected)
