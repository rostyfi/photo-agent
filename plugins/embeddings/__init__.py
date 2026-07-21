"""Embedding plugins for Open Photo Agent.

This package provides the plugin infrastructure for embedding backends.
Currently only Ollama backend is supported.

Vector search library is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

# Import to trigger backend registration
from . import backends  # noqa: F401
