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

Vector search operations are handled directly by FeaturesDatabase.
"""

import json
import logging
import sqlite3
import struct
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union, List, Tuple, Optional, Dict, Generator

from src.constants import VEC_REQUIRED
from src.sidecar.store import AbstractSidecarStore

logger = logging.getLogger(__name__)

# Vector table name
TABLE_VEC_EMBEDDINGS = "vec_embeddings"

# Fixed dimension for the vec0 virtual table. Stored and query vectors are
# padded/truncated to this size. For cosine similarity, zero-padding is
# mathematically harmless (it adds nothing to the dot product or magnitude),
# so models with smaller dimensions (e.g. nomic-embed-text at 768) search
# correctly. The value must match the dimension used at table creation.
VEC_TABLE_DIMENSION = 2048


class FeaturesDatabase:
    """SQLite features database for Local Photo Agent.

    Stores extraction results in the ``raw_features`` table and maintains
    normalised ``extracted_features``, ``feature_tags``, and an optional
    FTS5 index for fast content search. The schema is created from scratch
    on first use (no migrations).

    Vector embedding support:
    - Stores embeddings in image_embeddings table (metadata)
    - Uses vector search library (sqlite-vec) virtual table for fast vector search
    - Vector search library is a HARD REQUIREMENT for vector search functionality
    - Vectors are stored as binary BLOBs for efficiency
    - Embeddings are NOT stored in sidecar JSON files (SQLite only)
    
    Vector search operations are handled directly by FeaturesDatabase.
    """

    # =========================================================================
    # Vector Utility Methods (Static)
    # These are simple utilities that don't require sqlite-vec
    # =========================================================================
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors.
        
        Cosine similarity is the cosine of the angle between two vectors.
        Range: [-1, 1] where 1 = identical, 0 = orthogonal, -1 = opposite.
        
        Args:
            vec1: First vector (list of floats)
            vec2: Second vector (list of floats)
            
        Returns:
            Cosine similarity score in range [-1, 1]
            
        Raises:
            ValueError: If vectors have different dimensions or are empty
        """
        import math
        if not vec1 or not vec2:
            raise ValueError("Vectors cannot be empty")
        if len(vec1) != len(vec2):
            raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")
        
        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Magnitudes
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        
        # Avoid division by zero
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        similarity = dot_product / (mag1 * mag2)
        
        # Clamp to valid range due to floating point precision
        similarity = max(-1.0, min(1.0, similarity))
        
        return similarity

    @staticmethod
    def vector_to_blob(vector: List[float]) -> bytes:
        """Convert a vector (list of floats) to binary BLOB format.
        
        Each float is stored as 4 bytes (32-bit IEEE 754).
        This is compatible with sqlite-vec's raw bytes format.
        
        Args:
            vector: List of floats representing the embedding vector.
            
        Returns:
            Binary BLOB containing the vector data.
            
        Raises:
            ValueError: If vector is empty.
        """
        if not vector:
            raise ValueError("Vector cannot be empty")
        return b"".join(struct.pack("!f", float(val)) for val in vector)
    
    @staticmethod
    def blob_to_vector(blob: bytes, dimension: int) -> List[float]:
        """Convert a binary BLOB back to a vector (list of floats).
        
        Args:
            blob: Binary BLOB containing the vector data.
            dimension: Expected dimension of the vector.
            
        Returns:
            List of floats representing the embedding vector.
            
        Raises:
            ValueError: If BLOB size doesn't match expected dimension.
        """
        if len(blob) != dimension * 4:
            raise ValueError(
                f"BLOB size {len(blob)} doesn't match expected dimension "
                f"{dimension} (need {dimension * 4} bytes)"
            )
        return [struct.unpack("!f", blob[i:i+4])[0] for i in range(0, len(blob), 4)]

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._fts5_available: bool = True
        self._vector_initialized: bool = False

    @staticmethod
    def default_db_path(folder: Union[str, Path]) -> Path:
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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error:
                logger.warning("Could not set WAL journal mode on %s", self.db_path)
            # Enable loading extensions (required for vector search library)
            try:
                conn.enable_load_extension(True)
                logger.debug("Extension loading enabled for connection")
            except sqlite3.Error as e:
                logger.debug("Could not enable extension loading: %s", e)
            try:
                conn.execute("PRAGMA recursive_triggers = ON")
            except sqlite3.Error:
                pass
            # Ensure schema exists
            self._ensure_schema(conn)
            yield conn
        finally:
            conn.close()
    
    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection with WAL mode and thread safety.
        
        Note: Prefer using get_connection() context manager for automatic cleanup.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            logger.warning("Could not set WAL journal mode on %s", self.db_path)
        # Enable loading extensions (required for vector search library)
        try:
            conn.enable_load_extension(True)
            logger.debug("Extension loading enabled for connection")
        except sqlite3.Error as e:
            logger.debug("Could not enable extension loading: %s", e)
        try:
            conn.execute("PRAGMA recursive_triggers = ON")
        except sqlite3.Error:
            pass
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
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_features_image_path ON raw_features(image_path)"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_tags_tag ON feature_tags(tag)"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_embeddings_path ON image_embeddings(image_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_embeddings_model ON image_embeddings(model_name)"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_metadata_path ON image_metadata(image_path)"
        )

        conn.commit()

    @staticmethod
    def _to_text(value) -> Optional[str]:
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
    


    def init_vector_search(self) -> None:
        """Initialize vector search support.

        This method MUST be called before using vector search operations.
        It loads the sqlite-vec extension and creates the embeddings virtual table.

        Vector search library (sqlite-vec) is a HARD REQUIREMENT. If it's not available, this method will
        raise a RuntimeError with installation instructions.

        Raises:
            RuntimeError: If vector search library is not available.
        """
        if self._vector_initialized:
            return

        # Check if sqlite-vec is available
        if not self._check_sqlite_vec_available():
            raise RuntimeError(
                f"Vector search library (sqlite-vec) is a HARD REQUIREMENT for vector search. "
                f"Please install it with: pip install sqlite-vec"
            )

        with self.get_connection() as conn:
            # Load the extension
            self._ensure_extension_loaded(conn)
            # Create the virtual table
            self._create_vec_table(conn)
            self._vector_initialized = True
    
    def _check_sqlite_vec_available(self) -> bool:
        """Check if sqlite-vec is installed."""
        try:
            import sqlite_vec
            return True
        except ImportError:
            return False
    
    def _ensure_extension_loaded(self, conn: sqlite3.Connection) -> None:
        """Ensure the sqlite-vec extension is loaded on the connection."""
        try:
            conn.enable_load_extension(True)
        except sqlite3.Error as e:
            raise RuntimeError(
                f"Vector search extension loading is not authorized: {e}. "
                f"This usually means the SQLite library was not compiled with "
                f"extension loading support."
            )
        
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
        except Exception as e:
            # Try manual loading
            try:
                import sqlite_vec
                vec0_path = sqlite_vec.loadable_path()
                if not vec0_path.endswith('.so'):
                    vec0_path += '.so'
                if not Path(vec0_path).exists():
                    vec0_path = Path(sqlite_vec.__file__).parent / 'vec0.so'
                conn.load_extension(str(vec0_path))
            except Exception as e2:
                raise RuntimeError(
                    f"Failed to load vector search extension: {e2}. "
                    f"Vector search library (sqlite-vec) is a HARD REQUIREMENT."
                )
    
    def _create_vec_table(self, conn: sqlite3.Connection) -> None:
        """Create the vec_embeddings virtual table for sqlite-vec."""
        # Check if table already exists
        result = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='vec_embeddings'"
        ).fetchone()
        
        if result:
            return
        
        # Try to drop any existing table first for compatibility
        try:
            conn.execute("DROP TABLE IF EXISTS vec_embeddings")
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass
        
        # Create vec0 virtual table
        try:
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE vec_embeddings USING vec0(
                    image_path TEXT,
                    embedding float[{VEC_TABLE_DIMENSION}]
                )
                """
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "already exists" not in error_msg:
                raise RuntimeError(
                    f"Failed to create vec_embeddings table: {e}. "
                    f"Vector search library (sqlite-vec) is a HARD REQUIREMENT."
                )
    
    def _format_vector_for_vec(self, vector: List[float]) -> str:
        """Format a vector for sqlite-vec."""
        return "[" + ", ".join(f"{v:.15g}" for v in vector) + "]"

    @staticmethod
    def _normalize_vector(vector: List[float]) -> List[float]:
        """Pad or truncate a vector to ``VEC_TABLE_DIMENSION``.

        Cosine similarity is invariant to zero-padding, so padding shorter
        vectors with zeros preserves correct search results while satisfying
        the vec0 table's fixed dimension.
        """
        dim = VEC_TABLE_DIMENSION
        if len(vector) < dim:
            padded = vector + [0.0] * (dim - len(vector))
            logger.warning(f"Padding vector from {len(vector)} to {dim} dimensions")
            return padded
        if len(vector) > dim:
            truncated = vector[:dim]
            logger.warning(f"Truncating vector from {len(vector)} to {dim} dimensions")
            return truncated
        return vector
    
    def save_to_vec_table(
        self, 
        conn: sqlite3.Connection, 
        image_path: str, 
        vector: List[float]
    ) -> bool:
        """Save a vector to the vec_embeddings virtual table."""
        # Check if table exists
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_embeddings'"
        ).fetchone()
        
        if not result:
            logger.warning("vec_embeddings table does not exist")
            return False

        # The vec0 extension must be loaded on this connection to operate on
        # the virtual table (each connection loads extensions independently).
        self._ensure_extension_loaded(conn)

        # Pad or truncate to the fixed vec0 table dimension
        vector_padded = self._normalize_vector(vector)

        vector_str = self._format_vector_for_vec(vector_padded)

        # Check if entry already exists (parameterized to avoid SQL injection)
        existing = conn.execute(
            "SELECT 1 FROM vec_embeddings WHERE image_path = ?", (image_path,)
        ).fetchone()

        try:
            if existing:
                conn.execute(
                    "UPDATE vec_embeddings SET embedding = ? "
                    "WHERE image_path = ?",
                    (vector_str, image_path),
                )
            else:
                conn.execute(
                    "INSERT INTO vec_embeddings (image_path, embedding) "
                    "VALUES (?, ?)",
                    (image_path, vector_str),
                )
            conn.commit()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.warning(f"Failed to save to vec_embeddings for %s: %s", image_path, e)
            return False
    
    def delete_from_vec_table(
        self, 
        conn: sqlite3.Connection, 
        image_path: str
    ) -> bool:
        """Delete a vector from the vec_embeddings virtual table."""
        try:
            conn.execute(
                "DELETE FROM vec_embeddings WHERE image_path = ?", (image_path,)
            )
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to delete from vec_embeddings for %s: %s", image_path, e)
            return False
    
    def get_from_vec_table(
        self, 
        conn: sqlite3.Connection, 
        image_path: str, 
        dimension: int
    ) -> Optional[List[float]]:
        """Retrieve a vector from the vec_embeddings virtual table."""
        try:
            row = conn.execute(
                "SELECT embedding FROM vec_embeddings WHERE image_path = ?",
                (image_path,),
            ).fetchone()
            
            if row and row[0]:
                blob = row[0]
                return self.blob_to_vector(blob, dimension)
            return None
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(f"Failed to get embedding from vec_embeddings for %s: %s", image_path, e)
            return None
    
    def vec_find_similar(
        self, 
        conn: sqlite3.Connection, 
        query_vector: List[float], 
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """Find images similar to the query vector using sqlite-vec."""
        if not query_vector:
            raise ValueError("Query vector cannot be empty")

        # Normalize the query vector to the fixed vec0 table dimension so it
        # matches the dimension of the stored (padded) vectors.
        query_vector = self._normalize_vector(query_vector)
        vector_str = self._format_vector_for_vec(query_vector)
        
        try:
            cursor = conn.execute(
                """
                SELECT image_path, 1.0 - distance as similarity
                FROM vec_embeddings
                WHERE embedding MATCH ?
                ORDER BY distance ASC
                LIMIT ?
                """,
                (vector_str, limit),
            )
            
            results = []
            for row in cursor.fetchall():
                image_path = row[0]
                similarity = max(0.0, min(1.0, float(row[1])))
                results.append((image_path, similarity))
            
            return results
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Vector search failed: {e}")

    def _check_vec_available(self) -> None:
        """Check if vector search library (sqlite-vec) is available.

        Raises:
            RuntimeError: If vector search library is not available.
        """
        if not self._check_sqlite_vec_available():
            raise RuntimeError(
                f"{VEC_REQUIRED} but is not available. "
                f"Vector search operations will not work without it."
            )

    def save_extraction(self, image_path: str, result: Dict) -> None:
        """Upsert an extraction result into ``raw_features`` and normalised tables.

        Serialises the full ``result`` dict into ``model_output``, updates the
        indexed top-level columns, and mirrors the parsed data into
        ``extracted_features``, ``feature_tags``, and the FTS5 index.
        """
        with self.get_connection() as conn:
            model_output = json.dumps(result, ensure_ascii=False)
            success = 1 if result.get("success") else 0
            model = result.get("model")
            created_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO raw_features (image_path, model_output, success, model, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_path) DO UPDATE SET
                    model_output=excluded.model_output,
                    success=excluded.success,
                    model=excluded.model,
                    created_at=excluded.created_at
                """,
                (image_path, model_output, success, model, created_at),
            )

            parsed = result.get("parsed")
            if isinstance(parsed, dict):
                description = self._to_text(parsed.get("description"))
                subjects = self._to_text(parsed.get("subjects"))
                objects = self._to_text(parsed.get("objects"))
                colors = self._to_text(parsed.get("colors"))
                setting = self._to_text(parsed.get("setting"))
                mood = self._to_text(parsed.get("mood"))
                raw_tags = parsed.get("tags")
                if isinstance(raw_tags, str):
                    tags = [raw_tags]
                elif isinstance(raw_tags, list):
                    tags = [str(t) for t in raw_tags if t is not None]
                else:
                    tags = []
            else:
                description = subjects = objects = colors = setting = mood = None
                tags = []

            updated_at = datetime.now(timezone.utc).isoformat()
            tags_str = " ".join(tags)
            conn.execute(
                """
                INSERT INTO extracted_features (image_path, description, subjects, objects, colors, setting, mood, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_path) DO UPDATE SET
                    description=excluded.description,
                    subjects=excluded.subjects,
                    objects=excluded.objects,
                    colors=excluded.colors,
                    setting=excluded.setting,
                    mood=excluded.mood,
                    tags=excluded.tags,
                    updated_at=excluded.updated_at
                """,
                (image_path, description, subjects, objects, colors, setting, mood, tags_str, updated_at),
            )

            conn.execute("DELETE FROM feature_tags WHERE image_path = ?", (image_path,))
            for tag in tags:
                if tag:
                    conn.execute(
                        "INSERT INTO feature_tags (image_path, tag) VALUES (?, ?)",
                        (image_path, tag),
                    )

            if self._fts5_available:
                row = conn.execute(
                    "SELECT rowid FROM extracted_features WHERE image_path = ?", (image_path,)
                ).fetchone()
                if row:
                    rowid = row[0]
                    try:
                        conn.execute(
                            "INSERT INTO extracted_features_fts (extracted_features_fts, rowid) VALUES ('delete', ?)",
                            (rowid,),
                        )
                    except sqlite3.DatabaseError:
                        pass
                    conn.execute(
                        """
                        INSERT INTO extracted_features_fts (rowid, description, subjects, objects, colors, setting, mood, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (rowid, description or "", subjects or "", objects or "", colors or "", setting or "", mood or "", tags_str),
                    )

            conn.commit()

    def get_extraction(self, image_path: str) -> Optional[Dict]:
        """Read a single row by ``image_path`` and deserialise ``model_output``."""
        if not self.db_path.exists():
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT model_output FROM raw_features WHERE image_path = ?",
                (image_path,),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None

    def is_processed(self, image_path: str) -> bool:
        """Lightweight existence check for a given image path."""
        if not self.db_path.exists():
            return False
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM raw_features WHERE image_path = ?",
                (image_path,),
            ).fetchone()
            return row is not None

    def list_extractions(self) -> List[Dict]:
        """Return all rows, deserialising ``model_output`` back to dicts."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT model_output FROM raw_features").fetchall()
            return [json.loads(r[0]) for r in rows if r[0]]

    def execute_query(self, sql: str) -> Tuple[List[str], List[Tuple]]:
        """Execute a read-only SQL query and return column names plus rows.

        Raises:
            FileNotFoundError: If the database file does not exist.
            sqlite3.Error: If the query is malformed or execution fails.
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        with self.get_connection() as conn:
            # Enforce read-only mode to prevent destructive statements
            # (DELETE/DROP/UPDATE) coming from the SQL explorer UI.
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return columns, rows

    def search_features(self, query: str, limit: int = 50) -> List[Dict]:
        """Full-text search over normalised feature columns and tags."""
        if not self.db_path.exists() or not self._fts5_available:
            return []
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    e.image_path,
                    e.description,
                    e.subjects,
                    e.objects,
                    e.colors,
                    e.setting,
                    e.mood,
                    GROUP_CONCAT(t.tag, ', ') AS tags
                FROM extracted_features_fts f
                JOIN extracted_features e ON e.rowid = f.rowid
                LEFT JOIN feature_tags t ON e.image_path = t.image_path
                WHERE extracted_features_fts MATCH ?
                GROUP BY e.image_path
                LIMIT ?
                """,
                (query, limit),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_features_by_tag(self, tag: str) -> List[Dict]:
        """Return normalised features for images that have a given tag."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    e.image_path,
                    e.description,
                    e.subjects,
                    e.objects,
                    e.colors,
                    e.setting,
                    e.mood,
                    GROUP_CONCAT(t2.tag, ', ') AS tags
                FROM extracted_features e
                JOIN feature_tags t ON e.image_path = t.image_path
                LEFT JOIN feature_tags t2 ON e.image_path = t2.image_path
                WHERE t.tag = ?
                GROUP BY e.image_path
                """,
                (tag,),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_features_by_tags(self, tags: List[str]) -> List[Dict]:
        """Return normalised features for images that have ALL of the given tags.

        Uses an intersection query with ``HAVING COUNT(DISTINCT tag) = N``
        to enforce **AND** semantics. Comparisons are case-insensitive.
        """
        if not tags:
            return []
        if not self.db_path.exists():
            return []
        placeholders = ", ".join("?" for _ in tags)
        lower_tags = [t.lower() for t in tags]
        with self.get_connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT
                    e.image_path,
                    e.description,
                    e.subjects,
                    e.objects,
                    e.colors,
                    e.setting,
                    e.mood,
                    GROUP_CONCAT(t2.tag, ', ') AS tags
                FROM extracted_features e
                JOIN feature_tags t ON e.image_path = t.image_path
                LEFT JOIN feature_tags t2 ON e.image_path = t2.image_path
                WHERE LOWER(t.tag) IN ({placeholders})
                GROUP BY e.image_path
                HAVING COUNT(DISTINCT LOWER(t.tag)) = ?
                """,
                (*lower_tags, len(tags)),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_tag_frequencies(self, limit: int = 100) -> List[Tuple[str, int]]:
        """Return tag names with occurrence counts, ordered by frequency desc."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT tag, COUNT(*) as count
                FROM feature_tags
                GROUP BY tag
                ORDER BY count DESC, tag COLLATE NOCASE
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [(row[0], row[1]) for row in rows if row[0]]

    def list_tag_frequencies_restricted(self, selected_tags: List[str], limit: int = 100) -> List[Tuple[str, int]]:
        """Return tag frequencies for tags that co-occur with ALL selected tags.

        Returns only tags from photos that contain every tag in
        ``selected_tags``, excluding those already selected.
        """
        if not selected_tags:
            return self.list_tag_frequencies(limit=limit)
        if not self.db_path.exists():
            return []

        lower_tags = [t.lower() for t in selected_tags]
        placeholders = ", ".join("?" for _ in lower_tags)
        exclude_placeholders = ", ".join("?" for _ in lower_tags)

        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT t.tag, COUNT(*) as count
                FROM feature_tags t
                WHERE t.image_path IN (
                    SELECT e.image_path
                    FROM extracted_features e
                    JOIN feature_tags ft ON e.image_path = ft.image_path
                    WHERE LOWER(ft.tag) IN ({placeholders})
                    GROUP BY e.image_path
                    HAVING COUNT(DISTINCT LOWER(ft.tag)) = ?
                )
                AND LOWER(t.tag) NOT IN ({exclude_placeholders})
                GROUP BY t.tag
                ORDER BY count DESC, t.tag COLLATE NOCASE
                LIMIT ?
                """,
                (*lower_tags, len(lower_tags), *lower_tags, limit),
            ).fetchall()
            return [(row[0], row[1]) for row in rows if row[0]]

    def list_all_tags(self) -> List[str]:
        """Return all distinct tags in the database, sorted case-insensitively."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT tag FROM feature_tags ORDER BY tag COLLATE NOCASE"
            ).fetchall()
            return [row[0] for row in rows if row[0]]

    def get_feature_summary(self, image_path: str) -> Optional[Dict]:
        """Return a joined view of raw and normalised data for a single image."""
        if not self.db_path.exists():
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    r.image_path,
                    r.model_output,
                    r.success,
                    r.model,
                    r.created_at,
                    e.description,
                    e.subjects,
                    e.objects,
                    e.colors,
                    e.setting,
                    e.mood,
                    e.tags
                FROM raw_features r
                LEFT JOIN extracted_features e ON r.image_path = e.image_path
                WHERE r.image_path = ?
                """,
                (image_path,),
            ).fetchone()
            if not row:
                return None
            tags = [
                r[0]
                for r in conn.execute(
                    "SELECT tag FROM feature_tags WHERE image_path = ?", (image_path,)
                ).fetchall()
            ]
            result = {
                "image_path": row[0],
                "model_output": json.loads(row[1]) if row[1] else None,
                "success": bool(row[2]),
                "model": row[3],
                "created_at": row[4],
                "description": row[5],
                "subjects": row[6],
                "objects": row[7],
                "colors": row[8],
                "setting": row[9],
                "mood": row[10],
                "tags": tags,
            }
            
            # Include metadata if available
            logger.debug("About to query metadata for %s in %s", image_path, self.db_path)
            metadata = self.get_metadata(image_path)
            if metadata:
                logger.info("Found metadata for %s (keys: %s) in %s", image_path, list(metadata.keys()), self.db_path)
                result["metadata"] = metadata
            else:
                # Fallback: try to extract metadata on-the-fly if not in database
                logger.warning("No metadata in DB for %s, trying on-the-fly extraction", image_path)
                try:
                    from src.metadata import extract_metadata_dict
                    fallback_metadata = extract_metadata_dict(image_path)
                    if fallback_metadata:
                        logger.info("Fallback: Extracted metadata on-the-fly for %s (keys: %s)", 
                                   image_path, list(fallback_metadata.keys()))
                        result["metadata"] = fallback_metadata
                        # Also save it to database for future use
                        try:
                            self.save_metadata(image_path, fallback_metadata)
                            logger.info("Fallback: Saved on-the-fly metadata to DB for %s", image_path)
                        except Exception as e:
                            logger.error("Fallback: Failed to save on-the-fly metadata for %s: %s", 
                                       image_path, e)
                    else:
                        logger.warning("No metadata found for %s (neither in DB nor extracted)", image_path)
                except Exception as e:
                    logger.error("Failed to extract fallback metadata for %s: %s", image_path, e, exc_info=True)
            
            return result

    def save_metadata(self, image_path: str, metadata: Dict) -> None:
        """Save image metadata to the database.
        
        Args:
            image_path: Path to the image.
            metadata: Dictionary containing metadata (from src.metadata.extract_metadata_dict).
        """
        if not metadata:
            logger.debug("Not saving metadata: metadata dict is empty")
            return
            
        try:
            with self.get_connection() as conn:
                updated_at = datetime.now(timezone.utc).isoformat()
                
                # Prepare all metadata fields
                fields = [
                    "image_path", "file_name", "file_size_bytes", "file_extension",
                    "width", "height", "aspect_ratio", "make", "model", "camera_serial",
                    "lens_make", "lens_model", "exposure_time", "f_number", "iso_speed",
                    "focal_length", "focal_length_35mm", "aperture_value", "date_taken",
                    "date_created", "date_modified", "latitude", "longitude", "altitude",
                    "gps_precision", "location_name", "color_space", "bits_per_sample",
                    "orientation", "software", "copyright", "artist", "image_description",
                    "title", "updated_at"
                ]
                
                # Build placeholders
                placeholders = ", ".join(["?"] * len(fields))
                
                # Convert all values to SQLite-compatible types (handle IFDRational, etc.)
                def _convert_value(val: Any) -> Any:
                    """Convert special types to SQLite-compatible types."""
                    if val is None:
                        return None
                    # Handle IFDRational from Pillow EXIF
                    if hasattr(val, 'numerator') and hasattr(val, 'denominator'):
                        try:
                            return float(val.numerator) / float(val.denominator)
                        except (ValueError, ZeroDivisionError, TypeError):
                            return str(val)
                    # Handle tuples (already handled by metadata module, but just in case)
                    if isinstance(val, tuple) and len(val) == 2:
                        try:
                            return float(val[0]) / float(val[1])
                        except (ValueError, ZeroDivisionError, TypeError):
                            return str(val)
                    # Handle bytes
                    if isinstance(val, bytes):
                        try:
                            return val.decode('utf-8', errors='ignore')
                        except (UnicodeDecodeError, AttributeError):
                            return str(val)
                    # For lists, convert to comma-separated string
                    if isinstance(val, list):
                        return ", ".join(str(v) for v in val if v is not None)
                    return val
                
                values = [_convert_value(metadata.get(field, None)) for field in fields]
                values[-1] = updated_at  # Set updated_at
                values[0] = image_path  # Ensure image_path is set
                
                # Build SET clause for ON CONFLICT
                set_clause = ", ".join([f"{field} = excluded.{field}" for field in fields if field != "image_path"])
                
                conn.execute(
                    f"""
                    INSERT INTO image_metadata ({', '.join(fields)})
                    VALUES ({placeholders})
                    ON CONFLICT(image_path) DO UPDATE SET {set_clause}
                    """,
                    values,
                )
                conn.commit()
                logger.debug("Saved metadata for %s (keys: %s)", image_path, list(metadata.keys()))
        except Exception as e:
            logger.error("Failed to save metadata for %s: %s", image_path, e, exc_info=True)
            raise

    def get_metadata(self, image_path: str) -> Optional[Dict]:
        """Retrieve metadata for a specific image.
        
        Args:
            image_path: Path to the image.
            
        Returns:
            Dictionary containing all metadata fields, or None if not found.
        """
        if not self.db_path.exists():
            logger.debug("Database does not exist at %s", self.db_path)
            return None
            
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM image_metadata WHERE image_path = ?",
                    (image_path,),
                )
                row = cursor.fetchone()
                
                if not row:
                    logger.debug("No metadata row found for %s in %s", image_path, self.db_path)
                    return None
                
                # Get column names
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))
                logger.debug("Retrieved metadata for %s (keys: %s)", image_path, list(result.keys()))
                return result
        except Exception as e:
            logger.error("Failed to get metadata for %s: %s", image_path, e, exc_info=True)
            return None

    def get_metadata_for_display(self, image_path: str) -> Dict[str, str]:
        """Get metadata formatted for display.
        
        Args:
            image_path: Path to the image.
            
        Returns:
            Dictionary with formatted metadata suitable for UI display.
        """
        from src.metadata import ImageMetadata, format_metadata_for_display
        
        raw_metadata = self.get_metadata(image_path)
        if not raw_metadata:
            return {}
        
        # Convert to ImageMetadata object
        metadata_obj = ImageMetadata()
        for key, value in raw_metadata.items():
            if hasattr(metadata_obj, key):
                setattr(metadata_obj, key, value)
        
        return format_metadata_for_display(metadata_obj)

    def rebuild_fts_index(self) -> None:
        """Rebuild the FTS5 index from the normalised content table."""
        if not self.db_path.exists() or not self._fts5_available:
            return
        with self.get_connection() as conn:
            conn.execute("INSERT INTO extracted_features_fts(extracted_features_fts) VALUES('rebuild')")
            conn.commit()

    def save_embedding(self, image_path: str, model_name: str, vector: List[float]) -> None:
        """Save embedding to both metadata and vector index.

        Stores the embedding in both the image_embeddings table (for metadata)
        and the embeddings virtual table (for fast vector search).

        Args:
            image_path: Path to the image.
            model_name: Name of the embedding model used.
            vector: List of floats representing the embedding vector.

        Raises:
            RuntimeError: If sqlite-vec library is not available.
        """
        if not vector:
            raise ValueError("Vector cannot be empty")

        dimension = len(vector)
        created_at = datetime.now(timezone.utc).isoformat()
        blob = self.vector_to_blob(vector)

        # Always save to image_embeddings table (metadata + vector blob)
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO image_embeddings (image_path, model_name, embedding_dimension, embedding_blob, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(image_path, model_name) DO UPDATE SET
                        embedding_dimension=excluded.embedding_dimension,
                        embedding_blob=excluded.embedding_blob,
                        created_at=excluded.created_at
                    """,
                    (image_path, model_name, dimension, blob, created_at),
                )
                conn.commit()

                # Try to save to vec_embeddings table if available
                try:
                    self.save_to_vec_table(conn, image_path, vector)
                except (RuntimeError, sqlite3.OperationalError, MemoryError, sqlite3.DatabaseError) as e:
                    # sqlite-vec library not available or vec_embeddings table doesn't exist
                    # but we still saved metadata to image_embeddings table
                    logger.warning(
                        f"Failed to save to {TABLE_VEC_EMBEDDINGS} for %s: %s. Metadata saved to image_embeddings.",
                        image_path, e
                    )
                    # Don't re-raise - metadata was already saved successfully
        except sqlite3.OperationalError as e:
            logger.error("Failed to save embedding for %s: %s", image_path, e)
            raise RuntimeError(f"Failed to save embedding: {e}. {VEC_REQUIRED}")

    def get_embedding(self, image_path: str, model_name: str) -> Optional[List[float]]:
        """Retrieve embedding vector from metadata.

        Retrieves the embedding from the image_embeddings table where it's stored
        as a binary blob. This works even if vec_embeddings (vector search index) is not available.

        Args:
            image_path: Path to the image.
            model_name: Name of the embedding model.

        Returns:
            List of floats representing the embedding vector, or None if not found.
        """
        if not self.db_path.exists():
            return None

        with self.get_connection() as conn:
            # Get dimension and blob from image_embeddings table
            row = conn.execute(
                "SELECT embedding_dimension, embedding_blob FROM image_embeddings WHERE image_path = ? AND model_name = ?",
                (image_path, model_name),
            ).fetchone()

            if not row:
                return None

            dimension = row[0]
            blob = row[1]

            if not blob:
                return None

            # Convert blob back to vector
            return self.blob_to_vector(blob, dimension)

    def has_embedding(self, image_path: str, model_name: str) -> bool:
        """Check if an embedding exists for the given image and model.

        Args:
            image_path: Path to the image.
            model_name: Name of the embedding model.

        Returns:
            True if the embedding exists, False otherwise.
        """
        if not self.db_path.exists():
            return False

        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM image_embeddings WHERE image_path = ? AND model_name = ?",
                (image_path, model_name),
            ).fetchone()
            return row is not None

    def get_embedding_dimension(self, model_name: str) -> Optional[int]:
        """Get the embedding dimension for a given model.

        Args:
            model_name: Name of the embedding model.

        Returns:
            The dimension size, or None if no embeddings exist for this model.
        """
        if not self.db_path.exists():
            return None

        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT embedding_dimension FROM image_embeddings WHERE model_name = ? LIMIT 1",
                (model_name,),
            ).fetchone()
            return row[0] if row else None

    def delete_embedding(self, image_path: str, model_name: str) -> None:
        """Remove embedding from both tables.

        Args:
            image_path: Path to the image.
            model_name: Name of the embedding model.
        """
        if not self.db_path.exists():
            return

        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM image_embeddings WHERE image_path = ? AND model_name = ?",
                (image_path, model_name),
            )
            # Delete from vec_embeddings table
            self.delete_from_vec_table(conn, image_path)
            conn.commit()
            logger.debug("Deleted embedding for %s (model: %s)", image_path, model_name)

    def get_all_embeddings(self, model_name: str) -> List[Tuple[str, List[float]]]:
        """Retrieve all embeddings for a specific model.

        Args:
            model_name: Name of the embedding model.

        Returns:
            List of (image_path, vector) tuples.
            
        Note:
            This method reads embeddings from the image_embeddings table (metadata)
            and converts blobs to vectors. It does NOT require sqlite-vec.
        """
        if not self.db_path.exists():
            return []

        with self.get_connection() as conn:
            # Get all image paths, dimensions, and blobs for this model
            rows = conn.execute(
                "SELECT image_path, embedding_dimension, embedding_blob FROM image_embeddings WHERE model_name = ?",
                (model_name,),
            ).fetchall()

            results = []
            for image_path, dimension, blob in rows:
                if blob:
                    try:
                        vector = self.blob_to_vector(blob, dimension)
                        results.append((image_path, vector))
                    except (ValueError, struct.error) as e:
                        logger.warning(f"Failed to decode embedding for {image_path}: {e}")
                        continue

            return results

    def find_similar(
        self,
        query_vector: List[float],
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """Find images similar to the query vector using cosine similarity.

        Uses sqlite-vec to perform fast vector similarity search.
        Returns results sorted by similarity score (descending).

        Args:
            query_vector: The query embedding vector to search for.
            limit: Maximum number of results to return (default: 10).

        Returns:
            List of (image_path, similarity_score) tuples, sorted by score DESC.

        Raises:
            RuntimeError: If sqlite-vec library is not available.
        """
        if not query_vector:
            raise ValueError("Query vector cannot be empty")

        if not self.db_path.exists():
            return []

        # Check if vector search library is available
        try:
            self._check_vec_available()
        except RuntimeError:
            # Vector search library not available, return empty results
            from src.constants import VEC_NOT_AVAILABLE
            logger.warning(f"{VEC_NOT_AVAILABLE}. Returning empty results.")
            return []

        with self.get_connection() as conn:
            # The vec0 extension must be loaded on this connection before
            # querying the virtual table (each connection loads extensions
            # independently).
            self._ensure_extension_loaded(conn)
            # Use vec_find_similar for sqlite-vec search
            return self.vec_find_similar(conn, query_vector, limit=limit)

    def find_similar_rest(
        self,
        query_vector: List[float],
        model_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """Find images similar to the query vector using Python cosine similarity.
        
        This is a fallback method that works without sqlite-vec.
        It loads all embeddings from the database and computes cosine similarity
        in Python. Slower than sqlite-vec for large datasets but always available.
        
        Args:
            query_vector: The query embedding vector to search for.
            model_name: Optional filter by embedding model name.
            limit: Maximum number of results to return (default: 10).
            
        Returns:
            List of (image_path, similarity_score) tuples, sorted by score DESC.
            
        Raises:
            ValueError: If query_vector is empty or invalid.
        """
        if not query_vector:
            raise ValueError("Query vector cannot be empty")
        if len(query_vector) == 0:
            raise ValueError("Query vector cannot be empty")
        
        if not self.db_path.exists():
            return []
        
        # Get all embeddings from database
        embeddings = self.get_all_embeddings(model_name) if model_name else []
        
        if not embeddings:
            logger.warning("No embeddings found in database")
            return []
        
        # Compute similarity for each embedding
        results = []
        for image_path, vector in embeddings:
            try:
                # Ensure vectors are the same dimension
                if len(vector) != len(query_vector):
                    logger.warning(
                        f"Dimension mismatch for {image_path}: "
                        f"query={len(query_vector)}, stored={len(vector)}"
                    )
                    # Pad or truncate to match
                    min_dim = min(len(query_vector), len(vector))
                    q_vec = query_vector[:min_dim]
                    s_vec = vector[:min_dim]
                    similarity = self.cosine_similarity(q_vec, s_vec)
                else:
                    similarity = self.cosine_similarity(query_vector, vector)
                
                results.append((image_path, similarity))
            except Exception as e:
                logger.error(f"Failed to compute similarity for {image_path}: {e}")
                continue
        
        # Sort by similarity (descending) and take top-k
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:limit]

    def close(self) -> None:
        """Close the underlying SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class DatabaseSidecarStore(AbstractSidecarStore):
    """Write extraction results to the per-folder SQLite ``features.db``.

    Uses upserts into the ``raw_features`` table, enabling fast querying
    and concurrent reads.
    """

    def __init__(self):
        self._dbs: Dict[str, FeaturesDatabase] = {}

    def _get_db(self, image_path: str) -> FeaturesDatabase:
        folder = str(Path(image_path).parent)
        if folder not in self._dbs:
            db_path = FeaturesDatabase.default_db_path(folder)
            self._dbs[folder] = FeaturesDatabase(db_path)
        return self._dbs[folder]

    @classmethod
    def sidecar_path(cls, image_path: str) -> Path:
        """Return the expected database path for a given image."""
        return FeaturesDatabase.default_db_path(Path(image_path).parent)

    def save(self, image_path: str, result: Dict) -> str:
        """Persist an extraction result dict to the folder's features.db.

        Returns:
            The absolute path to the database file.
        """
        db = self._get_db(image_path)
        db.save_extraction(image_path, result)
        return str(db.db_path)

    def load(self, image_path: str) -> Optional[Dict]:
        """Read an extraction result for the given image from the DB."""
        db = self._get_db(image_path)
        return db.get_extraction(image_path)

    def exists(self, image_path: str) -> bool:
        """Return True if a DB row exists for the given image."""
        db = self._get_db(image_path)
        return db.is_processed(image_path)
