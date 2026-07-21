from typing import Optional

from .store import AbstractSidecarStore
from .database import FeaturesDatabase, DatabaseSidecarStore

__all__ = ["AbstractSidecarStore", "DatabaseSidecarStore", "get_writer", "FeaturesDatabase"]

_default_writer: Optional[DatabaseSidecarStore] = None


def get_writer() -> AbstractSidecarStore:
    """Return the module-level singleton DatabaseSidecarStore instance."""
    global _default_writer
    if _default_writer is None:
        _default_writer = DatabaseSidecarStore()
    return _default_writer
