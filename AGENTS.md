# Agent Instructions

## Project Context

**Local Photo Agent** is a Python application for extracting structured features, descriptions, and metadata from photos using Ollama vision models. It includes a CLI tool (`main.py`), a Dash web UI (`app.py`), and a pluggable architecture for LLM backends and image format handling.

For detailed project documentation, see `README.md`.

## Agent Workflow

1. **Analyze:** Understand the user's request and how it maps to CLI, web UI, or plugin code.
2. **Plan:** Break complex tasks into steps. Update `README.md` if behavior changes.
3. **Implement:** Make minimal, focused changes.
   - Prefer editing existing files over creating new ones.
   - Keep public interfaces backward-compatible.
4. **Validate:**
   - For CLI changes: `python main.py <test-image>` or `python main.py <folder>`.
   - For web changes: `python app.py`, visit `http://localhost:8050`, test folder processing.
   - For Docker changes: run `./setup.sh` (or `docker compose up -d --build`) and verify the app loads.
   - For tests: `python -m pytest tests/`.
5. **Commit:** Only create commits when explicitly asked. Do not push to remote unless requested.

## Coding Standards

- **Language:** Python 3.10+; use type hints on public methods (`Dict`, `List`, `Optional`, `Union`, `Path`).
- **Imports:** standard library -> third-party -> local plugins.
- **Logging:** use `logging.getLogger(__name__)`; never `print()` in library code.
- **Error handling:** catch `requests.exceptions.RequestException` in network calls; return structured `ProcessingResult` or `make_error_result()`.

### Plugin Development

- **LLM backends:** Subclass `BasePhotoExtractor` from `src.interfaces`, implement `extract()`, `extract_b64()`, `health_check()`, register via `plugins.llm.registry.register_backend()` in `plugins/llm/backends/<name>/__init__.py`. Auto-discovered by `factory.py` via `pkgutil`.
- **Image format plugins:** Create package under `plugins/formats/<name>/`, implement `read_*_bytes(path) -> bytes`, call `register_format()` from `plugins.formats.registry` in `__init__.py`. Auto-discovered by `read_image_bytes()`.
- **Embedding backends:** Create package under `plugins/embeddings/backends/<name>/`, extend `BaseEmbeddingGenerator`, register in `__init__.py`. Auto-discovered by embedding registry.
- **Chat Tools:** Create class in `src/services/chat_tools/`, extend `BaseTool`, implement `handle()`, use `@register_tool` decorator. Auto-discovered via `loader.py`.

### Configuration

Use `python-dotenv` via `AppConfig.from_env()` or `ProcessingConfig.from_env()`. Never hard-code credentials.

Environment variables (full details in `README.md`):

| Variable | Default | Purpose |
|---------|---------|---------|
| `LOCAL_PHOTO_AGENT_LLM_HOST` | `127.0.0.1` | LLM server hostname |
| `LOCAL_PHOTO_AGENT_LLM_PORT` | `11434` | LLM server port |
| `LOCAL_PHOTO_AGENT_LLM_MODEL` | `gemma4:e2b-it-qat` | Vision model tag |
| `LOCAL_PHOTO_AGENT_LLM_BACKEND` | `ollama` | LLM backend (`ollama`, `dry_run`) |
| `LOCAL_PHOTO_AGENT_LLM_TIMEOUT` | `600` | Request timeout (seconds) |
| `LOCAL_PHOTO_AGENT_DASH_HOST` | `127.0.0.1` | Web app bind address |
| `LOCAL_PHOTO_AGENT_DASH_PORT` | `8050` | Web app port |
| `LOCAL_PHOTO_AGENT_DASH_DEBUG` | `false` | Enable Dash debug mode |
| `LOCAL_PHOTO_AGENT_EMBEDDING_ENABLED` | `true` | Enable vector embeddings |
| `LOCAL_PHOTO_AGENT_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `LOCAL_PHOTO_AGENT_EMBEDDING_BACKEND` | `ollama` | Embedding backend |
| `LOCAL_PHOTO_AGENT_REVEAL_MAP` | _(empty)_ | Map server/container path prefixes to host paths for the "Copy Path" feature (`container_prefix=host_prefix`, semicolon/newline-separated) |

> **Note:** Legacy `LOCAL_PHOTO_AGENT_OLLAMA_*` variables are deprecated but still supported with warnings.

### Key Modules Reference

| Module | Purpose |
|--------|---------|
| `src/config.py` | `AppConfig`, `ProcessingConfig` dataclasses with env var loading |
| `src/constants.py` | Centralized constants (`VEC_REQUIRED`, `STATUS_*`, `TABLE_*`, etc.) |
| `src/interfaces.py` | `BasePhotoExtractor`, `ProcessingResult`, `ErrorCode` abstractions |
| `src/sequential_processor.py` | `SequentialProcessor`, `process_image()`, `process_paths()` |
| `src/simple_processing_tracker.py` | `SimpleProcessingTracker` for SQLite-based progress tracking |
| `src/sidecar/database/db.py` | `FeaturesDatabase` — SQLite schema and operations |
| `src/services/chat.py` | `ChatService` — centralized chat operations with tool support |
| `src/services/chat_tools/` | Tool handlers (`/about`, `/count`, `/find`, `/process`, `/scan`, `/status`, `/tools`) |
| `src/embeddings/` | `BaseEmbeddingGenerator`, `OllamaEmbeddingGenerator`, registry |
| `src/metadata.py` | EXIF, IPTC, XMP extraction utilities |
| `src/discovery.py` | `PhotoList` — recursive image file discovery |
| `plugins/llm/` | LLM backend plugins (Ollama, dry-run) and factory |
| `plugins/formats/` | Image format plugins (HEIC/HEIF conversion) |

### Database Schema Reference

The per-folder SQLite database (`<folder>/.local-photo-agent/features.db`) contains:

- `raw_features` — full JSON result for each image
- `extracted_features` — normalized columns (description, subjects, objects, colors, setting, mood, tags)
- `feature_tags` — 1:N tag table with index on `tag`
- `extracted_features_fts` — FTS5 full-text search index
- `image_embeddings` — vector embedding metadata
- `vec_embeddings` — sqlite-vec virtual table (if available)
- `processing_tracker` — processed file tracking
- `image_metadata` — EXIF, IPTC, XMP metadata

## Communication

- Respond in the same language as the user's request.
- Provide concise explanations.
- Ask for clarification if requirements are unclear.
- Never diverge from the task goal; avoid unnecessary refactoring.
- See `README.md` for user-facing feature documentation.

## Important Notes

- The default prompt asks the model to return JSON. Not all models strictly obey; check `result["parsed"]`.
- When processing large folders, consider memory usage from base64 encoding many images at once.
- Automatic resume: CLI skips already-processed images by default (use `--no-resume` to force reprocessing).
- The app uses a simplified processing tracker (`SimpleProcessingTracker`) with SQLite instead of WAL files.
- Vector embeddings require sqlite-vec for optimal performance; REST-based fallback is available.

IMPORTANT: For all project documentation (features, usage, API endpoints, setup instructions), see `README.md`.
