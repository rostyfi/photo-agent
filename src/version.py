"""Application version.

The canonical version lives in ``pyproject.toml`` (``[project].version``).
This module exposes it at runtime via :func:`get_version`, which reads the
installed package metadata when available and falls back to a literal
constant for source-checkout runs that have not been ``pip install``-ed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Fallback used when the package is not installed (e.g. ``python main.py``
# run directly from a checkout). Keep this in sync with pyproject.toml.
_FALLBACK_VERSION = "0.1.0"

try:  # pragma: no cover - exercised only when installed
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    def _resolve_version() -> str:
        try:
            return _pkg_version("local-photo-agent")
        except PackageNotFoundError:
            return _FALLBACK_VERSION
except ImportError:  # pragma: no cover - Python <3.8 guard
    def _resolve_version() -> str:
        return _FALLBACK_VERSION


__version__: str = _resolve_version()


def get_version() -> str:
    """Return the application version string."""
    return __version__
