import hashlib
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.ingestion.selection import real_catalog
from src.intelligence.approval import approve_plan, prepare_approval
from src.intelligence.evidence import load_evidence
from src.intelligence.extraction import extract_candidates
from src.intelligence.extractors import ModelExtraction
from src.intelligence.outlook import get_outlook
from src.intelligence.priorities import (
    PriorityAssessment,
    aggregate_assessments,
    approve_assessment,
    evaluate_priorities,
    load_policy,
    prepare_assessment,
)
from src.intelligence.sources import load_registry
from src.profiles.intake import create_profile
from src.profiles.onet_matching import OnetMatcher
from src.reskilling.planner import build_learning_plan
from src.schemas.approval import ApprovedTaskMapping
from src.schemas.extraction import ExtractionBatch

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, tzinfo=UTC)
BI = "role:onet_15_2051_01"
SKILL = "skill:onet_2_a_2_a"
TASK = "task:onet_16150"


def assessment(number, **changes):
    payload = {
        "assessment_id": f"{number:064x}",
        "review_path": "fictional.json",
        "reviewed_definition_sha256": "0" * 64,
        "evidence_sha256": "0" * 64,
        "policy_sha256": "0" * 64,
        "role_id": BI,
        "task_id": TASK,
        "skill_id": SKILL,
        "signal_id": f"signal:test_{number}",
        "publisher": f"Fictional publisher {number}",
        "published_at": NOW.date(),
        "evidence_type": "labour_market_observation",
        "study_group": f"fictional_independent_study_{number}",
        "direction": "increase",
        "quality": "strong",
        "relevance": "direct",
        "rationale": "Fictional assessment for policy tests only.",
    }
    return PriorityAssessment(**{**payload, **changes})


