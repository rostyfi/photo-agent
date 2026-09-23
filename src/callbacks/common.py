"""
Common utilities and shared state for Dash callbacks.

This module provides shared helpers and mutable state used across multiple
callback modules to avoid code duplication.

The simplified approach:
- Simple sequential processing
- Database tracking via SimpleProcessingTracker
"""

import logging
import os
from contextlib import contextmanager

from plugins.llm import create_extractor
from src.components import build_detail_modal_content, build_fullscreen_viewer
from src.config import AppConfig
from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL, DEFAULT_LLM_PORT, DEFAULT_LLM_TIMEOUT
from src.constants import SORT_KEY_DATE, SORT_KEY_DATE_TAKEN, SORT_KEY_NAME, SORT_KEY_RELEVANCE
from src.constants import SORT_ORDER_ASC, SORT_ORDER_DESC, default_order_for
from src.sidecar.database import FeaturesDatabase
from src.simple_processing_tracker import SimpleProcessingTracker
from src.vector_search.availability import is_vector_search_available

logger = logging.getLogger(__name__)

# Cache for SimpleProcessingTracker instances to avoid recreating on every poll
_TRACKER_INSTANCE_CACHE: dict = {}  # folder -> SimpleProcessingTracker

# Process-wide AppConfig cache. Environment variables do not change during a
# running session, so reading them once avoids re-parsing on every callback.
_CACHED_APP_CONFIG: AppConfig | None = None


def _get_app_config() -> AppConfig:
    """Return the process-wide AppConfig, loading it once from the environment.

    Callback hot paths should call this instead of ``AppConfig.from_env()``
    to avoid re-parsing the environment (and re-running ``load_dotenv()``) on
    every invocation. Per-folder ``settings.json`` overrides are applied so the
    cached config matches the one used at app start.
    """
    global _CACHED_APP_CONFIG
    if _CACHED_APP_CONFIG is None:
        config = AppConfig.from_env()
        from src.folder_settings import apply_folder_settings

        apply_folder_settings(config, config.folder_path)
        _CACHED_APP_CONFIG = config
    return _CACHED_APP_CONFIG


def _get_tracker(folder: str) -> SimpleProcessingTracker:
    """Get a cached SimpleProcessingTracker instance for the given folder."""
    if folder not in _TRACKER_INSTANCE_CACHE:
        _TRACKER_INSTANCE_CACHE[folder] = SimpleProcessingTracker(folder)
    return _TRACKER_INSTANCE_CACHE[folder]


@contextmanager
def _db_session(folder):
    """Yield a FeaturesDatabase for *folder*, or None if no DB exists."""
    db_path = FeaturesDatabase.default_db_path(folder)
    if not db_path.exists():
        yield None
        return
    db = FeaturesDatabase(db_path)
    try:
        yield db
    finally:
        db.close()


def _get_extractor(host, port, model, backend, timeout, default_prompt):
    """Create and return an extractor with the given parameters.

    This is the canonical helper used across callback modules; import it
    rather than redefining a local ``_get_extractor``.
    """
    return create_extractor(
        backend=backend or "ollama",
        host=host or DEFAULT_LLM_HOST,
        port=int(port) if port else DEFAULT_LLM_PORT,
        model=model or DEFAULT_LLM_MODEL,
        timeout=int(timeout) if timeout else DEFAULT_LLM_TIMEOUT,
        default_prompt=default_prompt,
    )


# Sort keys offered in the gallery and fullscreen viewer are defined in
# ``src.constants`` and imported above for use by ``sort_paths``.


def _normalize_date(value: str | None) -> str:
    """Normalise an EXIF-style date for lexicographic comparison.

    ``"YYYY:MM:DD HH:MM:SS"`` becomes ``"YYYY-MM-DD HH:MM:SS"``. Empty values
    return a sentinel that sorts missing dates last (ascending order).
    """
    if not value:
        return "9999-12-31"
    return value.replace(":", "-")


def _get_sort_metadata(folder: str, paths: list[str]) -> dict[str, dict]:
    """Fetch sort-relevant metadata for *paths* from *folder*'s database."""
    if not folder or not paths:
        return {}
    with _db_session(folder) as db:
        if db is None:
            return {}
        return db.get_sort_metadata_batch(paths)


