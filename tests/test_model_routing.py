"""Every AI task uses RunPod first; Gemini runs only for service failures."""

import unittest
from unittest.mock import Mock, patch
import os
from dataclasses import replace

from pydantic import BaseModel, SecretStr

from src.intelligence.extractors import ExtractionError
from src.intelligence.gemini import StructuredResponse
from src.intelligence.models import ModelClient
from src.intelligence.runpod_client import ChatModelClient, ProviderUnavailable


class Answer(BaseModel):
    ok: bool


class TestModelRouting(unittest.TestCase):
    def client(self, primary_error=None):
        primary = Mock()
        primary.generate.return_value = StructuredResponse(Answer(ok=True), "glm-actual")
        primary.generate.side_effect = primary_error
        backup = Mock()
        backup.generate.return_value = StructuredResponse(Answer(ok=True), "gemini-actual",
            ({"model": "gemini-actual", "outcome": "success"},))
        return ModelClient("zai-org/GLM-4.7-Flash", primary, backup, interactive=True)

    def test_primary_success_never_calls_backup(self):
        client = self.client()
        result = client.generate("Test", {}, Answer)
        self.assertEqual(result.provider, "runpod")
        self.assertEqual(result.returned_model, "glm-actual")
        client.backup.generate.assert_not_called()

    def test_availability_failure_calls_backup_and_records_both_attempts(self):
        client = self.client(ProviderUnavailable("HTTP 503"))
        schema = Answer.model_json_schema()
        result = client.generate("Test", {}, Answer, json_schema=schema)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.returned_model, "gemini-actual")
        self.assertEqual([a["provider"] for a in result.request_attempts], ["runpod", "gemini"])
        self.assertEqual(client.backup.generate.call_args.kwargs["json_schema"], schema)
        self.assertEqual(client.backup.generate.call_args.kwargs["timeout_seconds"], 30)

    def test_validation_failure_does_not_get_another_model_opinion(self):
        client = self.client(ExtractionError("Structured output failed validation"))
        with self.assertRaises(ExtractionError):
            client.generate("Test", {}, Answer)
        client.backup.generate.assert_not_called()

    def test_no_primary_configuration_is_explicit_in_backup_receipt(self):
        client = self.client()
        client = ModelClient(client.model, None, client.backup, "RunPod not configured")
        result = client.generate("Test", {}, Answer)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.request_attempts[0]["outcome"], "RunPod not configured")

    def test_primary_failure_without_backup_is_not_reported_as_success(self):
        client = self.client(ProviderUnavailable("HTTP 429"))
        client = ModelClient(client.model, client.primary, None)
        with self.assertRaisesRegex(ExtractionError, "Gemini backup is not configured"):
            client.generate("Test", {}, Answer)


class TestGroqRouting(unittest.TestCase):
    def test_bounded_request_reserves_time_for_backups(self):
        primary = ChatModelClient("groq", "https://example.org/groq", SecretStr("test"), "test-groq", timeout_seconds=20)
        runpod = replace(primary, provider="runpod", model="test-glm", timeout_seconds=90)
        backup = Mock()
        backup.generate.return_value = StructuredResponse(Answer(ok=True), "gemini-backup")
        client = ModelClient(primary.model, primary, backup, interactive=True,
            runpod_backup=runpod, primary_provider="groq", request_budget_seconds=45)
        now = [0.0]
        allocated = []

        def unavailable(provider, *args, **kwargs):
            allocated.append(provider.timeout_seconds)
            now[0] += provider.timeout_seconds
            raise ProviderUnavailable("timeout")

        with patch("src.intelligence.models.time.monotonic", side_effect=lambda: now[0]), patch.object(ChatModelClient, "generate", autospec=True, side_effect=unavailable):
            result = client.generate("Test", {}, Answer)
        self.assertEqual(allocated, [15, 15])
        self.assertEqual(backup.generate.call_args.kwargs["timeout_seconds"], 15)
        self.assertEqual(result.provider, "gemini")

    def client(self, groq_error=None, runpod_error=None):
        groq = Mock(model="openai/gpt-oss-120b")
        groq.generate.return_value = StructuredResponse(Answer(ok=True), "openai/gpt-oss-120b")
        groq.generate.side_effect = groq_error
        runpod = Mock(model="zai-org/GLM-4.7-Flash")
        runpod.generate.return_value = StructuredResponse(Answer(ok=True), runpod.model)
        runpod.generate.side_effect = runpod_error
        gemini = Mock()
        gemini.generate.return_value = StructuredResponse(Answer(ok=True), "gemini-backup")
        return ModelClient(groq.model, groq, gemini, interactive=True,
            runpod_backup=runpod, primary_provider="groq")

    def test_groq_success_never_uses_other_providers(self):
        client = self.client()
        result = client.generate("Test", {}, Answer)
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.returned_model, "openai/gpt-oss-120b")
        client.runpod_backup.generate.assert_not_called()
        client.backup.generate.assert_not_called()

    def test_runpod_is_second_and_gemini_last(self):
        for error, expected in ((None, ["groq", "runpod"]),
                (ProviderUnavailable("503"), ["groq", "runpod", "gemini"])):
            with self.subTest(expected=expected):
                client = self.client(ProviderUnavailable("429"), error)
                schema = Answer.model_json_schema()
                result = client.generate("Test", {}, Answer, json_schema=schema)
                self.assertEqual([a["provider"] for a in result.request_attempts], expected)
                self.assertEqual(result.provider, expected[-1])
                self.assertEqual(client.runpod_backup.generate.call_args.kwargs["json_schema"], schema)
                if error is None:
                    client.backup.generate.assert_not_called()

    def test_invalid_output_cannot_fall_back(self):
        for index in (0, 1):
            client = self.client(ExtractionError("invalid output") if index == 0 else ProviderUnavailable("503"),
                ExtractionError("invalid output"))
            with self.assertRaises(ExtractionError):
                client.generate("Test", {}, Answer)
            client.backup.generate.assert_not_called()
            if index == 0:
                client.runpod_backup.generate.assert_not_called()

    def test_environment_accepts_user_key_name_and_keeps_fixed_destination(self):
        with patch("src.intelligence.models.load_local_environment"), patch.dict(os.environ,
                {"GROQ_API": "test-groq-secret", "RUNPOD_API_KEY": "test-runpod-secret",
                 "RUNPOD_ENDPOINT_ID": "test-endpoint", "GEMINI_API_KEY": ""}, clear=True):
            client = ModelClient.from_environment(interactive=True)
        self.assertEqual(client.primary_provider, "groq")
        self.assertEqual(client.primary.model, "openai/gpt-oss-120b")
        self.assertEqual(client.primary.endpoint, "https://api.groq.com/openai/v1/chat/completions")
        self.assertFalse(client.primary.use_queue_api)
        self.assertTrue(client.runpod_backup.use_queue_api)
        self.assertNotIn("test-groq-secret", repr(client))
        self.assertNotIn("test-runpod-secret", repr(client))
