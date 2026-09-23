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


class TestOllamaChatClient(unittest.TestCase):
    def setUp(self):
        from plugins.llm import OllamaChatClient

        self.client = OllamaChatClient(
            host="localhost",
            port=11434,
            model="test-model",
            timeout=30,
            max_retries=1,
        )

    def _capture_payload(self, response_json):
        """Patch the session post and return the (payload, mock_response)."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = response_json
        captured = {}

        def _post(url, json=None, **kwargs):
            captured["payload"] = json
            return mock_response

        return captured, _post, mock_response

    def test_chat_without_think_omits_think_param(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "hello"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            result = self.client.chat("hi")
        self.assertEqual(result, "hello")
        self.assertNotIn("think", captured["payload"])

    def test_chat_with_think_sends_think_true(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "hello"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            self.client.chat("hi", think=True)
        self.assertTrue(captured["payload"].get("think"))

    def test_chat_uses_api_chat_endpoint(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "hello"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post) as mock_post:
            self.client.chat("hi")
        url = mock_post.call_args[0][0]
        self.assertTrue(url.endswith("/api/chat"), f"expected /api/chat, got {url}")

    def test_chat_with_thinking_returns_trace(self):
        captured, _post, _ = self._capture_payload(
            {"message": {"content": "OK", "thinking": "reasoning here"}, "done": True}
        )
        with patch.object(self.client._session, "post", side_effect=_post):
            response, thinking = self.client.chat_with_thinking("hi", think=True)
        self.assertEqual(response, "OK")
        self.assertEqual(thinking, "reasoning here")
        self.assertTrue(captured["payload"].get("think"))

    def test_chat_with_thinking_no_trace_returns_none(self):
        _, _post, _ = self._capture_payload({"message": {"content": "OK"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            response, thinking = self.client.chat_with_thinking("hi", think=False)
        self.assertEqual(response, "OK")
        self.assertIsNone(thinking)

    def test_chat_builds_messages_array(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "hello"}, "done": True})
        history = [
            {"sender": "user", "content": "hi", "type": "text"},
            {"sender": "assistant", "content": "hello", "type": "text"},
        ]
        with patch.object(self.client._session, "post", side_effect=_post):
            self.client.chat("how are you", system_prompt="You are helpful.", history=history)
        msgs = captured["payload"]["messages"]
        self.assertEqual(msgs[0], {"role": "system", "content": "You are helpful."})
        self.assertEqual(msgs[1], {"role": "user", "content": "hi"})
        self.assertEqual(msgs[2], {"role": "assistant", "content": "hello"})
        self.assertEqual(msgs[3], {"role": "user", "content": "how are you"})

    def test_think_injects_control_token_in_system_prompt(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "ok"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            self.client.chat_with_thinking("hi", system_prompt="You are helpful.", think=True)
        system_msg = captured["payload"]["messages"][0]
        self.assertEqual(system_msg["role"], "system")
        self.assertTrue(system_msg["content"].startswith("<|think|>"), system_msg["content"])
        self.assertIn("Reason briefly", system_msg["content"])
        self.assertIn("You are helpful.", system_msg["content"])
        self.assertTrue(captured["payload"].get("think"))

    def test_think_without_system_prompt_creates_token_only_message(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "ok"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            self.client.chat_with_thinking("hi", think=True)
        system_msg = captured["payload"]["messages"][0]
        self.assertEqual(system_msg["role"], "system")
        self.assertTrue(system_msg["content"].startswith("<|think|>"))
        self.assertIn("Reason briefly", system_msg["content"])

    def test_no_think_does_not_inject_control_token(self):
        captured, _post, _ = self._capture_payload({"message": {"content": "ok"}, "done": True})
        with patch.object(self.client._session, "post", side_effect=_post):
            self.client.chat("hi", system_prompt="You are helpful.", think=False)
        system_msg = captured["payload"]["messages"][0]
        self.assertEqual(system_msg["content"], "You are helpful.")
        self.assertNotIn("think", captured["payload"])

    def test_chat_stream_events_separates_thinking_and_response(self):
        lines = [
            json.dumps({"message": {"thinking": "Hmm"}, "done": False}),
            json.dumps({"message": {"thinking": " more"}, "done": False}),
            json.dumps({"message": {"content": "An"}, "done": False}),
            json.dumps({"message": {"content": "swer"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_lines.return_value = [s.encode() for s in lines]

        with patch.object(self.client._session, "post", return_value=mock_response):
            chunks = list(self.client.chat_stream_events("hi", think=True))

        kinds = [(c.kind, c.content) for c in chunks]
        self.assertEqual(
            kinds,
            [
                ("thinking", "Hmm"),
                ("thinking", " more"),
                ("response", "An"),
                ("response", "swer"),
            ],
        )

    def test_chat_stream_events_without_think_only_response(self):
        lines = [
            json.dumps({"message": {"content": "Hi"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_lines.return_value = [s.encode() for s in lines]

        with patch.object(self.client._session, "post", return_value=mock_response):
            chunks = list(self.client.chat_stream_events("hi", think=False))

        self.assertEqual([c.kind for c in chunks], ["response"])
        self.assertEqual(chunks[0].content, "Hi")


if __name__ == "__main__":
    unittest.main()
