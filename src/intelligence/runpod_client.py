"""RunPod OpenAI-compatible structured-output transport."""

import json
import time
from dataclasses import dataclass, field
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from pydantic import SecretStr, ValidationError

from src.intelligence.extractors import ExtractionError
from src.intelligence.feeds import RejectRedirects
from src.intelligence.gemini import StructuredResponse


class ProviderUnavailable(ExtractionError):
    """A service/configuration failure eligible for the configured backup."""


@dataclass(frozen=True)
class ChatModelClient:
    provider: str
    endpoint: str
    api_key: SecretStr = field(repr=False)
    model: str
    timeout_seconds: float = 45
    use_queue_api: bool = False

    def _queue_request(self, path, payload=None, *, timeout=15):
        base = self.endpoint.split("/openai/", 1)[0]
        request = Request(base + "/" + path,
            data=None if payload is None else json.dumps(payload).encode(),
            method="GET" if payload is None else "POST",
            headers={"Authorization": "Bearer " + self.api_key.get_secret_value(),
                     "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ikiguy/1.0"})
        with build_opener(RejectRedirects()).open(request, timeout=timeout) as response:
            raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ExtractionError("AI response exceeded the size limit.")
            return json.loads(raw)

    def _queued_completion(self, payload):
        deadline = time.monotonic() + self.timeout_seconds
        job_id = None
        pending = False
        try:
            job = self._queue_request("run", {
                "input": {"openai_route": "/v1/chat/completions", "openai_input": payload},
                "policy": {"executionTimeout": int(min(180, self.timeout_seconds) * 1000),
                           "ttl": int((self.timeout_seconds + 60) * 1000)},
            }, timeout=min(15, self.timeout_seconds))
            job_id = job["id"]
            if not isinstance(job_id, str) or not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in job_id):
                raise ExtractionError("RunPod returned an invalid job ID.")
            while job["status"] in {"IN_QUEUE", "IN_PROGRESS"}:
                pending = True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderUnavailable("RunPod job exceeded the request time budget.")
                time.sleep(min(1, remaining))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderUnavailable("RunPod job exceeded the request time budget.")
                job = self._queue_request("status/" + job_id, timeout=min(15, remaining))
            pending = False
            if job["status"] != "COMPLETED":
                raise ProviderUnavailable("RunPod inference job failed or was cancelled.")
            output = job.get("output")
            if isinstance(output, list):
                output = output[-1] if output else None
            if not isinstance(output, dict) or "error" in output:
                raise ProviderUnavailable("RunPod model worker did not return a completion.")
            return output
        finally:
            if job_id and pending:
                try:
                    self._queue_request("cancel/" + job_id, {}, timeout=5)
                except (OSError, URLError, HTTPException, ValueError):
                    pass

    def generate(self, instruction, data, response_model, *, json_schema=None):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instruction + " Return JSON only, matching this schema: "
                 + json.dumps(json_schema if json_schema is not None else response_model.model_json_schema())},
                {"role": "user", "content": json.dumps(data)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 8192 if isinstance(data, dict) and data.get("assessment_contract") in {"cv_skill_levels_v2", "learning_dependencies_v1", "public_text_translation_v1"} else 4096,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self.provider == "groq":
            # The response schema already constrains decoding; do not duplicate
            # it in the prompt and consume the account's token quota twice.
            payload["messages"][0]["content"] = instruction + " Return JSON only, matching the supplied response schema."
            payload.pop("chat_template_kwargs")
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            payload.update(reasoning_effort="low", include_reasoning=False)
            json_schema = _strict_schema(json_schema if json_schema is not None else response_model.model_json_schema())
        if json_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": response_model.__name__, "strict": True, "schema": json_schema}}
        request = Request(self.endpoint, data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": "Bearer " + self.api_key.get_secret_value(),
                     "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ikiguy/1.0"})
        try:
            if self.use_queue_api:
                body = self._queued_completion(payload)
            else:
                with build_opener(RejectRedirects()).open(request, timeout=self.timeout_seconds) as response:
                    if response.status != 200 or response.headers.get_content_type() != "application/json":
                        raise ExtractionError("AI provider returned an invalid response.")
                    raw = response.read(256 * 1024 + 1)
                    if len(raw) > 256 * 1024:
                        raise ExtractionError("AI response exceeded the size limit.")
                body = json.loads(raw)
            choice = body["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ExtractionError("AI output was incomplete.")
            parsed = response_model.model_validate_json(choice["message"]["content"])
            returned_model = body.get("model") or self.model
            if not isinstance(returned_model, str):
                raise ValueError("Invalid returned model")
            return StructuredResponse(parsed, returned_model)
        except HTTPError as error:
            raise (ProviderUnavailable if error.code in {401, 402, 403, 404, 408, 409, 429, 500, 502, 503, 504} else ExtractionError)(f"AI provider rejected the request (HTTP {error.code}).") from None
        except (OSError, URLError, HTTPException):
            raise ProviderUnavailable("AI transport_error: provider could not be reached.") from None
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise ExtractionError("AI structured output failed validation.") from None



def _strict_schema(schema):
    """Require explicit fields throughout Groq's constrained JSON schema."""
    if isinstance(schema, list):
        return [_strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _strict_schema(value) for key, value in schema.items() if key != "default"}
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result
