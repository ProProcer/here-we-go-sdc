import copy
import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from test_skill_evidence import NOW, StubMapper, catalog, seed

from src.intelligence import role_evidence
from src.intelligence.skill_evidence import run_assessments as map_skills
from src.intelligence.source_review import fingerprint
from src.intelligence.storage import atomic_json
from src.schemas.role_evidence import RoleAssessmentBatch
from src.schemas.skill_evidence import SkillChallengeBatch


def role_catalog():
    result = catalog()
    result.roles[0].role_title = "Fictional developer"
    result.roles[0].description = "Writes and evaluates code."
    result.roles[0].task_ids = ["task:code"]
    result.taxonomy.tasks = [
        SimpleNamespace(
            task_id="task:code",
            label="Write and evaluate code.",
            mapping_status="unmapped",
        )
    ]
    return result


class StubRoleMapper:
    model = StubMapper.model

    def __init__(
        self,
        *,
        relevance="potentially_relevant",
        supported=True,
        invent_task=False,
        invent_finding=False,
        duplicate=False,
        fail=False,
    ):
        self.relevance = relevance
        self.supported = supported
        self.invent_task = invent_task
        self.invent_finding = invent_finding
        self.duplicate = duplicate
        self.fail = fail
        self.calls = []

    def generate(self, instruction, packet, schema):
        self.calls.append((instruction, copy.deepcopy(packet), schema))
        if self.fail:
            raise ValueError("Fictional failure")
        if schema is RoleAssessmentBatch:
            rows = [
                {
                    "news_id": news["news_id"],
                    "relevance": self.relevance,
                    "finding_indices": [99 if self.invent_finding else 0]
                    if self.relevance == "potentially_relevant"
                    else [],
                    "task_ids": [
                        "task:invented"
                        if self.invent_task
                        else packet["role"]["tasks"][0]["task_id"]
                    ]
                    if self.relevance == "potentially_relevant"
                    else [],
                    "rationale": "Evaluated coding activity conditionally applies to the supplied coding task; demand is unknown.",
                    "applicability_conditions": [
                        "Only for coding activities matching the evaluated setting."
                    ]
                    if self.relevance == "potentially_relevant"
                    else [],
                    "human_checks": ["Check actual work setting."]
                    if self.relevance == "potentially_relevant"
                    else [],
                }
                for news in packet["news"]
            ]
            if self.duplicate:
                rows = [rows[0], rows[0]]
            value = schema.model_validate({"assessments": rows})
        else:
            value = SkillChallengeBatch.model_validate(
                {
                    "assessments": [
                        {
                            "news_id": n["news_id"],
                            "supported": self.supported,
                            "reason": "Checked the finding against the actual supplied task, not skill membership alone.",
                        }
                        for n in packet["news"]
                    ]
                }
            )
        return SimpleNamespace(
            value=value,
            returned_model=self.model,
            request_attempts=({"model": self.model, "outcome": "success"},),
        )


class TestRoleEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "queue.json"
        self.decisions = self.path.parent / "role_decisions.json"
        self.skill_decisions = self.path.parent / "skill_decisions.json"
        self.catalog = role_catalog()
        seed(self.path)
        map_skills(
            state_path=self.path, catalog=self.catalog, client=StubMapper(), now=NOW
        )

    def kwargs(self):
        return {
            "state_path": self.path,
            "catalog": self.catalog,
            "model": StubMapper.model,
            "skill_decisions_path": self.skill_decisions,
        }

    def run_roles(self, client=None, **kwargs):
        inputs = self.kwargs()
        inputs.pop("model")
        return role_evidence.run_assessments(
            **inputs,
            client=client or StubRoleMapper(),
            now=kwargs.pop("now", NOW),
            **kwargs,
        )

    def active(self):
        return role_evidence.active_assessments(
            **self.kwargs(), decisions_path=self.decisions
        )[0]

    def decide(self, record, decision="approve", **kwargs):
        return role_evidence.decide_impact(
            fingerprint(record),
            **self.kwargs(),
            decisions_path=self.decisions,
            decision=decision,
            reviewer="Fictional reviewer",
            **kwargs,
        )

    def test_shortlist_uses_positive_skills_then_checks_actual_tasks_and_caches(self):
        client = StubRoleMapper()
        first = self.run_roles(client)
        self.assertEqual(first["candidate_pairs"], 2)
        self.assertEqual(first["assessments_written"], 2)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            client.calls[0][1]["role"]["tasks"][0]["mapping_status"], "unmapped"
        )
        self.assertFalse(any(a["approved"] for a in self.active()))
        self.assertFalse(self.active()[0]["record"]["changes_weights"])
        client.calls.clear()
        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=AssertionError("No network on cache hit"),
        ):
            again = self.run_roles(client)
        self.assertEqual(again["batches_attempted"], 0)
        self.assertEqual(client.calls, [])

    def test_missing_positive_skill_evidence_means_no_role_calls(self):
        map_skills(
            state_path=self.path,
            catalog=self.catalog,
            client=StubMapper(relevance="not_relevant"),
            force=True,
            skill_ids=["skill:programming"],
            now=NOW + timedelta(seconds=1),
        )
        client = StubRoleMapper()
        result = self.run_roles(client)
        self.assertEqual(result["candidate_pairs"], 0)
        self.assertEqual(client.calls, [])

    def test_source_approval_required_before_shortlisting(self):
        queue = json.loads(self.path.read_text())
        for row in queue["items"]:
            row["source_review_status"] = "pending_review"
        atomic_json(self.path, queue)
        client = StubRoleMapper()
        self.assertEqual(self.run_roles(client)["candidate_pairs"], 0)
        self.assertEqual(client.calls, [])

    def test_missing_tasks_cache_insufficient_evidence_without_ai(self):
        self.catalog.roles[0].task_ids = []
        client = StubRoleMapper()
        self.assertEqual(self.run_roles(client)["assessments_written"], 2)
        self.assertEqual(client.calls, [])
        self.assertEqual(
            self.active()[0]["record"]["assessment"]["relevance"],
            "insufficient_evidence",
        )
        with self.assertRaisesRegex(ValueError, "Insufficient evidence"):
            self.decide(self.active()[0]["record"])

    def test_invalid_task_finding_or_duplicate_article_never_creates_records(self):
        for option in ("invent_task", "invent_finding", "duplicate"):
            with self.subTest(option=option):
                result = self.run_roles(StubRoleMapper(**{option: True}))
                self.assertEqual(result["failed_batches"], 1)
                self.assertEqual(result["assessments_written"], 0)
                self.assertEqual(self.active(), [])

    def test_skeptic_can_block_a_positive_role_claim(self):
        self.run_roles(StubRoleMapper(supported=False))
        item = self.active()[0]
        self.assertIn("flagged", item["block_reason"])
        with self.assertRaisesRegex(ValueError, "flagged"):
            self.decide(item["record"])

    def test_negative_and_insufficient_results_are_cached_and_not_approvable(self):
        for index, relevance in enumerate(("not_relevant", "insufficient_evidence")):
            with self.subTest(relevance=relevance):
                self.run_roles(
                    StubRoleMapper(relevance=relevance),
                    force=True,
                    role_ids=["role:first"],
                    now=NOW + timedelta(seconds=index),
                )
                for item in self.active():
                    self.assertTrue(item["block_reason"])
                    with self.assertRaises(ValueError):
                        self.decide(item["record"])
                client = StubRoleMapper()
                self.assertEqual(self.run_roles(client)["batches_attempted"], 0)
                self.assertEqual(client.calls, [])

    def test_approval_is_explicit_revisable_and_offline_lookup_has_tasks_and_quotes(
        self,
    ):
        self.run_roles()
        record = self.active()[0]["record"]
        before_skill = list((self.path.parent / "skill_assessments").glob("*.json"))
        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=AssertionError("No network"),
        ):
            self.decide(record)
            response = role_evidence.evidence_for_role(
                "role:first", **self.kwargs(), decisions_path=self.decisions
            )
        self.assertEqual(len(response["approved_conditional_role_impacts"]), 1)
        self.assertTrue(response["approved_conditional_role_impacts"][0]["tasks"])
        self.assertTrue(
            response["approved_conditional_role_impacts"][0]["supporting_findings"]
        )
        self.assertFalse(response["changes_weights"])
        self.decide(record, "reject", reason="Work setting does not match.")
        self.assertFalse(any(a["approved"] for a in self.active()))
        decision = self.decide(record, reason="Reviewed the narrow conditions.")
        self.assertEqual(
            [r["decision"] for r in decision["history"]], ["approve", "reject"]
        )
        self.assertEqual(
            before_skill, list((self.path.parent / "skill_assessments").glob("*.json"))
        )

    def test_new_role_checks_only_new_role_and_task_change_invalidates_only_that_role(
        self,
    ):
        self.run_roles()
        new = copy.deepcopy(self.catalog.roles[0])
        new.role_id = "role:second"
        self.catalog.roles.append(new)
        self.catalog.role_skills.append(
            SimpleNamespace(role_id="role:second", skill_id="skill:programming")
        )
        client = StubRoleMapper()
        self.assertEqual(self.run_roles(client)["assessments_written"], 2)
        self.assertEqual(
            {c[1]["role"]["role_id"] for c in client.calls}, {"role:second"}
        )
        self.catalog.roles[0].description = "Changed scope."
        client = StubRoleMapper()
        self.assertEqual(self.run_roles(client)["assessments_written"], 2)
        self.assertEqual(
            {c[1]["role"]["role_id"] for c in client.calls}, {"role:first"}
        )

    def test_source_change_or_upstream_skill_rejection_removes_approved_impacts(self):
        self.run_roles()
        record = self.active()[0]["record"]
        self.decide(record)
        atomic_json(
            self.skill_decisions,
            {
                "decisions": {
                    record["shortlist"][0]["assessment_sha256"]: {"decision": "reject"}
                }
            },
        )
        self.assertFalse(any(a["approved"] for a in self.active()))
        atomic_json(self.skill_decisions, {"decisions": {}})
        queue = json.loads(self.path.read_text())
        row = next(r for r in queue["items"] if r["discovery_id"] == record["news_id"])
        row["title"] += " changed"
        atomic_json(self.path, queue)
        self.assertFalse(any(a["approved"] for a in self.active()))
        with self.assertRaisesRegex(ValueError, "context changed"):
            self.decide(record)

    def test_failed_targeted_recheck_preserves_history_suspends_approval_then_recovers(
        self,
    ):
        self.run_roles()
        record = self.active()[0]["record"]
        self.decide(record)
        client = StubRoleMapper(fail=True)
        result = self.run_roles(
            client,
            force=True,
            role_ids=["role:first"],
            news_ids=[record["news_id"]],
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(result["failed_batches"], 1)
        self.assertEqual(
            [n["news_id"] for n in client.calls[0][1]["news"]], [record["news_id"]]
        )
        item = next(
            a for a in self.active() if a["record"]["news_id"] == record["news_id"]
        )
        self.assertFalse(item["approved"])
        self.assertIn("previous assessment", item["block_reason"])
        with self.assertRaisesRegex(ValueError, "failed"):
            self.decide(record)
        self.run_roles(
            force=True,
            role_ids=["role:first"],
            news_ids=[record["news_id"]],
            now=NOW + timedelta(seconds=2),
        )
        self.assertTrue(
            (
                self.path.parent / "role_assessments" / f"{fingerprint(record)}.json"
            ).exists()
        )
        latest = next(
            a for a in self.active() if a["record"]["news_id"] == record["news_id"]
        )
        self.assertFalse(latest["approved"])
        self.assertEqual(latest["block_reason"], "")

    def test_tampered_record_and_invalid_recheck_arguments_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "explicit role"):
            self.run_roles(force=True)
        with self.assertRaisesRegex(ValueError, "Unknown role"):
            self.run_roles(role_ids=["role:missing"])
        self.run_roles()
        path = next((self.path.parent / "role_assessments").glob("*.json"))
        record = json.loads(path.read_text())
        record["role"]["description"] = "Tampered"
        atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, "hash"):
            self.active()


if __name__ == "__main__":
    unittest.main()
