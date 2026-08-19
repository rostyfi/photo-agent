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
