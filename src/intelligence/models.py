"""Shared Groq primary, RunPod GLM fallback and Gemini backup for every application AI task."""

import os
import re
from dataclasses import dataclass, replace

from pydantic import SecretStr

from src.config import load_local_environment
from src.intelligence.extractors import ExtractionError, ModelExtraction
from src.intelligence.gemini import GeminiClient, SYSTEM_INSTRUCTION
from src.intelligence.runpod_client import ChatModelClient, ProviderUnavailable
from src.schemas.extraction import ExtractionBatch

DEFAULT_MODEL = "openai/gpt-oss-120b"
RUNPOD_MODEL = "zai-org/GLM-4.7-Flash"


def default_model():
    load_local_environment()
    if os.environ.get("LLM_PROVIDER", "groq") == "runpod":
        return os.environ.get("RUNPOD_MODEL", RUNPOD_MODEL).strip() or RUNPOD_MODEL
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def model_configuration():
    load_local_environment()
    provider = os.environ.get("LLM_PROVIDER", "groq")
    available = (os.environ.get("GROQ_API", "").strip() or os.environ.get("GROQ_API_KEY", "").strip()
        or (os.environ.get("RUNPOD_API_KEY", "").strip() and os.environ.get("RUNPOD_ENDPOINT_ID", "").strip())
        or os.environ.get("GEMINI_API_KEY", "").strip())
    return provider, [] if available else ["GROQ_API"]


@dataclass(frozen=True)
class ModelClient:
    model: str
    primary: ChatModelClient | None
    backup: GeminiClient | None
    primary_failure: str | None = None
    interactive: bool = False
    runpod_backup: ChatModelClient | None = None
    primary_provider: str = "runpod"

    @classmethod
    def from_environment(cls, model=None, *, interactive=False):
        load_local_environment()
        provider = os.environ.get("LLM_PROVIDER", "groq")
        if provider not in {"groq", "runpod"}:
            raise ExtractionError("LLM_PROVIDER must be groq or runpod.")
        requested_model = model or default_model()
        runpod_model = requested_model if provider == "runpod" else os.environ.get("RUNPOD_MODEL", RUNPOD_MODEL)
        if not re.fullmatch(r"[a-zA-Z0-9_./-]{1,200}", runpod_model) or "glm" not in runpod_model.lower():
            raise ExtractionError("RUNPOD_MODEL must name a GLM model served by RunPod.")
        if provider == "groq" and requested_model != DEFAULT_MODEL:
            raise ExtractionError("GROQ_MODEL must be openai/gpt-oss-120b.")
        runpod = None
        key = os.environ.get("RUNPOD_API_KEY", "").strip()
        endpoint = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
        if key and endpoint:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", endpoint):
                raise ExtractionError("Invalid RunPod endpoint ID.")
            runpod = ChatModelClient("runpod",
                f"https://api.runpod.ai/v2/{endpoint}/openai/v1/chat/completions",
                SecretStr(key), runpod_model, timeout_seconds=90, use_queue_api=True)
        primary = runpod
        if provider == "groq":
            key = os.environ.get("GROQ_API", "").strip() or os.environ.get("GROQ_API_KEY", "").strip()
            primary = ChatModelClient("groq", "https://api.groq.com/openai/v1/chat/completions",
                SecretStr(key), requested_model, timeout_seconds=20 if interactive else 45) if key else None
        backup = None
        if os.environ.get("GEMINI_API_KEY", "").strip():
            configured = GeminiClient.from_environment()
            backup = GeminiClient(configured.api_key, configured.model, ())
        if primary is None and runpod is None and backup is None:
            raise ExtractionError("Configure GROQ_API, RunPod credentials, or GEMINI_API_KEY.")
        return cls(requested_model, primary, backup,
            f"{provider} configuration is incomplete" if primary is None else None,
            interactive, runpod if provider == "groq" else None, provider)

    def generate(self, instruction, data, response_model, *, json_schema=None):
        attempts = []
        candidates = [(self.primary_provider, self.primary, self.model)]
        if self.runpod_backup is not None:
            candidates.append(("runpod", self.runpod_backup, self.runpod_backup.model))
        for provider, client, model in candidates:
            if client is None:
                attempts.append({"provider": provider, "model": model,
                    "outcome": self.primary_failure or "not_configured"})
                continue
            try:
                result = client.generate(instruction, data, response_model, json_schema=json_schema)
            except ProviderUnavailable as error:
                attempts.append({"provider": provider, "model": model, "outcome": str(error)})
            else:
                attempts.append({"provider": provider, "model": result.returned_model, "outcome": "success"})
                return replace(result, provider=provider, request_attempts=tuple(attempts))
        # Evidence/schema failures remain fatal; only service failures use backups.
        if self.backup is None:
            raise ExtractionError("Primary AI providers unavailable; Gemini backup is not configured.")
        try:
            result = self.backup.generate(instruction, data, response_model,
                json_schema=json_schema, timeout_seconds=30 if self.interactive else 45)
        except ExtractionError as error:
            raise ExtractionError("Primary AI providers unavailable; Gemini backup also failed: " + str(error)) from None
        attempts.extend({**attempt, "provider": "gemini"} for attempt in result.request_attempts)
        if not result.request_attempts:
            attempts.append({"provider": "gemini", "model": result.returned_model, "outcome": "success"})
        return replace(result, provider="gemini", request_attempts=tuple(attempts))


@dataclass(frozen=True)
class ModelExtractor:
    client: ModelClient

    @property
    def model(self):
        return self.client.model

    @classmethod
    def from_environment(cls, model=None):
        return cls(ModelClient.from_environment(model))

    def extract(self, report, source):
        data = {"source": source.model_dump(mode="json"), "title": report.title,
                "untrusted_report_passages": [{"passage_id": p.passage_id,
                    "section": p.section, "text": p.text} for p in report.passages]}
        result = self.client.generate(SYSTEM_INSTRUCTION, data, ExtractionBatch)
        return ModelExtraction(result.value, result.returned_model,
            provider=result.provider or self.client.primary_provider, request_attempts=result.request_attempts)
