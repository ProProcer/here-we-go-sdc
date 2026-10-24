"""Dependency curation must preserve course facts, privacy and a valid time-bounded DAG."""

import copy
import unittest
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.reskilling.dependencies import DependencyService, DraftProposal, Proposal, application_outline, normalize_support, validate_proposal


def context():
    return {
        "role_id": "role:test", "role_title": "Data Analyst", "description": "Analyse business data.",
        "tasks": [{"task_id": "task:clean", "label": "Clean and inspect a business dataset"},
                  {"task_id": "task:query", "label": "Query and explain business results"}],
        "gaps": [{"skill_id": "skill:math", "label": "Mathematics", "priority": .8, "kind": "general", "status": "not_confirmed"},
                 {"skill_id": "skill:critical", "label": "Critical Thinking", "priority": .9, "kind": "general", "status": "not_confirmed"},
                 {"skill_id": "skill:sql", "label": "SQL", "priority": .7, "kind": "software", "status": "suggested_tool"},
                 {"skill_id": "skill:learning", "label": "Active Learning", "priority": .6, "kind": "general", "status": "not_confirmed"}],
        "known_skills": [{"skill_id": "skill:writing", "label": "Writing", "level": "intermediate"}],
        "courses": [{"course_id": "course:math", "title": "Analyse numerical data", "provider": "TEST provider",
                     "skill_ids": ["skill:math", "skill:critical"], "prerequisite_skill_ids": [], "duration": {"hours": 4}},
                    {"course_id": "course:sql", "title": "Query business data", "provider": "TEST provider",
                     "skill_ids": ["skill:sql"], "prerequisite_skill_ids": ["skill:math"], "duration": {"hours": 3}}],
        "horizon": "short", "target_weeks": 12, "max_modules": 5, "weekly_hours": 5,
        "budget_hours": 60, "scenario": "baseline",
    }


def proposal():
    return {"summary": "Build reliable analysis skills before combining them in a business project.", "modules": [
        {"node_id": "node_foundation", "title": "Inspect and check a dataset", "objective": "Find missing values and test numerical results.",
         "task_id": "task:clean", "skill_ids": ["skill:math", "skill:critical"], "embedded_skill_ids": ["skill:learning"],
         "course_ids": ["course:math"], "practice_hours": 6, "deliverable": "A checked dataset and a brief quality report."},
        {"node_id": "node_queries", "title": "Query business performance", "objective": "Use queries to explain changes in business performance.",
         "task_id": "task:query", "skill_ids": ["skill:sql"], "embedded_skill_ids": [],
         "course_ids": ["course:sql"], "practice_hours": 6, "deliverable": "Queries with documented checks of each result."},
        {"node_id": "node_project", "title": "Build a decision brief", "objective": "Combine the dataset and queries in a practical business analysis.",
         "task_id": "task:query", "skill_ids": ["skill:sql", "skill:critical"], "embedded_skill_ids": ["skill:writing"],
         "course_ids": [], "practice_hours": 10, "deliverable": "A decision brief with reproducible data and results."}],
        "dependencies": [{"source": "node_queries", "target": "node_project", "reason": "Use the tested queries to support the final decision brief."}]}


