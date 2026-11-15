"""Vector search and embedding storage mixin for FeaturesDatabase.

Contains the sqlite-vec integration (virtual table management, extension
loading) and all embedding CRUD plus similarity search methods.
"""

import logging
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.constants import VEC_REQUIRED

logger = logging.getLogger(__name__)

# Vector table name
TABLE_VEC_EMBEDDINGS = "vec_embeddings"

# Fixed dimension for the vec0 virtual table. Stored and query vectors are
# padded/truncated to this size. For cosine similarity, zero-padding is
# mathematically harmless (it adds nothing to the dot product or magnitude),
# so models with smaller dimensions (e.g. nomic-embed-text at 768) search
# correctly. The value must match the dimension used at table creation.
VEC_TABLE_DIMENSION = 2048


class VectorSearchMixin:
    """Vector search (sqlite-vec) and embedding storage for FeaturesDatabase.

    Requires the owning class to provide ``db_path``, ``get_connection()``,
    and ``_vector_initialized`` (from :class:`DatabaseConnectionMixin`).
    """

    db_path: Path
    _vector_initialized: bool

    if TYPE_CHECKING:

        def get_connection(self): ...

    # =========================================================================
    # Vector Utility Methods (Static)
    # =========================================================================

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
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
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))

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
    def vector_to_blob(vector: list[float]) -> bytes:
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
    def blob_to_vector(blob: bytes, dimension: int) -> list[float]:
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
                f"BLOB size {len(blob)} doesn't match expected dimension {dimension} (need {dimension * 4} bytes)"
            )
        return [struct.unpack("!f", blob[i : i + 4])[0] for i in range(0, len(blob), 4)]

    # =========================================================================
    # sqlite-vec Extension Management
    # =========================================================================

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
                "Vector search library (sqlite-vec) is a HARD REQUIREMENT for vector search. "
                "Please install it with: pip install sqlite-vec"
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
            import sqlite_vec  # noqa: F401

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
            ) from e

        try:
            import sqlite_vec

            sqlite_vec.load(conn)
        except Exception:
            # Try manual loading
            try:
                import sqlite_vec

                vec0_path = sqlite_vec.loadable_path()
                if not vec0_path.endswith(".so"):
                    vec0_path += ".so"
                if not Path(vec0_path).exists():
                    vec0_path = Path(sqlite_vec.__file__).parent / "vec0.so"
                conn.load_extension(str(vec0_path))
            except Exception as e2:
                raise RuntimeError(
                    f"Failed to load vector search extension: {e2}. "
                    f"Vector search library (sqlite-vec) is a HARD REQUIREMENT."
                ) from e2

    def _create_vec_table(self, conn: sqlite3.Connection) -> None:
        """Create the vec_embeddings virtual table for sqlite-vec."""
        # Check if table already exists
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_embeddings'").fetchone()

        if result:
            return

        # Try to drop any existing table first for compatibility
        try:
            conn.execute("DROP TABLE IF EXISTS vec_embeddings")
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass

        # Create vec0 virtual table. Cosine distance makes ``1 - distance`` a
        # true cosine similarity score; the model_name auxiliary column lets
        # callers restrict search to vectors from one embedding model. Tables
        # created before these options existed keep their original definition
        # (this method only creates the table when missing).
        try:
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE vec_embeddings USING vec0(
                    image_path TEXT,
                    embedding float[{VEC_TABLE_DIMENSION}] distance_metric=cosine,
                    model_name TEXT
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
                ) from e

    def _format_vector_for_vec(self, vector: list[float]) -> str:
        """Format a vector for sqlite-vec."""
        return "[" + ", ".join(f"{v:.15g}" for v in vector) + "]"

    @staticmethod
    def _normalize_vector(vector: list[float]) -> list[float]:
        """Pad or truncate a vector to ``VEC_TABLE_DIMENSION``.

        Cosine similarity is invariant to zero-padding, so padding shorter
        vectors with zeros preserves correct search results while satisfying
        the vec0 table's fixed dimension.
        """
        dim = VEC_TABLE_DIMENSION
        if len(vector) < dim:
            padded = vector + [0.0] * (dim - len(vector))
            logger.debug("Padding vector from %s to %s dimensions", len(vector), dim)
            return padded
        if len(vector) > dim:
            truncated = vector[:dim]
            logger.warning("Truncating vector from %s to %s dimensions", len(vector), dim)
            return truncated
        return vector

    @staticmethod
    def _vec_table_has_model_column(conn: sqlite3.Connection) -> bool:
        """Return True if the vec_embeddings table has a ``model_name`` column.

        Tables created before the model column existed only store
        ``image_path`` and ``embedding``; writes and filters must adapt.
        """
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(vec_embeddings)")}
        except sqlite3.DatabaseError:
            return False
        return "model_name" in columns

    def save_to_vec_table(
        self, conn: sqlite3.Connection, image_path: str, vector: list[float], model_name: str | None = None
    ) -> bool:
        """Save a vector to the vec_embeddings virtual table.

        The table holds at most one (latest) vector per image so that rows
        from different embedding models never mix: when the table has a
        ``model_name`` column, existing rows for the image are replaced and
        the row is tagged with the producing model.
        """
        # Check if table exists
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_embeddings'").fetchone()

        if not result:
            logger.warning("vec_embeddings table does not exist")
            return False

        # The vec0 extension must be loaded on this connection to operate on
        # the virtual table (each connection loads extensions independently).
        self._ensure_extension_loaded(conn)

        # Pad or truncate to the fixed vec0 table dimension
        vector_padded = self._normalize_vector(vector)

        vector_str = self._format_vector_for_vec(vector_padded)

        has_model_column = self._vec_table_has_model_column(conn)

        try:
            if has_model_column:
                # One row per image: drop stale rows (e.g. written by another
                # embedding model), then insert the current vector.
                conn.execute("DELETE FROM vec_embeddings WHERE image_path = ?", (image_path,))
                conn.execute(
                    "INSERT INTO vec_embeddings (image_path, embedding, model_name) VALUES (?, ?, ?)",
                    (image_path, vector_str, model_name),
                )
            else:
                # Legacy table without the model column (parameterized to
                # avoid SQL injection).
                existing = conn.execute("SELECT 1 FROM vec_embeddings WHERE image_path = ?", (image_path,)).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE vec_embeddings SET embedding = ? WHERE image_path = ?",
                        (vector_str, image_path),
                    )
                else:
                    conn.execute(
                        "INSERT INTO vec_embeddings (image_path, embedding) VALUES (?, ?)",
                        (image_path, vector_str),
                    )
            conn.commit()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.warning("Failed to save to vec_embeddings for %s: %s", image_path, e)
            return False

    def delete_from_vec_table(self, conn: sqlite3.Connection, image_path: str) -> bool:
        """Delete a vector from the vec_embeddings virtual table."""
        try:
            conn.execute("DELETE FROM vec_embeddings WHERE image_path = ?", (image_path,))
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            logger.error("Failed to delete from vec_embeddings for %s: %s", image_path, e)
            return False

    def vec_find_similar(
        self,
        conn: sqlite3.Connection,
        query_vector: list[float],
        limit: int = 10,
        model_name: str | None = None,
    ) -> list[tuple[str, float]]:
        """Find images similar to the query vector using sqlite-vec.

        Args:
            conn: Open connection with the sqlite-vec extension loaded.
            query_vector: The query embedding vector to search for.
            limit: Maximum number of results.
            model_name: Optional embedding model to restrict results to. Only
                applied when the vec_embeddings table has a ``model_name``
                column; vectors from other models are not comparable anyway.
        """
        if not query_vector:
            raise ValueError("Query vector cannot be empty")

        # Normalize the query vector to the fixed vec0 table dimension so it
        # matches the dimension of the stored (padded) vectors.
        query_vector = self._normalize_vector(query_vector)
        vector_str = self._format_vector_for_vec(query_vector)

        # With the cosine distance metric, ``1 - distance`` is the cosine
        # similarity. Legacy tables use L2 distance, where the value is only
        # a monotone score, not a true similarity.
        sql = """
            SELECT image_path, 1.0 - distance as similarity
            FROM vec_embeddings
            WHERE embedding MATCH ?
        """
        params: list = [vector_str]
        if model_name is not None and self._vec_table_has_model_column(conn):
            sql += " AND model_name = ?"
            params.append(model_name)
        sql += " ORDER BY distance ASC LIMIT ?"
        params.append(limit)

        try:
            cursor = conn.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                image_path = row[0]
                similarity = max(0.0, min(1.0, float(row[1])))
                results.append((image_path, similarity))

            return results
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Vector search failed: {e}") from e

    def _check_vec_available(self) -> None:
        """Check if vector search library (sqlite-vec) is available.

        Raises:
            RuntimeError: If vector search library is not available.
        """
        if not self._check_sqlite_vec_available():
            raise RuntimeError(
                f"{VEC_REQUIRED} but is not available. Vector search operations will not work without it."
            )

    # =========================================================================
    # Embedding CRUD
    # =========================================================================

    def save_embedding(self, image_path: str, model_name: str, vector: list[float]) -> None:
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
                    self.save_to_vec_table(conn, image_path, vector, model_name=model_name)
                except (RuntimeError, sqlite3.OperationalError, MemoryError, sqlite3.DatabaseError) as e:
                    # sqlite-vec library not available or vec_embeddings table doesn't exist
                    # but we still saved metadata to image_embeddings table
                    logger.warning(
                        "Failed to save to %s for %s: %s. Metadata saved to image_embeddings.",
                        TABLE_VEC_EMBEDDINGS,
                        image_path,
                        e,
                    )
                    # Don't re-raise - metadata was already saved successfully
        except sqlite3.OperationalError as e:
            logger.error("Failed to save embedding for %s: %s", image_path, e)
            raise RuntimeError(f"Failed to save embedding: {e}. {VEC_REQUIRED}") from e

    def get_embedding(self, image_path: str, model_name: str) -> list[float] | None:
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

    def get_all_embeddings(self, model_name: str | None = None) -> list[tuple[str, list[float]]]:
        """Retrieve embeddings, optionally restricted to one model.

        Args:
            model_name: Name of the embedding model to filter by. When
                ``None``, embeddings for all models are returned.

        Returns:
            List of (image_path, vector) tuples.

        Note:
            This method reads embeddings from the image_embeddings table (metadata)
            and converts blobs to vectors. It does NOT require sqlite-vec.
        """
        if not self.db_path.exists():
            return []

        with self.get_connection() as conn:
            # Get all image paths, dimensions, and blobs (optionally per model)
            if model_name is not None:
                rows = conn.execute(
                    "SELECT image_path, embedding_dimension, embedding_blob FROM image_embeddings WHERE model_name = ?",
                    (model_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT image_path, embedding_dimension, embedding_blob FROM image_embeddings"
                ).fetchall()

            results = []
            for image_path, dimension, blob in rows:
                if blob:
                    try:
                        vector = self.blob_to_vector(blob, dimension)
                        results.append((image_path, vector))
                    except (ValueError, struct.error) as e:
                        logger.warning("Failed to decode embedding for %s: %s", image_path, e)
                        continue

            return results

    def get_embeddings_date_filtered(
        self, model_name: str | None, date_start: str, date_end: str
    ) -> list[tuple[str, list[float]]]:
        """Retrieve embeddings restricted to images taken within a date range.

        Joins ``image_embeddings`` with ``image_metadata`` and filters on the
        first available of ``date_taken``, ``date_created`` or
        ``date_modified``. EXIF dates are commonly stored as
        ``"YYYY:MM:DD HH:MM:SS"``; colons in the date portion are replaced
        with dashes so a lexicographic ``BETWEEN`` against ``YYYY-MM-DD``
        bounds works correctly. Images with no metadata row or no usable
        date are excluded.

        Args:
            model_name: Embedding model name to filter by. When ``None``,
                embeddings for all models are considered.
            date_start: Inclusive start date (``YYYY-MM-DD``).
            date_end: Inclusive end date (``YYYY-MM-DD``).

        Returns:
            List of (image_path, vector) tuples.
        """
        if not self.db_path.exists():
            return []

        with self.get_connection() as conn:
            # Normalise EXIF-style "YYYY:MM:DD ..." to "YYYY-MM-DD ..." and
            # compare only the date prefix so the time component is ignored.
            sql = """
                SELECT ie.image_path, ie.embedding_dimension, ie.embedding_blob
                FROM image_embeddings ie
                JOIN image_metadata im ON im.image_path = ie.image_path
                WHERE substr(replace(
                    COALESCE(im.date_taken, im.date_created, im.date_modified),
                    ':', '-'), 1, 10) BETWEEN ? AND ?
            """
            params: list = [date_start, date_end]
            if model_name is not None:
                sql += " AND ie.model_name = ?"
                params.append(model_name)
            rows = conn.execute(sql, params).fetchall()

            results = []
            for image_path, dimension, blob in rows:
                if blob:
                    try:
                        vector = self.blob_to_vector(blob, dimension)
                        results.append((image_path, vector))
                    except (ValueError, struct.error) as e:
                        logger.warning("Failed to decode embedding for %s: %s", image_path, e)
                        continue
            return results

    # =========================================================================
    # Similarity Search
    # =========================================================================

    def find_similar(
        self, query_vector: list[float], limit: int = 10, model_name: str | None = None
    ) -> list[tuple[str, float]]:
        """Find images similar to the query vector using cosine similarity.

        Uses sqlite-vec to perform fast vector similarity search.
        Returns results sorted by similarity score (descending).

        Args:
            query_vector: The query embedding vector to search for.
            limit: Maximum number of results to return (default: 10).
            model_name: Optional embedding model to restrict results to.
                Vectors from different models are not comparable; pass the
                model that produced the query vector when known.

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

            logger.warning("%s. Returning empty results.", VEC_NOT_AVAILABLE)
            return []

        with self.get_connection() as conn:
            # The vec0 extension must be loaded on this connection before
            # querying the virtual table (each connection loads extensions
            # independently).
            self._ensure_extension_loaded(conn)
            # Use vec_find_similar for sqlite-vec search
            return self.vec_find_similar(conn, query_vector, limit=limit, model_name=model_name)

    def find_similar_rest(
        self,
        query_vector: list[float],
        model_name: str | None = None,
        limit: int = 10,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> list[tuple[str, float]]:
        """Find images similar to the query vector using Python cosine similarity.

        This is a fallback method that works without sqlite-vec.
        It loads all embeddings from the database and computes cosine similarity
        in Python. Slower than sqlite-vec for large datasets but always available.

        Args:
            query_vector: The query embedding vector to search for.
            model_name: Optional filter by embedding model name. When
                ``None``, embeddings from all models are searched (rows whose
                dimension differs from the query are skipped below).
            limit: Maximum number of results to return (default: 10).
            date_start: Optional inclusive start date (``YYYY-MM-DD``). When
                provided together with ``date_end``, results are restricted to
                images whose ``date_taken`` (falling back to ``date_created``
                then ``date_modified``) falls within the range.
            date_end: Optional inclusive end date (``YYYY-MM-DD``).

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

        # Get all embeddings from database, optionally narrowed by a date range.
        if date_start and date_end:
            embeddings = self.get_embeddings_date_filtered(model_name, date_start, date_end)
        else:
            embeddings = self.get_all_embeddings(model_name)

        if not embeddings:
            logger.warning("No embeddings found in database")
            return []

        # Compute similarity for each embedding
        results = []
        for image_path, vector in embeddings:
            # Vectors from a different embedding model have misaligned axes;
            # comparing them (even truncated) yields meaningless scores, so
            # skip them instead of guessing.
            if len(vector) != len(query_vector):
                logger.warning(
                    "Skipping %s: dimension mismatch (query=%s, stored=%s); "
                    "reprocess the folder with the current embedding model",
                    image_path,
                    len(query_vector),
                    len(vector),
                )
                continue
            try:
                similarity = self.cosine_similarity(query_vector, vector)
                results.append((image_path, similarity))
            except Exception as e:
                logger.error("Failed to compute similarity for %s: %s", image_path, e)
                continue

        # Sort by similarity (descending) and take top-k
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]
