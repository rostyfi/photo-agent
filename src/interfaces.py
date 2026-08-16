from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
    def extract(
        self, image_path: str | Path, prompt: str | None = None, options: dict | None = None
    ) -> ProcessingResult:
        """Extract features from a single image file. Returns ProcessingResult."""
        ...

    @abstractmethod
    def extract_b64(self, image_b64: str, prompt: str | None = None, options: dict | None = None) -> ProcessingResult:
        """Extract features from an image provided as a base64 string. Returns ProcessingResult."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        ...


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

    @abstractmethod
    def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
    ) -> str:
        """Send a chat message to the LLM and return the response.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.

        Returns:
            The LLM's response text.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        ...

    def chat_stream(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list | None = None,
    ) -> Generator[str, None, None]:
        """Stream a chat response from the LLM, yielding incremental text chunks.

        This is a non-abstract method with a default fallback that delegates
        to ``chat`` and yields the full response as a single chunk. Subclasses
        that support native streaming should override this.

        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.

        Yields:
            Incremental response text chunks from the LLM.
        """
        yield self.chat(message, system_prompt=system_prompt, history=history)

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        ...


# Public API exports
__all__ = [
    "DEFAULT_PROMPT",
    "BasePhotoExtractor",
    "ErrorCode",
    "LLMChatClient",
    "ProcessingResult",
    "make_error_result",
]