class TestDependencyCuration(unittest.TestCase):
    def test_cache_survives_restart_but_settings_and_expiry_cannot_reuse_old_maps(self):
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=Proposal.model_validate(proposal()), returned_model='TEST model', provider='test')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'maps.json'
            service = DependencyService(client_factory=lambda: client, cache_path=path)
            first = service.curate(context())
            restarted = DependencyService(client_factory=lambda: client, cache_path=path)
            self.assertEqual(restarted.curate(context()), first)
            client.generate.assert_called_once()
            changed = context()
            changed['weekly_hours'] = 6
            changed['budget_hours'] = 72
            restarted.curate(changed)
            self.assertEqual(client.generate.call_count, 2)
            self.assertNotIn('known_skills', path.read_text())
            self.assertNotIn('profile', path.read_text())

    def test_simultaneous_identical_requests_generate_once(self):
        client = Mock()
        entered, release = threading.Event(), threading.Event()
        def generate(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return SimpleNamespace(value=Proposal.model_validate(proposal()), returned_model='TEST model', provider='test')
        client.generate.side_effect = generate
        service = DependencyService(client_factory=lambda: client)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.curate, context())
            self.assertTrue(entered.wait(2))
            second = pool.submit(service.curate, context())
            release.set()
            self.assertEqual(first.result(), second.result())
        client.generate.assert_called_once()

    def test_grouped_course_is_counted_once_and_actual_prerequisite_is_enforced(self):
        result = validate_proposal(proposal(), context())
        self.assertEqual(result["planned_hours"], 29)
        self.assertEqual(result["estimated_weeks"], 6)
        self.assertEqual([node["level"] for node in result["nodes"]], [0, 1, 2])
        self.assertTrue(all(skill["course_covered"] for skill in result["nodes"][0]["skills"]))
        self.assertFalse(result["nodes"][0]["embedded_skills"][0]["course_covered"])
        self.assertEqual(result["edges"][-1]["basis"], "course_prerequisite")
        self.assertFalse(result["changes_personal_fit"])

    def test_cycles_unknown_ids_and_duplicate_course_claims_are_rejected(self):
        for mutation in ("cycle", "skill", "task", "course", "duplicate_course"):
            with self.subTest(mutation=mutation):
                value = proposal()
                if mutation == "cycle":
                    value["dependencies"].append({"source": "node_project", "target": "node_foundation", "reason": "An invalid prerequisite makes a cycle in the learning graph."})
                elif mutation == "skill":
                    value["modules"][0]["skill_ids"] = ["skill:invented"]
                elif mutation == "task":
                    value["modules"][0]["task_id"] = "task:invented"
                elif mutation == "course":
                    value["modules"][0]["course_ids"] = ["course:invented"]
                else:
                    value["modules"][2]["course_ids"] = ["course:math"]
                with self.assertRaises(ValueError):
                    validate_proposal(value, context())

    def test_budget_missing_prerequisite_and_basic_only_heading_are_rejected(self):
        value = proposal()
        value["modules"][0]["practice_hours"] = 100
        with self.assertRaises(ValueError):
            validate_proposal(value, context())
        value = proposal()
        value["modules"][0]["skill_ids"] = ["skill:critical"]
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            validate_proposal(value, context())
        value = proposal()
        value["modules"][0]["title"] = "Active Learning"
        with self.assertRaises(ValueError):
            validate_proposal(value, context())

    def test_an_embedded_skill_does_not_become_verified_course_coverage(self):
        value = proposal()
        value["modules"][0]["embedded_skill_ids"] = ["skill:learning", "skill:writing"]
        result = validate_proposal(value, context())
        self.assertFalse(result["nodes"][0]["embedded_skills"][1]["course_covered"])
        self.assertTrue(result["nodes"][0]["embedded_skills"][1]["already_confirmed"])

    def test_ai_uses_shared_client_and_caches_only_validated_output(self):
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=Proposal.model_validate(proposal()), returned_model="TEST model", provider="test")
        service = DependencyService(client_factory=lambda: client)
        result = service.curate(context())
        self.assertEqual(result["origin"], "ai_generated")
        self.assertEqual(result["model"], "TEST model")
        self.assertEqual(service.curate(context()), result)
        client.generate.assert_called_once()
        self.assertIs(client.generate.call_args.args[2], DraftProposal)

    def test_invalid_ai_and_unconfigured_ai_return_an_honest_outline(self):
        client = Mock()
        client.generate.side_effect = RuntimeError("TEST unavailable")
        service = DependencyService(client_factory=lambda: client)
        result = service.curate(context())
        self.assertEqual(result["origin"], "application_outline")
        self.assertEqual(result["status"], "unavailable")
        self.assertLessEqual(result["planned_hours"], 60)
        with patch("src.reskilling.dependencies.model_configuration", return_value=("groq", ["GROQ_API"])):
            result = DependencyService().curate(context())
        self.assertEqual(result["status"], "not_configured")
        self.assertNotIn("ai_suggested", {edge["basis"] for edge in result["edges"]})

    def test_each_horizon_has_a_bounded_valid_outline_even_at_low_pace(self):
        for horizon, weeks, limit in (("short", 12, 5), ("standard", 26, 8), ("long", 52, 12)):
            value = context()
            value.update(horizon=horizon, target_weeks=weeks, max_modules=limit, budget_hours=weeks * .5, weekly_hours=.5)
            result = validate_proposal(application_outline(value), value, origin="application_outline")
            self.assertLessEqual(len(result["nodes"]), limit)
            self.assertLessEqual(result["planned_hours"], value["budget_hours"])
            self.assertLessEqual(result["estimated_weeks"], weeks)

    def test_context_is_not_mutated_by_validation(self):
        before = context()
        after = copy.deepcopy(before)
        validate_proposal(proposal(), after)
        self.assertEqual(before, after)

    def test_generic_compound_heading_becomes_a_concrete_occupational_task(self):
        value = proposal()
        value["modules"][0]["title"] = "Mathematics & Critical Thinking"
        result = validate_proposal(value, context())
        self.assertEqual(result["nodes"][0]["title"], "Clean and inspect a business dataset")

    def test_course_only_module_is_valid_but_zero_effort_module_is_not(self):
        value = proposal()
        value["modules"][0]["practice_hours"] = 0
        result = validate_proposal(value, context())
        self.assertEqual(result["nodes"][0]["hours"], 4)
        value["modules"][2]["practice_hours"] = 0
        with self.assertRaisesRegex(ValueError, "course time"):
            validate_proposal(value, context())

    def test_confirmed_skills_are_kept_as_support_instead_of_new_gaps(self):
        value = proposal()
        value["modules"][0]["skill_ids"].append("skill:writing")
        prepared = normalize_support(value, context())
        result = validate_proposal(prepared, context())
        self.assertNotIn("skill:writing", result["nodes"][0]["skill_ids"])
        self.assertTrue(next(skill for skill in result["nodes"][0]["embedded_skills"] if skill["skill_id"] == "skill:writing")["already_confirmed"])

    def test_draft_identifiers_and_verbose_text_are_normalized_without_changing_dependencies(self):
        value = proposal()
        value["summary"] = "A clear learning plan. " + "Additional context. " * 40
        value["modules"][0]["node_id"] = "module:foundation"
        prepared = normalize_support(value, context())
        result = validate_proposal(prepared, context())
        self.assertEqual(result["summary"], "A clear learning plan.")
        self.assertEqual(result["nodes"][0]["node_id"], "node_1")
        self.assertEqual(result["edges"][0]["source"], "node_2")
        self.assertEqual(result["edges"][0]["target"], "node_3")
