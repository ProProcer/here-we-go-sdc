"""User-visible CV review, real-catalog integration, and session boundaries."""

import unittest
import re
from unittest.mock import patch
from io import BytesIO

from fastapi.testclient import TestClient

from src.main import app
from src.profiles.cv_parser import MAX_BYTES, CVParseError, parse_cv
from src.profiles.samples import SAMPLE_PATH, sample_cv_pdf

ROLE = "role:onet_15_2051_01"


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def upload(self, text=b"Skills: Python, SQL"):
        response = self.client.post("/api/v2/profiles/upload", content=text,
                                    headers={"X-Filename": "fictional.txt"})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        return data, {"X-Session-ID": data["session_id"]}

    def review(self, data, headers, **extra):
        payload = {"revision": data["revision"],
                   "skills": [{**skill, "confirmation": "confirmed"}
                              for skill in data["profile"]["skills"]], **extra}
        response = self.client.patch("/api/v2/profiles/current", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_shell_assets_and_downloadable_cv(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="root"', page.text)
        self.assertIn("script-src 'self'", page.headers["Content-Security-Policy"])
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page.text)
        self.assertTrue(any(path.endswith(".js") for path in assets))
        self.assertTrue(any(path.endswith(".css") for path in assets))
        for path in [*assets, "/fonts/InterVariable.woff2", "/health"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        pdf = self.client.get("/api/v2/samples/graduate.pdf")
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertEqual(SAMPLE_PATH.with_suffix(".pdf").read_bytes(), sample_cv_pdf())
        # A text extractor can tolerate malformed page streams that viewers reject.
        # Check the actual downloaded bytes with the independent PDFium renderer.
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(pdf.content) as document:
            page = document[0]
            text = page.get_textpage()
            self.assertIn("AISHA TAN", text.get_text_range())
            text.close()
            bitmap = page.render(scale=1)
            image = bitmap.to_pil().convert("L")
            self.assertLess(image.getextrema()[0], 100, "Downloaded CV rendered as a blank page")
            self.assertGreater(sum(image.histogram()[:200]), 1000)
            bitmap.close()
            page.close()
        parsed = parse_cv(pdf.content, "sample.pdf")
        self.assertIn("AISHA TAN", parsed.pages[0])
        sample = self.client.post("/api/v2/profiles/sample").json()
        uploaded = self.client.post("/api/v2/profiles/upload", content=pdf.content,
                                   headers={"X-Filename": "downloaded.pdf"}).json()
        self.assertEqual(sample["profile"]["skills"], uploaded["profile"]["skills"])
        self.assertTrue(all(row["confirmation"] == "unverified"
                            for row in uploaded["profile"]["skills"]))

    def test_review_required_and_input_changes_computed_matches(self):
        data, headers = self.upload()
        self.assertEqual(self.client.get("/api/v2/matches?revision=0", headers=headers).status_code, 409)
        reviewed = self.review(data, headers)
        first = self.client.get("/api/v2/matches?revision=1", headers=headers).json()["matches"]
        self.assertTrue(first)
        self.assertEqual(first[0]["schema_version"], "0.2.0")
        reviewed = self.review(reviewed, headers, skills=[])
        empty = self.client.get("/api/v2/matches?revision=2", headers=headers).json()["matches"]
        self.assertTrue(all(row["fit_score"] == 0 for row in empty))
        self.assertNotEqual(first, empty)

    def test_actual_gaps_scenarios_and_fit_preservation(self):
        data, headers = self.upload()
        reviewed = self.review(data, headers, desired_role_id=ROLE,
                               constraints={"budget_myr": 0, "hours_per_week": 5})
        matches = self.client.get("/api/v2/matches?revision=1", headers=headers).json()["matches"]
        selected = next(row for row in matches if row["role_id"] == ROLE)
        request = {"revision": reviewed["revision"], "role_id": ROLE}
        baseline = self.client.post("/api/v2/pathways", headers=headers, json=request)
        self.assertEqual(baseline.status_code, 200, baseline.text)
        plan = baseline.json()["plan"]
        rapid = self.client.post("/api/v2/pathways", headers=headers,
                                 json={**request, "scenario_id": "rapid_ai_change"}).json()["plan"]
        self.assertEqual(plan["fit_score"], selected["fit_score"])
        self.assertEqual(plan["fit_score"], rapid["fit_score"])
        self.assertNotEqual(plan["prioritized_gaps"], rapid["prioritized_gaps"])
        restored = self.client.post("/api/v2/pathways", headers=headers, json=request).json()["plan"]
        self.assertEqual(plan["prioritized_gaps"], restored["prioritized_gaps"])
        self.assertEqual(plan["selected_courses"], [])
        self.assertTrue(plan["sdg_connections"])
        self.assertTrue(all(step["resource_status"] == "verified_resource_not_found"
                            for milestone in plan["milestones"] for step in milestone["steps"]))

    def test_unsupported_scenarios_and_unknown_roles(self):
        roles = self.client.get("/api/v2/roles?limit=2").json()
        self.assertEqual(roles["total"], 910)
        role_id = roles["roles"][0]["role_id"]
        self.assertNotEqual(role_id, ROLE)
        baseline = self.client.get(f"/api/v2/roles/{role_id}/outlook").json()
        self.assertEqual(baseline["available_scenarios"], ["baseline"])
        self.assertEqual(baseline["baseline_label"], "Insufficient evidence")
        response = self.client.get(f"/api/v2/roles/{role_id}/outlook?scenario_id=rapid_ai_change")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/v2/roles/unknown").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v2/roles/{role_id}/evidence").json()["chains"], [])

    def test_new_evidence_routes_are_offline_and_expose_only_approved_results(self):
        with patch("src.intelligence.gemini.GeminiClient.generate", side_effect=AssertionError("Public requests must never call Gemini")):
            skills = self.client.get(f"/api/v2/roles/{ROLE}/skill-evidence")
            impacts = self.client.get(f"/api/v2/roles/{ROLE}/impacts")
        self.assertEqual(skills.status_code, 200)
        self.assertEqual(impacts.status_code, 200)
        self.assertEqual(skills.json()["approved_conditional_skill_evidence"], [])
        self.assertEqual(impacts.json()["approved_conditional_role_impacts"], [])
        self.assertFalse(skills.json()["changes_weights"])
        self.assertFalse(impacts.json()["changes_weights"])
        with patch.object(self.client.app.state.backend, "skill_evidence", return_value={
            **skills.json(), "approved_conditional_skill_evidence": [{"skill_id": "skill:sql", "rationale": "Fictional test interpretation"}],
        }):
            result = self.client.get(f"/api/v2/roles/{ROLE}/skill-evidence").json()
        self.assertEqual(result["approved_conditional_skill_evidence"][0]["skill_label"], "SQL")
        for suffix in ("skill-evidence", "impacts"):
            self.assertEqual(self.client.get(f"/api/v2/roles/unknown/{suffix}").status_code, 404)
        with patch.object(self.client.app.state.backend, "skill_evidence", side_effect=ValueError("private backend detail")):
            result = self.client.get(f"/api/v2/roles/{ROLE}/skill-evidence")
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("private backend detail", result.text)

    def test_shared_course_store_is_read_by_status_and_planner(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from src.reskilling.course_catalog import CourseCatalogStore

        backend = self.client.app.state.backend
        original = backend.course_store
        with TemporaryDirectory() as directory:
            store = CourseCatalogStore(Path(directory) / "courses.json")
            backend.course_store = store
            try:
                response = self.client.get("/api/v2/courses/status")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "empty")
                self.assertIsNone(response.json()["updated_at"])
                data, headers = self.upload()
                reviewed = self.review(data, headers, desired_role_id=ROLE)
                matches = self.client.get(f"/api/v2/matches?revision={reviewed['revision']}", headers=headers).json()["matches"]
                gap = next(row for row in matches if row["role_id"] == ROLE)["missing_skills"][0]
                from datetime import UTC, datetime
                from src.schemas.roadmap import VerifiedCourse
                store.upsert(VerifiedCourse(
                    course_id="course:fictional_integration", title="Fictional integration course",
                    provider="Fictional test provider", course_url="https://example.org/test-course",
                    evidence_url="https://example.org/test-course", source_tier="trusted",
                    skill_ids=[gap["skill_id"]], coverage_strength={gap["skill_id"]: 1},
                    cost={"access": "free", "amount": 0, "includes_certificate": False},
                    duration={"hours": 1, "display_text": "1 hour", "basis": "provider_stated"},
                    delivery_mode="online", language="English", last_verified_at=datetime.now(UTC)))
                self.assertEqual(self.client.get("/api/v2/courses/status").json()["verified_course_count"], 1)
                result = self.client.post("/api/v2/pathways", headers=headers, json={"revision": reviewed["revision"], "role_id": ROLE})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertIn("course:fictional_integration", [course["course_id"] for course in result.json()["plan"]["selected_courses"]])
                store.path.write_text("invalid JSON", encoding="utf-8")
                self.assertEqual(self.client.get("/api/v2/courses/status").status_code, 503)
            finally:
                backend.course_store = original

    def test_sessions_stale_revisions_and_forgetting(self):
        data, headers = self.upload()
        self.review(data, headers)
        self.assertEqual(self.client.get("/api/v2/matches?revision=0", headers=headers).status_code, 409)
        self.assertEqual(self.client.get("/api/v2/matches?revision=1", headers={"X-Session-ID": "wrong"}).status_code, 401)
        self.assertEqual(self.client.patch("/api/v2/profiles/current", headers=headers,
                         json={"revision": 0, "skills": []}).status_code, 409)
        self.assertEqual(self.client.delete("/api/v2/profiles/current", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v2/matches?revision=1", headers=headers).status_code, 401)

    def test_upload_bounds_and_private_validation_errors(self):
        oversized = self.client.post("/api/v2/profiles/upload", content=b"a" * (MAX_BYTES + 1))
        self.assertEqual(oversized.status_code, 413)
        malformed = self.client.post("/api/v2/profiles/upload", content=b"private cv text",
                                     headers={"X-Filename": "wrong.pdf"})
        self.assertEqual(malformed.status_code, 422)
        self.assertNotIn("private cv text", malformed.text)
        data, headers = self.upload()
        invalid = self.client.patch("/api/v2/profiles/current", headers=headers, json={
            "revision": 0, "skills": [{"evidence": ["DO_NOT_ECHO_THIS"]}]})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("DO_NOT_ECHO_THIS", invalid.text)
        self.assertEqual(invalid.headers["Cache-Control"], "no-store")
        expired = app.state.sessions.get(data["session_id"])
        expired.expires_at = 0
        self.assertEqual(self.client.get("/api/v2/matches?revision=0", headers=headers).status_code, 401)

    def test_review_rejects_invented_skills_and_unconfirmed_claims(self):
        data, headers = self.upload()
        unconfirmed = self.client.patch("/api/v2/profiles/current", headers=headers,
            json={"revision": 0, "skills": data["profile"]["skills"]})
        self.assertEqual(unconfirmed.status_code, 422)
        skill = {**data["profile"]["skills"][0], "label": "Invented", "confirmation": "confirmed"}
        self.assertEqual(self.client.patch("/api/v2/profiles/current", headers=headers,
            json={"revision": 0, "skills": [skill]}).status_code, 422)

    def test_optional_software_is_explicit_and_validated(self):
        data, headers = self.upload()
        self.review(data, headers, desired_role_id=ROLE)
        matches = self.client.get("/api/v2/matches?revision=1", headers=headers).json()["matches"]
        role = next(row for row in matches if row["role_id"] == ROLE)
        selected = role["software_learning_options"][0]["skill_id"]
        request = {"revision": 1, "role_id": ROLE, "selected_software_skill_ids": [selected]}
        response = self.client.post("/api/v2/pathways", headers=headers, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plan"]["selected_software_skill_ids"], [selected])
        self.assertEqual(response.json()["plan"]["fit_score"], role["fit_score"])
        invalid = self.client.post("/api/v2/pathways", headers=headers,
            json={**request, "selected_software_skill_ids": ["skill:invented"]})
        self.assertEqual(invalid.status_code, 422)


class TestDocumentFormats(unittest.TestCase):
    def test_docx_reads_tables_and_rejects_malformed_files(self):
        from docx import Document

        document = Document()
        document.add_paragraph("Fictional graduate")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Skills: Python"
        table.cell(0, 1).text = "SQL, Tableau"
        content = BytesIO()
        document.save(content)
        text = "\n".join(parse_cv(content.getvalue(), "cv.docx").pages)
        self.assertIn("Python", text)
        self.assertIn("SQL", text)
        with self.assertRaises(CVParseError):
            parse_cv(b"not a word document", "cv.docx")

    def test_image_and_scanned_pdf_run_real_local_ocr(self):
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (1200, 400), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=38)
        draw.text((45, 55), "FICTIONAL CV", fill="black", font=font)
        draw.text((45, 140), "Skills: Python, SQL, Tableau", fill="black", font=font)
        for kind, suffix in [("PNG", "png"), ("JPEG", "jpg"), ("PDF", "pdf")]:
            with self.subTest(format=kind):
                content = BytesIO()
                image.save(content, format=kind)
                parsed = parse_cv(content.getvalue(), "cv." + suffix)
                text = "\n".join(parsed.pages)
                self.assertIn("Python", text)
                self.assertIn("SQL", text)


if __name__ == "__main__":
    unittest.main()
