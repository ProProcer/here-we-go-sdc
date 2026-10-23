"""Skill assessment uses the same RunPod-first policy as research workflows."""

from src.intelligence.models import ModelClient, model_configuration
from src.intelligence.runpod_client import ChatModelClient  # compatibility export


def assessment_configuration():
    return model_configuration()


def assessment_client():
    return ModelClient.from_environment(interactive=True)
