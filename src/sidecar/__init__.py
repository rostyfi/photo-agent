from .database import DatabaseSidecarStore, FeaturesDatabase
from .store import AbstractSidecarStore

__all__ = ["AbstractSidecarStore", "DatabaseSidecarStore", "FeaturesDatabase", "get_writer"]

_default_writer: DatabaseSidecarStore | None = None


def get_writer() -> AbstractSidecarStore:
    """Return the module-level singleton DatabaseSidecarStore instance."""
    global _default_writer
    if _default_writer is None:
        _default_writer = DatabaseSidecarStore()
    return _default_writer
