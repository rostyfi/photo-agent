"""
Centralized constants and error messages for Local Photo Agent.

This module provides a single source of truth for all repeated strings,
particularly error messages and configuration defaults, to reduce
duplication and ensure consistency across the codebase.

Note: Some configuration defaults are defined in their respective modules:
- DEFAULT_EMBEDDING_MODEL is defined in src.embeddings.ollama
- PROCESSING_ERROR is part of ErrorCode enum in src.interfaces
"""

# =============================================================================
# VECTOR SEARCH CONSTANTS
# =============================================================================

# Core requirement message
VEC_REQUIRED = "Vector search library (sqlite-vec) is a HARD REQUIREMENT for vector search"

VEC_NOT_AVAILABLE = f"Vector search library (sqlite-vec) is not available. {VEC_REQUIRED}"

# =============================================================================
# EMBEDDING-RELATED CONSTANTS
# =============================================================================

# Embedding generation error messages
EMBEDDING_GENERATION_RETURNED_NONE = (
    "Embedding generation returned None. Vector search library is required for vector search functionality."
)
EMBEDDING_UNAVAILABLE = "Embedding generation unavailable - check Ollama server connection and model support"
EMBEDDING_NO_DESCRIPTION = (
    "No description available, cannot generate text embedding. "
    "Vector search library is required for vector search functionality."
)

# =============================================================================
# PROCESSING CONSTANTS
# =============================================================================

# Processing status values
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Default configuration values.
# The LLM host default is Ollama's conventional local bind address; override
# per deployment via the LOCAL_PHOTO_AGENT_LLM_HOST environment variable.
DEFAULT_LLM_HOST = "127.0.0.1"
DEFAULT_LLM_PORT = 11434
DEFAULT_LLM_TIMEOUT = 120
DEFAULT_LLM_MODEL = "gemma4:e2b-it-qat"

# Default number of images to process in parallel against the LLM backend.
# 1 preserves the historical strictly-sequential behaviour. Values >1 require
# the backend (e.g. Ollama) to be configured for concurrent requests
# (OLLAMA_NUM_PARALLEL / multi-slot); otherwise requests will queue server-side.
DEFAULT_BATCH_CONCURRENCY = 1

# When a chat result yields more than this many photos, the preview gallery is
# replaced by a single "Start slideshow" button that opens the fullscreen
# viewer. Override via LOCAL_PHOTO_AGENT_SLIDESHOW_THRESHOLD or the per-folder
# settings (Settings → Connection → Slideshow threshold).
DEFAULT_SLIDESHOW_THRESHOLD = 50

# =============================================================================
# PHOTO SORT CONSTANTS
# =============================================================================
# Sort keys offered by the preview-gallery and fullscreen-slideshow sort
# controls. ``relevance`` orders by the search score (descending) for /find
# results and otherwise preserves the search-result order; ``date_taken`` is
# the EXIF capture date; ``date`` is the file modification date; ``name`` is
# the file name.
SORT_KEY_RELEVANCE = "relevance"
SORT_KEY_DATE_TAKEN = "date_taken"
SORT_KEY_DATE = "date"
SORT_KEY_NAME = "name"
DEFAULT_SORT_KEY = SORT_KEY_RELEVANCE

SORT_OPTIONS = [
    {"label": "Relevance", "value": SORT_KEY_RELEVANCE},
    {"label": "Date taken", "value": SORT_KEY_DATE_TAKEN},
    {"label": "Date", "value": SORT_KEY_DATE},
    {"label": "Name", "value": SORT_KEY_NAME},
]

# Sort direction. Each sort key has a natural default: relevance is
# descending (best match first), the others are ascending (oldest/A-first).
SORT_ORDER_ASC = "asc"
SORT_ORDER_DESC = "desc"
DEFAULT_SORT_ORDER = SORT_ORDER_ASC

_DEFAULT_ORDER_BY_KEY = {
    SORT_KEY_RELEVANCE: SORT_ORDER_DESC,
    SORT_KEY_DATE_TAKEN: SORT_ORDER_ASC,
    SORT_KEY_DATE: SORT_ORDER_ASC,
    SORT_KEY_NAME: SORT_ORDER_ASC,
}


def default_order_for(sort_key: str | None) -> str:
    """Return the natural default sort direction for *sort_key*."""
    return _DEFAULT_ORDER_BY_KEY.get(sort_key or "", DEFAULT_SORT_ORDER)

# =============================================================================
# LOGGING CONSTANTS
# =============================================================================


# Log messages
def LOG_EMBEDDING_GENERATION(path):
    return f"Generating embedding for {path}"


def LOG_EMBEDDING_SAVED(path, model, dim):
    return f"Saved embedding for {path} (model: {model}, dimension: {dim})"


def LOG_EMBEDDING_FAILED(path, e):
    return f"Failed to generate embedding for {path}: {e}"
