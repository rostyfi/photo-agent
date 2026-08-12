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
VEC_NOT_INSTALLED = f"Vector search library (sqlite-vec) is not installed. {VEC_REQUIRED}"
VEC_EXTENSION_LOAD_AUTH = f"Vector search extension loading is not authorized. {VEC_REQUIRED}"
VEC_EXTENSION_NOT_FOUND = f"Vector search extension module cannot be found. {VEC_REQUIRED}"
VEC_LOAD_FAILED = lambda e: f"Vector search library (sqlite-vec) could not be loaded: {e}. {VEC_REQUIRED}"
VEC_NOT_AVAILABLE = f"Vector search library (sqlite-vec) is not available. {VEC_REQUIRED}"

# =============================================================================
# EMBEDDING-RELATED CONSTANTS
# =============================================================================

# Embedding generation error messages
EMBEDDING_GENERATION_RETURNED_NONE = (
    "Embedding generation returned None. Vector search library is required for vector search functionality."
)
EMBEDDING_UNAVAILABLE = (
    "Embedding generation unavailable - check Ollama server connection and model support"
)
EMBEDDING_NO_DESCRIPTION = (
    "No description available, cannot generate text embedding. "
    "Vector search library is required for vector search functionality."
)
EMBEDDING_NO_FOLDER_CONTEXT = (
    "Cannot save embedding without folder context. "
    "Vector search library is required for vector search functionality."
)

# =============================================================================
# DATABASE CONSTANTS
# =============================================================================

# Database table names
TABLE_RAW_FEATURES = "raw_features"
TABLE_EXTRACTED_FEATURES = "extracted_features"
TABLE_FEATURE_TAGS = "feature_tags"
TABLE_EXTRACTED_FEATURES_FTS = "extracted_features_fts"
TABLE_IMAGE_EMBEDDINGS = "image_embeddings"

# =============================================================================
# PROCESSING CONSTANTS
# =============================================================================

# Processing status values
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Processing error messages
PROCESSING_ERROR = "Processing error"

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Default configuration values
DEFAULT_LLM_HOST = "192.168.0.150"
DEFAULT_LLM_PORT = 11434
DEFAULT_LLM_TIMEOUT = 120
DEFAULT_LLM_MODEL = "gemma4:e2b-it-qat"

# =============================================================================
# LOGGING CONSTANTS
# =============================================================================

# Log messages
LOG_EMBEDDING_GENERATION = lambda path: f"Generating embedding for {path}"
LOG_EMBEDDING_SAVED = lambda path, model, dim: f"Saved embedding for {path} (model: {model}, dimension: {dim})"
LOG_EMBEDDING_FAILED = lambda path, e: f"Failed to generate embedding for {path}: {e}"
