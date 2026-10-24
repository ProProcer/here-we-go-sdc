import copy
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.ingestion.coverage import CoverageIndex
from src.ingestion.onet import (
    CATALOG_FILE,
    DEFAULT_RAW,
    build_onet_catalog,
    load_onet_catalog,
    software_identity,
)
from src.ingestion.onet_api import get_onet_role, list_onet_roles
from src.profiles.intake import create_profile
from src.profiles.skill_normalizer import skill_index
from src.schemas.onet import CoveragePolicy, OnetCatalog


class TestOnetCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.audit = build_onet_catalog()
        cls.index = CoverageIndex(cls.catalog)
        cls.bi = "role:onet_15_2051_01"
        cls.nurse = "role:onet_29_1141_00"
        # Small, fully valid subcatalog for destructive validation cases.
        payload = cls.catalog.model_dump(mode="json")
        payload["roles"] = [r for r in payload["roles"] if r["role_id"] == cls.bi]
        payload["role_skills"] = [
            r for r in payload["role_skills"] if r["role_id"] == cls.bi
        ]
        payload["software_associations"] = [
            r for r in payload["software_associations"] if r["role_id"] == cls.bi
        ]
        task_ids = set(payload["roles"][0]["task_ids"])
        payload["taxonomy"]["tasks"] = [
            r for r in payload["taxonomy"]["tasks"] if r["task_id"] in task_ids
        ]
        skill_ids = {
            r["skill_id"]
            for r in payload["role_skills"] + payload["software_associations"]
        }
        payload["taxonomy"]["skills"] = [
            s for s in payload["taxonomy"]["skills"] if s["skill_id"] in skill_ids
        ]
        group_ids = {r["group_id"] for r in payload["software_associations"]}
        payload["taxonomy"]["software_groups"] = [
            {**g, "skill_ids": [s for s in g["skill_ids"] if s in skill_ids]}
            for g in payload["taxonomy"]["software_groups"]
            if g["group_id"] in group_ids
        ]
        payload["excluded_occupations"] = []
        cls.small = OnetCatalog.model_validate(payload).model_dump(mode="json")

    def test_real_coverage_and_exclusion_denominators(self):
        self.assertEqual(len(self.catalog.roles), 910)
        self.assertEqual(len(self.catalog.excluded_occupations), 106)
        self.assertEqual(len(self.catalog.role_skills), 28335)
        self.assertEqual(self.audit["filters"]["irrelevant_pairs_excluded"], 3515)
        self.assertEqual(self.audit["in_demand_per_role"]["zero_occupations"], 423)
        self.assertFalse(self.catalog.synthetic)

    def test_source_weights_relevance_and_level_suppression(self):
        for r in self.catalog.role_skills:
            self.assertAlmostEqual(r.importance, r.source_importance / 5)
            if r.level_suppressed:
                self.assertIsNone(r.source_level)
        self.assertEqual(sum(r.level_suppressed for r in self.catalog.role_skills), 146)
        self.assertNotIn(
            "skill:onet_2_b_3_j", {r.skill_id for r in self.index.general[self.bi]}
        )

    def test_no_fabricated_task_skill_relationships(self):
        self.assertTrue(
            all(
                t.skill_ids == [] and t.mapping_status == "unmapped"
                for t in self.catalog.taxonomy.tasks
            )
        )

    def test_rebuild_matches_committed_snapshot(self):
        rebuilt = (
            json.dumps(
                self.catalog.model_dump(mode="json"), indent=2, ensure_ascii=False
            )
            + "\n"
        )
        self.assertEqual(
            hashlib.sha256(rebuilt.encode()).digest(),
            # Git may check out JSON with CRLF on Windows. Compare canonical
            # text while retaining the complete content/formatting check.
            hashlib.sha256(CATALOG_FILE.read_text(encoding="utf-8").encode()).digest(),
        )
        self.assertEqual(load_onet_catalog().roles[0], self.catalog.roles[0])

    def test_pinned_raw_checksums_detect_tampering(self):
        with TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            shutil.copytree(DEFAULT_RAW, raw)
            with (raw / "occupation_data.csv").open("ab") as handle:
                handle.write(b"\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                build_onet_catalog(raw)

    def test_aliases_and_ids_are_stable_and_unambiguous(self):
        first = software_identity("Some Vendor Tool")
        second = software_identity(" some   vendor TOOL ")
        self.assertEqual(first[0], second[0])
        self.assertEqual(software_identity("Python")[0], "skill:python")
        index = skill_index(self.catalog.taxonomy)
        self.assertEqual(index["power bi"].skill_id, "skill:microsoft_power_bi")
        self.assertEqual(index["sql"].skill_id, "skill:sql")

    def test_rejects_corrupt_handoffs(self):
        mutations = []
        value = copy.deepcopy(self.small)
        value["role_skills"][0]["importance"] = 0.01
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["role_skills"][0]["skill_id"] = "skill:unknown"
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["roles"][0]["task_ids"] = ["task:unknown"]
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["taxonomy"]["tasks"][0]["skill_ids"] = ["skill:python"]
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["role_skills"].append(value["role_skills"][0])
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["software_associations"][0]["group_id"] = "group:unknown"
        mutations.append(value)
        value = copy.deepcopy(self.small)
        value["excluded_occupations"] = [
            {"occupation_code": "15-2051.01", "title": "BI", "reasons": ["test"]}
        ]
        mutations.append(value)
        for i, value in enumerate(mutations):
            with self.subTest(case=i), self.assertRaises(ValidationError):
                OnetCatalog.model_validate(value)

    def test_missing_software_is_not_zero_coverage(self):
        general = [r.skill_id for r in self.index.general[self.nurse]][:10]
        a = self.index.score(self.nurse, general, CoveragePolicy(general_share=0.25))
        b = self.index.score(self.nurse, general, CoveragePolicy(general_share=0.75))
        self.assertEqual(a.score, b.score)
        self.assertIsNone(a.software_coverage)
        self.assertEqual(a.effective_general_share, 1)
        self.assertAlmostEqual(a.score, 100 * a.general_coverage, places=5)

    def test_present_software_without_profile_evidence_is_zero(self):
        result = self.index.score(self.bi, [])
        self.assertEqual(result.software_coverage, 0)
        self.assertEqual(result.effective_general_share, 0.5)

    def test_group_credit_does_not_award_exact_tool_or_double_count(self):
        rid = "role:onet_15_1252_00"
        java = self.index.score(rid, ["skill:java"])
        python = self.index.score(rid, ["skill:python"])
        both = self.index.score(rid, ["skill:python", "skill:java"])
        self.assertNotIn("skill:python", java.matched_software_skill_ids)
        self.assertGreater(java.software_group_coverage, 0)
        self.assertEqual(java.software_group_coverage, both.software_group_coverage)
        self.assertGreater(both.software_exact_coverage, python.software_exact_coverage)
        duplicate = self.index.score(rid, ["skill:python", "skill:python"])
        self.assertEqual(duplicate.score, python.score)

    def test_reviewed_profile_integration_and_unknown_proficiency(self):
        profile = create_profile(
            "synthetic:onet_test", ["Python", "SQL", "python3"], catalog=self.catalog
        )
        self.assertEqual(len(profile.skills), 2)
        self.assertTrue(all(s.level == "unknown" for s in profile.skills))
        result = self.index.score_profile(self.bi, profile)
        self.assertGreater(result.score, 0)
        for skill in profile.skills:
            skill.confirmation = "unverified"
        self.assertEqual(self.index.score_profile(self.bi, profile).score, 0)
        profile.skills[0].label = "Wrong canonical label"
        with self.assertRaisesRegex(ValueError, "canonical label"):
            self.index.score_profile(self.bi, profile)

    def test_score_bounds_unknowns_and_invalid_policies(self):
        self.assertEqual(self.index.score(self.bi, []).score, 0)
        self.assertEqual(self.index.score(self.bi, self.index.skill_ids).score, 100)
        with self.assertRaises(ValueError):
            self.index.score(self.bi, ["skill:invented"])
        with self.assertRaises(KeyError):
            self.index.score("role:unknown", [])
        for value in [0, 1, float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CoveragePolicy(group_share=value)

    def test_paged_role_and_detail_adapters(self):
        page = list_onet_roles(self.catalog, query="Business Intelligence", limit=1)
        self.assertGreater(page["total"], 0)
        self.assertEqual(len(page["roles"]), 1)
        details = get_onet_role(self.catalog, self.bi)
        self.assertEqual(details["role"]["occupation_code"], "15-2051.01")
        self.assertEqual(len(details["general_requirements"]), 30)
        for group in details["software_groups"]:
            self.assertLessEqual(
                set(group["skill_ids"]),
                {r["skill_id"] for r in details["software_associations"]},
            )
        with self.assertRaises(ValueError):
            list_onet_roles(self.catalog, limit=1000)
        with self.assertRaises(KeyError):
            get_onet_role(self.catalog, "role:unknown")

    def test_search_prioritizes_visible_titles_before_aliases(self):
        page = list_onet_roles(self.catalog, query="data", limit=100)
        titles = [row["role_title"].casefold() for row in page["roles"]]
        self.assertIn("data scientists", titles[:5])
        alias_match = next(i for i, title in enumerate(titles) if "data" not in title)
        self.assertTrue(all("data" not in title for title in titles[alias_match:]))
        self.assertTrue(all(title.startswith("data") for title in titles[:5]))

    def test_search_ranks_exact_and_partial_titles_and_normalizes_query(self):
        for query in ("data sc", " DATA   SC ", "Data Scientists"):
            with self.subTest(query=query):
                page = list_onet_roles(self.catalog, query=query, limit=1)
                self.assertEqual(page["roles"][0]["role_title"], "Data Scientists")

    def test_search_paginates_after_ranking_and_keeps_alias_matches(self):
        full = list_onet_roles(self.catalog, query="data", limit=100)
        page = list_onet_roles(self.catalog, query="data", offset=2, limit=3)
        self.assertEqual(page["roles"], full["roles"][2:5])
        self.assertEqual(page["total"], full["total"])
        for row in full["roles"]:
            role = next(role for role in self.catalog.roles if role.role_id == row["role_id"])
            self.assertIn("data", " ".join([role.role_title, *role.aliases]).casefold())


if __name__ == "__main__":
    unittest.main()
