"""Extraction storage and tag query mixin for FeaturesDatabase.

Contains raw_features / extracted_features / feature_tags CRUD, FTS5
index maintenance, tag queries, and the feature-summary join.
"""

import json
import logging
import sqlite3
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)


class ExtractionMixin:
    """Extraction persistence and tag queries for FeaturesDatabase.

    Requires the owning class to provide ``db_path``, ``get_connection()``,
    ``_fts5_available``, and ``_to_text`` (from :class:`DatabaseConnectionMixin`),
    plus ``get_metadata`` / ``save_metadata`` (from :class:`MetadataMixin`)
    for the feature-summary join.
    """

    db_path: Path
    _fts5_available: bool

    if TYPE_CHECKING:

        def get_connection(self): ...

        @staticmethod
        def _to_text(value): ...

        def get_metadata(self, image_path: str): ...

        def save_metadata(self, image_path: str, metadata: dict): ...

    def save_extraction(self, image_path: str, result: dict) -> None:
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
                # parsed is None or not a dict — fall back to the raw response
                # text so the description column is not NULL when the model
                # produced usable text that failed JSON parsing.
                raw_response = result.get("response")
                description = raw_response.strip() if isinstance(raw_response, str) and raw_response.strip() else None
                subjects = objects = colors = setting = mood = None
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
                    with suppress(sqlite3.DatabaseError):
                        conn.execute(
                            "INSERT INTO extracted_features_fts (extracted_features_fts, rowid) VALUES ('delete', ?)",
                            (rowid,),
                        )
                    conn.execute(
                        """
                        INSERT INTO extracted_features_fts (rowid, description, subjects, objects, colors, setting, mood, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rowid,
                            description or "",
                            subjects or "",
                            objects or "",
                            colors or "",
                            setting or "",
                            mood or "",
                            tags_str,
                        ),
                    )

            conn.commit()

    def get_extraction(self, image_path: str) -> dict | None:
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

    def list_extractions(self) -> list[dict]:
        """Return all rows, deserialising ``model_output`` back to dicts."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT model_output FROM raw_features").fetchall()
            return [json.loads(r[0]) for r in rows if r[0]]

    def execute_query(self, sql: str) -> tuple[list[str], list[tuple]]:
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

    def get_features_by_tag(self, tag: str) -> list[dict]:
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
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def get_features_by_tags(self, tags: list[str]) -> list[dict]:
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
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def list_tag_frequencies(self, limit: int = 100) -> list[tuple[str, int]]:
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

    def list_tag_frequencies_restricted(self, selected_tags: list[str], limit: int = 100) -> list[tuple[str, int]]:
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

    def list_all_tags(self) -> list[str]:
        """Return all distinct tags in the database, sorted case-insensitively."""
        if not self.db_path.exists():
            return []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT tag FROM feature_tags ORDER BY tag COLLATE NOCASE").fetchall()
            return [row[0] for row in rows if row[0]]

    def get_feature_summary(self, image_path: str) -> dict | None:
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
                for r in conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", (image_path,)).fetchall()
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
                        logger.info(
                            "Fallback: Extracted metadata on-the-fly for %s (keys: %s)",
                            image_path,
                            list(fallback_metadata.keys()),
                        )
                        result["metadata"] = fallback_metadata
                        # Also save it to database for future use
                        try:
                            self.save_metadata(image_path, fallback_metadata)
                            logger.info("Fallback: Saved on-the-fly metadata to DB for %s", image_path)
                        except Exception as e:
                            logger.error("Fallback: Failed to save on-the-fly metadata for %s: %s", image_path, e)
                    else:
                        logger.warning("No metadata found for %s (neither in DB nor extracted)", image_path)
                except Exception as e:
                    logger.error("Failed to extract fallback metadata for %s: %s", image_path, e, exc_info=True)

            return result
