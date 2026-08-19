"""
Simple Sequential Processor for Local Photo Agent.

This module provides straightforward sequential processing of images
without batch-specific infrastructure. It processes images one at a time
and tracks progress in a simple database.

The simple approach:
1. Get list of image files
2. Filter out already-processed files (optional)
3. Process each file sequentially
4. Save results and mark as completed
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from src.config import ProcessingConfig
from src.constants import (
    EMBEDDING_GENERATION_RETURNED_NONE,
    EMBEDDING_NO_DESCRIPTION,
    EMBEDDING_UNAVAILABLE,
    LOG_EMBEDDING_FAILED,
    LOG_EMBEDDING_GENERATION,
    LOG_EMBEDDING_SAVED,
    VEC_REQUIRED,
)
from src.embeddings import create_generator
from src.interfaces import BasePhotoExtractor, ProcessingResult
from src.sidecar import get_writer
from src.sidecar.database import FeaturesDatabase
from src.simple_processing_tracker import SimpleProcessingTracker
from src.utils import encode_image_file

logger = logging.getLogger(__name__)


class SequentialProcessor:
    """
    Simple processor that processes images sequentially.

    This is the main processing class, providing:
    - Sequential processing of single files or lists of files
    - Simple database tracking of processed files
    - Automatic exclusion of already-processed files
    """

    def __init__(
        self,
        extractor: BasePhotoExtractor,
        config: ProcessingConfig | None = None,
        embedding_enabled: bool = True,
        folder: str | None = None,
    ):
        """
        Initialize the sequential processor.

        Args:
            extractor: The LLM extractor to use for feature extraction.
            config: Optional processing configuration.
            embedding_enabled: Whether to generate embeddings (default: True).
            folder: Optional folder path for database operations.
        """
        self.extractor = extractor
        self.config = config or ProcessingConfig.from_env()
        self._writer = get_writer()
        self.embedding_enabled = embedding_enabled and self.config.embedding_enabled
        self.folder = folder
        self._embedding_generator = None
        self._db = None
        # Serializes all writes to the shared SQLite database (features.db) from
        # concurrent worker threads. Both FeaturesDatabase and the per-folder
        # SimpleProcessingTracker write to the same file, so a single lock guards
        # every mutation. Network I/O (LLM extraction + embedding generation) is
        # performed outside this lock so it stays fully parallel.
        self._db_lock = threading.Lock()

        # Initialize database if folder is provided (needed for metadata and embeddings)
        if folder is not None:
            self._db = FeaturesDatabase(FeaturesDatabase.default_db_path(folder))
            try:
                # Initialize the database schema (creates all tables including image_metadata)
                conn = self._db.init_db()
                conn.close()  # Close the connection after schema initialization
            except Exception as e:
                logger.error("Failed to initialize database: %s", e)
                self._db = None

        # Initialize embedding generator if enabled and database is available
        if self.embedding_enabled and self._db is not None:
            self._initialize_embedding_generator()
            # Try to initialize vector search (optional, for fast similarity search)
            try:
                self._db.init_vector_search()
            except RuntimeError as e:
                logger.warning("Vector search not available (sqlite-vec not installed): %s", e)
                # This is OK - we can still save embeddings to image_embeddings table

    def _extract_and_save_metadata(self, image_path: str) -> None:
        """Extract metadata from an image file and save it to the database.

        The metadata is read from the file (local I/O) without holding the DB
        lock; only the database write is serialized so concurrent workers can
        parse metadata in parallel.

        Args:
            image_path: Path to the image file.
        """
        if self._db is None:
            logger.warning("No database available, skipping metadata extraction for %s", image_path)
            return

        try:
            from src.metadata import extract_metadata_dict

            # Extract metadata from the image (local I/O, no lock needed)
            metadata = extract_metadata_dict(image_path)

            if metadata:
                # Save metadata to database (serialized)
                with self._db_lock:
                    self._db.save_metadata(image_path, metadata)
                logger.info("Metadata extracted and saved for %s (keys: %s)", image_path, list(metadata.keys()))
            else:
                logger.warning("No metadata found for %s", image_path)
        except Exception as e:
            logger.error("Failed to extract metadata for %s: %s", image_path, e, exc_info=True)

    def _initialize_embedding_generator(self) -> None:
        """Initialize the embedding generator from config."""
        if not self.config.embedding_enabled:
            return
        try:
            self._embedding_generator = create_generator(
                backend=self.config.embedding_backend,
                host=self.config.host,
                port=self.config.port,
                model=self.config.embedding_model,
                timeout=self.config.timeout,
            )
        except ValueError as e:
            from src.embeddings import list_embedding_backends

            available = list_embedding_backends()
            logger.error(
                "Failed to create embedding generator: %s. Available backends: %s. Check LOCAL_PHOTO_AGENT_EMBEDDING_BACKEND environment variable. %s",
                e,
                available,
                VEC_REQUIRED,
            )
            self._embedding_generator = None
        except Exception as e:
            logger.error(
                "Failed to create embedding generator with backend='%s', host='%s', port=%s, model='%s': %s. Check that the embedding server is running and accessible. %s",
                self.config.embedding_backend,
                self.config.host,
                self.config.port,
                self.config.embedding_model,
                e,
                VEC_REQUIRED,
            )
            self._embedding_generator = None

    def process_image(
        self,
        image_path: str,
        prompt: str | None = None,
    ) -> ProcessingResult:
        """
        Process a single image file.

        Args:
            image_path: Path to the image file.
            prompt: Optional prompt override.

        Returns:
            ProcessingResult with extraction results and optional embedding.
        """
        logger.info("Processing image: %s", image_path)

        # Encode image to base64
        b64 = encode_image_file(image_path)

        # Extract features
        effective_prompt = prompt or self.config.default_prompt
        result = self.extractor.extract_b64(b64, prompt=effective_prompt)
        result.image_path = image_path

        # Extract and save metadata
        self._extract_and_save_metadata(image_path)

        # Generate and save embedding if enabled
        if self.embedding_enabled and self._embedding_generator is not None and self._db is not None:
            try:
                # Get the description from the result
                description = None
                if result.parsed and isinstance(result.parsed, dict):
                    description = result.parsed.get("description") or result.parsed.get("caption")
                elif result.response:
                    description = result.response

                if description:
                    # Generate embedding from the description text
                    embedding, error = self._generate_and_save_embedding(
                        image_path, description, self.config.embedding_model
                    )
                    if error:
                        logger.warning("Embedding error for %s: %s", image_path, error)
                        # Store error in result for display
                        result.embedding_error = error
                    else:
                        logger.info(
                            "Embedding generated for %s (dim: %s)", image_path, len(embedding) if embedding else 0
                        )
                else:
                    logger.warning("No description available for embedding generation for %s", image_path)
                    result.embedding_error = "No description available for embedding"
            except Exception as e:
                logger.error("Failed to generate embedding for %s: %s", image_path, e)
                result.embedding_error = str(e)

        # Save the extraction result to database
        self._save_result(result)

        return result

    def process_paths(
        self,
        paths: list[str],
        *,
        prompt: str | None = None,
        resume: bool = True,
        progress_callback=None,
        concurrency: int | None = None,
    ) -> dict[str, Any]:
        """
        Process a list of image paths.

        Args:
            paths: List of image file paths to process.
            prompt: Optional prompt override.
            resume: If True, skip already-processed images.
            progress_callback: Optional callable(processed, total) for progress.
            concurrency: Number of images to process in parallel against the LLM
                backend. ``None`` or ``1`` preserves the historical strictly
                sequential behaviour. Values >1 dispatch per-image LLM requests
                to a thread pool; database writes are serialized internally.

        Returns:
            Dictionary with processing statistics:
            - total_found: Total paths provided
            - processed: Number of images processed
            - skipped: Number of images skipped (already processed)
            - successes: Number of successful extractions
            - failures: Number of failed extractions
            - results: List of result dictionaries
        """
        total_found = len(paths)
        logger.info("Processing %d image paths", total_found)

        # Resolve effective concurrency: None/<=1 means sequential.
        effective_concurrency = concurrency if concurrency and concurrency > 1 else 1
        if effective_concurrency > 1:
            logger.info("Batch concurrency: %d", effective_concurrency)

        # Group paths by folder for tracking
        from collections import defaultdict

        folder_groups = defaultdict(list)
        for p in paths:
            folder_groups[_parent_dir(p)].append(p)

        # Process each folder group
        all_results = []
        skipped = 0
        successes = 0
        failures = 0

        for folder, folder_paths in folder_groups.items():
            tracker = SimpleProcessingTracker(folder)

            # Filter out already processed if resume is enabled
            if resume:
                processed_set = tracker.get_processed_files()
                paths_to_process = [p for p in folder_paths if p not in processed_set]
                skipped += len(folder_paths) - len(paths_to_process)
            else:
                paths_to_process = folder_paths

            if effective_concurrency > 1 and len(paths_to_process) > 1:
                # Concurrent batch processing: per-image LLM requests run in a
                # thread pool; DB writes are serialized via self._db_lock inside
                # process_image / _process_and_track.
                completed = 0
                total_in_folder = len(paths_to_process)
                with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
                    futures = {
                        pool.submit(self._process_and_track, p, prompt, tracker): p
                        for p in paths_to_process
                    }
                    for fut in as_completed(futures):
                        image_path = futures[fut]
                        try:
                            result_dict, ok = fut.result()
                        except Exception as e:  # pragma: no cover - defensive
                            logger.error("Worker raised for %s: %s", image_path, e)
                            error_result = ProcessingResult(
                                success=False,
                                image_path=image_path,
                                error=str(e),
                                error_code="PROCESSING_ERROR",
                            )
                            self._save_result(error_result)
                            with self._db_lock:
                                tracker.mark_failed(image_path, "PROCESSING_ERROR", str(e))
                            result_dict = error_result.as_dict()
                            ok = False
                        all_results.append(result_dict)
                        if ok:
                            successes += 1
                        else:
                            failures += 1
                        completed += 1
                        if progress_callback:
                            try:
                                progress_callback(completed, total_in_folder)
                            except Exception as e:
                                logger.debug("Progress callback failed: %s", e, exc_info=True)
                continue

            # Process each path (sequential)
            for i, image_path in enumerate(paths_to_process):
                logger.info("Processing: %s", image_path)

                # Update progress to show we're starting this file
                if progress_callback:
                    try:
                        progress_callback(i, len(paths_to_process))
                    except Exception as e:
                        logger.debug("Progress callback failed: %s", e, exc_info=True)

                try:
                    result = self.process_image(image_path, prompt=prompt)

                    # Mark as completed (result already saved in process_image)
                    tracker.mark_completed(image_path)

                    all_results.append(result.as_dict())
                    successes += 1
                except Exception as e:
                    logger.error("Failed to process %s: %s", image_path, e)

                    # Create error result
                    error_result = ProcessingResult(
                        success=False,
                        image_path=image_path,
                        error=str(e),
                        error_code="PROCESSING_ERROR",
                    )
                    self._save_result(error_result)
                    tracker.mark_failed(image_path, "PROCESSING_ERROR", str(e))

                    all_results.append(error_result.as_dict())
                    failures += 1

                    # Update progress if callback provided
                    if progress_callback:
                        try:
                            progress_callback(successes + failures, len(paths_to_process))
                        except Exception as e:
                            logger.debug("Progress callback failed: %s", e, exc_info=True)

        return {
            "total_found": total_found,
            "processed": len(all_results),
            "skipped": skipped,
            "successes": successes,
            "failures": failures,
            "results": all_results,
        }

    def _process_and_track(
        self,
        image_path: str,
        prompt: str | None,
        tracker: SimpleProcessingTracker,
    ) -> tuple[dict, bool]:
        """Process a single image and update the tracker.

        Used by the concurrent batch path. The LLM extraction and embedding
        generation (network I/O) run unguarded; all database mutations are
        serialized via ``self._db_lock``.

        Returns:
            Tuple of (result_dict, success_flag).
        """
        logger.info("Processing: %s", image_path)
        try:
            result = self.process_image(image_path, prompt=prompt)
            with self._db_lock:
                tracker.mark_completed(image_path)
            return result.as_dict(), True
        except Exception as e:
            logger.error("Failed to process %s: %s", image_path, e)
            error_result = ProcessingResult(
                success=False,
                image_path=image_path,
                error=str(e),
                error_code="PROCESSING_ERROR",
            )
            self._save_result(error_result)
            with self._db_lock:
                tracker.mark_failed(image_path, "PROCESSING_ERROR", str(e))
            return error_result.as_dict(), False

    def _generate_and_save_embedding(self, image_path: str, description: str, model_name: str) -> tuple:
        """Generate an embedding from text and save it to the database.

        Returns:
            Tuple of (embedding_vector, error_message).
        """
        # Check if embedding is enabled
        if not self.embedding_enabled:
            return None, None

        # Check if generator is available
        if self._embedding_generator is None:
            return None, EMBEDDING_UNAVAILABLE

        # Check if we have database
        if self._db is None:
            error_msg = f"{EMBEDDING_NO_DESCRIPTION} (image: {image_path})"
            logger.error(error_msg)
            return None, error_msg

        # Check if description is available
        if not description or not description.strip():
            error_msg = f"{EMBEDDING_NO_DESCRIPTION} (image: {image_path})"
            logger.warning(error_msg)
            return None, error_msg

        # Generate the embedding
        logger.debug(LOG_EMBEDDING_GENERATION(image_path))
        try:
            embedding = self._embedding_generator.generate_from_text(description, model=model_name)
        except Exception as e:
            error_msg = f"Embedding generation failed for {image_path}: {e}. {VEC_REQUIRED}"
            logger.error(LOG_EMBEDDING_FAILED(image_path, e))
            return None, error_msg

        # Check if embedding generation returned None
        if embedding is None:
            error_msg = f"{EMBEDDING_GENERATION_RETURNED_NONE} (image: {image_path})"
            logger.error(error_msg)
            return None, error_msg

        # Save the embedding to the database
        try:
            with self._db_lock:
                self._db.save_embedding(image_path, model_name, embedding)
            logger.info(LOG_EMBEDDING_SAVED(image_path, model_name, len(embedding)))
            return embedding, None
        except Exception as e:
            error_msg = f"Failed to save embedding for {image_path}: {e}. {VEC_REQUIRED}"
            logger.error(error_msg)
            return embedding, error_msg

    def _save_result(self, result: ProcessingResult) -> None:
        """Save a processing result to database."""
        if result.image_path:
            data = result.as_dict()
            with self._db_lock:
                if self._db is not None:
                    # Use the folder's database for consistency with metadata
                    self._db.save_extraction(result.image_path, data)
                else:
                    # Fallback to sidecar store for single image processing
                    self._writer.save(result.image_path, data)


def _parent_dir(p: str) -> str:
    """Return the parent directory of a path, or the path itself if it's already a directory."""
    pp = Path(p).resolve()
    if pp.is_dir():
        return str(pp)
    return str(pp.parent)


