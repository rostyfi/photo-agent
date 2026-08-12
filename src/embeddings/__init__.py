"""Vector embedding support for Local Photo Agent.

This module provides embedding generation and vector search capabilities
for photo collections using Ollama vision models and vector search library.

Requirements:
- Vector search library (HARD REQUIREMENT) - SQLite extension for vector search
- Ollama v0.1.0+ - For /api/embeddings endpoint support
  Check with: ollama --version

Features:
- Generate vector embeddings for images using Ollama
- Store embeddings in SQLite with vector search library for fast similarity search
- Find visually similar images using cosine similarity
- Support for multiple embedding models per image

Example usage:
    from src.embeddings import create_generator
    
    # Create a generator
    generator = create_generator(
        backend="ollama",
        host="localhost",
        port=11434,
        model="clip-vit-base-patch32"
    )
    
    # Generate embedding for an image
    embedding = generator.generate("photo.jpg")
    
    # Save to database
    from src.sidecar.database import FeaturesDatabase
    db = FeaturesDatabase("/photos/.local-photo-agent/features.db")
    db.init_vector_search()  # Requires vector search library
    db.save_embedding("photo.jpg", "clip-vit-base-patch32", embedding)
    
    # Find similar images
    similar = db.find_similar(embedding, limit=10)
"""

import logging
import pkgutil
from typing import Callable, Optional

from src.constants import DEFAULT_LLM_HOST
from src.embeddings.base import BaseEmbeddingGenerator
from src.embeddings.ollama import OllamaEmbeddingGenerator, DEFAULT_EMBEDDING_MODEL
from src.embeddings.registry import (
    register_embedding_backend,
    get_embedding_backend,
    list_embedding_backends,
    unregister_embedding_backend,
)

logger = logging.getLogger(__name__)

# Auto-register built-in backends
register_embedding_backend("ollama", OllamaEmbeddingGenerator)

# Auto-discover backend packages
try:
    for finder, name, ispkg in pkgutil.iter_modules(["plugins.embeddings.backends"]):
        if ispkg:
            try:
                __import__(f"plugins.embeddings.backends.{name}")
                logger.debug("Discovered embedding backend package: %s", name)
            except ImportError as e:
                logger.debug("Could not import embedding backend %s: %s", name, e)
except Exception as e:
    logger.debug("No plugins.embeddings.backends to discover: %s", e)


def create_generator(
    backend: str = "ollama",
    host: str = DEFAULT_LLM_HOST,
    port: int = 11434,
    model: str = DEFAULT_EMBEDDING_MODEL,
    timeout: int = 120,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    **kwargs,
) -> BaseEmbeddingGenerator:
    """Factory function to create an embedding generator.
    
    Auto-discovers and instantiates the requested embedding backend.
    
    Args:
        backend: The backend name (e.g., "ollama"). Default: "ollama".
        host: Server hostname or IP.
        port: Server port.
        model: Embedding model name. Default: nomic-embed-text.
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts on failure.
        backoff_factor: Multiplier for exponential backoff.
        **kwargs: Additional backend-specific arguments.
        
    Returns:
        A configured BaseEmbeddingGenerator instance.
        
    Raises:
        ValueError: If the requested backend is not found.
        RuntimeError: If vector search library is not available (checked on first use).
    """
    factory = get_embedding_backend(backend)
    if factory is None:
        available = list_embedding_backends()
        raise ValueError(
            f"Unknown embedding backend: '{backend}'. "
            f"Available backends: {available}. "
            f"Vector search library is a HARD REQUIREMENT for vector search."
        )
    
    return factory(
        host=host,
        port=port,
        model=model,
        timeout=timeout,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        **kwargs,
    )


__all__ = [
    "BaseEmbeddingGenerator",
    "OllamaEmbeddingGenerator",
    "DEFAULT_EMBEDDING_MODEL",
    "create_generator",
    "register_embedding_backend",
    "get_embedding_backend",
    "list_embedding_backends",
    "unregister_embedding_backend",
]
