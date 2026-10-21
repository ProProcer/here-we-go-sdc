import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.backend import CareerBackend
from src.ingestion.selection import real_catalog
from src.intelligence.evidence import load_evidence, validate_catalog_references
from src.intelligence.feeds import ReviewedSource, refresh_evidence
from src.intelligence.impacts import get_evidence_chain_response
from src.intelligence.outlook import get_outlook
from src.profiles.intake import create_profile
from src.profiles.matching import match_roles
from src.profiles.onet_matching import OnetMatcher
from src.reskilling.course_catalog import (
    CourseCatalog,
    CourseCatalogStore,
    trusted_providers_for_family,
)
from src.reskilling.planner import build_learning_plan
from src.schemas.onet import CoveragePolicy
from src.schemas.onet_profile import OnetRoleMatch
from src.schemas.roadmap import VerifiedCourse
from src.schemas.trends import EvidenceLedger

ROOT = Path(__file__).resolve().parents[1]
BI = "role:onet_15_2051_01"
NURSE = "role:onet_29_1141_00"
CRITICAL = "skill:onet_2_a_2_a"


def training(course_id, skill_ids, *, amount=0, currency=None):
    return VerifiedCourse(
        course_id=course_id,
        title="TEST ONLY training resource",
        provider="Test provider",
        course_url="https://example.edu/" + course_id.split(":")[1],
        evidence_url="https://example.edu/evidence",
        source_tier="trusted",
        skill_ids=skill_ids,
        coverage_strength={s: 1 for s in skill_ids},
        cost={
            "access": "paid" if amount else "free",
            "amount": amount,
            "currency": currency,
            "includes_certificate": False,
        },
        duration={"hours": 2, "display_text": "2 hours", "basis": "provider_stated"},
        delivery_mode="online",
        language="English",
        last_verified_at=datetime(2026, 10, 21, tzinfo=UTC),
        validation_notes=["Synthetic test fixture, not a verified real course."],
    )


class TestOnetMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()
        cls.matcher = OnetMatcher(cls.catalog)

    def profile(self, entries=None):
        return create_profile(
            "synthetic:migration_test",
            entries or ["Python", "SQL"],
            catalog=self.catalog,
        )

    def plan(self, profile, match, **kwargs):
        return build_learning_plan(
            profile,
            match,
            "baseline",
            country="Malaysia",
            preferred_language="English",
            catalog=self.catalog,
            **kwargs,
        )

    def test_matching_dispatch_and_target_pinning_preserve_scores(self):
        p = self.profile()
        all_rows = self.matcher.match(p)
        original = {r.role_id: r for r in all_rows}
        p.desired_role_id = BI
        rows = match_roles(p, self.catalog, top_n=2)
        self.assertTrue(all(isinstance(r, OnetRoleMatch) for r in rows))
        target = next(r for r in rows if r.role_id == BI)
        self.assertEqual(target.fit_score, original[BI].fit_score)
        self.assertEqual(target.rank, original[BI].rank)
        self.assertTrue(target.pinned)
        self.assertFalse(target.catalog_synthetic)

    def test_software_is_separate_and_unverified_claims_do_not_score(self):
        p = self.profile()
        match = self.matcher.match_role(p, BI)
        general = {
            s.skill_id for s in self.catalog.taxonomy.skills if s.kind == "general"
        }
        self.assertLessEqual({s.skill_id for s in match.missing_skills}, general)
        self.assertTrue(match.software_learning_options)
        for skill in p.skills:
            skill.confirmation = "unverified"
        self.assertEqual(self.matcher.match_role(p, BI).fit_score, 0)
        self.assertEqual(match.score_breakdown.transferability, 0)

    def test_missing_software_and_preferences_have_explicit_components(self):
        p = self.profile(["Critical Thinking"])
        row = self.matcher.match_role(p, NURSE)
        self.assertIsNone(row.score_breakdown.coverage.software_coverage)
        self.assertEqual(row.score_breakdown.coverage.effective_general_share, 1)
        p.interests = ["Business Intelligence Analysts"]
        row = self.matcher.match_role(p, BI)
        self.assertEqual(row.score_breakdown.preferences, 1)
        self.assertEqual(row.score_breakdown.preference_weight, 0.1)

    def test_real_outlook_has_no_mock_evidence_and_scoped_scenarios(self):
        baseline = get_outlook(BI, catalog=self.catalog)
        rapid = get_outlook(BI, "rapid_ai_change", catalog=self.catalog)
        self.assertEqual(baseline.schema_version, "0.2.0")
        self.assertFalse(baseline.catalog_synthetic)
        self.assertEqual(baseline.signals, [])
        self.assertTrue(
            all(t.evidence_status == "insufficient_evidence" for t in baseline.tasks)
        )
        a = {
            p.skill_id: p.adjusted_priority for p in baseline.scenario.skill_priorities
        }
        b = {p.skill_id: p.adjusted_priority for p in rapid.scenario.skill_priorities}
        self.assertGreater(b[CRITICAL], a[CRITICAL])
        self.assertTrue(rapid.scenario.synthetic)
        with self.assertRaises(ValueError):
            get_outlook(NURSE, "rapid_ai_change", catalog=self.catalog)
        self.assertEqual(
            get_evidence_chain_response(BI, catalog=self.catalog)["status"],
            "insufficient_evidence",
        )

    def test_injected_real_evidence_propagates_and_cross_catalog_links_fail(self):
        old = load_evidence().model_dump(mode="json")
        payload = {
            "schema_version": "0.2.0",
            "sources": old["sources"],
            "signals": old["signals"],
            "task_interpretations": [
                {
                    "role_id": BI,
                    "task_id": "task:onet_16150",
                    "signal_ids": [old["signals"][0]["signal_id"]],
                    "interpretation": "TEST ONLY contextual mapping",
                    "mapping_basis": "team_interpretation",
                    "evidence_scope": "contextual_not_task_measurement",
                }
            ],
            "evidence_chains": [],
        }
        ledger = EvidenceLedger.model_validate(payload)
        validate_catalog_references(ledger, self.catalog)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(json.dumps(payload))
            outlook = get_outlook(BI, catalog=self.catalog, evidence_path=path)
            self.assertEqual(len(outlook.signals), 1)
        payload["task_interpretations"][0]["task_id"] = "task:routine_reporting"
        with self.assertRaises(ValueError):
            validate_catalog_references(
                EvidenceLedger.model_validate(payload), self.catalog
            )

    def test_review_refresh_accepts_real_task_ids_and_isolates_ledger(self):
        data = json.loads(
            (ROOT / "data/sources/anthropic_january_2026.json").read_text()
        )
        data["evidence_chains"] = []
        data["task_interpretations"] = [
            {
                "role_id": BI,
                "task_id": "task:onet_16150",
                "signal_ids": [data["signal"]["signal_id"]],
                "interpretation": "TEST ONLY contextual mapping",
                "mapping_basis": "team_interpretation",
                "evidence_scope": "contextual_not_task_measurement",
            }
        ]
        review = ReviewedSource.model_validate(data)
        page = (
            "<html><body><h1>"
            + review.title_marker
            + "</h1>"
            + review.publication_marker
            + " "
            + " ".join(review.required_markers)
            + "</body></html>"
        ).encode()
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "review.json"
            path.write_text(json.dumps(data))
            result = refresh_evidence(
                review_path=path,
                ledger_path=folder / "ledger.json",
                snapshots_path=folder / "snapshots",
                catalog=self.catalog,
                fetcher=lambda url: page,
                now=datetime(2026, 10, 21, tzinfo=UTC),
            )
            self.assertEqual(result.status, "updated", result.message)
            self.assertEqual(
                load_evidence(folder / "ledger.json", catalog=self.catalog)
                .task_interpretations[0]
                .role_id,
                BI,
            )

    def test_plan_uses_real_gap_ids_and_only_selected_software(self):
        p = self.profile()
        match = self.matcher.match_role(p, BI)
        base = self.plan(p, match).plan
        self.assertEqual(base.schema_version, "0.2.0")
        self.assertEqual(base.fit_score, match.fit_score)
        self.assertEqual(
            {g.skill_id for g in base.prioritized_gaps},
            {g.skill_id for g in match.missing_skills},
        )
        chosen = match.software_learning_options[0].skill_id
        result = self.plan(p, match, selected_software_skill_ids=[chosen]).plan
        self.assertIn(chosen, {g.skill_id for g in result.prioritized_gaps})
        self.assertEqual(result.selected_software_skill_ids, [chosen])
        self.assertEqual(result.sdg_connections[0].target_id, "4.4")
        self.assertTrue(
            all(
                s.resource_status == "verified_resource_not_found"
                for m in result.milestones
                for s in m.steps
            )
        )
        with self.assertRaises(ValueError):
            self.plan(p, match, selected_software_skill_ids=["skill:python"])

    def test_plan_rejects_tampered_or_stale_matching_result(self):
        p = self.profile()
        match = self.matcher.match_role(p, BI)
        changed = match.model_copy(deep=True)
        changed.fit_score += 1
        with self.assertRaisesRegex(ValueError, "stale or altered"):
            self.plan(p, changed)
        p.skills[0].confirmation = "unverified"
        with self.assertRaisesRegex(ValueError, "stale or altered"):
            self.plan(p, match)

    def test_verified_cache_budget_and_currency_are_enforced(self):
        p = self.profile()
        p.constraints.budget_myr = 10
        # Two independent real general gaps; courses below are synthetic fixtures.
        targets = [CRITICAL, "skill:onet_2_a_1_a"]
        with TemporaryDirectory() as tmp:
            store = CourseCatalogStore(Path(tmp) / "courses.json")
            store.save(
                [
                    training("course:test_a", [targets[0]], amount=8, currency="MYR"),
                    training("course:test_b", [targets[1]], amount=8, currency="MYR"),
                    training("course:test_usd", targets, amount=1, currency="USD"),
                ]
            )
            result = self.plan(
                p, self.matcher.match_role(p, BI), course_store=store
            ).plan
            self.assertLessEqual(
                sum(c.cost.amount for c in result.selected_courses), 10
            )
            self.assertTrue(
                all(c.cost.currency == "MYR" for c in result.selected_courses)
            )
            self.assertEqual(len(result.selected_courses), 1)
            p.constraints.budget_myr = None
            result = self.plan(
                p, self.matcher.match_role(p, BI), course_store=store
            ).plan
            self.assertEqual(result.selected_courses, [])

    def test_family_provider_selection_and_real_plan_serialization(self):
        config = CourseCatalog.model_validate_json(
            (ROOT / "data/processed/onet/31.0/courses.json").read_text()
        )
        providers = trusted_providers_for_family(config, "family:soc_15")
        self.assertIn("provider:microsoft_learn", {p.provider_id for p in providers})
        p = self.profile()
        result = self.plan(p, self.matcher.match_role(p, BI))
        self.assertEqual(
            result.model_dump(mode="json")["plan"]["family_id"], "family:soc_15"
        )
        self.assertTrue(
            result.model_dump(mode="json")["plan"]["software_learning_options"]
        )

    def test_backend_preserves_custom_matching_policy_in_plan(self):
        backend = CareerBackend(self.catalog)
        p = self.profile()
        policy = CoveragePolicy(general_share=0.75, group_share=0.25)
        expected = backend.matcher.match_role(p, BI, policy=policy)
        result = backend.learning_plan(p, BI, policy=policy)
        self.assertEqual(result.plan.fit_score, expected.fit_score)
        self.assertNotEqual(
            expected.fit_score, backend.matcher.match_role(p, BI).fit_score
        )


if __name__ == "__main__":
    unittest.main()