def process_image(
    image_path: str,
    extractor: BasePhotoExtractor,
    prompt: str | None = None,
    folder: str | None = None,
) -> ProcessingResult:
    """
    Process a single image file.

    This is a standalone function for processing a single image.

    Args:
        image_path: Path to the image file.
        extractor: The LLM extractor to use.
        prompt: Optional prompt override.
        folder: Optional folder path for database operations (required for embedding generation).

    Returns:
        ProcessingResult with extraction results.
    """
    processor = SequentialProcessor(extractor, folder=folder)
    return processor.process_image(image_path, prompt=prompt)


def process_paths(
    paths: list[str],
    extractor: BasePhotoExtractor,
    *,
    prompt: str | None = None,
    resume: bool = True,
    folder: str | None = None,
    concurrency: int | None = None,
) -> dict[str, Any]:
    """
    Process a list of image paths.

    This is a standalone function for processing multiple images.

    Args:
        paths: List of image file paths to process.
        extractor: The LLM extractor to use.
        prompt: Optional prompt override.
        resume: If True, skip already-processed images.
        folder: Optional folder path for database operations (required for embedding generation).
        concurrency: Optional number of images to process in parallel (default: sequential).

    Returns:
        Dictionary with processing statistics.
    """
    processor = SequentialProcessor(extractor, folder=folder)
    return processor.process_paths(paths, prompt=prompt, resume=resume, concurrency=concurrency)
