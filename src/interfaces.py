from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

# Import constants for default values
from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL

DEFAULT_PROMPT = (
    "Return ONLY valid JSON. Do NOT add any text before or after the JSON. "
    'Format: {"description": "...", "subjects": [...], "objects": [...], '
    '"colors": [...], "setting": "...", "mood": "...", "tags": [...]}. '
)


class ErrorCode(Enum):
    """Standardized error codes for photo extraction failures."""

    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    FORMAT_NOT_SUPPORTED = "format_not_supported"
    PROCESSING_ERROR = "processing_error"


def make_error_result(error_code: ErrorCode, message: str, image_path: str | None = None) -> dict:
    """Build a standardized error result dict for a failed extraction.

    Args:
        error_code: An ErrorCode enum member identifying the failure category.
        message: Human-readable description of the error.
        image_path: Optional path to the image that failed.

    Returns:
        A dict with keys ``success`` (False), ``error_code``, ``error``, and
        optionally ``image_path``.
    """
    result: dict = {
        "success": False,
        "error_code": error_code.value,
        "error": message,
    }
    if image_path is not None:
        result["image_path"] = image_path
    return result


@dataclass
class ProcessingResult:
    """Value object returned by every extract/process step.

    Holds the full outcome of a single image extraction: success flag, the
    raw and parsed LLM response, performance metrics, and optional error
    details.
    """

    image_path: str | None = None
    filename: str | None = None
    b64: str | None = None
    success: bool = False
    model: str | None = None
    prompt: str | None = None
    response: str | None = None
    parsed: dict | None = None
    total_duration_ms: float | None = None
    eval_count: int | None = None
    done: bool | None = None
    error: str | None = None
    error_code: str | None = None
    embedding_error: str | None = None

    def as_dict(self) -> dict:
        """Return a dict with all non-None fields for serialization."""
        result = {}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        return result