def sort_paths(
    paths: list[str],
    sort_key: str | None,
    folder: str | None,
    original_paths: list[str] | None = None,
    scores: dict[str, float] | None = None,
    order: str | None = None,
) -> list[str]:
    """Return *paths* reordered according to *sort_key* and *order*.

    Args:
        paths: Current ordering of the photo paths.
        sort_key: One of ``relevance``, ``date_taken``, ``date``, ``name``.
            ``None`` or an unknown key preserves the original result order.
        folder: Folder whose database supplies date metadata.
        original_paths: The search-result order (used by ``relevance`` to
            restore the original ordering). Defaults to *paths*.
        scores: Optional ``{path: score}`` mapping for ``relevance`` sort;
            when absent, ``relevance`` restores *original_paths* order.
        order: ``"asc"`` or ``"desc"``. ``None`` falls back to the natural
            default for *sort_key* (desc for relevance, asc otherwise).

    Returns:
        A new list of paths in the requested order. Photos whose date
        metadata is missing always sort to the end, regardless of direction.
    """
    base = list(original_paths) if original_paths is not None else list(paths)
    if order is None:
        order = default_order_for(sort_key)
    descending = order == SORT_ORDER_DESC

    if sort_key == SORT_KEY_RELEVANCE:
        if scores:
            # Ascending = lowest score first; descending = highest first.
            ascending = sorted(
                base,
                key=lambda p: (scores[p] if p in scores and scores[p] is not None else float("-inf")),
            )
            return list(reversed(ascending)) if descending else ascending
        return base

    if sort_key == SORT_KEY_NAME:
        ascending = sorted(base, key=lambda p: os.path.basename(p).lower())
        return list(reversed(ascending)) if descending else ascending

    if sort_key in (SORT_KEY_DATE_TAKEN, SORT_KEY_DATE):
        meta = _get_sort_metadata(folder or "", base)

        def date_val(path: str) -> str:
            m = meta.get(path) or {}
            if sort_key == SORT_KEY_DATE_TAKEN:
                return m.get("date_taken") or m.get("date_modified") or ""
            return m.get("date_modified") or m.get("date_taken") or ""

        # Partition so missing dates always sort last in either direction.
        present = [p for p in base if date_val(p)]
        missing = [p for p in base if not date_val(p)]
        present_sorted = sorted(
            present,
            key=lambda p: (_normalize_date(date_val(p)), os.path.basename(p).lower()),
        )
        if descending:
            present_sorted = list(reversed(present_sorted))
        return present_sorted + missing

    return base


