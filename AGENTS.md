# Agent Instructions

## Project Overview

**Open Photo Agent** is a lightweight Python application for extracting structured features, descriptions, and metadata from photos using Ollama vision models over a local network.

It provides:
- A CLI tool (`main.py`) for single-image, multi-image, and recursive folder processing with simple database-based resume support.
- A **Dash web UI** (`app.py`) for server-side folder scanning and batch processing.
- A pluggable architecture for image format handling (HEIC/HEIF conversion included) and LLM backends (Ollama + dry-run).
- SQLite features database for structured data storage and fast querying.
- Batch state persistence for the web UI to survive restarts.
- A **sequential processing system** (`src/sequential_processor.py`) that handles image processing, metadata extraction, and embedding generation.
- A **simple processing tracker** (`src/simple_processing_tracker.py`) that replaces the complex WAL system with straightforward SQLite tracking.
- **Vector embedding support** with sqlite-vec for semantic search and similarity matching (sqlite-vec is recommended; REST-based fallback available).

## New Components (Code Simplification)

### Constants Module (`src/constants.py`)
- Centralized location for all repeated error messages and configuration defaults
- **`VEC_REQUIRED`**: Core message for sqlite-vec requirement
- **`EMBEDDING_*`**: Standardized embedding-related error messages
- **`VECTOR_SEARCH_*`**: Vector search error messages
- **`OLLAMA_VERSION_*`**: Ollama version requirements
- **`DEFAULT_*`**: Default configuration values
- **`STATUS_*`**: Processing status constants (`STATUS_COMPLETED`, `STATUS_FAILED`)
- **`TABLE_*`**: Database table names

### Services Package (`src/services/`)
- **`ChatService`** (`src/services/chat.py`): Centralized service for chat operations
  - Handles chat message processing with tool support
  - Delegates to specialized tool handlers
  - Manages conversation state

### Chat Tools Package (`src/services/chat_tools/`)
- **Tool-based architecture** for chat commands:
  - `about.py` - `/about` command to learn about the agent
  - `count.py` - `/count` command to count photos in a folder
  - `find.py` - `/find` command to find photos by description
  - `process.py` - `/process` command to process a folder
  - `scan.py` - `/scan` command to scan a folder
  - `status.py` - `/status` command to check processing status
  - `tools_tool.py` - `/tools` command to list available tools
  - `base.py` - Base tool class with registration decorator
- Tools are automatically discovered and registered via `loader.py`

### Sequential Processor (`src/sequential_processor.py`)
- **`SequentialProcessor`**: Main processing class providing:
  - Sequential processing of single files or lists of files
  - Simple database tracking of processed files
  - Automatic exclusion of already-processed files
  - Embedding generation and storage
  - Metadata extraction and storage
- **`process_image()`**: Standalone function for processing a single image
- **`process_paths()`**: Standalone function for processing multiple images
- Handles both LLM extraction and embedding generation in one workflow

### Simple Processing Tracker (`src/simple_processing_tracker.py`)
- **`SimpleProcessingTracker`**: Replaces complex WAL system with simple database-based tracking
  - Tracks which images have been processed in a SQLite table
  - Methods: `get_processed_files()`, `get_completed_files()`, `get_failed_files()`, `mark_completed()`, `mark_failed()`, `is_processed()`, `get_stats()`
  - Uses `processing_tracker` table in the features.db database
  - Maintains backward compatibility with existing `raw_features` table
  - Automatically invalidates cache when data changes

### Vector Search Package (`src/vector_search/`)
- **`availability.py`**: Checks if sqlite-vec extension is available and can be loaded
  - `is_vector_search_available()` - Check if vector search library is available
  - Comprehensive fallback strategies for different environments

### Embeddings Package (`src/embeddings/`)
- **`BaseEmbeddingGenerator`** (`src/embeddings/base.py`): Abstract base class for pluggable embedding backends
- **`OllamaEmbeddingGenerator`** (`src/embeddings/ollama.py`): Uses Ollama's `/api/embeddings` endpoint
  - Requires Ollama v0.1.0+
  - Supports multiple embedding models (nomic-embed-text, all-minilm, clip-vit-base-patch32)
- **`create_generator()`**: Factory function to create embedding generators
- **`list_embedding_backends()`**: List all registered embedding backends
- **`registry.py`**: Embedding backend registry

