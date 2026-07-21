from typing import Callable, Dict, Optional

from src.interfaces import BasePhotoExtractor

_backend_factories: Dict[str, Callable[..., BasePhotoExtractor]] = {}


def register_backend(name: str, factory: Callable[..., BasePhotoExtractor]) -> None:
    """Register an LLM backend factory under the given name."""
    _backend_factories[name] = factory


def get_backend(name: str) -> Optional[Callable[..., BasePhotoExtractor]]:
    """Return the factory for a registered backend, or None if not found."""
    return _backend_factories.get(name)


def list_backends() -> list:
    """Return a list of all registered backend names."""
    return list(_backend_factories.keys())
