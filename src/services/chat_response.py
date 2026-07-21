"""Chat response dataclass for Open Photo Agent.

This module contains the ChatResponse dataclass which is used throughout
the chat service and tools for structured responses.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ChatResponse:
    """Structured response from chat service.
    
    Attributes:
        status: The status of the response ("success", "error", etc.)
        response: The actual response content (string, dict, list, etc.)
        sender: Who sent the response (default: "assistant")
        model: The model that generated the response (default: "unknown")
        response_type: Optional type classifier (e.g., "photos", "error")
    """
    status: str
    response: Any
    sender: str = "assistant"
    model: str = "unknown"
    response_type: Optional[str] = None