### Discovery Module (`src/discovery.py`)
- **`PhotoList`**: Discovers image files in directories
  - Recursive and non-recursive scanning
  - Caching of processed file sets with automatic invalidation
  - Filters already-processed images using SimpleProcessingTracker
- **`clear_processed_cache()`**: Remove cached processed-set data for a folder

### File Processing Module (`src/file_processing.py`)
- File-level processing utilities
- Handles file path resolution and validation

### API Module (`src/api/`)
- REST API handlers separated from app.py
- **`api_chat_handler()`**: Handles chat API requests with tool support

### Sidecar Package (`src/sidecar/`)
- **`AbstractSidecarStore`** (`src/sidecar/store.py`): Interface for sidecar persistence
- **`DatabaseSidecarStore`** (`src/sidecar/database/db.py`): Persists results to per-folder SQLite `features.db`
- **`FeaturesDatabase`** (`src/sidecar/database/db.py`): SQLite database schema and operations
  - `raw_features` table stores the full JSON result for every processed image
  - `extracted_features` normalised table with columns (`description`, `subjects`, `objects`, `colors`, `setting`, `mood`, `tags`)
  - `feature_tags` normalised 1:N tag table with index on `tag`
  - `extracted_features_fts` FTS5 virtual table for fast full-text search
  - `image_embeddings` metadata table for vector embeddings
  - `vec_embeddings` sqlite-vec virtual table for fast vector similarity search
  - `processing_tracker` simple tracking table replacing the WAL system
  - `image_metadata` EXIF, IPTC, and XMP metadata extracted from images
  - Vector storage and retrieval methods
  - Cosine similarity calculations for REST-based fallback

### Metadata Module (`src/metadata.py`)
- EXIF, IPTC, and XMP metadata extraction
- `extract_metadata_dict()`: Extract all metadata from an image file
- `extract_metadata()`: Lower-level metadata extraction
- Handles various image formats and metadata standards

### State Module (`src/state.py`)
- Global shutdown and job cancellation signals
- `request_shutdown()` / `is_shutdown_requested()`: Global shutdown event for the Dash UI Stop button
- `cancel_job(job_id)` / `is_job_cancelled(job_id)` / `clear_job_cancel(job_id)`: Per-job cancellation scoped to background threads

### Batch State Module (`src/batch_state.py`)
- Atomic read/write of batch progress to `<folder>/.open-photo-agent/`
- `write_batch_state(folder, status, total, completed, **extra)`: Atomic write of batch progress JSON
- `read_batch_state(folder)` / `clear_batch_state(folder)`: Read and clear batch state
- State files are stored at `<folder>/.open-photo-agent/batch_state.json`

### Utils Module (`src/utils.py`)
- `encode_image_file(image_path) -> str`: Reads image bytes via the plugin system, returns base64-encoded string
- `compute_duration_stats()`: Compute statistics from processing durations

## Architecture

