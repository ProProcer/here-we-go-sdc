"""Versioned real-catalog learning plan; optional tools remain identifiable."""

from typing import Literal

from src.schemas.onet_profile import SoftwareLearningOption
from src.schemas.roadmap import LearningPlan
from src.schemas.role import SkillId
from src.schemas.sdg import SDGSummary


class OnetLearningPlan(LearningPlan):
    schema_version: Literal["0.2.0"] = "0.2.0"
    catalog_id: Literal["onet_31_0"] = "onet_31_0"
    family_id: str
    family: str
    score_method: Literal["reviewed_onet_fit_v5"] = "reviewed_onet_fit_v5"
    software_learning_options: list[SoftwareLearningOption]
    selected_software_skill_ids: list[SkillId]
    budget_myr: float
    sdg_summary: SDGSummary | None = None