def _open_modal(image_path, folder, index, paths, original_paths=None):
    """Open the detail modal for an image."""
    metadata = None
    embedding = None
    embedding_error = None

    with _db_session(folder) as db:
        if db is not None:
            try:
                metadata = db.get_feature_summary(image_path)

                # Check if there's an embedding_error in the metadata
                if metadata and metadata.get("embedding_error"):
                    embedding_error = metadata["embedding_error"]
                elif metadata and metadata.get("model_output"):
                    # Fallback: check model_output for embedding_error
                    model_output = metadata["model_output"]
                    if isinstance(model_output, dict) and model_output.get("embedding_error"):
                        embedding_error = model_output["embedding_error"]

                # Try to get embedding vector (only if we don't already have an error)
                if embedding_error is None:
                    try:
                        config = _get_app_config()

                        # Check if vector search library is available
                        vec_available = is_vector_search_available()

                        if vec_available:
                            embedding = db.get_embedding(image_path, config.embedding_model)
                        else:
                            # Vector search library not available, but try to get from metadata anyway
                            embedding = db.get_embedding(image_path, config.embedding_model)
                            if embedding is None:
                                embedding_error = (
                                    "sqlite-vec is not available. "
                                    "Embeddings saved to metadata only. "
                                    "Please install the required vector search library."
                                )
                    except RuntimeError as e:
                        # Vector search library not available - preserve the error message
                        embedding_error = f"Vector search not available: {e!s}"
                        logger.debug("Vector search library not available for %s: %s", image_path, e)
                    except Exception as e:
                        # Other error (e.g., embedding not found)
                        embedding_error = f"Failed to load embedding: {str(e)[:100]}"
                        logger.debug("Failed to load embedding for %s: %s", image_path, e)

                # Check if embedding metadata exists in image_embeddings table
                if embedding_error is None and embedding is None:
                    try:
                        config = _get_app_config()
                        if db.has_embedding(image_path, config.embedding_model):
                            # Embedding metadata exists but vector not available for search
                            vec_available = is_vector_search_available()

                            if vec_available:
                                # sqlite-vec library is available now but vector wasn't saved during processing
                                actual_error = None
                                if metadata and metadata.get("embedding_error"):
                                    actual_error = metadata.get("embedding_error")
                                elif (
                                    metadata
                                    and metadata.get("model_output")
                                    and isinstance(metadata.get("model_output"), dict)
                                ):
                                    actual_error = metadata["model_output"].get("embedding_error")

                                if actual_error:
                                    embedding_error = (
                                        f"Embedding metadata exists but vector not saved. "
                                        f"Original error: {actual_error}. "
                                        f"To fix: Re-process the image with a working embedding backend, "
                                        f"or use 'Store Vector in Database' to manually add the vector."
                                    )
                                else:
                                    embedding_error = (
                                        "Embedding metadata exists but vector not saved. "
                                        "sqlite-vec was not available during processing or embedding generation failed. "
                                        "To fix: Re-process the image or use 'Store Vector in Database' to manually add the vector."
                                    )
                            else:
                                # sqlite-vec library still not available
                                embedding_error = (
                                    "Embedding metadata saved but vector not available for similarity search. "
                                    "sqlite-vec is required for vector search. "
                                    "Please install the required vector search library."
                                )
                    except Exception as e:
                        logger.debug("Failed to load embedding metadata for %s: %s", image_path, e, exc_info=True)

                # If image was processed but no embedding and no error, it means embedding generation failed
                if embedding_error is None and embedding is None and metadata and metadata.get("success"):
                    try:
                        config = _get_app_config()
                        if config.embedding_enabled:
                            embedding_error = "Embedding was enabled during processing but no result was produced - check Ollama server and model support"
                    except Exception as e:
                        logger.debug("Failed to check embedding config for %s: %s", image_path, e, exc_info=True)
            except Exception:
                logger.warning("Failed to load metadata for %s", image_path, exc_info=True)

    content = build_detail_modal_content(image_path, folder, metadata, embedding, embedding_error)
    if original_paths is None:
        original_paths = paths
    return True, content, {"paths": paths, "original_paths": original_paths, "index": index}


def _open_fullscreen_content(image_path, folder, index, paths, original_paths=None):
    """Build the fullscreen viewer content and updated store for an image."""
    metadata = None
    embedding = None
    embedding_error = None

    with _db_session(folder) as db:
        if db is not None:
            try:
                metadata = db.get_feature_summary(image_path)

                # Try to get embedding vector
                try:
                    config = _get_app_config()

                    # Check if vector search library is available
                    vec_available = is_vector_search_available()

                    if vec_available:
                        embedding = db.get_embedding(image_path, config.embedding_model)
                    else:
                        # Try to get from metadata anyway
                        embedding = db.get_embedding(image_path, config.embedding_model)
                        if embedding is None:
                            embedding_error = "sqlite-vec is not available. Embeddings saved to metadata only."
                except RuntimeError as e:
                    # sqlite-vec library not available
                    embedding_error = f"sqlite-vec not available: {e!s}"
                    logger.debug("sqlite-vec library not available for %s: %s", image_path, e)
                except Exception as e:
                    # Other error (e.g., embedding not found)
                    embedding_error = f"Embedding not found: {str(e)[:100]}"
                    logger.debug("No embedding found for %s: %s", image_path, e)
            except Exception:
                logger.warning("Failed to load metadata for %s", image_path, exc_info=True)

    content = build_fullscreen_viewer(image_path, folder, metadata, embedding, embedding_error)
    if original_paths is None:
        original_paths = paths
    return content, {"paths": paths, "original_paths": original_paths, "index": index}