```
.
├── main.py                      # CLI entry point: argument parsing, image discovery, coordinator
├── app.py                       # Dash web application bootstrap with REST API endpoints (including /_api/chat)
├── Dockerfile                   # Python 3.11 slim image with uv pip installer
├── docker-compose.yml           # Service definition with health check
├── docker-compose.override.yml  # Developer-specific volume mounts (git-ignored)
├── .dockerignore
├── requirements.txt             # Python deps: requests, python-dotenv, dash, dash-bootstrap-components, pillow, pillow-heif, diskcache
├── setup.sh                     # Bash convenience script: optional host folder mounting + docker compose up
├── setup.bat                    # Windows batch equivalent of setup.sh
├── .env.example                 # Template for environment variables
├── README.md                    # Human-facing documentation
├── src/
│   ├── __init__.py
│   ├── config.py                # AppConfig / ProcessingConfig dataclasses with env var loading + validation
│   ├── constants.py             # Centralized constants and error messages
│   ├── interfaces.py            # Core abstractions: BasePhotoExtractor, ProcessingResult, ErrorCode
│   ├── discovery.py             # PhotoList class: recursive image file discovery
│   ├── simple_processing_tracker.py  # Simple database-based processing tracker (replaces WAL)
│   ├── state.py                 # Thread-safe shutdown and per-job cancellation signals
│   ├── batch_state.py           # Atomic read/write of batch progress
│   ├── file_processing.py       # File processing utilities
│   ├── utils.py                 # encode_image_file(): base64 encoding via plugin system
│   ├── metadata.py               # EXIF/IPTC/XMP metadata extraction utilities
│   ├── sequential_processor.py # Main processing logic with SequentialProcessor
│   ├── api/                     # REST API handlers
│   │   ├── __init__.py          # Re-exports api_chat_handler
│   │   └── chat.py             # Chat API handler with tool support
│   ├── embeddings/              # Vector embedding support
│   │   ├── __init__.py          # Factory, re-exports, sqlite-vec requirement documentation
│   │   ├── base.py             # BaseEmbeddingGenerator abstract class
│   │   ├── ollama.py           # OllamaEmbeddingGenerator: uses /api/embeddings endpoint
│   │   └── registry.py         # Plugin registry for embedding backends
│   ├── vector_search/           # Vector search utilities
│   │   ├── __init__.py          # Re-exports
│   │   └── availability.py     # sqlite-vec availability checking
│   ├── sidecar/                 # Sidecar persistence package
│   │   ├── __init__.py          # Re-exports AbstractSidecarStore, DatabaseSidecarStore, FeaturesDatabase
│   │   ├── store.py             # AbstractSidecarStore interface, DatabaseSidecarStore
│   │   └── database/
│   │       ├── __init__.py      # Re-exports FeaturesDatabase
│   │       └── db.py            # FeaturesDatabase: SQLite schema + CRUD for raw_features + vector embeddings
│   ├── services/                # Service layer
│   │   ├── __init__.py          # Re-exports ChatService
│   │   ├── chat.py              # ChatService: centralized chat operations with tool support
│   │   └── chat_tools/          # Tool handlers for chat commands
│   │       ├── __init__.py      # Re-exports all tools
│   │       ├── loader.py        # Auto-discovery and registration of tools
│   │       ├── base.py          # BaseTool class with registration decorator
│   │       ├── about.py         # /about tool
│   │       ├── count.py         # /count tool
│   │       ├── find.py          # /find tool
│   │       ├── process.py       # /process tool
│   │       ├── scan.py          # /scan tool
│   │       ├── status.py        # /status tool
│   │       └── tools_tool.py    # /tools tool
│   ├── callbacks/               # Dash callbacks package
│   │   ├── __init__.py          # register_callbacks() + re-exports for backward compat
│   │   ├── common.py            # Shared helpers (_WAL_STATS_CACHE, _db_session, _run_batch_loop, etc.)
│   │   ├── errors.py            # Error handling callbacks
│   │   ├── folder.py            # Folder discovery & file-list toggle callbacks
│   │   ├── batch.py             # Batch processing, process-all, reprocess, stop, polling, history toggle callbacks
│   │   ├── health_settings.py   # Health check & settings modal callbacks
│   │   ├── prompt_tester.py      # Prompt tester feature callbacks
│   │   ├── chat.py              # Chat interface callbacks with Ollama
│   │   ├── similarity.py         # Vector similarity search callbacks
│   │   ├── sql_explorer.py      # SQL explorer callback
│   │   ├── search.py            # Full-text search callback
│   │   ├── tags.py              # Tag cloud load/render/toggle callbacks
│   │   ├── mode_toggle.py       # Mode toggle callbacks
│   │   ├── metadata_tester.py   # Metadata extraction testing callbacks
│   │   └── viewer.py            # Detail modal & fullscreen viewer callbacks
│   ├── components.py            # Dash UI component builders (folder controls, buttons, search results, tag cloud, detail modal, fullscreen viewer, similar photos, chat interface)
│   ├── layout_components.py     # Layout component utilities
│   └── layout.py                # Dash layout: Settings + Process Server Folder UI + Search Photos card + SQL Explorer + Tag Cloud + Chat + detail modal + fullscreen photo viewer modal
├── plugins/
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py          # Re-exports BasePhotoExtractor, OllamaPhotoExtractor, DryRunPhotoExtractor, create_extractor
│   │   ├── base.py              # Backward-compat re-export of src.interfaces
│   │   ├── ollama.py            # OllamaPhotoExtractor: Ollama client, retry logic, JSON parsing
│   │   ├── dry_run.py           # DryRunPhotoExtractor: no-op backend for testing
│   │   ├── chat.py              # OllamaChatClient: chat client for Ollama
│   │   ├── factory.py           # create_extractor(): auto-discovers LLM backends
│   │   ├── registry.py          # register_backend() / get_backend() / list_backends()
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── ollama/
│   │       │   └── __init__.py  # Auto-registers "ollama" backend
│   │       └── dry_run/
│   │           └── __init__.py  # Auto-registers "dry_run" backend
│   └── formats/
│       ├── __init__.py          # Re-exports read_image_bytes
│       ├── image.py             # read_image_bytes(): auto-discovers format plugins, dispatches via registry
│       ├── registry.py          # register_format() / get_reader(): extensible format reader registry
│       └── heic/
│           ├── __init__.py      # Auto-registers .heic/.heif readers via register_format()
│           └── converter.py     # HEIC to in-memory JPEG conversion (Pillow + pillow-heif)
│   └── embeddings/              # Vector embedding plugins
│       ├── __init__.py          # Re-exports and auto-discovery
│       └── backends/
│           ├── __init__.py      # Auto-discovers embedding backend packages
│           └── ollama/
│               └── __init__.py  # Auto-registers "ollama" embedding backend
├── tests/
│   ├── __init__.py
│   └── test_*.py                # Various test modules
├── assets/              # Static assets (CSS, etc.)
└── plan/                # Development planning documents
```

