"""
Common utilities and shared state for Dash callbacks.

This module provides shared helpers and mutable state used across multiple
callback modules to avoid code duplication.

The simplified approach:
- Simple sequential processing
- Database tracking via SimpleProcessingTracker
"""

import logging
from contextlib import contextmanager

from plugins.llm import create_extractor
from src.components import build_detail_modal_content, build_fullscreen_viewer
from src.config import AppConfig
from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL, DEFAULT_LLM_PORT, DEFAULT_LLM_TIMEOUT
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
    every invocation.
    """
    global _CACHED_APP_CONFIG
    if _CACHED_APP_CONFIG is None:
        _CACHED_APP_CONFIG = AppConfig.from_env()
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


def _make_processing_config(
    host,
    port,
    model,
    backend,
    timeout,
    default_prompt,
    dry_run=False,
    app_config=None,
    embedding_enabled=True,
    embedding_model=None,
    embedding_backend=None,
):
    """Build a ProcessingConfig from loosely-typed form/state values.

    This is the canonical helper used across callback modules; import it
    rather than redefining a local ``_make_processing_config``.

    Args:
        host: LLM server host
        port: LLM server port
        model: LLM model name
        backend: LLM backend name
        timeout: Request timeout in seconds
        default_prompt: Default extraction prompt
        dry_run: If True, use dry_run backend
        app_config: Optional AppConfig to draw embedding/similarity defaults from
        embedding_enabled: Override for the embedding toggle (default True)
        embedding_model: Override for embedding model (falls back to app_config)
        embedding_backend: Override for embedding backend (falls back to app_config)
    """
    if app_config is not None:
        emb_model = embedding_model or app_config.embedding_model
        emb_backend = embedding_backend or app_config.embedding_backend
        similarity_limit = app_config.similarity_limit
        similarity_metric = app_config.similarity_metric
    else:
        emb_model = embedding_model or "nomic-embed-text"
        emb_backend = embedding_backend or "ollama"
        similarity_limit = 10
        similarity_metric = "cosine"

    from src.config import ProcessingConfig

    return ProcessingConfig(
        backend="dry_run" if dry_run else (backend or "ollama"),
        host=host or DEFAULT_LLM_HOST,
        port=int(port) if port else DEFAULT_LLM_PORT,
        model=model,
        timeout=int(timeout) if timeout else DEFAULT_LLM_TIMEOUT,
        default_prompt=default_prompt,
        embedding_enabled=bool(embedding_enabled) if embedding_enabled is not None else True,
        embedding_model=emb_model,
        embedding_backend=emb_backend,
        similarity_limit=similarity_limit,
        similarity_metric=similarity_metric,
    )


def _open_modal(image_path, folder, index, paths):
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
    return True, content, {"paths": paths, "index": index}


def _open_fullscreen_content(image_path, folder, index, paths):
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
    return content, {"paths": paths, "index": index}
