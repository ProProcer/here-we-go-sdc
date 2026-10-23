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

    def test_learning_skill_names_are_not_confused_with_aspirations(self):
        profile = create_profile_from_cv("synthetic:learning_names",
            b"Active Learning: independently applied a new reporting method.\nLearning Strategies: selected exercises for a practice curriculum.\nI am learning Python.\nNo SQL experience.",
            "cv.txt", catalog=real_catalog())
        self.assertEqual({s.label for s in profile.skills}, {"Active Learning", "Learning Strategies"})

    def test_specific_software_name_does_not_add_its_generic_substring(self):
        profile = create_profile_from_cv("synthetic:specific_tool",
            b"Used SAP ERP Financials and Moz search engine optimization SEO software independently.",
            "cv.txt", catalog=real_catalog())
        self.assertEqual({s.label for s in profile.skills}, {"SAP ERP Financials", "Moz search engine optimization SEO software"})
        separate = create_profile_from_cv("synthetic:separate_tools",
            b"Used SAP ERP Financials and SAP ERP independently.", "cv.txt", catalog=real_catalog())
        self.assertEqual({s.label for s in separate.skills}, {"SAP ERP Financials", "SAP ERP"})