## Key Modules

- **`src.constants`**
  - Centralized constants and error messages to reduce duplication
  - `VEC_REQUIRED` — Core sqlite-vec requirement message
  - `EMBEDDING_*`, `VECTOR_SEARCH_*`, `LOG_*` — Standardized error and log messages
  - `DEFAULT_*` — Default configuration values
  - `STATUS_*` — Processing status constants (`STATUS_COMPLETED`, `STATUS_FAILED`)
  - `TABLE_*` — Database table names

- **`src.interfaces`**
  - `BasePhotoExtractor` (abstract base) — defines the interface for all LLM backends with three abstract methods: `extract()`, `extract_b64()`, `health_check()`.
  - `LLMChatClient` (abstract base) — defines the interface for chat clients with `chat()` and `health_check()` methods.
  - `ErrorCode` enum — `NETWORK_ERROR`, `TIMEOUT`, `INVALID_RESPONSE`, `FORMAT_NOT_SUPPORTED`, `PROCESSING_ERROR`.
  - `ProcessingResult` dataclass — value object for extraction outcomes with `as_dict()` for serialization.
  - `DEFAULT_PROMPT` — built-in default extraction prompt.
  - `make_error_result()` — factory for standardized failure dicts.

- **`plugins.llm.ollama.OllamaPhotoExtractor`**
  - `__init__(host, port, model, timeout=120, default_prompt=None, max_retries=3, backoff_factor=1.0)`.
  - `extract(image_path, prompt, options)` — returns `ProcessingResult`.
  - `extract_b64(image_b64, prompt, options)` — same but accepts base64 string.
  - `health_check()` — pings `/api/tags` with retry logic.
  - Strips markdown code fences from responses before JSON parsing.
  - `PhotoFeatureExtractor = OllamaPhotoExtractor` (alias for backward compatibility).

- **`plugins.llm.dry_run.DryRunPhotoExtractor`**
  - No-op backend that returns placeholder `ProcessingResult` without network calls.
  - Registered under backend name `"dry_run"`.
  - Useful for testing and CI.

- **`plugins.llm.ollama.OllamaChatClient`**
  - Chat client for Ollama that implements the `LLMChatClient` interface
  - Uses Ollama's `/api/chat` endpoint for conversational AI
  - Handles tool calling and message history

- **`plugins.llm.factory.create_extractor(backend, **kwargs)`**
  - Auto-discovers backend packages under `plugins.llm.backends` via `pkgutil`.
  - Raises `ValueError` if the requested backend is unknown.

- **`plugins.llm.registry`**
  - `register_backend(name, factory)` — registers an LLM backend factory.
  - `get_backend(name)` / `list_backends()` — runtime lookup.