class BasePhotoExtractor(ABC):
    """Abstract interface for pluggable LLM backends that extract structured features from photos."""

    def __init__(
        self,
        host: str = DEFAULT_LLM_HOST,
        port: int = 11434,
        model: str = DEFAULT_LLM_MODEL,
        timeout: int = 120,
        default_prompt: str | None = None,
    ):
        """Initialise the extractor with connection and model parameters.

        Args:
            host: Server hostname or IP address.
            port: Server API port.
            model: Vision model identifier (tag) to use.
            timeout: HTTP request timeout in seconds.
            default_prompt: Fallback prompt if none is provided per call.
        """
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.port}"
        self.default_prompt = default_prompt or DEFAULT_PROMPT

    @abstractmethod
    def extract_b64(self, image_b64: str, prompt: str | None = None, options: dict | None = None) -> ProcessingResult:
        """Extract features from an image provided as a base64 string. Returns ProcessingResult."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        ...


class ToolCall(NamedTuple):
    """A single tool invocation requested by the LLM.

    Attributes:
        name: The tool function name (e.g. ``find`` for the ``/find`` tool).
        arguments: The parsed JSON arguments as a dict.
    """

    name: str
    arguments: dict


class ChatReply(NamedTuple):
    """Structured reply from a chat client that supports native tool calling.

    Attributes:
        content: The assistant's text answer (may be empty when the model
            only requested tool calls).
        thinking: The model's reasoning trace, when requested and supported.
        tool_calls: Tool invocations requested by the model, in call order.
    """

    content: str
    thinking: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class LLMChatClient(ABC):
    """Abstract interface for pluggable LLM chat clients.

    This interface provides a clean abstraction for chat-based LLM interactions,
    allowing different backends (Ollama, etc.) to be used interchangeably without
    the calling code needing to know which backend is being used.
    """

    def __init__(
        self,
        host: str = DEFAULT_LLM_HOST,
        port: int = 11434,
        model: str = DEFAULT_LLM_MODEL,
        timeout: int = 120,
    ):
        """Initialise the chat client with connection and model parameters.

        Args:
            host: Server hostname or IP address.
            port: Server API port.
            model: Model identifier (tag) to use for chat.
            timeout: HTTP request timeout in seconds.
        """
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.port}"

    @staticmethod
    def build_messages(
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
    ) -> list[dict]:
        """Build a ``messages`` array from a user message and web-UI history.

        Converts the chat history (entries with ``sender``/``content``/``type``
        fields from the web UI) into chat messages with ``role`` and
        ``content`` fields, then appends the current user message. Non-text
        entries are summarised so the model gets useful context without raw
        photo paths or error stack traces.

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

                # Map web UI sender to chat role.
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

    @abstractmethod
    def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> str:
        """Send a chat message to the LLM and return the response.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace in addition
                to the answer. Backends that support it surface the trace via
                :meth:`chat_stream_events` or :meth:`chat_with_thinking`; this
                method returns only the answer text.

        Returns:
            The LLM's response text.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        ...

    def chat_with_thinking(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> tuple[str, str | None]:
        """Send a chat message and return the answer plus optional reasoning trace.

        Default implementation delegates to :meth:`chat` and reports no
        thinking content. Backends that support reasoning traces (``think``)
        override this to return ``(response, thinking)``.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Returns:
            A ``(response_text, thinking_text_or_None)`` tuple.
        """
        return self.chat(message, system_prompt=system_prompt, history=history, think=think), None

    def chat_messages(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        think: bool = False,
    ) -> ChatReply:
        """Send a raw message list, optionally with tool definitions.

        This is the primitive behind native tool calling: ``messages`` may
        include prior assistant tool calls and ``role="tool"`` results, and
        ``tools`` carries tool specifications (e.g. Ollama ``tools`` format).
        The reply reports both the text answer and any requested tool calls,
        so the caller can execute them and continue the conversation.

        The default implementation ignores tool definitions and delegates to
        :meth:`chat` with the last user message and the first system message,
        so backends without native tool support degrade to plain chat.

        Args:
            messages: Chat messages (``{"role": ..., "content": ...}`` dicts).
            tools: Optional tool specifications to offer the model.
            think: When True, request the model's reasoning trace.

        Returns:
            A :class:`ChatReply` with content, thinking, and tool calls.
        """
        user_message = ""
        system_prompt = None
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
            elif msg.get("role") == "system" and system_prompt is None:
                system_prompt = msg.get("content")
        content = self.chat(user_message, system_prompt=system_prompt, think=think)
        return ChatReply(content=content)

    def chat_messages_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        think: bool = False,
    ) -> Generator["ChatStreamChunk", None, None]:
        """Stream a reply to a raw message list, optionally with tool definitions.

        Like :meth:`chat_messages` but yields :class:`ChatStreamChunk`
        instances; tool invocations requested by the model arrive as a final
        ``"tool_calls"`` chunk.

        The default implementation ignores tool definitions and delegates to
        :meth:`chat_stream_events` with the last user message and the first
        system message.

        Args:
            messages: Chat messages (``{"role": ..., "content": ...}`` dicts).
            tools: Optional tool specifications to offer the model.
            think: When True, request the model's reasoning trace.

        Yields:
            :class:`ChatStreamChunk` instances.
        """
        user_message = ""
        system_prompt = None
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
            elif msg.get("role") == "system" and system_prompt is None:
                system_prompt = msg.get("content")
        yield from self.chat_stream_events(user_message, system_prompt=system_prompt, think=think)

    def chat_stream(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> Generator[str, None, None]:
        """Stream a chat response from the LLM, yielding incremental text chunks.

        This is a non-abstract method with a default fallback that delegates
        to ``chat`` and yields the full response as a single chunk. Subclasses
        that support native streaming should override this.

        When ``think`` is True, backends that support reasoning traces should
        prefer overriding :meth:`chat_stream_events` so the reasoning is
        surfaced separately from the answer.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Yields:
            Incremental response text chunks from the LLM.
        """
        yield self.chat(message, system_prompt=system_prompt, history=history, think=think)

    def chat_stream_events(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
        think: bool = False,
    ) -> Generator["ChatStreamChunk", None, None]:
        """Stream a chat response as typed chunks, separating reasoning from the answer.

        Yields :class:`ChatStreamChunk` instances whose ``kind`` is either
        ``"thinking"`` (the model's reasoning trace) or ``"response"`` (the
        final answer). The default implementation wraps :meth:`chat_stream`
        as ``"response"`` chunks, so backends without reasoning support work
        unchanged; backends that support ``think`` override this.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            think: When True, request the model's reasoning trace.

        Yields:
            :class:`ChatStreamChunk` instances.
        """
        for chunk in self.chat_stream(message, system_prompt=system_prompt, history=history, think=think):
            yield ChatStreamChunk(kind="response", content=chunk)

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        ...


class ChatStreamChunk(NamedTuple):
    """A single streamed chunk from a chat client.

    Attributes:
        kind: ``"response"`` for final-answer text, ``"thinking"`` for the
            model's reasoning trace (only emitted when ``think`` is requested
            and the backend supports it), or ``"tool_calls"`` when the model
            requested tool invocations (carried in ``tool_calls``).
        content: The incremental text for this chunk (empty for tool calls).
        tool_calls: Complete tool invocations; present only on ``"tool_calls"``
            chunks.
    """

    kind: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


# Public API exports
__all__ = [
    "DEFAULT_PROMPT",
    "BasePhotoExtractor",
    "ChatReply",
    "ChatStreamChunk",
    "ErrorCode",
    "LLMChatClient",
    "ProcessingResult",
    "ToolCall",
    "make_error_result",
]
