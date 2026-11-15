"""
SQLite features database for Local Photo Agent.

Stores extraction results in the ``raw_features`` table and maintains
normalised ``extracted_features``, ``feature_tags``, and an optional
FTS5 index for fast content search. The schema is created from scratch
on first use (no migrations).

Vector embedding support:
- Stores embeddings in image_embeddings table (metadata)
- Uses sqlite-vec virtual table for fast vector search
- Vector search library (sqlite-vec) is a HARD REQUIREMENT for vector search functionality
- Vectors are stored as binary BLOBs for efficiency
- Embeddings are NOT stored in sidecar JSON files (SQLite only)

This module is the composition point: ``FeaturesDatabase`` combines four
focused mixins from sibling modules:

- ``connection.py``   — connection lifecycle, schema, init_db
- ``vectors.py``      — sqlite-vec integration, embedding CRUD, similarity search
- ``extractions.py``  — raw/extracted feature CRUD, tag queries, FTS5
- ``metadata.py``     — EXIF/IPTC/XMP metadata persistence
"""

import logging
from pathlib import Path

from src.sidecar.store import AbstractSidecarStore

from .connection import DatabaseConnectionMixin
from .extractions import ExtractionMixin
from .metadata import MetadataMixin
from .vectors import TABLE_VEC_EMBEDDINGS, VEC_TABLE_DIMENSION, VectorSearchMixin

logger = logging.getLogger(__name__)

__all__ = [
    "TABLE_VEC_EMBEDDINGS",
    "VEC_TABLE_DIMENSION",
    "DatabaseSidecarStore",
    "FeaturesDatabase",
]


class FeaturesDatabase(DatabaseConnectionMixin, VectorSearchMixin, ExtractionMixin, MetadataMixin):
    """SQLite features database for Local Photo Agent.

    Composed from four mixins (see module docstring). All methods are
    provided by the mixin classes; this class only exists to combine them.
    """


class DatabaseSidecarStore(AbstractSidecarStore):
    """Write extraction results to the per-folder SQLite ``features.db``.

    Uses upserts into the ``raw_features`` table, enabling fast querying
    and concurrent reads.
    """

    def __init__(self):
        self._dbs: dict[str, FeaturesDatabase] = {}

    def _get_db(self, image_path: str) -> FeaturesDatabase:
        folder = str(Path(image_path).parent)
        if folder not in self._dbs:
            db_path = FeaturesDatabase.default_db_path(folder)
            self._dbs[folder] = FeaturesDatabase(db_path)
        return self._dbs[folder]

    def save(self, image_path: str, result: dict) -> str:
        """Persist an extraction result dict to the folder's features.db.

        Returns:
            The absolute path to the database file.
        """
        db = self._get_db(image_path)
        db.save_extraction(image_path, result)
        return str(db.db_path)

    def load(self, image_path: str) -> dict | None:
        """Read an extraction result for the given image from the DB."""
        db = self._get_db(image_path)
        return db.get_extraction(image_path)

    def exists(self, image_path: str) -> bool:
        """Return True if a DB row exists for the given image."""
        db = self._get_db(image_path)
        return db.is_processed(image_path)
