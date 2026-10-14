"""Ollama LLM chat client for text-based chat interactions.

This module provides OllamaChatClient which implements LLMChatClient
for text-based chat with Ollama models.
"""

import json
import logging
from collections.abc import Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.interfaces import (
    DEFAULT_LLM_HOST,
    DEFAULT_LLM_MODEL,
    ChatReply,
    ChatStreamChunk,
    LLMChatClient,
    ToolCall,
)

logger = logging.getLogger(__name__)


class OllamaChatClient(LLMChatClient):
    """Ollama-based chat client for text chat interactions.

    This client handles text-based chat with Ollama models via the /api/chat
    endpoint, providing retry logic and connection management.

    The /api/chat endpoint (rather than /api/generate) is used because it
    applies the model's chat template, which is required for features like
    Gemma 4's ``think`` reasoning mode to work correctly.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model: str | None = None,
        timeout: int = 120,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        """Initialise the Ollama chat client with connection and retry settings.

        Args:
            host: Ollama server hostname (default: DEFAULT_LLM_HOST).
            port: Ollama API port (default: 11434).
            model: Model tag to use for chat (default: DEFAULT_LLM_MODEL).
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of automatic retries on transient errors.
            backoff_factor: Backoff multiplier for retry delays.
        """
        super().__init__(
            host=host or DEFAULT_LLM_HOST,
            port=port or 11434,
            model=model or DEFAULT_LLM_MODEL,
            timeout=timeout,
        )
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session = self._create_session()
        logger.info("Initialized Ollama chat client for %s using model '%s'", self.base_url, self.model)

    def _create_session(self) -> requests.Session:
        """Build a requests Session with automatic retries on transient failures."""
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"GET", "POST"},
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _build_messages(
        self,
        message: str,
        system_prompt: str | None,
        history: list | None,
    ) -> list[dict]:
        """Build the ``messages`` array for the /api/chat endpoint.

        Thin wrapper around :meth:`LLMChatClient.build_messages` so the
        web-UI history conversion lives in exactly one place.
        """
        return LLMChatClient.build_messages(message, system_prompt=system_prompt, history=history)

    @staticmethod
    def _apply_think_prefix(messages: list[dict]) -> list[dict]:
        """Prepend the Gemma 4 thinking control token to the system message.

        Gemma 4 E2B/E4B edge variants only enter thinking mode when the
        ``<|think|>`` control token appears at the start of the system prompt;
        the Ollama ``think`` API parameter alone extracts the reasoning into
        ``message.thinking`` but does not engage the mode for these variants.

        A brief instruction to reason before responding is also injected.
        Without it the model frequently emits an empty thinking block for
        trivial routing tasks, so no trace is surfaced.
        """
        prefix = "<|think|>\nReason briefly about the user's request before responding."
        if not messages:
            return [{"role": "system", "content": prefix}]
        first = messages[0]
        if first.get("role") == "system":
            merged = dict(first)
            merged["content"] = f"{prefix}\n\n{first.get('content', '')}"
            return [merged, *messages[1:]]
        return [{"role": "system", "content": prefix}, *messages]

    def _build_payload_from_messages(
        self,
        messages: list[dict],
        stream: bool,
        think: bool,
        tools: list[dict] | None = None,
    ) -> dict:
        """Build the /api/chat payload from a raw message list.

        Args:
            messages: Chat messages (``{"role": ..., "content": ...}`` dicts).
            stream: Whether to stream the response.
            think: When True, inject the thinking control token into the
                system message and send the Ollama ``think`` parameter.
            tools: Optional tool specifications for native tool calling.

        Returns:
            The request payload dict.
        """
        if think:
            messages = self._apply_think_prefix(messages)
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if think:
            payload["think"] = True
        if tools:
            payload["tools"] = tools
        return payload

    def _build_payload(
        self,
        message: str,
        system_prompt: str | None,
        history: list | None,
        stream: bool,
        think: bool,
    ) -> dict:
        """Build the request payload for the /api/chat endpoint."""
        messages = self._build_messages(message, system_prompt, history)
        return self._build_payload_from_messages(messages, stream=stream, think=think)

    def _post_chat(self, payload: dict) -> dict:
        """POST a payload to /api/chat and return the parsed JSON response.

        Raises:
            requests.exceptions.RequestException: If the request fails.
            RuntimeError: If the response is not valid JSON.
        """
        url = f"{self.base_url}/api/chat"
        logger.debug("Sending chat request to %s with model '%s'", url, self.model)
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as e:
            logger.error(
                "Ollama chat returned non-JSON response (status %d): %s", response.status_code, response.text[:200]
            )
            raise RuntimeError(
                f"Ollama chat response was not valid JSON (status {response.status_code}). "
                f"Model: {self.model}. Response: {response.text[:200]}"
            ) from e

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: list | None) -> tuple[ToolCall, ...]:
        """Normalise an Ollama ``message.tool_calls`` list into ToolCall tuples.

        ``function.arguments`` may arrive as a dict or as a JSON string;
        anything unparseable degrades to an empty argument dict.
        """
        calls: list[ToolCall] = []
        for raw in raw_tool_calls or []:
            function = raw.get("function", {}) or {}
            name = function.get("name") or ""
            if not name:
                continue
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = OllamaChatClient._parse_arguments_text(arguments)
            if not isinstance(arguments, dict):
                arguments = {}
            calls.append(ToolCall(name=name, arguments=arguments))
        return tuple(calls)

    @staticmethod
    def _parse_arguments_text(text: str) -> dict:
        """Parse a tool-call arguments JSON string, tolerating partial input."""
        if not text or not text.strip():
            return {}
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _finalise_streamed_tool_calls(pending: dict[int, dict]) -> tuple[ToolCall, ...]:
        """Parse accumulated streamed tool-call fragments into ToolCall tuples.

        Ollama streams ``function.arguments`` as partial JSON strings that
        concatenate across chunks; some versions instead repeat the complete
        arguments on every chunk. Both shapes are handled: the concatenation
        of all fragments is tried first, then the last non-empty fragment.
        """
        calls: list[ToolCall] = []
        for position in sorted(pending):
            entry = pending[position]
            name = entry.get("name") or ""
            if not name:
                continue
            arguments: dict = {}
            fragments = [f for f in entry.get("fragments", []) if f]
            if fragments:
                arguments = OllamaChatClient._parse_arguments_text("".join(fragments))
                if not arguments:
                    arguments = OllamaChatClient._parse_arguments_text(fragments[-1])
            calls.append(ToolCall(name=name, arguments=arguments))
        return tuple(calls)

    def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> str:
        """Send a chat message to Ollama and return the response.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, ask the model for its reasoning trace. The trace
                is not returned here; use :meth:`chat_with_thinking` or
                :meth:`chat_stream_events` to retrieve it.

        Returns:
            The LLM's response text.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        messages = self._build_messages(message, system_prompt, history)
        return self.chat_messages(messages, think=think).content

    def chat_messages(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        think: bool = False,
    ) -> ChatReply:
        """Send a raw message list to /api/chat and return a structured reply.

        Supports native tool calling: ``tools`` carries the tool
        specifications offered to the model, and the reply reports any
        requested tool calls alongside the text answer. Prior assistant tool
        calls and ``role="tool"`` results may be included in ``messages`` so
        the model can continue a tool-calling conversation.

        Args:
            messages: Chat messages (``{"role": ..., "content": ...}`` dicts).
            tools: Optional tool specifications (Ollama ``tools`` format).
            think: When True, request the model's reasoning trace.

        Returns:
            A :class:`ChatReply` with content, thinking, and tool calls.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        payload = self._build_payload_from_messages(messages, stream=False, think=think, tools=tools)
        logger.debug("Sending chat request (tools=%s) with model '%s'", bool(tools), self.model)
        result = self._post_chat(payload)
        msg = result.get("message", {}) or {}
        return ChatReply(
            content=msg.get("content", "") or "",
            thinking=msg.get("thinking") or None,
            tool_calls=self._parse_tool_calls(msg.get("tool_calls")),
        )

    def chat_with_thinking(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> tuple[str, str | None]:
        """Send a chat message to Ollama and return the answer plus reasoning trace.

        When ``think`` is True the Ollama ``think`` parameter is sent and the
        model's reasoning trace (the ``thinking`` field) is returned alongside
        the answer. When ``think`` is False (or the model does not produce a
        trace) the thinking component is ``None``.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Returns:
            A ``(response_text, thinking_text_or_None)`` tuple.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        messages = self._build_messages(message, system_prompt, history)
        reply = self.chat_messages(messages, think=think)
        if think and reply.thinking:
            logger.debug("[Chat LLM] Reasoning trace: %r", reply.thinking)
        return reply.content, reply.thinking

    def chat_stream(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> Generator[str, None, None]:
        """Stream a chat response from Ollama, yielding text chunks.

        Uses the /api/chat endpoint with stream=True so that tokens
        arrive incrementally as they are produced by the model. Only the
        final-answer text (the ``message.content`` field) is yielded; reasoning
        traces (the ``message.thinking`` field, emitted when ``think`` is True)
        are dropped here. Use :meth:`chat_stream_events` to receive both.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Yields:
            Incremental response text chunks from the model.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        messages = self._build_messages(message, system_prompt, history)
        for chunk in self.chat_messages_stream(messages, think=think):
            if chunk.kind == "response" and chunk.content:
                yield chunk.content

    def chat_messages_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        think: bool = False,
    ) -> Generator[ChatStreamChunk, None, None]:
        """Stream a reply to a raw message list, yielding typed chunks.

        Supports native tool calling: ``tools`` carries the tool
        specifications offered to the model. Reasoning (``think``) and answer
        text stream incrementally; tool invocations requested by the model
        are accumulated across chunks (Ollama streams ``function.arguments``
        as partial JSON strings) and emitted as a single final
        ``"tool_calls"`` chunk.

        Args:
            messages: Chat messages (``{"role": ..., "content": ...}`` dicts).
            tools: Optional tool specifications (Ollama ``tools`` format).
            think: When True, request the model's reasoning trace.

        Yields:
            :class:`ChatStreamChunk` instances (``"thinking"``, ``"response"``,
            and/or a final ``"tool_calls"`` chunk).

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        payload = self._build_payload_from_messages(messages, stream=True, think=think, tools=tools)
        logger.debug("Streaming chat request (tools=%s) with model '%s'", bool(tools), self.model)

        url = f"{self.base_url}/api/chat"
        response = self._session.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        pending: dict[int, dict] = {}
        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            msg = chunk.get("message", {}) or {}
            thinking = msg.get("thinking") or None
            if thinking:
                yield ChatStreamChunk(kind="thinking", content=thinking)
            content = msg.get("content") or None
            if content:
                yield ChatStreamChunk(kind="response", content=content)
            for position, raw_call in enumerate(msg.get("tool_calls") or []):
                function = raw_call.get("function", {}) or {}
                entry = pending.setdefault(position, {"name": "", "fragments": []})
                if function.get("name"):
                    entry["name"] = function["name"]
                fragment = function.get("arguments")
                if isinstance(fragment, dict):
                    fragment = json.dumps(fragment)
                if isinstance(fragment, str) and fragment:
                    entry["fragments"].append(fragment)
            if chunk.get("done"):
                break

        tool_calls = self._finalise_streamed_tool_calls(pending)
        if tool_calls:
            yield ChatStreamChunk(kind="tool_calls", content="", tool_calls=tool_calls)

    def chat_stream_events(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> Generator[ChatStreamChunk, None, None]:
        """Stream a chat response from Ollama, yielding typed chunks.

        Like :meth:`chat_stream` but yields :class:`ChatStreamChunk` instances,
        separating the model's reasoning trace (``kind="thinking"``) from the
        final answer (``kind="response"``). When ``think`` is True, Ollama
        streams the ``message.thinking`` field first, then ``message.content``.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Yields:
            :class:`ChatStreamChunk` instances (``"thinking"`` and/or
            ``"response"``).

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        messages = self._build_messages(message, system_prompt, history)
        yield from self.chat_messages_stream(messages, think=think)

    def health_check(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            url = f"{self.base_url}/api/tags"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            logger.info("Ollama server is reachable")
            return True
        except requests.exceptions.RequestException as e:
            logger.error("Health check failed: %s", e)
            return False
