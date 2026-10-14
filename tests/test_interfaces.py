import unittest

from src.interfaces import (
    DEFAULT_PROMPT,
    BasePhotoExtractor,
    ChatReply,
    ChatStreamChunk,
    ErrorCode,
    LLMChatClient,
    ProcessingResult,
    ToolCall,
    make_error_result,
)


class _MinimalExtractor(BasePhotoExtractor):
    def extract(self, image_path, prompt=None, options=None):
        return ProcessingResult()

    def extract_b64(self, image_b64, prompt=None, options=None):
        return ProcessingResult()

    def health_check(self):
        return True


class _MinimalChatClient(LLMChatClient):
    """Minimal chat client: plain text replies, no native tool support."""

    def __init__(self, response="hello"):
        self._response = response
        self.chat_calls = []

    def chat(self, message, system_prompt=None, history=None, think=False):
        self.chat_calls.append(
            {"message": message, "system_prompt": system_prompt, "history": history, "think": think}
        )
        return self._response

    def health_check(self):
        return True


class TestInterfaces(unittest.TestCase):
    def test_default_prompt_is_string(self):
        self.assertIsInstance(DEFAULT_PROMPT, str)
        self.assertIn("description", DEFAULT_PROMPT)
        self.assertIn("JSON", DEFAULT_PROMPT)

    def test_error_code_values(self):
        self.assertEqual(ErrorCode.NETWORK_ERROR.value, "network_error")
        self.assertEqual(ErrorCode.TIMEOUT.value, "timeout")
        self.assertEqual(ErrorCode.INVALID_RESPONSE.value, "invalid_response")
        self.assertEqual(ErrorCode.FORMAT_NOT_SUPPORTED.value, "format_not_supported")
        self.assertEqual(ErrorCode.PROCESSING_ERROR.value, "processing_error")

    def test_base_photo_extractor_is_abstract(self):
        with self.assertRaises(TypeError):
            BasePhotoExtractor()

    def test_base_photo_extractor_init_defaults(self):
        e = _MinimalExtractor()
        self.assertEqual(e.host, "127.0.0.1")
        self.assertEqual(e.port, 11434)
        self.assertEqual(e.model, "gemma4:e2b-it-qat")
        self.assertEqual(e.timeout, 120)
        self.assertEqual(e.base_url, "http://127.0.0.1:11434")
        self.assertEqual(e.default_prompt, DEFAULT_PROMPT)

    def test_make_error_result_without_path(self):
        result = make_error_result(ErrorCode.TIMEOUT, "Request timed out")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "timeout")
        self.assertEqual(result["error"], "Request timed out")
        self.assertNotIn("image_path", result)

    def test_make_error_result_with_path(self):
        result = make_error_result(ErrorCode.NETWORK_ERROR, "Connection refused", image_path="/photos/img.jpg")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "network_error")
        self.assertEqual(result["error"], "Connection refused")
        self.assertEqual(result["image_path"], "/photos/img.jpg")

    def test_make_error_result_all_error_codes(self):
        for code in ErrorCode:
            result = make_error_result(code, "test")
            self.assertEqual(result["error_code"], code.value)


class TestChatClientToolCalling(unittest.TestCase):
    """Tests for the native tool-calling primitives on LLMChatClient."""

    def test_build_messages_with_system_and_history(self):
        history = [
            {"sender": "user", "content": "hi", "type": "text"},
            {"sender": "assistant", "content": "hello", "type": "text"},
            {"sender": "assistant", "type": "photos", "photo_paths": ["/a.jpg"], "count": 1},
            {"sender": "assistant", "type": "loading", "content": ""},
        ]
        messages = LLMChatClient.build_messages("how are you", system_prompt="Be nice.", history=history)
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "Be nice."},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "assistant", "content": "Found 1 matching photos"},
                {"role": "user", "content": "how are you"},
            ],
        )

    def test_build_messages_without_system_or_history(self):
        messages = LLMChatClient.build_messages("hello")
        self.assertEqual(messages, [{"role": "user", "content": "hello"}])

    def test_chat_messages_default_ignores_tools(self):
        client = _MinimalChatClient("hi there")
        reply = client.chat_messages(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}],
            tools=[{"type": "function", "function": {"name": "find"}}],
        )
        self.assertIsInstance(reply, ChatReply)
        self.assertEqual(reply.content, "hi there")
        self.assertIsNone(reply.thinking)
        self.assertEqual(reply.tool_calls, ())
        # Delegated to chat() with the last user message and first system message
        self.assertEqual(client.chat_calls[0]["message"], "hello")
        self.assertEqual(client.chat_calls[0]["system_prompt"], "sys")

    def test_chat_messages_stream_default_delegates(self):
        client = _MinimalChatClient("hi there")
        chunks = list(client.chat_messages_stream([{"role": "user", "content": "hello"}]))
        self.assertEqual([c.kind for c in chunks], ["response"])
        self.assertEqual(chunks[0].content, "hi there")
        self.assertEqual(chunks[0].tool_calls, ())

    def test_tool_call_namedtuple(self):
        call = ToolCall(name="find", arguments={"description": "cats"})
        self.assertEqual(call.name, "find")
        self.assertEqual(call.arguments, {"description": "cats"})

    def test_chat_stream_chunk_tool_calls_default(self):
        chunk = ChatStreamChunk(kind="response", content="hi")
        self.assertEqual(chunk.tool_calls, ())
        chunk = ChatStreamChunk(kind="tool_calls", content="", tool_calls=(ToolCall("find", {}),))
        self.assertEqual(chunk.tool_calls[0].name, "find")


if __name__ == "__main__":
    unittest.main()