- **`src.config.AppConfig`**
  - Master `@dataclass` with fields: `llm_host`, `llm_port`, `llm_model`, `llm_backend`, `dash_host`, `dash_port`, `dash_debug`, `timeout`, `default_prompt`, plus embedding configuration.
  - Embedding fields: `embedding_enabled`, `embedding_model`, `embedding_backend`, `similarity_limit`, `similarity_metric`.
  - `from_env()` classmethod loads `.env`, reads vars with `OPEN_PHOTO_AGENT_` prefix, falls back to legacy `OPEN_PHOTO_AGENT_OLLAMA_*` names with deprecation warnings.
  - `validate()` raises `ValueError` on bad ports / hosts / timeouts.
  - `to_processing_config()` returns a `ProcessingConfig` snapshot.

- **`src.config.ProcessingConfig`**
  - Slimmer config used by `SequentialProcessor` and CLI: `backend`, `host`, `port`, `model`, `timeout`, `default_prompt`, plus embedding configuration.

- **`src.discovery.PhotoList`**
  - `__init__(recursive=True, extensions=None)` — defaults to common image extensions (jpg, jpeg, png, webp, gif, bmp, tiff, tif, heic, heif).
  - `list_photos(paths, limit, exclude_processed_from)` — expands directories to flat file list, optionally excluding already-processed images by reading from the simple processing tracker.

- **`src.simple_processing_tracker.SimpleProcessingTracker`**
  - Simple database-based tracker replacing the complex WAL system
  - `__init__(folder)` — initializes tracker for a folder
  - `get_processed_files()` — returns set of all processed image paths
  - `get_completed_files()` — returns set of successfully completed image paths
  - `get_failed_files()` — returns list of failed files with error info
  - `mark_completed(image_path)` — marks an image as successfully processed
  - `mark_failed(image_path, error_code, error_msg)` — marks an image as failed
  - `is_processed(image_path)` — checks if an image has been processed
  - `get_stats()` — returns processing statistics
  - Uses `processing_tracker` table in the features.db database

- **`src.sequential_processor.SequentialProcessor`**
  - Top-level processor for sequential image processing
  - `__init__(extractor, config=None, embedding_enabled=True, folder=None)` — initializes with extractor, config, and folder
  - `process_image(image_path, prompt=None)` — processes a single image
  - `process_paths(paths, *, prompt=None, resume=True, progress_callback=None)` — processes multiple images
  - Handles embedding generation, metadata extraction, and result saving
  - Automatically initializes database and vector search when folder is provided

- **`src.sequential_processor.process_image()`** and **`process_paths()`**
  - Standalone functions for processing single images or lists of images
  - Wrap the SequentialProcessor for convenience

- **`src.sidecar.database.FeaturesDatabase`**
  - SQLite features database stored at `<folder>/.open-photo-agent/features.db`.
  - `raw_features` table stores the full JSON result blob (unchanged).
  - `extracted_features` normalised table with columns `description`, `subjects`, `objects`, `colors`, `setting`, `mood`, `tags` (all `TEXT`).
  - `feature_tags` normalised 1:N tag table with index on `tag`.
  - `extracted_features_fts` FTS5 virtual table (external content) indexing the above columns for fast full-text search.
  - `image_embeddings` — metadata table for embeddings (image_path, model_name, embedding_dimension, created_at) with UNIQUE constraint on (image_path, model_name).
  - `vec_embeddings` — sqlite-vec virtual table for fast vector similarity search (requires sqlite-vec).
  - `processing_tracker` — simple tracking table for processed files.
  - `image_metadata` — EXIF, IPTC, and XMP metadata extracted from images.
  - `search_features(query, limit=50)`, `get_features_by_tag(tag)`, `get_features_by_tags(tags)` (AND logic, case-insensitive), `list_all_tags()`, `list_tag_frequencies(limit=100)`, `get_feature_summary(image_path)`, `rebuild_fts_index()`.
  - **Vector methods:** `init_vector_search()`, `save_embedding()`, `get_embedding()`, `find_similar()`, `has_embedding()`, `delete_embedding()`, `get_all_embeddings()`, `get_embedding_dimension()`.
  - **REST-based fallback:** `find_similar_rest()` for Python-based cosine similarity when sqlite-vec is not available.
  - Graceful fallback: if FTS5 is unavailable in the SQLite build, the virtual table is skipped and search helpers return empty results.
  - WAL journal mode for concurrency.

