import unittest
from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile_from_cv

class TestCVCatalogAliases(unittest.TestCase):
    def test_common_web_abbreviations_and_dotted_tool_are_canonical(self):
        profile = create_profile_from_cv("synthetic:web_aliases", b"Skills: HTML, CSS, Node.js.",
            "cv.txt", catalog=real_catalog())
        self.assertEqual({s.label for s in profile.skills},
            {"Hypertext markup language HTML", "Cascading style sheets CSS", "Node.js"})

    def test_unknown_tools_and_negated_claims_are_excluded(self):
        profile = create_profile_from_cv("synthetic:unknown_aliases",
            b"Skills: ImaginaryQuantumTool. Not familiar with Node.js. No HTML experience.",
            "cv.txt", catalog=real_catalog())
        self.assertEqual(profile.skills, [])
