"""
Photo discovery and processing state tracking for Local Photo Agent.

This module provides:
- PhotoList: Discovers image files in directories
- Simple processing state tracking using the database

The new simple approach:
1. At every run, get all files from the folder
2. Remove files that are already in the processed table
3. Process remaining files one by one
4. As each photo is processed, write details directly to the database
"""

from pathlib import Path
from typing import List, Optional, Set, Tuple, Dict
import logging

from src.sidecar.database import FeaturesDatabase
from src.simple_processing_tracker import SimpleProcessingTracker

logger = logging.getLogger(__name__)

# module-level cache: folder -> (cache_key, processed_set)
_PROCESSED_SET_CACHE: Dict[str, Tuple[Tuple, Set[str]]] = {}


def _db_cache_key(image_dir: str) -> Tuple:
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


class PhotoList:
    """Handles discovery and listing of photos in specified folders."""

    def __init__(self, recursive: bool = True, extensions: Set[str] = None):
        """Initialise the photo discovery helper.

        Args:
            recursive: If True, scan sub-directories recursively.
            extensions: Set of lowercase file extensions to include.
                Defaults to common image formats.
        """
        self.recursive = recursive
        self.extensions = extensions or {
            ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
            ".tiff", ".tif", ".heic", ".heif"
        }

    def list_photos(
        self,
        paths: List[str],
        limit: Optional[int] = None,
        exclude_processed_from: Optional[str] = None,
    ) -> List[str]:
        """
        Expand directories into image file paths.

        Args:
            paths: List of paths (files or directories).
            limit: If set, return at most this many image paths.
            exclude_processed_from: If set to a directory path, use the
                simple processing tracker to exclude already processed images.

        Returns:
            List of absolute image file paths.
        """
        images = []
        logger.info(f"Listing photos for paths: {paths}")
        
        for p in paths:
            path = Path(p).absolute()
            logger.info(f"Checking path: {path} (Exists: {path.exists()}, IsDir: {path.is_dir()})")
            
            if path.is_dir():
                if self.recursive:
                    candidates = list(path.rglob("*"))
                    logger.info(f"Found {len(candidates)} total candidates in {path} (recursive)")
                else:
                    candidates = list(path.iterdir())
                    logger.info(f"Found {len(candidates)} total candidates in {path} (non-recursive)")
                
                for child in candidates:
                    if child.is_file() and child.suffix.lower() in self.extensions:
                        images.append(str(child))
            elif path.is_file():
                if path.suffix.lower() in self.extensions:
                    images.append(str(path))
                else:
                    logger.warning(f"File is not a supported image: {p}")
            else:
                logger.warning(f"Path not found: {p}")

        logger.info(f"Total images discovered: {len(images)}")

        if exclude_processed_from:
            processed = self._load_processed_set(exclude_processed_from)
            if processed:
                images = [img for img in images if img not in processed]
                logger.info(f"After excluding {len(processed)} processed: {len(images)} remaining")

        if limit is not None:
            images = images[:limit]
            logger.info(f"After limiting to {limit}: {len(images)} remaining")

        return images

    @staticmethod
    def _load_processed_set(image_dir: str) -> set:
        """Build a set of already-processed image paths from the simple tracker.

        Uses SimpleProcessingTracker to get all processed images.
        Falls back to the features.db rows if the tracker is not available.
        Results are cached by folder and invalidated only when DB
        data changes on disk.
        """
        cached = _PROCESSED_SET_CACHE.get(image_dir)
        current_key = _db_cache_key(image_dir)
        if cached is not None and cached[0] == current_key:
            return cached[1]

        processed: Set[str] = set()

        # Use simple processing tracker
        try:
            tracker = SimpleProcessingTracker(image_dir)
            processed = tracker.get_processed_files()
            logger.debug(f"Loaded {len(processed)} processed images from simple tracker")
        except Exception as e:
            logger.warning(f"Failed to read processing tracker for {image_dir}: {e}")
            
            # Fallback: try to read from features.db directly
            db_path = FeaturesDatabase.default_db_path(image_dir)
            if db_path.exists():
                try:
                    db = FeaturesDatabase(db_path)
                    extractions = db.list_extractions()
                    db.close()
                    processed = {
                        ex["image_path"] for ex in extractions
                        if ex.get("image_path")
                    }
                    logger.debug(f"Loaded {len(processed)} processed images from features.db fallback")
                except Exception:
                    logger.warning("Failed to read features DB for %s", image_dir, exc_info=True)

        _PROCESSED_SET_CACHE[image_dir] = (current_key, processed)
        return processed