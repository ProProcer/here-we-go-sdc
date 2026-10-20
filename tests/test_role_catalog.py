import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.ingestion.catalog import DEFAULT_DIRECTORY, get_roles, load_role_catalog
from src.schemas.role import RoleCatalog


class TestRoleCatalog(unittest.TestCase):
    def test_mock_has_shared_skills_and_distinct_requirements(self):
        catalog = load_role_catalog()
        requirements = {
            role.role_id: {
                row.skill_id for row in catalog.role_skills if row.role_id == role.role_id
            }
            for role in catalog.roles
        }
        profile = {"skill:sql", "skill:python"}
        analyst = requirements["role:data_analyst"]
        self.assertEqual(profile & analyst, profile)
        self.assertEqual(analyst - profile, {
            "skill:statistics", "skill:data_visualization", "skill:communication"
        })
        self.assertEqual(profile & requirements["role:it_support_specialist"], set())

    def test_response_matches_committed_snapshot(self):
        snapshot = DEFAULT_DIRECTORY.parents[1] / "demo/roles_response.json"
        self.assertEqual(get_roles(), json.loads(snapshot.read_text()))
        self.assertEqual(get_roles(), get_roles())

    def test_rejects_broken_handoffs(self):
        payload = get_roles()
        cases = []
        for field, value in (
            ("skill_id", "skill:unknown"),
            ("role_id", "role:unknown"),
            ("importance", 1.5),
            ("evidence_ids", ["source:unknown"]),
            ("synthetic", False),
        ):
            changed = copy.deepcopy(payload)
            changed["role_skills"][0][field] = value
            cases.append(changed)
        for field in ("roles", "role_skills"):
            changed = copy.deepcopy(payload)
            changed[field].append(copy.deepcopy(changed[field][0]))
            cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["roles"][0]["task_ids"] = ["task:unknown"]
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["role_skills"] = [
            row for row in changed["role_skills"]
            if row["role_id"] != "role:data_analyst"
        ]
        cases.append(changed)
        for index, changed in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValidationError):
                RoleCatalog.model_validate(changed)

    def test_loader_accepts_explicit_directory(self):
        with TemporaryDirectory() as directory:
            for path in DEFAULT_DIRECTORY.glob("*.json"):
                (Path(directory) / path.name).write_text(path.read_text())
            self.assertEqual(load_role_catalog(directory), load_role_catalog())


if __name__ == "__main__":
    unittest.main()