- **`src.metadata`**
  - `extract_metadata_dict(image_path)` — extracts all metadata from an image file
  - `extract_metadata(image_path)` — lower-level metadata extraction
  - Handles EXIF, IPTC, and XMP metadata standards
  - Returns a dictionary with all available metadata

- **`src.embeddings`** (Vector embedding support)
  - `BaseEmbeddingGenerator` — abstract base class for pluggable embedding backends.
  - `OllamaEmbeddingGenerator` — uses Ollama's `/api/embeddings` endpoint (requires Ollama v0.1.0+).
  - `create_generator()` — factory function to create embedding generators.
  - `list_embedding_backends()` — list all registered embedding backends.
  - Known models: `nomic-embed-text` (768d, default), `all-minilm` (384d), `clip-vit-base-patch32` (512d).

- **`src.vector_search`**
  - `is_vector_search_available()` — Check if sqlite-vec extension can be loaded
  - Comprehensive fallback strategies for different environments

- **`src.services.ChatService`**
  - Centralized service for chat operations
  - Handles message processing with tool support
  - Manages conversation state and history
  - Uses dependency injection for chat client and config

- **`src.services.chat_tools`**
  - Tool-based architecture for chat commands
  - Each tool is a class that implements specific functionality
  - Tools are automatically discovered and registered via `@register_tool` decorator
  - Available tools: about, count, find, process, scan, status, tools

- **`src.utils`**
  - `encode_image_file(image_path) -> str` — reads image bytes via the plugin system, returns base64-encoded string.
  - `compute_duration_stats(durations)` — computes min/max/avg/total statistics from processing durations

- **`plugins.formats.registry`**
  - `register_format(extensions, reader)` — registers a reader callable for one or more file extensions.
  - `get_reader(suffix)` — looks up the reader for a given file extension.

- **`plugins.formats.image.read_image_bytes(image_path)`**
  - Uses `pkgutil` to auto-discover format sub-packages under `plugins.formats`.
  - Dispatches to registered format readers via the registry.
  - Falls back to raw binary read for unknown formats.
  - Never modifies originals.

- **`plugins.formats.heic`**
  - Auto-registers at import time: calls `register_format((".heic", ".heif"), _read_heic)`.
  - `convert_heic_to_jpeg_bytes(path)` — converts HEIC to in-memory JPEG (quality 95), preserves EXIF/ICC profile.
  - Re-exports `PIL_AVAILABLE` and `HEIF_AVAILABLE` availability flags.

- **`src.callbacks.prompt_tester`**
  - `register_prompt_tester_callbacks()` — Registers callbacks for prompt testing feature
  - Handles file upload, feature extraction, and result display for prompt evaluation
  - Includes raw response toggle and image preview

- **`src.callbacks.similarity`**
  - `register_find_similar_callback()` — Find similar photos for a given image
  - `register_similarity_search_callback()` — Upload an image and find similar photos
  - `register_embedding_status_callback()` — Check if embeddings are available for an image
  - `register_display_similar_photos_callback()` — Display similar photos in detail modal
  - `register_closest_photos_callback()` — Find closest photos by text description
  - `register_clear_closest_photos_callback()` — Clear closest photos results

- **`src.callbacks.errors`**
  - Error handling callbacks for the web UI

- **`app.py`**
  - Dash application bootstrap (`create_app()`).
  - Also registers Flask routes:
    - `/preview` — Serves resized image thumbnails with HEIC->JPEG fallback and strict path validation
    - `/_api/chat` — Chat with Ollama LLM with tool support
    - `/_api/find_similar` — Find similar images using REST-based vector search
    - `/_api/test_rest_vector_search` — Test endpoint to verify REST vector search is working
    - `/_api/test_vec` — Test storing vectors in database
    - `/_api/test_vector_roundtrip` — Test vector storage and retrieval
    - `/_api/store_vector` — Store a vector in the database (POST)
    - `/_api/get_vector` — Get a vector from the database (GET)

- **`src.layout`**
  - `create_layout()` builds the full Dash Bootstrap layout.
  - Contains a hidden `dbc.Modal` (`detail-modal`) with dynamic content container (`detail-modal-body`) and close button (`btn-close-detail`) for the photo detail view.
  - Contains a full-viewport `dbc.Modal` (`fullscreen-modal`) with a black background for high-resolution photo browsing, including navigation arrows, a close button, and a toggleable metadata overlay.
  - Includes prompt tester section with file upload and extraction controls
  - Includes vector search testing and storage controls
  - Tag Cloud card includes `dcc.Store(id="tag-cloud-data-store")` and `dcc.Store(id="selected-tags-store")`, a **Clear filters** button (`btn-tag-clear-all`), and a `selected-tags-bar` container for removable filter pills.

