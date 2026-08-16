"""
Simple Processing Tracker for Local Photo Agent.

This module provides a simple database-based approach to track which images
have been processed, replacing the complex WAL system.

The logic is simple:
1. When processing starts, get all files from the folder
2. Remove files that are already in the processed table
3. Process remaining files one by one
4. As each photo is processed, write details to the database

This eliminates the need for:
- Complex WAL files
- Microbatch tracking
- Heartbeat monitoring
- Compaction logic
- Abandoned entry repair
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.constants import STATUS_COMPLETED, STATUS_FAILED
from src.sqlite_utils import open_connection

logger = logging.getLogger(__name__)

# Table name for simple processing tracking
TABLE_PROCESSING_TRACKER = "processing_tracker"


class SimpleProcessingTracker:
    """
    Simple database-based tracker for processed images.

    Tracks which images have been processed in a folder by storing
    entries in a SQLite table. This replaces the complex WAL system
    with a much simpler approach.
    """

    def __init__(self, folder: str):
        """Initialize the tracker for a folder.

        Args:
            folder: The folder to track processing for.
        """
        self.folder = Path(folder).absolute()
        self._db_path = self._get_db_path()
        self._schema_ensured = False  # Track if schema has been ensured
        self._connection = None  # Cached connection

    def _get_db_path(self) -> Path:
        """Get the database path for this folder."""
        return self.folder / ".local-photo-agent" / "features.db"

    def _get_connection(self) -> sqlite3.Connection:
        """Get a cached connection or create a new one."""
        if self._connection is None:
            self._connection = open_connection(self._db_path)
            # Ensure schema on first connection
            if not self._schema_ensured:
                self._ensure_schema_with_conn(self._connection)
                self._schema_ensured = True
        return self._connection

    def _ensure_schema_with_conn(self, conn: sqlite3.Connection) -> None:
        """Create the processing_tracker table if it doesn't exist using an existing connection."""
        try:
            # Create processing tracker table
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_PROCESSING_TRACKER} (
                    image_path TEXT PRIMARY KEY,
                    status TEXT NOT NULL,  -- 'completed' or 'failed'
                    processed_at TEXT NOT NULL,
                    error_code TEXT,
                    error_msg TEXT
                )
                """
            )
            conn.commit()
            logger.debug("Processing tracker schema ensured for %s", self._db_path)
        except Exception as e:
            logger.error("Failed to ensure processing tracker schema: %s", e)
            raise

    def get_processed_files(self) -> set[str]:
        """Get all image paths that have been processed (completed or failed).

        Returns:
            Set of image paths that have been processed.
        """
        if not self._db_path.exists():
            return set()

        conn = self._get_connection()
        try:
            processed = set()

            # Get from processing_tracker table
            cursor = conn.execute(f"SELECT image_path FROM {TABLE_PROCESSING_TRACKER}")
            processed.update(row[0] for row in cursor.fetchall())

            # Also check raw_features table for backward compatibility
            # Images that have entries in raw_features are considered processed
            try:
                cursor2 = conn.execute("SELECT DISTINCT image_path FROM raw_features WHERE success = 1")
                processed.update(row[0] for row in cursor2.fetchall())
            except sqlite3.OperationalError:
                # raw_features table doesn't exist, skip it
                pass

            return processed
        except Exception as e:
            logger.error("Failed to get processed files: %s", e)
            return set()

    def get_failed_files(self) -> list[dict]:
        """Get all failed files with error information.

        Returns:
            List of dicts with image_path, error_code, and error_msg.
        """
        if not self._db_path.exists():
            return []

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"SELECT image_path, error_code, error_msg FROM {TABLE_PROCESSING_TRACKER} WHERE status = ?",
                (STATUS_FAILED,),
            )
            return [
                {
                    "image_path": row[0],
                    "error_code": row[1],
                    "error_msg": row[2],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error("Failed to get failed files: %s", e)
            return []

    def mark_completed(self, image_path: str) -> None:
        """Mark an image as successfully completed.

        Args:
            image_path: Path to the image.
        """
        conn = self._get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                f"""
                INSERT INTO {TABLE_PROCESSING_TRACKER} (image_path, status, processed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(image_path) DO UPDATE SET
                    status = excluded.status,
                    processed_at = excluded.processed_at,
                    error_code = NULL,
                    error_msg = NULL
                """,
                (image_path, STATUS_COMPLETED, now),
            )
            conn.commit()
            logger.debug("Marked %s as completed", image_path)
            # Invalidate the processed set cache so new queries get fresh data
            from src.discovery import clear_processed_cache

            clear_processed_cache(self.folder)
        except Exception as e:
            logger.error("Failed to mark %s as completed: %s", image_path, e)
            raise

    def mark_failed(self, image_path: str, error_code: str | None = None, error_msg: str | None = None) -> None:
        """Mark an image as failed.

        Args:
            image_path: Path to the image.
            error_code: Optional error code.
            error_msg: Optional error message.
        """
        conn = self._get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                f"""
                INSERT INTO {TABLE_PROCESSING_TRACKER} (image_path, status, processed_at, error_code, error_msg)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_path) DO UPDATE SET
                    status = excluded.status,
                    processed_at = excluded.processed_at,
                    error_code = excluded.error_code,
                    error_msg = excluded.error_msg
                """,
                (image_path, STATUS_FAILED, now, error_code, error_msg),
            )
            conn.commit()
            logger.debug("Marked %s as failed: %s", image_path, error_msg)
            # Invalidate the processed set cache so new queries get fresh data
            from src.discovery import clear_processed_cache

            clear_processed_cache(self.folder)
        except Exception as e:
            logger.error("Failed to mark %s as failed: %s", image_path, e)
            raise

    def is_processed(self, image_path: str) -> bool:
        """Check if an image has been processed (completed or failed).

        Args:
            image_path: Path to the image.

        Returns:
            True if the image has been processed, False otherwise.
        """
        if not self._db_path.exists():
            return False

        conn = self._get_connection()
        try:
            cursor = conn.execute(f"SELECT 1 FROM {TABLE_PROCESSING_TRACKER} WHERE image_path = ?", (image_path,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error("Failed to check if %s is processed: %s", image_path, e)
            return False

    def get_stats(self) -> dict:
        """Get processing statistics.

        Returns:
            Dict with total, completed, and failed counts.
        """
        if not self._db_path.exists():
            return {"total": 0, "completed": 0, "failed": 0}

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed
                FROM {TABLE_PROCESSING_TRACKER}
                """,
                (STATUS_COMPLETED, STATUS_FAILED),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "total": row[0] or 0,
                    "completed": row[1] or 0,
                    "failed": row[2] or 0,
                }
            return {"total": 0, "completed": 0, "failed": 0}
        except Exception as e:
            logger.error("Failed to get stats: %s", e)
            return {"total": 0, "completed": 0, "failed": 0}
