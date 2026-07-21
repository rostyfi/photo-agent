"""Ollama embedding backend auto-registration.

Vector search library is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

import logging

from src.embeddings.registry import register_embedding_backend
from src.embeddings.ollama import OllamaEmbeddingGenerator

logger = logging.getLogger(__name__)

# Auto-register the Ollama backend
register_embedding_backend("ollama", OllamaEmbeddingGenerator)
logger.debug("Registered Ollama embedding backend")
