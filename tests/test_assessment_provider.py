"""Provider routing, .env loading and transport contracts without live spending."""

import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from pydantic import SecretStr

from src.config import load_local_environment
from src.intelligence.extractors import ExtractionError
from src.profiles.assessment import AssessmentBatch
from src.profiles.model_client import ChatModelClient, assessment_client, assessment_configuration
from src.intelligence.runpod_client import ProviderUnavailable


class TestAssessmentProvider(TestCase):
    def test_local_env_loads_known_settings_without_overriding_host(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"PORT": "9000"}, clear=True):
            path = Path(tmp) / ".env"
            path.write_text('PORT=8000\nRUNPOD_API_KEY="test-secret"\nUNRELATED=value\n', encoding="utf-8")
            load_local_environment(path)
            self.assertEqual(os.environ["PORT"], "9000")
            self.assertEqual(os.environ["RUNPOD_API_KEY"], "test-secret")
            self.assertNotIn("UNRELATED", os.environ)

    def test_runpod_is_always_primary_with_a_glm_default(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "runpod", "GROQ_API": "", "GROQ_API_KEY": "", "RUNPOD_API_KEY": "test-key",
             "RUNPOD_ENDPOINT_ID": "test-endpoint", "RUNPOD_MODEL": "test/glm",
             "GEMINI_API_KEY": "", "GEMINI_MODEL": "gemini-test"}, clear=True):
            self.assertEqual(assessment_configuration(), ("runpod", []))
            client = assessment_client()
            self.assertEqual(client.primary.provider, "runpod")
            self.assertEqual(client.primary.endpoint,
                "https://api.runpod.ai/v2/test-endpoint/openai/v1/chat/completions")
            self.assertIsNone(client.backup)
            self.assertTrue(client.primary.use_queue_api)
            self.assertEqual(client.primary.timeout_seconds, 90)
            self.assertNotIn("test-key", repr(client))

    def test_endpoint_id_cannot_redirect_credentials(self):
        with patch.dict(os.environ, {
             "LLM_PROVIDER": "runpod", "GROQ_API": "", "GROQ_API_KEY": "", "RUNPOD_API_KEY": "test", "RUNPOD_ENDPOINT_ID": "evil.example/path",
             "RUNPOD_MODEL": "test/glm"}, clear=True):
            with self.assertRaises(ExtractionError):
                assessment_client()

    def test_chat_contract_applies_validated_json_output(self):
        client = ChatModelClient("runpod", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                                 SecretStr("test-secret"), "test/glm")
        response = Mock(status=200)
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = json.dumps({"model": "test/glm-version", "choices": [{
            "finish_reason": "stop", "message": {"content": '{"skills": []}'}}]}).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch("src.intelligence.runpod_client.build_opener", return_value=opener):
            result = client.generate("Estimate fictional skills.", {"skills": []}, AssessmentBatch)
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertNotIn("test-secret", request.data.decode())
        self.assertEqual(result.returned_model, "test/glm-version")

    def test_http_errors_do_not_expose_provider_response_or_key(self):
        client = ChatModelClient("runpod", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                                 SecretStr("test-secret"), "test/glm")
        opener = Mock()
        opener.open.side_effect = HTTPError(client.endpoint, 401, "private provider details", {}, None)
        with patch("src.intelligence.runpod_client.build_opener", return_value=opener):
            with self.assertRaisesRegex(ExtractionError, "HTTP 401") as raised:
                client.generate("Test", {}, AssessmentBatch)
        self.assertNotIn("test-secret", str(raised.exception))
        self.assertNotIn("private provider details", str(raised.exception))

    def queue_client(self):
        return ChatModelClient("runpod", "https://api.runpod.ai/v2/test/openai/v1/chat/completions",
                               SecretStr("test-secret"), "test/glm", use_queue_api=True)

    def test_native_queue_unwraps_the_worker_completion(self):
        completion = {"model": "test/glm", "choices": [{"finish_reason": "stop",
            "message": {"content": '{"skills": []}'}}]}
        with patch.object(ChatModelClient, "_queue_request", side_effect=[
            {"id": "job-1", "status": "IN_QUEUE"},
            {"id": "job-1", "status": "COMPLETED", "output": [completion]},
        ]) as request, patch("src.intelligence.runpod_client.time.sleep"):
            result = self.queue_client().generate("Test", {}, AssessmentBatch,
                json_schema=AssessmentBatch.model_json_schema())
        self.assertEqual(result.returned_model, "test/glm")
        self.assertEqual(request.call_args_list[0].args[0], "run")
        self.assertEqual(request.call_args_list[1].args[0], "status/job-1")
        submitted = request.call_args_list[0].args[1]
        self.assertEqual(submitted["input"]["openai_route"], "/v1/chat/completions")
        self.assertEqual(submitted["input"]["openai_input"]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(submitted["input"]["openai_input"]["response_format"]["type"], "json_schema")

    def test_native_queue_cancels_its_job_when_deadline_expires(self):
        client = replace(self.queue_client(), timeout_seconds=1)
        with patch.object(ChatModelClient, "_queue_request", side_effect=[
            {"id": "job-1", "status": "IN_QUEUE"}, {"status": "CANCELLED"},
        ]) as request, patch("src.intelligence.runpod_client.time.monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(ProviderUnavailable, "time budget"):
                client.generate("Test", {}, AssessmentBatch)
        self.assertEqual(request.call_args_list[-1].args[0], "cancel/job-1")

    def test_native_worker_failure_is_sanitized(self):
        with patch.object(ChatModelClient, "_queue_request", return_value={
            "id": "job-1", "status": "FAILED", "error": "private worker details",
        }) as request:
            with self.assertRaises(ProviderUnavailable) as error:
                self.queue_client().generate("Test", {}, AssessmentBatch)
        request.assert_called_once()
        self.assertNotIn("private worker details", str(error.exception))


class TestGroqTransport(TestCase):
    def test_groq_sends_strict_schema_without_glm_template_options(self):
        client = ChatModelClient("groq", "https://api.groq.com/openai/v1/chat/completions",
            SecretStr("groq-test-secret"), "openai/gpt-oss-120b")
        response = Mock(status=200)
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = json.dumps({"model": client.model, "choices": [{
            "finish_reason": "stop", "message": {"content": '{"skills": []}'}}]}).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch("src.intelligence.runpod_client.build_opener", return_value=opener):
            result = client.generate("Test", {}, AssessmentBatch)
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        schema = payload["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])
        self.assertEqual(schema["schema"]["required"], ["skills"])
        self.assertNotIn("chat_template_kwargs", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertFalse(payload["include_reasoning"])
        self.assertEqual(payload["max_completion_tokens"], 4096)
        self.assertNotIn('"$defs"', payload["messages"][0]["content"])
        self.assertEqual(request.get_header("User-agent"), "ikiguy/1.0")
        self.assertEqual(result.returned_model, client.model)
