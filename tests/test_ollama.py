import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from plugins.llm import create_extractor, list_backends
from plugins.llm.base import BasePhotoExtractor, ErrorCode
from plugins.llm.ollama import OllamaPhotoExtractor


class TestOllamaPhotoExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = OllamaPhotoExtractor(
            host="localhost",
            port=11434,
            model="test-model",
            timeout=30,
            max_retries=1,
        )

    def test_init_defaults(self):
        e = OllamaPhotoExtractor()
        self.assertEqual(e.host, "127.0.0.1")
        self.assertEqual(e.port, 11434)
        self.assertEqual(e.model, "gemma4:e2b-it-qat")
        self.assertEqual(e.timeout, 120)

    def test_init_custom_values(self):
        e = OllamaPhotoExtractor(
            host="10.0.0.1",
            port=9999,
            model="custom-model",
            timeout=60,
            default_prompt="Custom prompt",
            max_retries=5,
            backoff_factor=2.0,
        )
        self.assertEqual(e.host, "10.0.0.1")
        self.assertEqual(e.port, 9999)
        self.assertEqual(e.model, "custom-model")
        self.assertEqual(e.timeout, 60)
        self.assertEqual(e.default_prompt, "Custom prompt")
        self.assertEqual(e.max_retries, 5)
        self.assertEqual(e.backoff_factor, 2.0)

    def test_strip_markdown_fences_json_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = OllamaPhotoExtractor._strip_markdown_fences(text)
        self.assertEqual(result, '{"key": "value"}')

    def test_strip_markdown_fences_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = OllamaPhotoExtractor._strip_markdown_fences(text)
        self.assertEqual(result, '{"key": "value"}')

    def test_strip_markdown_fences_no_fences(self):
        text = '{"key": "value"}'
        result = OllamaPhotoExtractor._strip_markdown_fences(text)
        self.assertEqual(result, '{"key": "value"}')

    def test_strip_markdown_fences_empty(self):
        self.assertEqual(OllamaPhotoExtractor._strip_markdown_fences(""), "")
        self.assertEqual(OllamaPhotoExtractor._strip_markdown_fences(None), None)

    def test_build_payload(self):
        payload = self.extractor._build_payload("base64data", "test prompt")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["prompt"], "test prompt")
        self.assertEqual(payload["images"], ["base64data"])
        self.assertFalse(payload["stream"])

    def test_build_payload_with_options(self):
        payload = self.extractor._build_payload("base64data", "test prompt", options={"temperature": 0.5})
        self.assertEqual(payload["options"], {"temperature": 0.5})

    def test_extract_successful(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "response": '{"description": "test"}',
            "done": True,
            "total_duration": 1_500_000_000,
            "eval_count": 42,
        }

        with patch.object(self.extractor._session, "post", return_value=mock_response):
            result = self.extractor.extract_b64("ZmFrZS1pbWFnZS1kYXRh")

        self.assertTrue(result.success)
        self.assertEqual(result.model, "test-model")
        self.assertEqual(result.response, '{"description": "test"}')
        self.assertEqual(result.parsed, {"description": "test"})
        self.assertEqual(result.total_duration_ms, 1500.0)
        self.assertEqual(result.eval_count, 42)

    def test_extract_invalid_json_response(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "response": "not valid json at all",
            "done": True,
            "total_duration": 1_000_000_000,
            "eval_count": 10,
        }

        with patch.object(self.extractor._session, "post", return_value=mock_response):
            result = self.extractor.extract_b64("ZmFrZS1pbWFnZS1kYXRh")

        self.assertTrue(result.success)
        self.assertIsNone(result.parsed)

    def test_extract_timeout(self):
        with patch.object(
            self.extractor._session,
            "post",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            result = self.extractor.extract_b64("ZmFrZS1pbWFnZS1kYXRh")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ErrorCode.TIMEOUT.value)
        self.assertIn("timed out", result.error)

    def test_extract_network_error(self):
        with patch.object(
            self.extractor._session,
            "post",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            result = self.extractor.extract_b64("ZmFrZS1pbWFnZS1kYXRh")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ErrorCode.NETWORK_ERROR.value)
        self.assertIn("refused", result.error)

    def test_extract_b64_successful(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "response": '{"result": "ok"}',
            "done": True,
            "total_duration": 500_000_000,
            "eval_count": 20,
        }

        with patch.object(self.extractor._session, "post", return_value=mock_response):
            result = self.extractor.extract_b64("base64data")

        self.assertTrue(result.success)
        self.assertEqual(result.parsed, {"result": "ok"})

    def test_extract_b64_with_custom_prompt(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "response": "{}",
            "done": True,
            "total_duration": 0,
            "eval_count": 0,
        }

        with patch.object(self.extractor._session, "post", return_value=mock_response):
            result = self.extractor.extract_b64("base64data", prompt="custom")

        self.assertEqual(result.prompt, "custom")

    def test_health_check_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch.object(self.extractor._session, "get", return_value=mock_response):
            self.assertTrue(self.extractor.health_check())

    def test_health_check_failure(self):
        with patch.object(
            self.extractor._session,
            "get",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            self.assertFalse(self.extractor.health_check())

    def test_ollama_photo_extractor_instantiation(self):
        e = OllamaPhotoExtractor(host="x", port=1, model="m")
        self.assertIsInstance(e, OllamaPhotoExtractor)

    def test_subclass_of_base_photo_extractor(self):
        self.assertIsInstance(self.extractor, BasePhotoExtractor)

    def test_create_extractor_defaults_to_ollama(self):
        e = create_extractor(host="x", port=1, model="m")
        self.assertIsInstance(e, OllamaPhotoExtractor)
        self.assertEqual(e.host, "x")

    def test_create_extractor_explicit_backend(self):
        e = create_extractor(backend="ollama", host="x", port=1, model="m")
        self.assertIsInstance(e, OllamaPhotoExtractor)

    def test_create_extractor_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_extractor(backend="unknown")

    def test_list_backends_includes_ollama(self):
        backends = list_backends()
        self.assertIn("ollama", backends)


if __name__ == "__main__":
    unittest.main()
