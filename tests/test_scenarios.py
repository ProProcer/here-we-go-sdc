import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.ingestion.catalog import get_roles, load_role_catalog
from src.intelligence.evidence import load_evidence
from src.intelligence.outlook import get_outlook, get_outlook_response
from src.intelligence.scenarios import apply_scenario, load_scenarios
from src.schemas.scenario import Scenario
from src.schemas.trends import EvidenceLedger


class TestDataAnalystOutlook(unittest.TestCase):
    def test_expected_priorities_reversibility_and_no_catalog_mutation(self):
        original = get_roles()
        baseline = get_outlook("role:data_analyst")
        moderate = get_outlook("role:data_analyst", "moderate_ai_change")
        rapid = get_outlook("role:data_analyst", "rapid_ai_change")
        priorities = lambda result: {
            row.skill_id: row.adjusted_priority
            for row in result.scenario.skill_priorities
        }
        self.assertEqual(priorities(baseline)["skill:statistics"], 0.8)
        self.assertEqual(priorities(moderate)["skill:statistics"], 0.9)
        self.assertEqual(priorities(rapid)["skill:statistics"], 1.0)
        self.assertEqual(priorities(rapid)["skill:communication"], 0.8)
        self.assertEqual(priorities(rapid)["skill:sql"], 0.9)
        self.assertEqual(get_outlook("role:data_analyst"), baseline)
        self.assertEqual(get_outlook("role:data_analyst", "rapid_ai_change"), rapid)
        self.assertEqual(original, get_roles())
        self.assertTrue(baseline.catalog_synthetic)
        self.assertFalse(baseline.scenario.synthetic)
        self.assertTrue(rapid.scenario.synthetic)
        self.assertEqual(baseline.signals, rapid.signals)
        self.assertEqual(baseline.sources, rapid.sources)

    def test_missing_evidence_is_explicit_and_has_no_unrelated_citations(self):
        result = get_outlook("role:it_support_specialist")
        self.assertEqual(result.baseline_label, "Insufficient evidence")
        self.assertEqual(result.sources, [])
        self.assertEqual(result.signals, [])
        self.assertTrue(
            all(row.evidence_status == "insufficient_evidence" for row in result.tasks)
        )

    def test_rejects_missing_citations_and_synthetic_real_contamination(self):
        original = load_evidence().model_dump(mode="json")
        cases = []
        changed = copy.deepcopy(original)
        changed["sources"] = []
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["sources"][0]["source_url"] = "not a URL"
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["task_interpretations"][0]["signal_ids"] = ["signal:missing"]
        cases.append(changed)
        for field in ("sources", "signals"):
            changed = copy.deepcopy(original)
            changed[field][0]["synthetic"] = True
            cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                EvidenceLedger.model_validate(changed)
        scenario = load_scenarios()[0].model_dump(mode="json")
        scenario["synthetic"] = False
        with self.assertRaises(ValidationError):
            Scenario.model_validate(scenario)

    def test_cached_evidence_change_is_reflected_without_network(self):
        # A test-only mutation proves input propagation, not a real publication update.
        payload = load_evidence().model_dump(mode="json")
        payload["signals"][0]["claim"] = "TEST ONLY: changed reviewed input"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = get_outlook("role:data_analyst", evidence_path=path)
        self.assertEqual(result.signals[0].claim, "TEST ONLY: changed reviewed input")
        self.assertNotEqual(result.signals, get_outlook("role:data_analyst").signals)

    def test_invalid_ids_and_out_of_scope_adjustments(self):
        with self.assertRaises(KeyError):
            get_outlook("role:unknown")
        with self.assertRaises(ValueError):
            get_outlook("role:data_analyst", "unknown")
        with self.assertRaises(ValueError):
            get_outlook("role:business_analyst", "rapid_ai_change")
        scenario = load_scenarios()[0].model_dump(mode="json")
        scenario["skill_priority_adjustments"] = {"skill:spreadsheets": 0.1}
        with self.assertRaises(ValueError):
            apply_scenario(
                load_role_catalog(),
                "role:data_analyst",
                "moderate_ai_change",
                [Scenario.model_validate(scenario)],
            )
        scenario["skill_priority_adjustments"] = {"skill:statistics": float("nan")}
        with self.assertRaises(ValidationError):
            Scenario.model_validate(scenario)

    def test_clamping_and_applied_delta(self):
        scenario = load_scenarios()[0].model_dump(mode="json")
        scenario["skill_priority_adjustments"] = {
            "skill:statistics": 0.5,
            "skill:communication": -1,
        }
        result = apply_scenario(
            load_role_catalog(),
            "role:data_analyst",
            "moderate_ai_change",
            [Scenario.model_validate(scenario)],
        )
        priorities = {row.skill_id: row for row in result.skill_priorities}
        self.assertEqual(priorities["skill:statistics"].adjusted_priority, 1)
        self.assertEqual(priorities["skill:statistics"].applied_adjustment, 0.2)
        self.assertEqual(priorities["skill:communication"].adjusted_priority, 0)

    def test_committed_handoff_matches_adapter(self):
        path = (
            Path(__file__).resolve().parents[1] / "data/demo/data_analyst_outlooks.json"
        )
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        for scenario_id, response in snapshot.items():
            self.assertEqual(
                response, get_outlook_response("role:data_analyst", scenario_id)
            )
        self.assertEqual(
            set(snapshot), {"baseline", "moderate_ai_change", "rapid_ai_change"}
        )


if __name__ == "__main__":
    unittest.main()
