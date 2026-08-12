"""API handlers package for Local Photo Agent.

This package contains Flask route handlers extracted from app.py to improve
modularity and reduce code size in the main application file.

Available handlers:
- chat: Handler for /_api/chat endpoint
"""

from .chat import api_chat_handler

__all__ = [
    "api_chat_handler",
]
