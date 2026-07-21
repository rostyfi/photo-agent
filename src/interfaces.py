from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Union

# Import constants for default values
from src.constants import DEFAULT_LLM_MODEL, DEFAULT_LLM_HOST

DEFAULT_PROMPT = (
    "Return ONLY valid JSON. Do NOT add any text before or after the JSON. "
    "Format: {\"description\": \"...\", \"subjects\": [...], \"objects\": [...], "
    "\"colors\": [...], \"setting\": \"...\", \"mood\": \"...\", \"tags\": [...]}. "
)


class ErrorCode(Enum):
    """Standardized error codes for photo extraction failures."""

    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    FORMAT_NOT_SUPPORTED = "format_not_supported"
    PROCESSING_ERROR = "processing_error"


def make_error_result(error_code: ErrorCode, message: str, image_path: Optional[str] = None) -> Dict:
    """Build a standardized error result dict for a failed extraction.

    Args:
        error_code: An ErrorCode enum member identifying the failure category.
        message: Human-readable description of the error.
        image_path: Optional path to the image that failed.

    Returns:
        A dict with keys ``success`` (False), ``error_code``, ``error``, and
        optionally ``image_path``.
    """
    result: Dict = {
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

    image_path: Optional[str] = None
    filename: Optional[str] = None
    b64: Optional[str] = None
    success: bool = False
    model: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    parsed: Optional[Dict] = None
    total_duration_ms: Optional[float] = None
    eval_count: Optional[int] = None
    done: Optional[bool] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    embedding_error: Optional[str] = None

    def as_dict(self) -> Dict:
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
        default_prompt: Optional[str] = None,
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
    def extract(self, image_path: Union[str, Path], prompt: Optional[str] = None, options: Optional[Dict] = None) -> ProcessingResult:
        """Extract features from a single image file. Returns ProcessingResult."""
        ...

    @abstractmethod
    def extract_b64(self, image_b64: str, prompt: Optional[str] = None, options: Optional[Dict] = None) -> ProcessingResult:
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
        system_prompt: Optional[str] = None,
        history: Optional[list] = None,
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

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        ...


# Public API exports
__all__ = [
    "ErrorCode",
    "make_error_result",
    "ProcessingResult",
    "DEFAULT_PROMPT",
    "BasePhotoExtractor",
    "LLMChatClient",
]


