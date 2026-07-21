"""Embedding backend plugins.

Vector search library is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

# Import all backend packages to trigger registration
from . import ollama  # noqa: F401
