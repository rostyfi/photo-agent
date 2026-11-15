"""Processed-image cache shared by discovery and the processing tracker.

Extracted from ``src.discovery`` to break the circular dependency between
``src.discovery`` (which imports ``SimpleProcessingTracker``) and
``src.simple_processing_tracker`` (which needs to invalidate the cache
after marking images as processed).
"""

import logging
from pathlib import Path

from src.sidecar.database import FeaturesDatabase

logger = logging.getLogger(__name__)

# module-level cache: folder -> (cache_key, processed_set)
_PROCESSED_SET_CACHE: dict[str, tuple[tuple, set[str]]] = {}


def _db_cache_key(image_dir: str) -> tuple:
    """Return a cache key that changes if any data source is created,
    deleted, or modified.

    Note: In WAL mode, SQLite writes go to a separate -wal file, so we need
    to check both the main database file and the WAL file for changes.
    """
    key_parts = []
    db_path = FeaturesDatabase.default_db_path(image_dir)

    # Check both possible paths (they should be the same, but check both for safety)
    paths_to_check = [
        db_path,
        Path(image_dir) / ".local-photo-agent" / "features.db",
        # Also check WAL files for WAL mode databases
        Path(str(db_path) + "-wal"),
        Path(image_dir) / ".local-photo-agent" / "features.db-wal",
    ]

    for p in paths_to_check:
        try:
            if p.exists():
                st = p.stat()
                key_parts.append((str(p), True, st.st_mtime, st.st_size))
            else:
                key_parts.append((str(p), False, 0, 0))
        except OSError:
            key_parts.append((str(p), False, 0, 0))
    return tuple(key_parts)


def clear_processed_cache(image_dir: str) -> None:
    """Remove cached processed-set data for a folder, forcing a re-read."""
    _PROCESSED_SET_CACHE.pop(image_dir, None)


def get_cached_processed_set(image_dir: str) -> tuple[tuple, set[str]] | None:
    """Return the cached ``(cache_key, processed_set)`` for *image_dir*, or None."""
    return _PROCESSED_SET_CACHE.get(image_dir)


def store_cached_processed_set(image_dir: str, cache_key: tuple, processed: set[str]) -> None:
    """Store *processed* under *cache_key* for *image_dir*."""
    _PROCESSED_SET_CACHE[image_dir] = (cache_key, processed)
