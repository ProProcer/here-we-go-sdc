"""Evidence grounding, failure handling and human control over AI estimates."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.intelligence.extractors import ExtractionError
from src.profiles.assessment import AssessmentBatch, assess_levels, assessment_input, assessment_schema, selected_evidence
from src.schemas.profile import ProfileSkill, SkillsProfile


class TestSkillAssessment(unittest.TestCase):
    def test_sample_core_practice_is_selected_ahead_of_a_longer_skill_list(self):
        from src.ingestion.selection import real_catalog
        from src.profiles.samples import SAMPLE_PATH
        from src.profiles.cv_parser import ParsedCV
        from src.profiles.extraction import extract_profile
        catalog = real_catalog()
        profile = extract_profile(ParsedCV(format='txt', pages=[SAMPLE_PATH.read_text(encoding='utf-8')]),
                                  'synthetic:sample_evidence', catalog=catalog)
        for label in ('Active Listening', 'Critical Thinking'):
            skill = next(skill for skill in profile.skills if skill.label == label)
            selected = selected_evidence(skill)
            self.assertIn('Practised Active Listening and Critical Thinking', selected['text'])
            self.assertNotIn('General skills:', selected['text'])
            self.assertEqual(selected['text'], skill.evidence[selected['index']][:240])

    def test_coursework_and_checked_work_outrank_a_longer_bare_list(self):
        for evidence in ('Relevant coursework: Critical Thinking.', 'Checked a result using Critical Thinking.'):
            skill = ProfileSkill(skill_id='skill:onet_2_a_2_a', label='Critical Thinking', evidence=[
                evidence, 'General skills: Reading Comprehension, Writing, Active Listening, Critical Thinking.'])
            self.assertEqual(selected_evidence(skill)['index'], 0)
        skill = ProfileSkill(skill_id='skill:onet_2_a_2_a', label='Critical Thinking', evidence=[
            'Critical Thinking: advanced proficiency.', 'Relevant coursework: Critical Thinking.'])
        self.assertEqual(selected_evidence(skill)['index'], 1)

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
        row = schema["$defs"]["AssessedSkill"]
        self.assertEqual(row["properties"]["skill_id"]["enum"], ["skill:python"])
        self.assertEqual(row["properties"]["evidence_indices"]["items"]["enum"], [0])
        self.assertEqual(schema["properties"]["skills"]["minItems"], 1)

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


    def test_large_profile_is_assessed_in_full_and_never_reports_prefix_success(self):
        from scripts.create_high_match_cv import OUTPUT
        from src.profiles.intake import create_profile_from_cv
        from src.ingestion.selection import real_catalog
        from src.profiles.assessment import selected_evidence
        import json
        catalog = real_catalog()
        path = OUTPUT / "rina_search_marketing.pdf"
        profile = create_profile_from_cv("synthetic:complete_cv", path.read_bytes(), path.name, catalog=catalog)
        wanted = SkillsProfile.model_validate_json((OUTPUT / "reviewed_profile.json").read_text())
        levels = {s.skill_id: s.level for s in wanted.skills}
        rows = [dict(skill_id=s.skill_id, level=levels[s.skill_id], confidence="medium",
            rationale="Independent task evidence in supplied passage.",
            evidence_indices=[selected_evidence(s)["index"]]) for s in profile.skills]
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=AssessmentBatch(skills=rows), returned_model="test-complete", provider="groq")
        complete = assess_levels(profile, client=client, catalog=catalog)
        self.assertEqual(complete.assessment_status.assessed_skill_count, 39)
        self.assertEqual(len(client.generate.call_args.args[1]["skills"]), 39)
        self.assertTrue(all(s.level_assessment is not None for s in complete.skills))
        self.assertTrue(all(s.confirmation == "unverified" for s in complete.skills))
        self.assertLess(len(json.dumps(assessment_input(profile.skills, catalog))) + len(json.dumps(assessment_schema(profile.skills))), 20000)
        # A provider returning only the old prefix cannot be called completed.
        client.generate.return_value.value = AssessmentBatch(skills=rows[:12])
        partial = assess_levels(profile, client=client, catalog=catalog)
        self.assertEqual(partial.assessment_status.status, "failed")
        self.assertEqual(partial.assessment_status.assessed_skill_count, 0)
        self.assertTrue(all(s.level_assessment is None for s in partial.skills))

    def test_evidence_reference_must_have_been_supplied_not_merely_exist(self):
        profile = self.profile()
        skill = profile.skills[0].model_copy(update={"evidence": ["Skills: Python", "Independently used Python to validate campaign records."]})
        profile = profile.model_copy(update={"skills": [skill]})
        packet = assessment_input(profile.skills)
        self.assertEqual(packet["skills"][0]["evidence"][0]["index"], 1)
        invalid = assess_levels(profile, client=self.client(evidence_indices=[0]))
        self.assertEqual(invalid.assessment_status.status, "failed")
        valid = assess_levels(profile, client=self.client(evidence_indices=[1]))
        self.assertEqual(valid.assessment_status.status, "completed")

    def test_oversize_profile_is_rejected_without_partial_prediction(self):
        from src.ingestion.selection import real_catalog
        skills = [ProfileSkill(skill_id=s.skill_id, label=s.label, evidence=["Explicit test skill claim."])
            for s in real_catalog().taxonomy.skills[:101]]
        profile = SkillsProfile(profile_id="synthetic:oversize", skills=skills)
        client = Mock()
        result = assess_levels(profile, client=client)
        self.assertEqual(result.assessment_status.error_code, "profile_too_large")
        self.assertEqual(result.assessment_status.assessed_skill_count, 0)
        client.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
