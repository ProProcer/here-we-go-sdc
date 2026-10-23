import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from pydantic import SecretStr, ValidationError

from src.ingestion.catalog import load_role_catalog
from src.intelligence.approval import approve_plan, prepare_approval
from src.intelligence.extraction import extract_candidates
from src.intelligence.extractors import ExtractionError, ModelExtraction
from src.intelligence.feeds import APPROVED_URL
from src.intelligence.gemini import GeminiClient
from src.intelligence.proposals import (
    generate_task_skill_proposal,
    load_current_proposal,
    load_proposal_context,
    main,
)
from src.intelligence.proposers import GeminiTaskSkillProposer, ModelProposal
from src.schemas.extraction import ExtractionBatch
from src.schemas.proposals import TaskSkillProposal
from src.schemas.trends import EvidenceLedger

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "tests/fixtures/extraction_report.html").read_bytes()
FINDINGS = (ROOT / "tests/fixtures/approval_findings.json").read_bytes()
NOW = datetime(2026, 10, 21, 1, tzinfo=timezone.utc)


class FixtureExtractor:
    model = "test-model"

    def extract(self, report, source):
        return ModelExtraction(
            ExtractionBatch.model_validate_json(FINDINGS), "test-model"
        )


def insufficient_payload(packet):
    return {
        "role_id": packet["role"]["role_id"],
        "signal_id": packet["accepted_finding"]["signal_id"],
        "summary": "The finding does not establish role-specific task or skill changes.",
        "tasks": [
            {
                "task_id": task["task_id"],
                "assessment": "insufficient_evidence",
                "finding_relevance": "This finding is not a measurement of this particular role task.",
                "task_change": None,
                "assumptions": [],
                "human_responsibilities": [],
                "limitations": ["Task-specific evidence is missing."],
                "skill_implications": [
                    {
                        "skill_id": skill["skill_id"],
                        "direction": "insufficient_evidence",
                        "less_emphasis": [],
                        "more_emphasis": [],
                        "rationale": "No task-specific direction follows from the accepted finding.",
                        "employer_demand_direction": "insufficient_evidence",
                    }
                    for skill in task["allowed_skills"]
                ],
            }
            for task in packet["role"]["tasks"]
        ],
    }


class StubProposer:
    model = "test-model"

    def __init__(self, mutate=None):
        self.mutate = mutate
        self.calls = 0
        self.packet = None

    def propose(self, packet):
        self.calls += 1
        self.packet = packet
        payload = insufficient_payload(packet)
        if self.mutate:
            self.mutate(payload)
        return ModelProposal(
            TaskSkillProposal.model_validate(payload), "test-model-version"
        )


