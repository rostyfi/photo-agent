"""Extensible image format reader registry.

Format plugins call ``register_format`` at import time to register a reader
callable for one or more file extensions. The ``get_reader`` function looks
up the appropriate reader for a given suffix.
"""

from collections.abc import Callable
from pathlib import Path

_readers: dict[str, Callable[[Path], bytes]] = {}


def register_format(extensions: tuple[str, ...], reader: Callable[[Path], bytes]) -> None:
    """Register a reader callable for one or more file extensions.

    Args:
        extensions: Tuple of lowercase file extensions with leading dot
            (e.g. ``('.heic', '.heif')``).
        reader: A callable that takes a Path and returns image bytes.
    """
    for ext in extensions:
        _readers[ext.lower()] = reader


def get_reader(suffix: str) -> Callable[[Path], bytes] | None:
    """Look up the registered reader for a file suffix. Returns None if not found."""
    return _readers.get(suffix.lower())


def unregister_format(extensions: tuple[str, ...]) -> None:
    """Remove registered reader callables for the given file extensions.

    Args:
        extensions: Tuple of lowercase file extensions with leading dot
            (e.g. ``('.heic', '.heif')``).
    """
    for ext in extensions:
        _readers.pop(ext.lower(), None)
