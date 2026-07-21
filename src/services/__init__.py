"""Services package for Open Photo Agent.

This package contains service classes that encapsulate business logic,
providing clean separation of concerns and improved testability.

Available services:
- ChatService: Handles chat messages and tool commands
- ChatResponse: Structured response from chat service
"""

from .chat import ChatService
from .chat_response import ChatResponse

__all__ = [
    "ChatService",
    "ChatResponse",
]