- **`src.components`**
  - `build_folder_controls()` renders a responsive grid of clickable image thumbnails with filename captions.
  - `build_detail_modal_content()` constructs the modal body with a large preview (`size=full`) and a read-out of extracted metadata fields (description, subjects, objects, colors, setting, mood, tags) or a "Not yet processed" placeholder.
  - `build_fullscreen_viewer()` builds the full-viewport photo viewer with centered image, prev/next navigation arrows, close button, and a toggleable semi-transparent metadata overlay showing description, subjects, and tags.
  - `build_tag_cloud(tags_with_counts, max_tags, selected_tags=[])` — builds a visual tag cloud with font sizes scaled by frequency; active tags in the chain are styled with `color="primary"`.
  - `build_selected_tags_bar(selected_tags)` — returns a row of removable `dbc.Badge` pills with small x buttons for clearing individual tags from the active chain.
  - `build_similar_photos_carousel(similar_data, folder)` — builds a carousel of similar photos with similarity scores.
  - `build_errors_display(errors, folder)` — displays processing errors in a formatted component.
  - `build_closest_photos_input()` — builds the input component for finding closest photos by text.

## Coding Standards

- **Language:** Python 3.10+; keep type hints on public methods (`Dict`, `List`, `Optional`, `Union`, `Path`).
- **Imports:** standard library -> third-party -> local plugins.
- **Logging:** use `logging.getLogger(__name__)`; never `print()` in library code.
- **Error handling:** catch `requests.exceptions.RequestException` in network calls; return structured `ProcessingResult` or `make_error_result()`.
- **Plugins (LLM backends):**
  - Subclass `BasePhotoExtractor` from `src.interfaces`.
  - Implement all three abstract methods.
  - Register via `plugins.llm.registry.register_backend()` in a sub-package under `plugins/llm/backends/<name>/__init__.py`.
  - The package is auto-discovered by `factory.py` via `pkgutil`.
- **Plugins (image formats):**
  - Create a sub-package under `plugins/formats/` (e.g. `plugins/formats/webp/`).
  - Implement a `read_*_bytes(path) -> bytes` function.
  - In your `__init__.py`, call `register_format()` from `plugins.formats.registry` to register your reader.
  - The module will be auto-discovered by `read_image_bytes()` via `pkgutil` — no manual import needed in `image.py`.
- **Plugins (embedding backends):**
  - Create a sub-package under `plugins/embeddings/backends/<name>/`.
  - Implement an embedding generator class that extends `BaseEmbeddingGenerator`.
  - In your `__init__.py`, call the appropriate registration function.
  - The module will be auto-discovered by the embedding registry.
- **Chat Tools:**
  - Create a new tool class in `src/services/chat_tools/`
  - Extend `BaseTool` and implement the `handle()` method
  - Use the `@register_tool` decorator to automatically register the tool
  - Tools are automatically discovered and loaded via `loader.py`