class TestTaskSkillProposals(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ledger = self.directory / "ledger.json"
        self.output = self.directory / "proposals"
        self.catalog = load_role_catalog()
        record, candidate_path = extract_candidates(
            APPROVED_URL,
            FixtureExtractor(),
            output_directory=self.directory / "candidates",
            fetcher=lambda url: HTML,
            now=NOW,
        )
        _, plan = prepare_approval(
            candidate_path,
            record.findings[0].candidate_id,
            output_directory=self.directory / "plans",
            now=NOW,
        )
        result = approve_plan(
            plan,
            reviewer="Test reviewer",
            approve=True,
            ledger_path=self.ledger,
            definitions_directory=self.directory / "definitions",
            snapshots_path=self.directory / "snapshots",
            fetcher=lambda url: HTML,
            now=NOW,
        )
        self.review = result.reviewed_source_path

    def generate(self, proposer=None, **kwargs):
        return generate_task_skill_proposal(
            self.review,
            "role:data_analyst",
            proposer or StubProposer(),
            evidence_path=self.ledger,
            output_directory=self.output,
            now=NOW + timedelta(minutes=1),
            **kwargs,
        )

    def test_insufficient_evidence_covers_all_allowed_skills_and_stays_pending(self):
        before = self.ledger.read_bytes()
        catalog_before = self.catalog.model_dump()
        record, path = self.generate()
        self.assertEqual(record.status, "insufficient_evidence")
        self.assertEqual(record.review_status, "pending_review")
        self.assertFalse(record.changes_skill_weights)
        self.assertTrue(record.catalog_synthetic)
        self.assertEqual(len(record.tasks), 2)
        self.assertEqual(
            [row.skill_id for row in record.tasks[0].skill_implications],
            ["skill:python", "skill:sql"],
        )
        self.assertEqual(
            [row.skill_id for row in record.tasks[1].skill_implications],
            ["skill:data_visualization"],
        )
        self.assertEqual(
            {row.skill_id for row in record.unmapped_role_skills},
            {"skill:statistics", "skill:communication"},
        )
        self.assertEqual(load_current_proposal(path, evidence_path=self.ledger), record)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(load_role_catalog().model_dump(), catalog_before)

    def test_conditional_skill_aspects_are_explained_without_global_priority_changes(
        self,
    ):
        def conditional(payload):
            task = payload["tasks"][0]
            task.update(
                assessment="conditional_interpretation",
                task_change="If AI drafts routine cleaning code, review may take more of the workflow.",
                assumptions=["An employer adopts a human-reviewed coding workflow."],
                human_responsibilities=["Validate transformations and row counts."],
            )
            task["skill_implications"][0].update(
                direction="mixed",
                less_emphasis=[
                    "Drafting repetitive boilerplate, if AI handles it reliably."
                ],
                more_emphasis=[
                    "Reading and testing generated transformations in the assumed workflow."
                ],
                rationale="Within this assumed workflow, emphasis shifts between drafting and validation; broad skill demand remains unknown.",
            )

        record, _ = self.generate(StubProposer(conditional))
        self.assertEqual(record.status, "proposed_interpretations")
        self.assertEqual(record.tasks[0].skill_implications[0].direction, "mixed")
        self.assertEqual(record.tasks[1].assessment, "insufficient_evidence")

    def test_packet_exposes_approved_context_but_no_owner_paths_or_numeric_weights(
        self,
    ):
        proposer = StubProposer()
        self.generate(proposer)
        packet = json.dumps(proposer.packet)
        self.assertNotIn("importance", packet)
        self.assertNotIn("reviewer", packet)
        self.assertNotIn(str(self.directory), packet)
        self.assertIn("reviewed_limitations", packet)
        self.assertIn("published_at", packet)
        self.assertIn("study_period", packet)
        self.assertEqual(proposer.calls, 1)

    def test_saved_but_unadmitted_or_unapproved_findings_never_reach_the_model(self):
        proposer = Mock()
        accepted = self.ledger.read_bytes()
        empty = EvidenceLedger(
            schema_version="0.1.0", sources=[], signals=[], task_interpretations=[]
        )
        self.ledger.write_text(empty.model_dump_json(), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not present"):
            self.generate(proposer)
        self.ledger.write_bytes(accepted)
        review = json.loads(self.review.read_bytes())
        review["approval"] = None
        self.review.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "explicit approval"):
            self.generate(proposer)
        proposer.propose.assert_not_called()

    def test_changed_accepted_claim_and_source_metadata_are_rejected(self):
        original = json.loads(self.ledger.read_bytes())
        for target in ("claim", "source"):
            payload = copy.deepcopy(original)
            if target == "claim":
                payload["signals"][0]["claim"] = "Changed accepted wording."
            else:
                payload["sources"][0]["coverage"] = "Changed source coverage."
            self.ledger.write_text(json.dumps(payload), encoding="utf-8")
            proposer = Mock()
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.generate(proposer)
            proposer.propose.assert_not_called()

    def test_unknown_role_is_rejected_without_a_model_call(self):
        proposer = Mock()
        with self.assertRaisesRegex(ValueError, "Unknown"):
            generate_task_skill_proposal(
                self.review, "role:missing", proposer, evidence_path=self.ledger
            )
        proposer.propose.assert_not_called()

    def test_wrong_scope_duplicate_tasks_and_missing_tasks_are_rejected(self):
        for case in ("role", "signal", "duplicate", "missing"):

            def mutate(payload, case=case):
                if case == "role":
                    payload["role_id"] = "role:business_analyst"
                elif case == "signal":
                    payload["signal_id"] = "signal:unrelated"
                elif case == "duplicate":
                    payload["tasks"].append(copy.deepcopy(payload["tasks"][0]))
                else:
                    payload["tasks"].pop()

            with self.subTest(case=case), self.assertRaises(ValueError):
                self.generate(StubProposer(mutate))
        self.assertFalse(self.output.exists())

    def test_extra_missing_duplicate_and_wrong_task_skills_are_rejected(self):
        for skill in ("skill:spreadsheets", "skill:statistics", "skill:invented"):

            def extra(payload, skill=skill):
                item = copy.deepcopy(payload["tasks"][0]["skill_implications"][0])
                item["skill_id"] = skill
                payload["tasks"][0]["skill_implications"].append(item)

            with self.subTest(skill=skill), self.assertRaises(ValueError):
                self.generate(StubProposer(extra))
        for duplicate in (True, False):

            def mutate(payload, duplicate=duplicate):
                skills = payload["tasks"][0]["skill_implications"]
                if duplicate:
                    skills.append(copy.deepcopy(skills[0]))
                else:
                    skills.pop()

            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                self.generate(StubProposer(mutate))

    def test_insufficient_evidence_cannot_smuggle_in_an_increase_or_workflow(self):
        for case in ("workflow", "direction", "weights", "approval"):

            def mutate(payload, case=case):
                task = payload["tasks"][0]
                if case == "workflow":
                    task["task_change"] = "Invented workflow."
                elif case == "direction":
                    task["skill_implications"][0].update(
                        direction="increase", more_emphasis=["Invented increase."]
                    )
                elif case == "weights":
                    task["skill_implications"][0]["adjusted_priority"] = 0.9
                else:
                    payload["review_status"] = "approved"

            with self.subTest(case=case), self.assertRaises(ValidationError):
                self.generate(StubProposer(mutate))

    def test_each_direction_requires_consistent_aspects(self):
        packet = load_proposal_context(
            self.review, "role:data_analyst", evidence_path=self.ledger
        ).packet
        for direction in ("increase", "decrease", "mixed", "unchanged"):
            payload = insufficient_payload(packet)
            task = payload["tasks"][0]
            task.update(
                assessment="conditional_interpretation",
                task_change="A conditional workflow.",
                assumptions=["Assumed adoption."],
                human_responsibilities=["Review results."],
            )
            skill = task["skill_implications"][0]
            skill["direction"] = direction
            if direction == "unchanged":
                skill["more_emphasis"] = ["Contradicts unchanged."]
            with self.subTest(direction=direction), self.assertRaises(ValidationError):
                TaskSkillProposal.model_validate(payload)

    def test_repeated_runs_preserve_history_and_failed_runs_preserve_previous_outputs(
        self,
    ):
        _, first = self.generate()
        _, second = self.generate()
        self.assertNotEqual(first, second)
        before = {path.name: path.read_bytes() for path in self.output.glob("*.json")}
        proposer = Mock(model="test-model")
        proposer.propose.side_effect = ExtractionError("Provider failure")
        with self.assertRaises(ExtractionError):
            self.generate(proposer)
        self.assertEqual(
            {path.name: path.read_bytes() for path in self.output.glob("*.json")},
            before,
        )

    def test_input_mutation_and_concurrent_accepted_changes_cannot_expand_scope(self):
        class MutatingProposer(StubProposer):
            def propose(inner, packet):
                packet["role"]["tasks"][0]["allowed_skills"].append(
                    {"skill_id": "skill:invented", "label": "Invented"}
                )
                return super().propose(packet)

        with self.assertRaises(ValueError):
            self.generate(MutatingProposer())

        def concurrent_change(payload):
            ledger = json.loads(self.ledger.read_bytes())
            ledger["signals"][0]["claim"] = "Changed during generation."
            self.ledger.write_text(json.dumps(ledger), encoding="utf-8")

        with self.assertRaises(ValueError):
            self.generate(StubProposer(concurrent_change))
        self.assertFalse(self.output.exists())

    def test_stale_review_and_catalog_are_detected_on_load(self):
        _, path = self.generate()
        changed = self.catalog.model_dump()
        changed["role_skills"][0]["importance"] = 0.6
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            load_current_proposal(
                path,
                evidence_path=self.ledger,
                catalog=type(self.catalog).model_validate(changed),
            )
        self.review.write_bytes(self.review.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            load_current_proposal(path, evidence_path=self.ledger)

    def test_unrelated_new_signals_do_not_make_a_proposal_stale(self):
        record, path = self.generate()
        ledger = json.loads(self.ledger.read_bytes())
        signal = copy.deepcopy(ledger["signals"][0])
        signal.update(signal_id="signal:unrelated", claim="Unrelated accepted context.")
        ledger["signals"].append(signal)
        self.ledger.write_text(json.dumps(ledger), encoding="utf-8")
        self.assertEqual(load_current_proposal(path, evidence_path=self.ledger), record)

    def test_old_prompt_policies_and_false_approval_flags_are_rejected(self):
        record, path = self.generate()
        payload = record.model_dump(mode="json")
        payload["prompt_version"] = "older-policy"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            load_current_proposal(path, evidence_path=self.ledger)
        payload["review_status"] = "approved"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_current_proposal(path, evidence_path=self.ledger)

    def test_empty_task_skill_intersections_do_not_add_requirements(self):
        catalog = self.catalog.model_dump()
        catalog["role_skills"] = [
            row
            for row in catalog["role_skills"]
            if not (
                row["role_id"] == "role:data_analyst"
                and row["skill_id"] in {"skill:python", "skill:sql"}
            )
        ]
        record, _ = self.generate(catalog=type(self.catalog).model_validate(catalog))
        self.assertEqual(record.tasks[0].skill_implications, [])

    def test_cli_inspect_and_check_need_no_credentials_and_generate_reports_missing_key(
        self,
    ):
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "inspect",
                        "--review",
                        str(self.review),
                        "--ledger",
                        str(self.ledger),
                    ]
                ),
                0,
            )
        self.assertFalse(json.loads(output.getvalue())["model_called"])
        _, path = self.generate()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(["check", "--proposal", str(path), "--ledger", str(self.ledger)]),
                0,
            )
        error = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), patch("src.intelligence.models.load_local_environment"), redirect_stderr(error):
            self.assertEqual(
                main(
                    [
                        "generate",
                        "--review",
                        str(self.review),
                        "--ledger",
                        str(self.ledger),
                    ]
                ),
                1,
            )
        self.assertIn("GEMINI_API_KEY", error.getvalue())

    def test_gemini_adapter_requests_proposal_schema_and_keeps_secret_out_of_payload(
        self,
    ):
        context = load_proposal_context(
            self.review, "role:data_analyst", evidence_path=self.ledger
        )
        reply = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": json.dumps(insufficient_payload(context.packet))}
                        ]
                    },
                }
            ],
            "modelVersion": "gemini-test",
        }
        with patch("src.intelligence.gemini.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.headers.get_content_type.return_value = "application/json"
            response.read.return_value = json.dumps(reply).encode()
            proposer = GeminiTaskSkillProposer(
                GeminiClient(SecretStr("sentinel-secret"), "gemini-test")
            )
            result = proposer.propose(context.packet)
            request = opener.return_value.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertIn(
            "tasks", body["generationConfig"]["responseJsonSchema"]["properties"]
        )
        schema = body["generationConfig"]["responseJsonSchema"]
        self.assertEqual(schema["properties"]["tasks"]["maxItems"], 2)
        self.assertEqual(schema["properties"]["tasks"]["minItems"], 2)
        self.assertEqual(
            schema["$defs"]["ProposedTaskImpact"]["properties"]["skill_implications"][
                "maxItems"
            ],
            2,
        )
        demand = schema["$defs"]["ProposedSkillImplication"]["properties"][
            "employer_demand_direction"
        ]
        self.assertEqual(demand["enum"], ["insufficient_evidence"])
        self.assertEqual(demand["type"], "string")
        self.assertNotIn("const", demand)
        self.assertNotIn("sentinel-secret", request.data.decode())
        self.assertNotIn("tools", body)
        self.assertEqual(result.proposal.role_id, "role:data_analyst")


if __name__ == "__main__":
    unittest.main()
