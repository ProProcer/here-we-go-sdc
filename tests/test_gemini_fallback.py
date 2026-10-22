import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from pydantic import BaseModel, SecretStr

from src.intelligence.extractors import ExtractionError
from src.intelligence.gemini import DEFAULT_FALLBACK_MODELS, DEFAULT_MODEL, GeminiClient


class Probe(BaseModel):
    ok: bool


def envelope(*, version="gemini-returned", text='{"ok":true}'):
    result = {
        "candidates": [
            {"finishReason": "STOP", "content": {"parts": [{"text": text}]}}
        ],
    }
    if version is not None:
        result["modelVersion"] = version
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers.get_content_type.return_value = "application/json"
    response.read.return_value = json.dumps(result).encode()
    return response


class TestGeminiFallback(unittest.TestCase):
    def setUp(self):
        self.client = GeminiClient(
            SecretStr("sentinel-secret"),
            "gemini-primary",
            ("gemini-backup", "gemini-last"),
        )
        self.opener_patch = patch("src.intelligence.gemini.build_opener")
        self.opener = self.opener_patch.start().return_value
        self.addCleanup(self.opener_patch.stop)
        self.sleep_patch = patch("src.intelligence.gemini.time.sleep")
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)
        self.jitter_patch = patch("src.intelligence.gemini.uniform", return_value=0)
        self.jitter_patch.start()
        self.addCleanup(self.jitter_patch.stop)

    def generate(self):
        return self.client.generate("Return the supplied JSON.", {"ok": True}, Probe)

    def test_temporary_failure_moves_to_next_model_and_records_actual_model(self):
        self.opener.open.side_effect = [
            HTTPError("url", 503, "sentinel-secret", {}, None),
            envelope(version="gemini-backup-version"),
        ]
        result = self.generate()
        self.assertTrue(result.value.ok)
        self.assertEqual(result.returned_model, "gemini-backup-version")
        self.assertEqual(
            result.request_attempts,
            (
                {"model": "gemini-primary", "outcome": "HTTP 503"},
                {"model": "gemini-backup", "outcome": "success"},
            ),
        )
        calls = self.opener.open.call_args_list
        self.assertTrue(
            calls[0].args[0].full_url.endswith("/gemini-primary:generateContent")
        )
        self.assertTrue(
            calls[1].args[0].full_url.endswith("/gemini-backup:generateContent")
        )
        self.assertEqual(calls[0].args[0].data, calls[1].args[0].data)
        self.assertEqual(self.client.model, "gemini-primary")
        self.sleep.assert_called_once_with(1)
        for call in calls:
            request = call.args[0]
            self.assertTrue(
                request.full_url.startswith(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                )
            )
            self.assertNotIn("sentinel-secret", request.full_url)
            self.assertNotIn("sentinel-secret", request.data.decode())
        self.assertNotIn("sentinel-secret", repr(result))

    def test_no_fallback_when_primary_succeeds(self):
        self.opener.open.return_value = envelope()
        self.generate()
        self.opener.open.assert_called_once()
        self.sleep.assert_not_called()

    def test_missing_model_version_uses_model_that_actually_answered(self):
        self.opener.open.side_effect = [
            HTTPError("url", 503, "unavailable", {}, None),
            envelope(version=None),
        ]
        self.assertEqual(self.generate().returned_model, "gemini-backup")

    def test_auth_billing_quota_configuration_and_redirect_errors_stop_immediately(
        self,
    ):
        for status in (302, 400, 401, 402, 403, 404, 429):
            with self.subTest(status=status):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = HTTPError(
                    "url", status, "sentinel-secret", {}, None
                )
                with self.assertRaises(ExtractionError) as caught:
                    self.generate()
                self.opener.open.assert_called_once()
                self.assertNotIn("sentinel-secret", str(caught.exception))

    def test_all_allowed_temporary_codes_and_network_errors_can_fall_back(self):
        for error in [
            *[
                HTTPError("url", code, "secret", {}, None)
                for code in (408, 500, 502, 503, 504)
            ],
            URLError("sentinel-secret"),
        ]:
            with self.subTest(error=type(error).__name__):
                self.opener.open.side_effect = [error, envelope()]
                self.assertTrue(self.generate().value.ok)

    def test_exhaustion_is_bounded_deduplicated_and_sanitized(self):
        self.client = GeminiClient(
            SecretStr("sentinel-secret"),
            "gemini-primary",
            ("gemini-primary", "gemini-backup", "gemini-backup"),
        )
        self.opener.open.side_effect = HTTPError(
            "secret-url", 503, "sentinel-secret", {}, None
        )
        with self.assertRaisesRegex(
            ExtractionError, "availability attempts exhausted"
        ) as caught:
            self.generate()
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertNotIn("sentinel-secret", str(caught.exception))
        self.assertNotIn("secret-url", str(caught.exception))

    def test_blocked_truncated_or_invalid_json_never_switches_models(self):
        for finish, text in (
            ("SAFETY", "{}"),
            ("MAX_TOKENS", "{}"),
            ("STOP", "not json"),
            ("STOP", "{}"),
        ):
            with self.subTest(finish=finish, text=text):
                response = envelope(text=text)
                data = json.loads(response.read.return_value)
                data["candidates"][0]["finishReason"] = finish
                response.read.return_value = json.dumps(data).encode()
                self.opener.open.reset_mock()
                self.opener.open.return_value = response
                self.opener.open.side_effect = None
                with self.assertRaises(ExtractionError):
                    self.generate()
                self.opener.open.assert_called_once()

    def test_total_time_budget_stops_before_another_model(self):
        self.opener.open.side_effect = HTTPError("url", 503, "unavailable", {}, None)
        with (
            patch("src.intelligence.gemini.time.monotonic", side_effect=[0, 0, 90]),
            self.assertRaises(ExtractionError),
        ):
            self.generate()
        self.opener.open.assert_called_once()
        self.sleep.assert_not_called()

    def test_environment_default_override_and_opt_out(self):
        with patch.dict(
            "os.environ", {"GEMINI_API_KEY": "sentinel-secret"}, clear=True
        ):
            client = GeminiClient.from_environment()
            self.assertEqual(client.model, DEFAULT_MODEL)
            self.assertEqual(client.fallback_models, DEFAULT_FALLBACK_MODELS)
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "sentinel-secret",
                "GEMINI_MODEL": "gemini-custom",
                "GEMINI_FALLBACK_MODELS": "gemini-a, gemini-b",
            },
            clear=True,
        ):
            client = GeminiClient.from_environment()
            self.assertEqual(client.model, "gemini-custom")
            self.assertEqual(client.fallback_models, ("gemini-a", "gemini-b"))
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "sentinel-secret", "GEMINI_FALLBACK_MODELS": "none"},
            clear=True,
        ):
            self.assertEqual(GeminiClient.from_environment().fallback_models, ())

    def test_invalid_fallback_ids_are_rejected_before_network_access(self):
        for backups in (
            ("https://example.org",),
            ("../../secret",),
            ("gemma-4-26b-a4b-it",),
            tuple("gemini-" + str(i) for i in range(6)),
        ):
            with self.subTest(backups=backups), self.assertRaises(ExtractionError):
                GeminiClient(SecretStr("sentinel-secret"), "gemini-primary", backups)
        self.opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
