"""Role and individual-skill coverage, honest scope and confirmed-skill retention."""

import unittest

from src.ingestion.selection import real_catalog
from src.reskilling.sdg_mapper import build_sdg_summary, load_sdg_rules, map_role_sdg_connections, ROOT, SDGRuleSet
from src.schemas.profile import ProfileSkill

ROLE = "role:onet_13_1161_01"


class TestSDGCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = real_catalog()
        cls.skills = {s.skill_id: s for s in cls.catalog.taxonomy.skills}

    def test_every_catalog_role_has_a_conditional_connection(self):
        scopes = set()
        for role in self.catalog.roles:
            connections = map_role_sdg_connections(role.role_id, catalog=self.catalog)
            self.assertTrue(connections, role.role_id)
            for connection in connections:
                self.assertEqual(connection.evidence_kind, "inferred")
                self.assertIn("sdgs.un.org/goals/", str(connection.evidence_url))
                self.assertTrue(connection.rationale)
                scopes.add(connection.scope)
        self.assertIn("career_preparation", scopes)
        self.assertIn("role_application", scopes)

    def test_every_catalog_skill_has_a_learning_tag(self):
        rules = load_sdg_rules(ROOT / "data/processed/onet/31.0/sdg_mappings.json")
        covered = {sid for rule in rules.rules if not rule.role_ids and rule.target_id == "4.4" for sid in rule.skill_ids}
        self.assertEqual(set(self.skills) - covered, set())

    def test_search_marketing_has_an_explained_work_application(self):
        links = map_role_sdg_connections(ROLE, catalog=self.catalog)
        self.assertEqual(links[0].target_id, "8.2")
        self.assertEqual(links[0].scope, "role_application")
        self.assertIn("could support", links[0].rationale)
        role = next(r for r in self.catalog.roles if r.role_id == ROLE)
        task_labels = {t.label for t in self.catalog.taxonomy.tasks if t.task_id in role.task_ids}
        self.assertTrue(any(label in links[0].rationale for label in task_labels))

    def test_confirmed_skills_keep_individual_tags_when_no_learning_gaps_remain(self):
        ids = {r.skill_id for r in self.catalog.role_skills if r.role_id == ROLE}
        profile = [ProfileSkill(skill_id=sid, label=self.skills[sid].label,
            evidence=["Synthetic confirmed example"], confirmation="confirmed") for sid in ids]
        result = build_sdg_summary(ROLE, ids, catalog=self.catalog, profile_skills=profile)
        self.assertEqual(result.mapped_skill_count, len(ids))
        self.assertTrue(result.role_connections)
        self.assertTrue(all(s.status == "confirmed" for s in result.skills))
        for skill in result.skills:
            self.assertTrue(skill.connections)
            self.assertTrue(all(c.skill_ids == [skill.skill_id] for c in skill.connections))
            self.assertIn(skill.label, skill.connections[0].application_example)
        self.assertEqual(len(profile), len(ids))

    def test_other_profile_skills_are_tagged_without_claiming_role_relevance(self):
        relevant = {r.skill_id for r in self.catalog.role_skills if r.role_id == ROLE}
        relevant.update(r.skill_id for r in self.catalog.software_associations if r.role_id == ROLE)
        sid = next(sid for sid in self.skills if sid not in relevant)
        result = build_sdg_summary(ROLE, [sid], catalog=self.catalog)
        self.assertFalse(result.skills[0].role_relevant)
        self.assertEqual(result.skills[0].connections[0].target_id, "4.4")
        self.assertIn("not evidence of impact", result.interpretation_note)

    def test_unknown_skills_and_explicitly_empty_rules_do_not_get_invented_links(self):
        with self.assertRaises(ValueError):
            build_sdg_summary(ROLE, ["skill:invented"], catalog=self.catalog)
        self.assertEqual(map_role_sdg_connections(ROLE, catalog=self.catalog, rules=SDGRuleSet()), [])