- **Configuration:** use `python-dotenv` via `AppConfig.from_env()` or `ProcessingConfig.from_env()`; never hard-code credentials.
- **Docker:** update `Dockerfile` if adding system libraries; keep `requirements.txt` as the single source of Python deps.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|---------|---------|-------------|
| `OPEN_PHOTO_AGENT_LLM_HOST` | `192.168.0.150` | LLM server hostname or IP |
| `OPEN_PHOTO_AGENT_LLM_PORT` | `11434` | LLM server port |
| `OPEN_PHOTO_AGENT_LLM_MODEL` | `gemma4:e2b-it-qat` | Vision model tag |
| `OPEN_PHOTO_AGENT_LLM_BACKEND` | `ollama` | LLM backend name (`ollama` or `dry_run`) |
| `OPEN_PHOTO_AGENT_LLM_TIMEOUT` | `600` | Request timeout in seconds |
| `OPEN_PHOTO_AGENT_DASH_HOST` | `127.0.0.1` | Web app bind address (`0.0.0.0` in Docker) |
| `OPEN_PHOTO_AGENT_DASH_PORT` | `8050` | Web app port |
| `OPEN_PHOTO_AGENT_DASH_DEBUG` | `false` | Enable Dash debug mode |
| `OPEN_PHOTO_AGENT_DEFAULT_PROMPT` | *(built-in)* | Override the default extraction prompt |
| `OPEN_PHOTO_AGENT_EMBEDDING_ENABLED` | `true` | Enable vector embedding generation |
| `OPEN_PHOTO_AGENT_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model to use |
| `OPEN_PHOTO_AGENT_EMBEDDING_BACKEND` | `ollama` | Embedding backend name |
| `OPEN_PHOTO_AGENT_SIMILARITY_LIMIT` | `10` | Number of similar results to return |
| `OPEN_PHOTO_AGENT_SIMILARITY_METRIC` | `cosine` | Similarity metric to use |

> **Deprecation note:** Legacy `OPEN_PHOTO_AGENT_OLLAMA_*` variables are still read as fallbacks but will emit a warning.

## Workflow for Agents

1. **Analyze:** Understand the user's request and how it maps to CLI, web UI, or plugin code.
2. **Plan:** Break complex tasks into steps. Update this file and `README.md` if behavior changes.
3. **Implement:** Make minimal, focused changes.
   - Prefer editing existing files over creating new ones.
   - Keep public interfaces backward-compatible.
4. **Validate:**
   - For CLI changes: `python main.py <test-image>` or `python main.py <folder>`.
   - For web changes: `python app.py`, visit `http://localhost:8050`, test folder processing.
   - For Docker changes: run `./setup.sh` (or `docker compose up -d --build`) and verify the app loads.
   - For tests: `python -m pytest tests/`.
5. **Commit:** Only create commits when explicitly asked. Do not push to remote unless requested.

## How to Run / Test

### Local (outside Docker)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# CLI single image
python main.py photo.jpg

# CLI folder (recursive) with custom prompt
python main.py ./my-photos --prompt "Return JSON with title and tags"

# CLI dry-run (skip LLM, write placeholder sidecars + tracking)
python main.py ./my-photos --dry-run

# CLI with resume disabled (force reprocess)
python main.py ./my-photos --no-resume

# CLI embeddings only
python main.py ./photos --embeddings-only

# CLI with embeddings disabled
python main.py ./photos --no-embeddings

# Find similar images
python main.py ./photos/photo1.jpg --find-similar --similar-limit 5

# List available embedding models
python main.py --list-embedding-models

# Web UI
python app.py
# Open http://localhost:8050

# Run tests
python -m pytest tests/
```

### Docker

```bash
# Quick start with optional host folder mount
./setup.sh /path/to/photos    # Linux/macOS
setup.bat "C:\path\to\photos" # Windows

# Or manually
docker compose up -d --build
# Visit http://localhost:8050
# Logs: docker compose logs -f
# Stop:  docker compose down
```

## SQLite Database Storage

Whenever an image inside a folder is processed, the result is stored in a SQLite database:

```
photos/
├── vacation.jpg
└── .open-photo-agent/
    ├── batch_state.json         # Batch processing progress (web UI)
    └── features.db            # SQLite database (raw + normalised data + tracking + embeddings)
```

The `features.db` SQLite database includes:
- `raw_features` — the full JSON result for every processed image
- `extracted_features` — normalised columns (`description`, `subjects`, `objects`, `colors`, `setting`, `mood`, `tags`) for fast querying
- `feature_tags` — one row per tag per image, enabling tag counts and filtering
- `extracted_features_fts` — FTS5 full-text index for searching descriptions and tags
- `image_embeddings` — metadata table for vector embeddings (image_path, model_name, embedding_dimension, created_at)
- `vec_embeddings` — sqlite-vec virtual table for fast vector similarity search (requires sqlite-vec)
- `processing_tracker` — simple tracking table replacing the WAL system (image_path, status, processed_at, error_code, error_msg)
- `image_metadata` — EXIF, IPTC, and XMP metadata extracted from images

## Communication

- Respond in the same language as the user's request.
- Provide concise explanations.
- Ask for clarification if requirements are unclear.
- Never diverge from the task goal; avoid unnecessary refactoring.

IMPORTANT: this context may or may not be relevant to your tasks. You should act on these guidelines if they are relevant to your task.