class TestPriorityAggregation(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def calc(self, rows, when=None):
        return aggregate_assessments(rows, self.policy, when or NOW.date())

    def test_one_source_and_duplicate_studies_cannot_change_priority(self):
        self.assertEqual(self.calc([assessment(1)])["adjustment"], 0)
        result = self.calc(
            [assessment(1), assessment(2, study_group="fictional_independent_study_1")]
        )
        self.assertEqual(result["adjustment"], 0)
        result = self.calc(
            [assessment(1), assessment(2, publisher="Fictional publisher 1")]
        )
        self.assertEqual(result["adjustment"], 0)

    def test_benchmarks_projections_and_indirect_mappings_cannot_set_weights(self):
        for change in (
            {"evidence_type": "benchmark"},
            {"evidence_type": "author_projection"},
            {"relevance": "indirect"},
        ):
            result = self.calc([assessment(1, **change), assessment(2, **change)])
            self.assertEqual(result["adjustment"], 0)

    def test_two_independent_sources_produce_bounded_directional_change(self):
        self.assertEqual(self.calc([assessment(1), assessment(2)])["adjustment"], 0.1)
        self.assertEqual(
            self.calc(
                [
                    assessment(1, direction="decrease"),
                    assessment(2, direction="decrease"),
                ]
            )["adjustment"],
            -0.1,
        )

    def test_disagreement_withholds_adjustment(self):
        result = self.calc([assessment(1), assessment(2, direction="decrease")])
        self.assertEqual(result["status"], "conflicting_evidence")
        self.assertEqual(result["adjustment"], 0)

    def test_recency_decay_expiry_and_quality_reduce_influence(self):
        rows = [assessment(1), assessment(2)]
        self.assertAlmostEqual(
            self.calc(rows, NOW.date() + timedelta(days=180))["adjustment"], 0.05
        )
        self.assertEqual(
            self.calc(rows, NOW.date() + timedelta(days=731))["adjustment"], 0
        )
        self.assertEqual(
            self.calc(rows, NOW.date() - timedelta(days=1))["adjustment"], 0
        )
        self.assertEqual(
            self.calc(
                [assessment(1, quality="moderate"), assessment(2, quality="moderate")]
            )["adjustment"],
            0.05,
        )


class FictionalExtractor:
    model = "fictional-test-only"

    def extract(self, report, source):
        return ModelExtraction(
            ExtractionBatch.model_validate(
                {
                    "findings": [
                        {
                            "claim": "A fictional study reports a skill-related observation.",
                            "evidence_type": "observed_usage",
                            "support": {
                                "passage_id": next(
                                    p.passage_id
                                    for p in report.passages
                                    if "Fictional evidence for testing" in p.text
                                ),
                                "quote": "Fictional evidence for testing",
                            },
                            "study_period": {
                                "start": None,
                                "end": None,
                                "passage_id": None,
                            },
                            "limitations": [
                                "Synthetic test data; no real-world claims."
                            ],
                        }
                    ],
                    "no_findings_reason": None,
                }
            ),
            self.model,
        )


class TestPriorityApprovalIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / "ledger.json"
        self.store = self.root / "assessments.json"
        self.store.write_text('{"schema_version":"0.1.0","assessments":[]}')

    def admit(self, index):
        source = load_registry().sources[index]
        page = (
            f"<html><main><h1>Fictional policy integration report</h1><p>{source.published_at}</p><p>Fictional evidence for testing "
            + "makes no actual occupational claim. " * 10
            + "</p></main></html>"
        ).encode()
        record, candidate_path = extract_candidates(
            str(source.source_url),
            FictionalExtractor(),
            output_directory=self.root / "candidates",
            fetcher=lambda url: page,
            now=NOW,
        )
        _, plan_path = prepare_approval(
            candidate_path,
            record.findings[0].candidate_id,
            task_mapping=ApprovedTaskMapping(
                role_id=BI, task_id=TASK, interpretation="Fictional test mapping only."
            ),
            output_directory=self.root / "plans",
            now=NOW,
        )
        result = approve_plan(
            plan_path,
            reviewer="Fictional test reviewer",
            approve=True,
            ledger_path=self.ledger,
            snapshots_path=self.root / "snapshots",
            definitions_directory=self.root / "definitions",
            fetcher=lambda url: page,
            now=NOW,
        )
        self.assertEqual(result.refresh.status, "updated", result.refresh.message)
        return result.reviewed_source_path

    def prepare(self, review, number):
        return prepare_assessment(
            review,
            role_id=BI,
            task_id=TASK,
            skill_id=SKILL,
            direction="increase",
            study_group=f"fictional_study_{number}",
            quality="strong",
            relevance="direct",
            rationale="Fictional independently reviewed relevance; not real evidence.",
            catalog=self.catalog,
            evidence_path=self.ledger,
            output_directory=self.root / "priorities",
        )

    def approve(self, path, **kwargs):
        return approve_assessment(
            path,
            reviewer="Fictional test reviewer",
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            store_path=self.store,
            catalog=self.catalog,
            evidence_path=self.ledger,
            now=NOW,
            **kwargs,
        )

    def test_prepared_and_single_approved_assessments_do_not_change_priority(self):
        _, plan = self.prepare(self.admit(0), 0)
        with self.assertRaisesRegex(ValueError, "Explicit approval"):
            self.approve(plan)
        self.assertEqual(json.loads(self.store.read_text())["assessments"], [])
        self.approve(plan, approve=True)
        result = evaluate_priorities(
            BI,
            catalog=self.catalog,
            ledger=load_evidence(self.ledger, catalog=self.catalog),
            store_path=self.store,
            as_of=NOW.date(),
        )
        self.assertEqual(result["decisions"][0]["adjustment"], 0)

    def test_two_reviewed_studies_flow_into_planner_without_changing_fit(self):
        for index in (0, 1):
            _, path = self.prepare(self.admit(index), index)
            self.approve(path, approve=True)
        outlook = get_outlook(
            BI,
            catalog=self.catalog,
            evidence_path=self.ledger,
            priority_store_path=self.store,
            priority_as_of=NOW.date(),
        )
        decision = outlook.learning_priority_evidence["decisions"][0]
        self.assertGreater(decision["adjustment"], 0)
        profile = create_profile(
            "synthetic:priority_test", ["Python"], catalog=self.catalog
        )
        match = OnetMatcher(self.catalog).match_role(profile, BI)
        result = build_learning_plan(
            profile,
            match,
            "baseline",
            catalog=self.catalog,
            country="Malaysia",
            preferred_language="English",
            outlook_loader=lambda role, scenario: outlook,
            generated_at=NOW,
        )
        gap = next(g for g in result.plan.prioritized_gaps if g.skill_id == SKILL)
        self.assertGreater(gap.adjusted_priority, gap.baseline_priority)
        self.assertEqual(result.plan.fit_score, match.fit_score)

    def test_tampered_plan_fails_before_writing_store(self):
        _, plan = self.prepare(self.admit(0), 0)
        original_hash = hashlib.sha256(plan.read_bytes()).hexdigest()
        payload = json.loads(plan.read_text())
        payload["direction"] = "decrease"
        plan.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "changed"):
            approve_assessment(
                plan,
                reviewer="Fictional test reviewer",
                expected_sha256=original_hash,
                approve=True,
                store_path=self.store,
            )
        self.assertEqual(json.loads(self.store.read_text())["assessments"], [])


if __name__ == "__main__":
    unittest.main()
