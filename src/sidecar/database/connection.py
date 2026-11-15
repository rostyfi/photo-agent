"""Database connection and schema management mixin for FeaturesDatabase."""

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.sqlite_utils import open_connection

logger = logging.getLogger(__name__)


class DatabaseConnectionMixin:
    """Connection lifecycle and schema creation for the features database.

    Provides ``db_path``, connection management (``get_connection``,
    ``_connect``, ``close``), schema initialisation (``_ensure_schema``,
    ``init_db``), and the shared ``_to_text`` helper.
    """

    db_path: Path
    _conn: sqlite3.Connection | None
    _fts5_available: bool
    _vector_initialized: bool

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._fts5_available: bool = True
        self._vector_initialized: bool = False

    @staticmethod
    def default_db_path(folder: str | Path) -> Path:
        """Return the default features.db path for a given folder.

        The database is placed inside ``.local-photo-agent/`` to match the
        existing per-folder convention used by sidecars and the processing tracker.
        """
        return Path(folder) / ".local-photo-agent" / "features.db"

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection as a context manager.

        This ensures proper connection lifecycle management (opening, setup, closing).

        Yields:
            An open SQLite connection with WAL mode, foreign keys, and extension loading enabled.
        """
        conn = open_connection(self.db_path, enable_extensions=True)
        try:
            # Ensure schema exists
            self._ensure_schema(conn)
            yield conn
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection with WAL mode and thread safety.

        Note: Prefer using get_connection() context manager for automatic cleanup.
        """
        conn = open_connection(self.db_path, enable_extensions=True)
        # Ensure schema exists on first connection
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create all tables and indexes from scratch."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL UNIQUE,
                model_output TEXT,
                success INTEGER,
                model TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_features_image_path ON raw_features(image_path)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extracted_features (
                image_path TEXT PRIMARY KEY,
                description TEXT,
                subjects TEXT,
                objects TEXT,
                colors TEXT,
                setting TEXT,
                mood TEXT,
                tags TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_tags (
                image_path TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (image_path, tag)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feature_tags_tag ON feature_tags(tag)")

        if self._fts5_available is not False:
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS extracted_features_fts USING fts5(
                        description, subjects, objects, colors, setting, mood, tags,
                        content='extracted_features',
                        content_rowid='rowid'
                    )
                    """
                )
                self._fts5_available = True
            except sqlite3.OperationalError as e:
                error_text = str(e).lower()
                if "fts5" in error_text or "no such module" in error_text:
                    logger.warning("FTS5 is not available in this SQLite build. Full-text search disabled.")
                    self._fts5_available = False
                else:
                    raise

        # Create image_embeddings table for storing embedding metadata
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS image_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                model_name TEXT NOT NULL,
                embedding_dimension INTEGER NOT NULL,
                embedding_blob BLOB,
                created_at TEXT NOT NULL,
                UNIQUE(image_path, model_name)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_embeddings_path ON image_embeddings(image_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_embeddings_model ON image_embeddings(model_name)")

        # Create image_metadata table for storing image metadata (EXIF, etc.)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS image_metadata (
                image_path TEXT PRIMARY KEY,
                file_name TEXT,
                file_size_bytes INTEGER,
                file_extension TEXT,
                width INTEGER,
                height INTEGER,
                aspect_ratio REAL,
                make TEXT,
                model TEXT,
                camera_serial TEXT,
                lens_make TEXT,
                lens_model TEXT,
                exposure_time TEXT,
                f_number TEXT,
                iso_speed INTEGER,
                focal_length TEXT,
                focal_length_35mm TEXT,
                aperture_value TEXT,
                date_taken TEXT,
                date_created TEXT,
                date_modified TEXT,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                gps_precision TEXT,
                location_name TEXT,
                color_space TEXT,
                bits_per_sample INTEGER,
                orientation TEXT,
                software TEXT,
                copyright TEXT,
                artist TEXT,
                image_description TEXT,
                title TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_metadata_path ON image_metadata(image_path)")

        conn.commit()

    @staticmethod
    def _to_text(value) -> str | None:
        """Coerce a parsed field to a flat TEXT value."""
        if value is None:
            return None
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v is not None)
        return str(value)

    def init_db(self) -> sqlite3.Connection:
        """Open or create the features database, ensuring the schema exists.

        Returns:
            An open ``sqlite3.Connection`` with the schema initialised.
            The caller is responsible for closing the connection.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()
        logger.info("Features database ready at %s", self.db_path)
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
