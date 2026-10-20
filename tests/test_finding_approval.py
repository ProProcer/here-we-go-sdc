import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import URLError

from pydantic import ValidationError

from src.intelligence.approval import approve_plan, main, prepare_approval
from src.intelligence.evidence import DEFAULT_EVIDENCE, load_evidence
from src.intelligence.extraction import extract_candidates
from src.intelligence.extractors import ModelExtraction
from src.intelligence.feeds import APPROVED_URL, ReviewedSource, refresh_evidence
from src.intelligence.outlook import get_outlook
from src.schemas.approval import ApprovalPlan, ApprovedTaskMapping
from src.schemas.extraction import ExtractionBatch, ExtractionRecord
from src.schemas.trends import EvidenceLedger

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "tests/fixtures/extraction_report.html").read_bytes()
FINDINGS = (ROOT / "tests/fixtures/approval_findings.json").read_bytes()
NOW = datetime(2026, 10, 20, 16, tzinfo=timezone.utc)


class FixtureExtractor:
    model = "test-model"

    def extract(self, report, source):
        return ModelExtraction(
            ExtractionBatch.model_validate_json(FINDINGS), "test-model"
        )


class TestFindingApproval(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ledger = self.directory / "ledger.json"
        self.snapshots = self.directory / "snapshots"
        self.definitions = self.directory / "definitions"
        self.plans = self.directory / "plans"
        self.record, self.candidate_path = extract_candidates(
            APPROVED_URL,
            FixtureExtractor(),
            output_directory=self.directory / "candidates",
            fetcher=lambda url: HTML,
            now=NOW,
        )
        self.candidate_id = self.record.findings[0].candidate_id
        self.empty = EvidenceLedger(
            schema_version="0.1.0", sources=[], signals=[], task_interpretations=[]
        )
        self.ledger.write_text(self.empty.model_dump_json(), encoding="utf-8")
        self.fetcher = Mock(return_value=HTML)

    def prepare(self, **kwargs):
        return prepare_approval(
            self.candidate_path,
            self.candidate_id,
            output_directory=self.plans,
            now=NOW,
            **kwargs,
        )

    def approve(self, plan_path, **kwargs):
        return approve_plan(
            plan_path,
            reviewer=kwargs.pop("reviewer", "Test reviewer"),
            approve=kwargs.pop("approve", True),
            ledger_path=self.ledger,
            snapshots_path=self.snapshots,
            definitions_directory=self.definitions,
            fetcher=self.fetcher,
            now=NOW + timedelta(minutes=1),
            **kwargs,
        )

    def test_preparation_is_offline_and_preserves_candidate_and_accepted_evidence(self):
        candidate_before = self.candidate_path.read_bytes()
        ledger_before = self.ledger.read_bytes()
        plan, path = self.prepare()
        self.assertEqual(ApprovalPlan.model_validate_json(path.read_bytes()), plan)
        self.assertEqual(plan.status, "prepared")
        self.assertEqual(plan.reviewed_claim, self.record.findings[0].claim)
        self.assertEqual(self.candidate_path.read_bytes(), candidate_before)
        self.assertEqual(self.ledger.read_bytes(), ledger_before)
        self.assertFalse(self.definitions.exists())
        self.fetcher.assert_not_called()

    def test_approval_generates_definition_and_admits_finding_with_audit_provenance(
        self,
    ):
        _, path = self.prepare()
        result = self.approve(path)
        self.assertEqual(result.refresh.status, "updated")
        self.fetcher.assert_called_once_with(APPROVED_URL)
        ledger = load_evidence(self.ledger)
        self.assertEqual(len(ledger.signals), 1)
        self.assertEqual(ledger.task_interpretations, [])
        self.assertIn("not an employment outcome", ledger.signals[0].claim)
        self.assertIn(self.record.findings[0].limitations[0], ledger.signals[0].claim)
        review = ReviewedSource.model_validate_json(
            result.reviewed_source_path.read_bytes()
        )
        self.assertEqual(review.approval.reviewer, "Test reviewer")
        self.assertEqual(review.approval.candidate_id, self.candidate_id)
        snapshot = json.loads(Path(result.refresh.snapshot_path).read_bytes())
        self.assertEqual(snapshot["approval"], review.approval.model_dump(mode="json"))
        self.assertEqual(snapshot["ledger"], ledger.model_dump(mode="json"))
        self.assertEqual(
            snapshot["review_sha256"],
            hashlib.sha256(result.reviewed_source_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            ExtractionRecord.model_validate_json(self.candidate_path.read_bytes()),
            self.record,
        )

    def test_optional_mapping_affects_outlook_and_never_changes_scenario_weights(self):
        before = get_outlook("role:data_analyst", evidence_path=self.ledger)
        mapping = ApprovedTaskMapping(
            role_id="role:data_analyst",
            task_id="task:data_cleaning",
            interpretation="Reviewed contextual interpretation, not measured cleaning automation.",
        )
        _, path = self.prepare(task_mapping=mapping)
        self.approve(path)
        after = get_outlook("role:data_analyst", evidence_path=self.ledger)
        self.assertEqual(before.scenario, after.scenario)
        self.assertEqual(after.tasks[0].interpretation, mapping.interpretation)
        self.assertEqual(len(after.signals), 1)
        self.assertEqual(after.tasks[1].evidence_status, "insufficient_evidence")

    def test_reviewer_corrections_and_projection_classification_are_preserved(self):
        _, path = self.prepare(
            reviewed_claim="Reviewed conditional projection, not an observed employment outcome.",
            reviewed_limitations=["Reviewed projection assumptions remain uncertain."],
            reviewed_evidence_type="author_projection",
        )
        result = self.approve(path)
        signal = load_evidence(self.ledger).signals[0]
        self.assertTrue(signal.claim.startswith("Author projection"))
        self.assertIn("Reviewed projection assumptions", signal.claim)
        audit = ReviewedSource.model_validate_json(
            result.reviewed_source_path.read_bytes()
        ).approval
        self.assertEqual(audit.evidence_type, "author_projection")
        self.assertEqual(audit.extracted_evidence_type, "observed_usage")

    def test_explicit_approval_and_nonblank_reviewer_are_required_before_fetch(self):
        _, path = self.prepare()
        for kwargs in ({"approve": False}, {"reviewer": "   "}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.approve(path, **kwargs)
        self.fetcher.assert_not_called()
        self.assertFalse(self.definitions.exists())

    def test_stale_candidate_file_or_plan_digest_is_rejected_before_fetch(self):
        _, path = self.prepare()
        with self.assertRaisesRegex(ValueError, "Plan file changed"):
            self.approve(path, expected_plan_sha256="0" * 64)
        self.candidate_path.write_bytes(self.candidate_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Candidate file changed"):
            self.approve(path)
        self.fetcher.assert_not_called()

    def test_changed_report_is_rejected_even_when_the_old_quote_remains_present(self):
        _, path = self.prepare()
        before = self.ledger.read_bytes()
        self.fetcher.return_value = HTML.replace(
            b"national skill demand", b"regional skill demand"
        )
        with self.assertRaisesRegex(ValueError, "Report text changed"):
            self.approve(path)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertFalse(self.definitions.exists())

    def test_nonarticle_html_changes_do_not_invalidate_approval(self):
        _, path = self.prepare()
        self.fetcher.return_value = HTML + b"<!-- transport-only change -->"
        result = self.approve(path)
        self.assertEqual(result.refresh.status, "updated")
        self.assertNotEqual(result.refresh.response_sha256, self.record.response_sha256)

    def test_reusable_definition_also_blocks_report_drift_on_later_refresh(self):
        _, path = self.prepare()
        result = self.approve(path)
        before = self.ledger.read_bytes()
        changed = HTML.replace(b"national skill demand", b"regional skill demand")
        refresh = refresh_evidence(
            review_path=result.reviewed_source_path,
            ledger_path=self.ledger,
            snapshots_path=self.snapshots,
            fetcher=lambda url: changed,
            now=NOW + timedelta(days=1),
        )
        self.assertEqual(refresh.status, "cached")
        self.assertIn("re-extract", refresh.message)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_edited_approved_definition_cannot_reuse_old_review_provenance(self):
        _, path = self.prepare()
        result = self.approve(path)
        payload = json.loads(result.reviewed_source_path.read_bytes())
        payload["signal"]["claim"] = "Unreviewed replacement wording."
        with self.assertRaisesRegex(ValidationError, "wording or mapping changed"):
            ReviewedSource.model_validate(payload)

    def test_existing_sources_chains_and_unrelated_signals_are_preserved(self):
        self.ledger.write_bytes(DEFAULT_EVIDENCE.read_bytes())
        before = load_evidence(self.ledger)
        _, path = self.prepare()
        self.approve(path)
        after = load_evidence(self.ledger)
        self.assertEqual(after.sources, before.sources)
        self.assertEqual(after.evidence_chains, before.evidence_chains)
        self.assertEqual(after.signals[:-1], before.signals)
        self.assertEqual(after.task_interpretations, before.task_interpretations)

    def test_repeated_approval_does_not_duplicate_or_silently_revise_a_signal(self):
        _, path = self.prepare()
        self.approve(path)
        repeated = self.approve(path)
        self.assertEqual(repeated.refresh.status, "unchanged")
        self.assertEqual(len(load_evidence(self.ledger).signals), 1)
        _, revised = self.prepare(reviewed_claim="Different approved wording.")
        before = self.ledger.read_bytes()
        with self.assertRaisesRegex(ValueError, "already has different"):
            self.approve(revised)
        self.assertEqual(before, self.ledger.read_bytes())

    def test_unknown_candidates_modified_content_and_invalid_mappings_are_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            prepare_approval(
                self.candidate_path,
                "candidate:" + "0" * 24,
                output_directory=self.plans,
                now=NOW,
            )
        bad_mapping = ApprovedTaskMapping(
            role_id="role:data_analyst",
            task_id="task:incident_triage",
            interpretation="Unsupported pair.",
        )
        with self.assertRaises(ValueError):
            self.prepare(task_mapping=bad_mapping)
        payload = self.record.model_dump(mode="json")
        payload["findings"][0]["claim"] = (
            "Edited candidate without an updated content identity."
        )
        self.candidate_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "extraction identity"):
            self.prepare()

    def test_saved_quote_offsets_and_hashes_are_rechecked_on_admission(self):
        payload = self.record.model_dump(mode="json")
        payload["findings"][0]["support"]["passage_sha256"] = "0" * 64
        self.candidate_path.write_text(json.dumps(payload), encoding="utf-8")
        _, path = self.prepare()
        with self.assertRaisesRegex(ValueError, "references do not match"):
            self.approve(path)
        self.assertEqual(load_evidence(self.ledger), self.empty)

    def test_fetch_and_storage_failures_do_not_change_the_ledger(self):
        _, path = self.prepare()
        before = self.ledger.read_bytes()
        self.fetcher.side_effect = URLError("offline")
        with self.assertRaises(URLError):
            self.approve(path)
        self.fetcher.side_effect = None
        with (
            patch(
                "src.intelligence.approval.atomic_json",
                side_effect=OSError("disk full"),
            ),
            self.assertRaises(OSError),
        ):
            self.approve(path)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_failed_refresh_reports_not_admitted_and_keeps_the_definition_for_retry(
        self,
    ):
        _, path = self.prepare()
        before = self.ledger.read_bytes()
        from src.intelligence.feeds import atomic_json as real_write

        def fail_ledger(target, payload):
            if target == self.ledger:
                raise OSError("disk full")
            real_write(target, payload)

        with patch("src.intelligence.feeds.atomic_json", side_effect=fail_ledger):
            result = self.approve(path)
        self.assertEqual(result.refresh.status, "cached")
        self.assertTrue(result.reviewed_source_path.exists())
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_invalid_existing_ledger_is_not_overwritten(self):
        self.ledger.write_text("not JSON", encoding="utf-8")
        _, path = self.prepare()
        with self.assertRaises(ValidationError):
            self.approve(path)
        self.fetcher.assert_not_called()
        self.assertEqual(self.ledger.read_text(), "not JSON")


class TestApprovalCLI(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        _, self.path = extract_candidates(
            APPROVED_URL,
            FixtureExtractor(),
            output_directory=self.directory / "candidates",
            fetcher=lambda url: HTML,
            now=NOW,
        )

    def test_list_and_prepare_work_without_credentials_or_network(self):
        for arguments in (
            ["list", "--candidate-file", str(self.path)],
            [
                "prepare",
                "--candidate-file",
                str(self.path),
                "--finding",
                "1",
                "--output-dir",
                str(self.directory / "plans"),
            ],
        ):
            output = io.StringIO()
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("src.intelligence.approval._utc", return_value=NOW),
                redirect_stdout(output),
            ):
                self.assertEqual(main(arguments), 0)
            self.assertFalse(json.loads(output.getvalue())["accepted_evidence_changed"])

    def test_missing_approval_flag_is_an_argument_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
            main(["approve", "--plan", "unused.json", "--reviewer", "Test reviewer"])
        self.assertEqual(context.exception.code, 2)

    def test_partial_task_mapping_and_bad_selection_fail_without_a_plan(self):
        for suffix in (
            ["--finding", "0"],
            ["--finding", "1", "--role", "role:data_analyst"],
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "prepare",
                            "--candidate-file",
                            str(self.path),
                            *suffix,
                            "--output-dir",
                            str(self.directory / "plans"),
                        ]
                    ),
                    1,
                )
        self.assertFalse((self.directory / "plans").exists())


if __name__ == "__main__":
    unittest.main()
