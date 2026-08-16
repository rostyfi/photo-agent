"""
File processing utilities for Local Photo Agent.

This module provides a simple, database-backed approach to track and list
files that need processing, replacing the complex batching logic.

The approach:
1. Scan folder for all image files
2. Use database tracker to identify already processed files
3. Return only unprocessed files for processing
4. Mark files as processed/failed as they complete
"""

import logging
from pathlib import Path

from src.discovery import PhotoList
from src.simple_processing_tracker import SimpleProcessingTracker

logger = logging.getLogger(__name__)


class ProcessableFileLister:
    """
    Handles listing of files that need to be processed.

    This class provides a simple interface for:
    - Listing all image files in a folder (recursively or not)
    - Filtering out already processed files
    - Getting counts of total and pending files

    It uses SimpleProcessingTracker to check which files have already been
    processed, ensuring that reprocessing is avoided unless explicitly requested.
    """

    def __init__(
        self,
        folder: str,
        recursive: bool = True,
        extensions: set[str] | None = None,
    ):
        """
        Initialize the file lister.

        Args:
            folder: Path to the folder to scan for images.
            recursive: If True, scan subdirectories recursively.
            extensions: Set of file extensions to include. If None, uses default
                       image extensions.
        """
        self.folder = Path(folder).absolute()
        self.recursive = recursive
        self.extensions = extensions or {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
            ".tiff",
            ".tif",
            ".heic",
            ".heif",
        }
        self._photo_list = PhotoList(recursive=recursive, extensions=self.extensions)
        self._tracker = SimpleProcessingTracker(str(self.folder))

        # Cache for all files (doesn't change during a session)
        self._all_files: list[str] | None = None

    def _get_all_files(self) -> list[str]:
        """Get all image files in the folder (cached)."""
        if self._all_files is None:
            self._all_files = self._photo_list.list_photos([str(self.folder)])
        return self._all_files

    def get_processed_files(self) -> set[str]:
        """Get set of already processed file paths."""
        return self._tracker.get_processed_files()

    def get_pending_files(self, limit: int | None = None) -> list[str]:
        """
        Get list of files that still need processing.

        Args:
            limit: Maximum number of files to return. If None, returns all.

        Returns:
            List of absolute file paths that haven't been processed yet.
        """
        all_files = self._get_all_files()
        processed = self.get_processed_files()

        pending = [f for f in all_files if f not in processed]

        if limit is not None:
            pending = pending[:limit]

        return pending

    def get_failed_files(self) -> list[dict]:
        """
        Get list of files that failed processing.

        Returns:
            List of dicts with image_path, error_code, and error_msg.
        """
        return self._tracker.get_failed_files()

    def get_all_files(self) -> list[str]:
        """Get all image files in the folder."""
        return self._get_all_files()

    def total_all(self) -> int:
        """Get total number of image files in the folder."""
        return len(self._get_all_files())

    def total_pending(self) -> int:
        """Get number of files still pending processing."""
        return len(self.get_pending_files())

    def total_processed(self) -> int:
        """Get number of files already processed."""
        return len(self.get_processed_files())

    def total_failed(self) -> int:
        """Get number of files that failed processing."""
        return len(self.get_failed_files())

    def mark_completed(self, file_path: str) -> None:
        """Mark a file as successfully processed."""
        self._tracker.mark_completed(file_path)
        # Invalidate cache so next call to get_pending_files() is fresh
        self._all_files = None

    def mark_failed(
        self,
        file_path: str,
        error_code: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        """Mark a file as failed."""
        self._tracker.mark_failed(file_path, error_code, error_msg)
        # Invalidate cache
        self._all_files = None

    def is_processed(self, file_path: str) -> bool:
        """Check if a file has been processed (completed or failed)."""
        return self._tracker.is_processed(file_path)

    def get_stats(self) -> dict:
        """
        Get processing statistics.

        Returns:
            Dict with total, pending, processed, and failed counts.
        """
        return {
            "total": self.total_all(),
            "pending": self.total_pending(),
            "processed": self.total_processed(),
            "failed": self.total_failed(),
        }
