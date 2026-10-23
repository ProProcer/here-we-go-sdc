"""Evidence grounding, failure handling and human control over AI estimates."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.intelligence.extractors import ExtractionError
from src.profiles.assessment import AssessmentBatch, assess_levels, assessment_input, assessment_schema
from src.schemas.profile import ProfileSkill, SkillsProfile


class TestSkillAssessment(unittest.TestCase):
    def profile(self):
        return SkillsProfile(profile_id="synthetic:assessment_test", skills=[ProfileSkill(
            skill_id="skill:python", label="Python",
            evidence=["Built and independently deployed a Python dashboard."],
        )])

    def client(self, **changes):
        row = dict(skill_id="skill:python", level="intermediate", confidence="medium",
                   rationale="Independent project application; production experience is unclear.",
                   evidence_indices=[0])
        row.update(changes)
        result = SimpleNamespace(value=AssessmentBatch(skills=[row]), returned_model="gemini-test")
        return Mock(generate=Mock(return_value=result))

    def test_estimate_keeps_claim_unverified_and_preserves_evidence(self):
        profile = self.profile()
        result = assess_levels(profile, client=self.client())
        self.assertEqual(result.skills[0].level, "intermediate")
        self.assertEqual(result.skills[0].confirmation, "unverified")
        self.assertEqual(result.skills[0].evidence, profile.skills[0].evidence)
        self.assertEqual(result.skills[0].level_assessment.model, "gemini-test")
        self.assertEqual(profile.skills[0].level, "unknown")

    def test_unknown_skill_and_bad_citation_do_not_change_profile(self):
        for changes in ({"skill_id": "skill:invented"}, {"evidence_indices": [7]}):
            result = assess_levels(self.profile(), client=self.client(**changes))
            self.assertEqual(result.skills[0].level, "unknown")
            self.assertIsNone(result.skills[0].level_assessment)
            self.assertIn("could not complete", result.warnings[-1])

    def test_missing_key_and_service_failure_are_explicit(self):
        with patch.dict(os.environ, {"GROQ_API": "", "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "RUNPOD_API_KEY": "", "RUNPOD_ENDPOINT_ID": ""}):
            result = assess_levels(self.profile())
        self.assertIn("unavailable", result.warnings[-1])
        client = Mock(generate=Mock(side_effect=ExtractionError("Temporary failure")))
        result = assess_levels(self.profile(), client=client)
        self.assertEqual(result.skills[0].level, "unknown")
        self.assertIn("could not complete", result.warnings[-1])
        self.assertEqual(result.assessment_status.status, "failed")

    def test_connection_failure_is_distinguished_from_invalid_model_output(self):
        client = Mock(generate=Mock(side_effect=ExtractionError("provider transport_error")))
        result = assess_levels(self.profile(), client=client)
        self.assertEqual(result.assessment_status.error_code, "connection_failed")
        self.assertEqual(result.assessment_status.assessed_skill_count, 0)
        self.assertEqual(result.skills[0].level, "unknown")

    def test_backup_is_reported_as_gemini_rather_than_runpod(self):
        client = self.client()
        client.generate.return_value.provider = "gemini"
        result = assess_levels(self.profile(), client=client)
        self.assertEqual(result.assessment_status.provider, "gemini")
        self.assertTrue(result.assessment_status.used_backup)
        self.assertEqual(result.skills[0].level_assessment.provider, "gemini")

    def test_input_and_schema_use_explicit_skill_local_evidence_indices(self):
        profile = self.profile()
        packet = assessment_input(profile.skills)
        self.assertEqual(packet["skills"][0]["evidence"][0]["index"], 0)
        schema = assessment_schema(profile.skills)
        branch = schema["properties"]["skills"]["items"]["anyOf"][0]
        self.assertEqual(branch["properties"]["skill_id"]["enum"], ["skill:python"])
        self.assertEqual(branch["properties"]["evidence_indices"]["items"]["enum"], [0])
        self.assertEqual(schema["properties"]["skills"]["minItems"], 1)
        # Groq accepts one enum discriminator for object unions.
        for field in ("level", "confidence"):
            self.assertNotIn("enum", branch["properties"][field])
            self.assertIn("pattern", branch["properties"][field])

    def test_prompt_contains_database_kind_definition_and_supported_levels(self):
        packet = assessment_input(self.profile().skills)
        self.assertEqual(packet["skills"][0]["kind"], "software")
        self.assertEqual(packet["skills"][0]["label"], "Python")
        self.assertTrue(packet["skills"][0]["definition"])
        self.assertEqual(packet["allowed_levels"], ["unknown", "beginner", "intermediate", "advanced"])

    def test_unknown_input_skill_is_removed_before_ai_and_known_label_is_canonical(self):
        profile = self.profile()
        unknown = profile.skills[0].model_copy(update={"skill_id": "skill:invented", "label": "Invented"})
        forged = profile.skills[0].model_copy(update={"label": "Made-up label"})
        profile = profile.model_copy(update={"skills": [forged, unknown]})
        client = self.client()
        result = assess_levels(profile, client=client)
        self.assertEqual([(s.skill_id, s.label) for s in result.skills], [("skill:python", "Python")])
        packet = client.generate.call_args.args[1]
        self.assertEqual([s["skill_id"] for s in packet["skills"]], ["skill:python"])
        self.assertTrue(any("absent from the active database" in warning for warning in result.warnings))

    def test_invented_ai_prediction_is_filtered_while_valid_prediction_survives(self):
        client = self.client()
        valid = client.generate.return_value.value.skills[0]
        unknown = valid.model_copy(update={"skill_id": "skill:invented"})
        client.generate.return_value.value = AssessmentBatch(skills=[valid, unknown])
        result = assess_levels(self.profile(), client=client)
        self.assertEqual(result.skills[0].level, "intermediate")
        self.assertEqual(len(result.skills), 1)
        self.assertTrue(any("outside the database-backed" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
