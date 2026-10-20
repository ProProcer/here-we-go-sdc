import subprocess
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.profiles.cv_parser import MAX_BYTES, MAX_TEXT, CVParseError, ParsedCV, parse_cv
from src.profiles.extraction import extract_profile
from src.profiles.intake import create_profile, create_profile_from_cv, review_profile
from src.profiles.matching import match_roles

ROOT = Path(__file__).resolve().parents[1]


def fictional_pdf(text="Skills: Python3, SQL", *, pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("fictional-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def reviewed(profile):
    return review_profile(
        profile,
        [{**s.model_dump(), "confirmation": "confirmed"} for s in profile.skills],
    )


class TestCVPipeline(unittest.TestCase):
    def assert_parse_error(self, code, content, filename):
        with self.assertRaises(CVParseError) as context:
            parse_cv(content, filename)
        self.assertEqual(context.exception.code, code)
        self.assertIn("typed-skills form", str(context.exception))

    def test_text_and_pdf_review_to_identical_ranking(self):
        text = create_profile_from_cv(
            "synthetic:example", b"Skills: Python3, SQL", "cv.txt"
        )
        pdf = create_profile_from_cv("synthetic:example", fictional_pdf(), "cv.pdf")
        self.assertEqual(
            [s.skill_id for s in text.skills], [s.skill_id for s in pdf.skills]
        )
        self.assertTrue(
            all(
                s.level == "unknown" and s.confirmation == "unverified"
                for s in pdf.skills
            )
        )
        self.assertTrue(all(r.fit_score == 0 for r in match_roles(pdf)))
        self.assertEqual(
            [(r.role_id, r.fit_score) for r in match_roles(reviewed(text))],
            [(r.role_id, r.fit_score) for r in match_roles(reviewed(pdf))],
        )
        self.assertEqual(match_roles(reviewed(pdf))[0].fit_score, 42.11)
        self.assertIn("Page 1, line", pdf.skills[0].evidence[0])

    def test_fictional_cv_fixture_expected_skills(self):
        expected = {
            "analytics": {"skill:python", "skill:sql"},
            "business": {
                "skill:spreadsheets",
                "skill:requirements_analysis",
                "skill:communication",
            },
            "support": {"skill:it_troubleshooting", "skill:communication"},
        }
        for filename, ids in expected.items():
            path = ROOT / f"data/synthetic/profiles/cvs/{filename}.txt"
            profile = create_profile_from_cv(
                "synthetic:fixture", path.read_bytes(), path.name
            )
            self.assertEqual({s.skill_id for s in profile.skills}, ids)

    def test_negation_aspiration_boundaries_and_personal_fields(self):
        parsed = ParsedCV(
            format="txt",
            pages=[
                (
                    "Name: Python SQL\nInterests: statistics\nNo Python experience.\n"
                    "I want SQL. Not familiar with Excel.\nUsed pythonic tools.\nSkills: communication"
                )
            ],
        )
        profile = extract_profile(parsed, "synthetic:example")
        self.assertEqual([s.skill_id for s in profile.skills], ["skill:communication"])

    def test_protected_attribute_changes_do_not_change_cv_scores(self):
        candidates = [
            b"Name: A\nAge: 21\nGender: female\nNationality: Malaysia\nSkills: Python, SQL",
            b"Name: B\nAge: 60\nGender: male\nNationality: Indonesia\nSkills: Python, SQL",
        ]
        results = [
            match_roles(
                reviewed(create_profile_from_cv("synthetic:example", c, "cv.txt"))
            )
            for c in candidates
        ]
        self.assertEqual(results[0], results[1])

    def test_similar_cv_case_layout_aliases(self):
        candidates = [
            b"Skills: Python, SQL",
            b"SKILLS: python3\nStructured query language",
        ]
        results = [
            match_roles(
                reviewed(create_profile_from_cv("synthetic:example", c, "cv.txt"))
            )
            for c in candidates
        ]
        self.assertEqual(
            [(r.role_id, r.fit_score) for r in results[0]],
            [(r.role_id, r.fit_score) for r in results[1]],
        )

    def test_text_input_limits_and_formats(self):
        for code, content, filename in [
            ("empty", b"", "cv.txt"),
            ("file_limit", b"a" * (MAX_BYTES + 1), "cv.txt"),
            ("text_limit", b"a" * (MAX_TEXT + 1), "cv.txt"),
            ("encoding", b"\xff", "cv.txt"),
            ("no_text", b" \n ", "cv.txt"),
            ("invalid_text", b"abc\x00", "cv.txt"),
            ("unsupported_format", b"skills", "cv.docx"),
            ("invalid_pdf", b"abc", "cv.pdf"),
        ]:
            with self.subTest(code=code):
                self.assert_parse_error(code, content, filename)
        self.assertEqual(parse_cv(b"\xef\xbb\xbfPython", "CV.TXT").pages, ["Python"])

    def test_pdf_encrypted_blank_malformed_page_and_text_limits(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        blank = BytesIO()
        writer.write(blank)
        for code, content in [
            ("encrypted", fictional_pdf(encrypted=True)),
            ("no_text", blank.getvalue()),
            ("invalid_pdf", b"%PDF-1.7\nbroken"),
            ("page_limit", fictional_pdf(pages=6)),
            ("text_limit", fictional_pdf("A" * (MAX_TEXT + 1))),
        ]:
            with self.subTest(code=code):
                self.assert_parse_error(code, content, "cv.pdf")

    def test_timeout_and_worker_failure_have_fallback(self):
        with patch(
            "src.profiles.cv_parser.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 10),
        ):
            self.assert_parse_error("timeout", b"%PDF-1.7", "cv.pdf")
        with patch(
            "src.profiles.cv_parser.subprocess.run", side_effect=OSError("unavailable")
        ):
            self.assert_parse_error("worker_unavailable", b"%PDF-1.7", "cv.pdf")

    def test_transfer_is_partial_explained_and_keeps_gap(self):
        profile = create_profile("synthetic:example", ["Excel"])
        analyst = next(
            r for r in match_roles(profile) if r.role_id == "role:data_analyst"
        )
        self.assertEqual(analyst.score_breakdown.required_skill_coverage, 0)
        self.assertEqual(analyst.fit_score, 5.26)  # 0.8 * 0.25 / 3.8
        self.assertEqual(
            analyst.transferable_skills[0].target_skill_id, "skill:data_visualization"
        )
        self.assertIn(
            "skill:data_visualization", {s.skill_id for s in analyst.missing_skills}
        )
        self.assertEqual(analyst.transferable_skills[0].weighted_contribution, 0.2)
        profile = create_profile("synthetic:example", ["Python"])
        analyst = next(
            r for r in match_roles(profile) if r.role_id == "role:data_analyst"
        )
        self.assertEqual(
            analyst.transferable_skills, []
        )  # Already required; no second credit toward SQL.

    def test_preferences_missing_unknown_multiple_and_no_target_bonus(self):
        base = create_profile("synthetic:example", ["Python", "SQL"])
        payload = base.model_dump()
        payload["interests"] = ["analytics"]
        interested = type(base).model_validate(payload)
        self.assertEqual(
            match_roles(interested)[0].fit_score, 47.89
        )  # .9 * (1.6 / 3.8) + .1
        payload["interests"] = ["analytics", "business"]
        self.assertEqual(
            match_roles(type(base).model_validate(payload))[
                0
            ].score_breakdown.preferences,
            0.5,
        )
        payload["interests"] = ["female", "Malaysia", "unrecognized"]
        self.assertEqual(
            match_roles(type(base).model_validate(payload)), match_roles(base)
        )

    def test_top_n_pins_original_rank_score_without_promoting(self):
        base = create_profile(
            "synthetic:example",
            ["Python", "SQL"],
            desired_role_id="role:it_support_specialist",
        )
        all_matches = match_roles(base)
        selected = match_roles(base, top_n=1)
        self.assertEqual([r.rank for r in selected], [1, 3])
        self.assertTrue(selected[-1].pinned)
        self.assertEqual(selected[-1].fit_score, all_matches[-1].fit_score)
        self.assertEqual(len(match_roles(base, top_n=3)), 3)
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                match_roles(base, top_n=value)


if __name__ == "__main__":
    unittest.main()
