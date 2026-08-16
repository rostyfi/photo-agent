from importlib import import_module

from plugins.llm.registry import get_backend, list_backends
from src.interfaces import BasePhotoExtractor

_backends_loaded = False


def _ensure_backends_loaded():
    """Auto-discover and import LLM backend packages under ``plugins.llm.backends``."""
    global _backends_loaded
    if _backends_loaded:
        return
    _backends_loaded = True

    import pkgutil

    import plugins.llm.backends

    for _, name, is_pkg in pkgutil.iter_modules(plugins.llm.backends.__path__, plugins.llm.backends.__name__ + "."):
        if is_pkg:
            try:
                import_module(name)
            except Exception:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning("Failed to load LLM backend %s", name, exc_info=True)


def create_extractor(backend: str = "ollama", **kwargs) -> BasePhotoExtractor:
    """Create and return an LLM extractor by backend name.

    Discovers registered backends automatically. Raises ValueError if the
    requested backend is unknown.
    """
    _ensure_backends_loaded()

    factory = get_backend(backend)
    if factory is None:
        available = list_backends()
        raise ValueError(f"Unknown LLM backend: {backend!r}. Available: {available}")

    return factory(**kwargs)
