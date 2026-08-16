"""Plugin registry for embedding backends.

Vector search library is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Registry of available embedding backends
_embedding_backends: dict[str, Callable] = {}


def register_embedding_backend(name: str, factory: Callable) -> None:
    """Register an embedding backend factory function.

    Args:
        name: The backend name (e.g., "ollama").
        factory: A callable that returns a BaseEmbeddingGenerator instance.
    """
    if name in _embedding_backends:
        logger.warning("Embedding backend '%s' already registered, overwriting", name)
    _embedding_backends[name] = factory
    logger.debug("Registered embedding backend: %s", name)


def get_embedding_backend(name: str) -> Callable | None:
    """Get the factory function for a registered embedding backend.

    Args:
        name: The backend name to look up.

    Returns:
        The factory callable, or None if not found.
    """
    return _embedding_backends.get(name)


def list_embedding_backends() -> list:
    """List all registered embedding backend names.

    Returns:
        List of registered backend names.
    """
    return list(_embedding_backends.keys())


def unregister_embedding_backend(name: str) -> bool:
    """Unregister an embedding backend.

    Args:
        name: The backend name to unregister.

    Returns:
        True if the backend was found and unregistered, False otherwise.
    """
    if name in _embedding_backends:
        del _embedding_backends[name]
        logger.debug("Unregistered embedding backend: %s", name)
        return True
    return False
