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

from src.interfaces import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL, ChatStreamChunk, LLMChatClient

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

        Converts the chat history (entries with ``sender``/``content``/``type``
        fields from the web UI) into Ollama chat messages with ``role`` and
        ``content`` fields, then appends the current user message.

        Args:
            message: The current user message/prompt.
            system_prompt: Optional system prompt; prepended as a system message.
            history: Optional chat history from the web UI.

        Returns:
            A list of ``{"role": ..., "content": ...}`` dicts.
        """
        messages: list[dict] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            for entry in history:
                sender = entry.get("sender", "")
                content = entry.get("content", "")
                entry_type = entry.get("type", "text")

                # Map web UI sender to Ollama role.
                role = "assistant" if sender == "assistant" else "user"

                # Summarise non-text entries so the model gets useful context
                # without raw photo paths or error stack traces.
                if entry_type == "photos":
                    photo_paths = entry.get("photo_paths", [])
                    count = entry.get("count", len(photo_paths))
                    text = f"Found {count} matching photos"
                elif entry_type == "error":
                    text = f"Error - {content}"
                elif entry_type == "loading":
                    continue  # skip loading placeholders
                else:
                    text = str(content)

                if text:
                    messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": message})
        return messages

    def _build_payload(
        self,
        message: str,
        system_prompt: str | None,
        history: list | None,
        stream: bool,
        think: bool,
    ) -> dict:
        """Build the request payload for the /api/chat endpoint.

        When ``think`` is True the ``<|think|>`` control token is prepended to
        the system prompt. Gemma 4 E2B/E4B edge variants only enter thinking
        mode when this token appears at the start of the system prompt; the
        Ollama ``think`` API parameter alone extracts the reasoning into
        ``message.thinking`` but does not engage the mode for these variants.

        A brief instruction to reason before responding is also injected.
        Without it the model frequently emits an empty thinking block for
        trivial routing tasks (the system prompt's "Return ONLY the tool
        command" instruction suppresses reasoning), so no trace is surfaced.
        """
        if think:
            prefix = "<|think|>\nReason briefly about the user's request before responding."
            system_prompt = f"{prefix}\n\n{system_prompt}" if system_prompt else prefix
        payload: dict = {
            "model": self.model,
            "messages": self._build_messages(message, system_prompt, history),
            "stream": stream,
        }
        if think:
            payload["think"] = True
        return payload

    @staticmethod
    def _parse_response(result: dict) -> tuple[str, str | None]:
        """Extract (content, thinking) from a non-streaming /api/chat response."""
        msg = result.get("message", {}) or {}
        content = msg.get("content", "") or ""
        thinking = msg.get("thinking") or None
        return content, thinking

    @staticmethod
    def _parse_stream_chunk(chunk: dict) -> tuple[str | None, str | None]:
        """Extract (content_token, thinking_token) from a streaming /api/chat chunk."""
        msg = chunk.get("message", {}) or {}
        content = msg.get("content") or None
        thinking = msg.get("thinking") or None
        return content, thinking

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
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(message, system_prompt, history, stream=False, think=think)

        logger.debug("Sending chat request to %s with model '%s'", url, self.model)

        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as e:
            logger.error(
                "Ollama chat returned non-JSON response (status %d): %s", response.status_code, response.text[:200]
            )
            raise RuntimeError(
                f"Ollama chat response was not valid JSON (status {response.status_code}). "
                f"Model: {self.model}. Response: {response.text[:200]}"
            ) from e

        content, _ = self._parse_response(result)
        return content

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
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(message, system_prompt, history, stream=False, think=think)

        logger.debug("Sending chat request (think=%s) to %s with model '%s'", think, url, self.model)

        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as e:
            logger.error(
                "Ollama chat returned non-JSON response (status %d): %s", response.status_code, response.text[:200]
            )
            raise RuntimeError(
                f"Ollama chat response was not valid JSON (status {response.status_code}). "
                f"Model: {self.model}. Response: {response.text[:200]}"
            ) from e

        content, thinking = self._parse_response(result)
        if think and thinking:
            logger.debug("[Chat LLM] Reasoning trace: %r", thinking)
        return content, thinking

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
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(message, system_prompt, history, stream=True, think=think)

        logger.debug("Streaming chat request to %s with model '%s'", url, self.model)

        response = self._session.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            content, _ = self._parse_stream_chunk(chunk)
            if content:
                yield content
            if chunk.get("done"):
                break

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
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(message, system_prompt, history, stream=True, think=think)

        logger.debug("Streaming chat request (think=%s) to %s with model '%s'", think, url, self.model)

        response = self._session.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            content, thinking = self._parse_stream_chunk(chunk)
            if thinking:
                yield ChatStreamChunk(kind="thinking", content=thinking)
            if content:
                yield ChatStreamChunk(kind="response", content=content)
            if chunk.get("done"):
                break

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
