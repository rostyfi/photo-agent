"""API handlers package for Local Photo Agent.

This package contains Flask route handlers extracted from app.py to improve
modularity and reduce code size in the main application file.

Available handlers:
- chat: Handler for /_api/chat endpoint
- vectors: Blueprint for vector storage/search REST API
- debug: Blueprint for diagnostic vector self-test endpoints
"""

from .chat import api_chat_handler, api_chat_stream_handler
from .vectors import register_vectors_blueprint
from .debug import register_debug_blueprint

__all__ = [
    "api_chat_handler",
    "api_chat_stream_handler",
    "register_vectors_blueprint",
    "register_debug_blueprint",
]
