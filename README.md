# Open Photo Agent

A lightweight Python application for extracting structured features, descriptions, and metadata from photos using Ollama vision models over a local network.

## Features

- Connect to an Ollama instance via configurable host/port
- Extract structured features from single or multiple images
- **Process entire folders (recursive or flat) from the CLI**
- **Process entire server-side folders via the web UI**
- Support for custom prompts and model options
- Automatic JSON parsing of model responses
- Batch processing with progress logging and resume support
- **Simple database-based tracking** — replaces complex WAL system with straightforward SQLite tracking
- Health check to verify Ollama availability
- **Metadata extraction** — automatic EXIF, IPTC, and XMP metadata extraction from images
- **Visual thumbnail previews** in the web UI — browse folder contents, search results, and tag-cloud results with image thumbnails; click any thumbnail to open a detail modal with a larger preview and extracted metadata.
- **Fullscreen photo viewer** — from the detail modal, open a full-viewport viewer with navigation arrows, keyboard controls, and a toggleable metadata overlay for high-resolution browsing.
- **Web-based UI via Dash** for drag-and-drop image processing
- **Full-text search (FTS5)** over extracted descriptions, subjects, tags, and more from the web UI
- **Tag cloud browsing** — visually explore photos by tag frequency, then click tags to chain multiple filters together with AND logic. Active filters appear as removable pills and the result set narrows to only photos containing every selected tag. Changing folder clears the chain.
- **Vector embedding support** — generate vector embeddings for images using Ollama's `/api/embeddings` endpoint and find visually similar photos using cosine similarity with sqlite-vec
- **Find Similar** — click "Find Similar" in the detail modal or fullscreen viewer to discover visually similar images in your collection
- **Semantic search** — upload an image to find similar photos in your collection via the web UI
- **Closest Photos** — type a natural language description (e.g., "a dog running on the beach") to find the top 10 most semantically similar photos in the current folder using vector embeddings
- **Chat with Ollama** — interact directly with your Ollama LLM via a simple chat interface in the web UI; use `/about` to learn about the agent
- **Chat API** — REST endpoint at `POST /_api/chat` for programmatic access to the LLM

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose installed (optional)
- A running Ollama server (local or on the network)
- A vision-capable model pulled in Ollama (e.g., `gemma4:e2b-it-qat`)

### Vector Embedding Requirements (Optional)

**Vector search and similarity features have two modes:**

#### Mode 1: sqlite-vec (Recommended for Production)

For best performance with large datasets, use sqlite-vec:

1. **sqlite-vec (RECOMMENDED)** — SQLite extension for fast vector search
   ```bash
   pip install sqlite-vec
   ```

2. **Ollama v0.1.0+** — For the `/api/embeddings` endpoint
   ```bash
   ollama --version  # Check your version
   # Upgrade if needed by following Ollama's upgrade instructions
   ```

3. **Embedding model** — Pull an embedding-capable model:
   ```bash
   ollama pull nomic-embed-text  # Default, 768 dimensions
   # or
   ollama pull all-minilm       # 384 dimensions
   ```

#### Mode 2: REST-based Vector Search (Fallback - No sqlite-vec Required)

If sqlite-vec cannot be installed (e.g., in Docker containers without extension loading support), the application automatically falls back to REST-based vector search:

- **No sqlite-vec required** — Uses Python-based cosine similarity calculations
- **Works in Docker** — Tested in the open-photo-agent container
- **Slower for large datasets** — Loads all embeddings into memory for comparison
- **Same functionality** — All vector search features work identically

**REST API Endpoint:**
```
POST /_api/find_similar
{
    "folder": "/path/to/folder",
    "query": "text description",  // OR
    "vector": [0.123, 0.456, ...],  // OR
    "image_path": "/path/to/image.jpg",
    "model_name": "nomic-embed-text",
    "limit": 10
}
```

**Test Endpoint:**
```
GET /_api/test_rest_vector_search
```

This returns a status report confirming REST vector search is working.

Or use alternative embedding models:
```bash
ollama pull clip-vit-base-patch32  # 512 dimensions
```

## Quick Start with Docker

Run the one-command setup script:

```bash
# Start the app without mounting a folder
./setup.sh

# Start the app and mount a host folder into /photos in the container
./setup.sh /path/to/your/photos
```

Then open [http://localhost:8050](http://localhost:8050).

**Tip:** When you pass a folder to `setup.sh`, it automatically creates a temporary `docker-compose.override.yml` that mounts your folder into the container as `/photos`. This makes it easy to process that folder via the web UI by entering `/photos` in the **Process Server Folder** field.

### Manual Docker commands

```bash
# Build and start the container
docker compose up -d --build

# View logs
docker compose logs -f

# Stop the container
docker compose down
```

**Note:** Update `OPEN_PHOTO_AGENT_OLLAMA_HOST` in your `.env` file or `docker-compose.yml` if your Ollama server is on a different IP.

### Mounting a folder for processing inside Docker

If you want to process photos that live on the host via the **Process Server Folder** web UI, mount them into the container:

```yaml
volumes:
  - /path/on/host:/photos
```

Then enter `/photos` in the folder path field on the web page.

## Command-Line Usage

The `main.py` script accepts individual files **or folders**.

```bash
# Process a single image
python main.py photo.jpg

# Process multiple images
python main.py photo1.jpg photo2.png

# Process an entire folder (recursive by default)
python main.py ./my-vacation-photos

# Process a folder without recursion
python main.py ./my-vacation-photos --no-recursive

# Save results to a JSON file
python main.py ./photos --output results.json

# Resume a previously interrupted batch (skip already-processed images)
python main.py ./photos --resume

# Force reprocess all images, ignoring previous progress
python main.py ./photos --no-resume

# Control batch size (images per batch; 0 = no limit)
python main.py ./photos --batch-size 50

# Vector embedding options
# Generate embeddings (enabled by default)
python main.py ./photos

# Disable embedding generation
python main.py ./photos --no-embeddings

# Use a specific embedding model
python main.py ./photos --embedding-model all-minilm

# Only generate embeddings (skip LLM extraction)
python main.py ./photos --embeddings-only

# Find similar images to a specific photo
python main.py ./photos/photo1.jpg --find-similar --similar-limit 5

# List available embedding models from Ollama
python main.py --list-embedding-models

# Generate embeddings for existing photos (without reprocessing)
python main.py ./photos --embeddings-only
```

Supported image extensions: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.tiff`, `.tif`

### SQLite Database Storage

Whenever the app processes an image inside a folder, the result is stored in a local SQLite `features.db`.

```
my-photos/
├── vacation.jpg
└── .open-photo-agent/
    ├── batch_state.json       # Web UI batch progress summary
    └── features.db            # SQLite database (raw + normalised data + tracking)
```

The `features.db` SQLite database includes:
- `raw_features` — the full JSON result for every processed image.
- `extracted_features` — normalised columns (`description`, `subjects`, `objects`, `colors`, `setting`, `mood`, `tags`) for fast querying.
- `feature_tags` — one row per tag per image, enabling tag counts and filtering.
- `extracted_features_fts` — FTS5 full-text index (external content) for searching descriptions and tags.
- `image_embeddings` — metadata table for vector embeddings (image_path, model_name, embedding_dimension, created_at)
- `vec_embeddings` — sqlite-vec virtual table for fast vector similarity search (requires sqlite-vec)
- `processing_tracker` — simple tracking table replacing the WAL system (image_path, status, processed_at, error_code, error_msg)
- `image_metadata` — EXIF, IPTC, and XMP metadata extracted from images

**Note:** Vector embeddings are stored in SQLite for efficiency.

## Web UI Usage

Open [http://localhost:8050](http://localhost:8050) after starting the app.

1. **Settings**: Enter the LLM host, port, model, and **Batch Size** (images processed per batch).
2. **Upload Images**: Drag & drop or select files, then click **Extract Features**
3. **Process Server Folder**: Type an absolute folder path (e.g. `/photos`), optionally tick *Scan sub-folders*, then click **Process Folder**.  
   The folder must be readable by the server/container running the app.

   **Database storage:** When processing a folder via the web UI, results are stored in a SQLite `features.db` database inside `.open-photo-agent/` in the same folder.
4. **Search Photos** (below SQL Explorer): After processing a folder, use the search card to find photos by description, subjects, or tags via full-text search.
5. **Tag Cloud** (below Search Photos): After processing a folder, click **Load Tag Cloud** to see a visual cloud of all extracted tags sized by frequency. Click any tag to add it as an active filter, then click additional tags to narrow the results with **AND** semantics. Active filters appear as removable pill badges above the cloud. Click a pill (or the tag again) to remove it, or press **Clear filters** to reset the chain. Changing the folder automatically clears the tag chain. Click any thumbnail to open the detail modal or fullscreen viewer — navigation arrows will only cycle through the currently filtered subset.
6. **Closest Photos** (below Tag Cloud): Enter a natural language description (e.g., "a dog running on the beach") and click **Find Similar** to discover the top 10 most semantically similar photos in the current folder using vector embeddings. Each result shows a similarity percentage. Click any thumbnail to open the detail modal or fullscreen viewer.
7. **SQL Explorer**: Run raw SQL queries against the per-folder `features.db` SQLite database for advanced exploration.
8. **Metadata Tester**: Test metadata extraction from uploaded images to verify EXIF, IPTC, and XMP data extraction.

### Vector Embedding Features in Web UI

- **Find Similar** — In the photo detail modal, click "Find Similar" to display a carousel of visually similar images with similarity scores
- **Fullscreen Similar** — In the fullscreen viewer, click "Find Similar" to find and navigate through similar photos
- **Embedding Status** — The detail modal shows whether an embedding is available for the current image
- **Closest Photos** — Type a natural language query to find semantically similar photos by description using vector embeddings
- **Performance** — Similarity search typically completes in <500ms for collections of 10,000+ images (using sqlite-vec)

> **Preview & Detail Modal:** When you scan a folder, the file list appears as a grid of clickable thumbnails. Click any thumbnail (in the folder grid, search results, or tag-cloud results) to open a modal with a larger image preview and the extracted metadata (description, subjects, objects, colors, setting, mood, tags). If an image has not been processed yet, the modal shows a "Not yet processed" placeholder.
>
> **Fullscreen Viewer:** From the detail modal, click the **Fullscreen** button to open a full-viewport photo browser with a black background. Use the left/right arrow buttons (or keyboard arrow keys) to navigate through the album. A **Toggle Info** button shows or hides a semi-transparent overlay with the extracted description, subjects, and tags. You can also press **`i`** on the keyboard to toggle the overlay when the fullscreen viewer is open.

## REST API Endpoints

The web application (`app.py`) provides several REST API endpoints for programmatic access:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/preview?path=<path>&size=<size>` | Get a resized image thumbnail (supports HEIC/HEIF conversion) |
| POST | `/_api/chat` | Send a chat message to Ollama and get a response |
| POST | `/_api/find_similar` | Find similar images using vector embeddings |
| GET | `/_api/test_rest_vector_search` | Test REST-based vector search functionality |
| GET | `/_api/test_vec` | Test vector storage in database |
| GET | `/_api/test_vector_roundtrip` | Test vector storage and retrieval |
| POST | `/_api/store_vector` | Store a vector embedding in the database |
| GET | `/_api/get_vector` | Retrieve a vector embedding from the database |
| GET | `/_api/test_vec_db` | Check vector database status |

### Chat API Example

```bash
curl -X POST http://localhost:8050/_api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Describe this photo", "images": ["base64_encoded_image"]}'
```

Response:
```json
{
  "response": "This is a beautiful landscape photo with...",
  "model": "gemma4:e2b-it-qat",
  "done": true
}
```

### Find Similar API Example

```bash
curl -X POST http://localhost:8050/_api/find_similar \
  -H "Content-Type: application/json" \
  -d '{"folder": "/path/to/photos", "image_path": "/path/to/query.jpg", "limit": 5}'
```

## Usage as a Library

If you want to use the extractor in your own Python scripts (outside Docker):

```bash
pip install -r requirements.txt
```

```python
from plugins.llm import create_extractor

extractor = create_extractor(
    host="192.168.0.150",
    port=11434,
    model="gemma4:e2b-it-qat",
)

result = extractor.extract("photo.jpg")
print(result.as_dict())
```

### Batch processing from code

```python
from plugins.llm import create_extractor
from src.config import ProcessingConfig
from src.sequential_processor import process_paths

extractor = create_extractor(host="192.168.0.150", port=11434, model="gemma4:e2b-it-qat")
config = ProcessingConfig.from_env()  # Or specify individual parameters

# Process multiple images sequentially
results = process_paths(
    ["photo1.jpg", "photo2.jpg"],
    extractor,
    prompt="Describe this photo",
    resume=False
)

for result in results["results"]:
    print(result.get("image_path"), result.get("success"))
```

You can also discover and process a whole folder:

```python
from src.discovery import PhotoList
from src.sequential_processor import process_paths

# Discover all images in a folder
photo_list = PhotoList(recursive=True)
image_paths = photo_list.list_photos(["./my-photos"])

# Process all discovered images
results = process_paths(image_paths, extractor, resume=True)
print(f"Processed {results['processed']} images, {results['successes']} succeeded")
```

## Project Structure

```
.
├── main.py              # Core extractor module + CLI entry point
├── app.py               # Dash web application with REST API endpoints
├── Dockerfile           # Docker image definition
├── Dockerfile.arm       # ARM-specific Docker image
├── docker-compose.yml   # Docker Compose configuration
├── docker-compose.arm.yml # ARM-specific compose config
├── .dockerignore        # Files excluded from Docker build
├── entrypoint.sh        # Container entrypoint script
├── requirements.txt     # Python dependencies
├── .env.example         # Configuration template
├── setup.sh             # One-command Docker setup & run (Linux/macOS)
├── setup-arm.sh         # ARM-specific setup script
├── setup.bat            # Windows setup script
├── src/                 # Core application modules
│   ├── __init__.py
│   ├── config.py        # AppConfig / ProcessingConfig with env var loading
│   ├── constants.py     # Centralized constants and error messages
│   ├── interfaces.py    # BasePhotoExtractor, ProcessingResult, ErrorCode
│   ├── discovery.py     # PhotoList: recursive image file discovery
│   ├── utils.py         # Utility functions (image encoding, etc.)
│   ├── state.py         # Global shutdown and job cancellation signals
│   ├── batch_state.py   # Batch progress state persistence
│   ├── sequential_processor.py # Sequential image processing
│   ├── simple_processing_tracker.py # Simple database-based processing tracker
│   ├── metadata.py       # EXIF/IPTC/XMP metadata extraction
│   ├── file_processing.py # File processing utilities
│   ├── sidecar/         # Sidecar persistence
│   │   ├── __init__.py
│   │   ├── store.py     # AbstractSidecarStore
│   │   └── database/    # FeaturesDatabase (SQLite)
│   │       ├── __init__.py
│   │       └── db.py
│   ├── embeddings/       # Vector embedding support
│   │   ├── __init__.py
│   │   ├── base.py       # BaseEmbeddingGenerator
│   │   ├── ollama.py     # OllamaEmbeddingGenerator
│   │   └── registry.py   # Embedding backend registry
│   ├── vector_search/    # Vector search utilities
│   │   ├── __init__.py
│   │   └── availability.py # sqlite-vec availability checking
│   ├── services/         # Service layer
│   │   ├── __init__.py
│   │   └── chat.py       # Chat service
│   ├── callbacks/        # Dash UI callbacks
│   │   ├── __init__.py
│   │   ├── batch.py      # Batch processing callbacks
│   │   ├── chat.py       # Chat interface callbacks
│   │   ├── common.py     # Shared callback helpers
│   │   ├── errors.py     # Error handling callbacks
│   │   ├── folder.py     # Folder discovery callbacks
│   │   ├── health_settings.py # Health check & settings
│   │   ├── metadata_tester.py # Metadata extraction testing
│   │   ├── mode_toggle.py # Mode toggle callbacks
│   │   ├── prompt_tester.py # Prompt testing callbacks
│   │   ├── search.py     # Full-text search callback
│   │   ├── similarity.py  # Vector similarity callbacks
│   │   ├── sql_explorer.py # SQL explorer callback
│   │   ├── tags.py       # Tag cloud callbacks
│   │   └── viewer.py     # Detail modal & fullscreen viewer
│   ├── components.py     # Dash UI component builders
│   ├── layout_components.py # Layout component utilities
│   └── layout.py         # Main Dash application layout
├── plugins/             # Plugin system
│   ├── __init__.py
│   ├── llm/              # LLM backend plugins
│   │   ├── __init__.py
│   │   ├── base.py       # Backward-compat re-exports
│   │   ├── ollama.py     # OllamaPhotoExtractor
│   │   ├── dry_run.py    # DryRunPhotoExtractor
│   │   ├── factory.py    # create_extractor() factory
│   │   ├── registry.py   # Backend registration
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── ollama/
│   │       │   └── __init__.py
│   │       └── dry_run/
│   │           └── __init__.py
│   └── formats/          # Image format plugins
│       ├── __init__.py
│       ├── image.py      # read_image_bytes() with auto-discovery
│       ├── registry.py   # Format reader registry
│       └── heic/
│           ├── __init__.py
│           └── converter.py # HEIC/HEIF to JPEG conversion
│   └── embeddings/       # Embedding backend plugins
│       ├── __init__.py
│       └── backends/
│           ├── __init__.py
│           └── ollama/
│               └── __init__.py
├── assets/              # Static assets (CSS, etc.)
├── tests/               # Unit and integration tests
│   ├── __init__.py
│   └── test_*.py        # Various test modules
├── plan/                # Development planning documents
└── README.md            # This file
```

## Supported Image Formats

Any format your local environment can read (commonly `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.tiff`, `.tif`), plus **HEIC / HEIF** (Apple iPhone photos) through on-the-fly JPEG conversion for both processing and web previews.

### HEIC / HEIF support

Processing `.heic`/`.heif` files requires two extra Python packages:

```bash
pip install pillow pillow-heif
```

They are already listed in `requirements.txt`, so installing from there is enough.

When a HEIC image is processed or previewed in the web UI, it is automatically converted to a high-quality JPEG **in memory** before being sent to Ollama or the browser. No originals are modified.

## Notes

- The default prompt asks the model to return JSON. Not all models will strictly obey; check `result["parsed"]`.
- You can override the default prompt with any custom text via the `--prompt` CLI argument, the web UI text area, or the `prompt` parameter in code.
- When processing large folders, consider potential memory usage from base64 encoding many images at once.
- The application now uses a **simplified processing tracker** (`SimpleProcessingTracker`) that stores tracking information directly in the SQLite database instead of using WAL files.
- **Automatic resume**: By default, the CLI will skip already-processed images on consecutive runs (use `--no-resume` to force reprocessing).

## Code Organization

The codebase follows a clean architecture with:

- **`src/constants.py`** — Centralized constants and error messages to reduce duplication (e.g., `VEC_REQUIRED`, `STATUS_COMPLETED`, `STATUS_FAILED`)
- **`src/config.py`** — Configuration dataclasses with environment variable loading and validation
- **`src/interfaces.py`** — Core abstractions: `BasePhotoExtractor`, `ProcessingResult`, `ErrorCode` enum
- **`src/sequential_processor.py`** — Main processing logic with `SequentialProcessor` class handling image processing, metadata extraction, and embedding generation
- **`src/simple_processing_tracker.py`** — Simple database-based tracking replacing the complex WAL system
- **`src/metadata.py`** — EXIF, IPTC, and XMP metadata extraction utilities
- **`src/services/chat.py`** — Chat service for Ollama interaction
- **`src/embeddings/`** — Vector embedding support with pluggable backends
- **`src/vector_search/`** — Vector search utilities and availability checking
- **`src/sidecar/database/db.py`** — SQLite database schema and operations via `FeaturesDatabase`
- **Pluggable architecture** — LLM backends (`plugins/llm/`) and image format handlers (`plugins/formats/`) can be added via plugins
- **Clean separation** — CLI processing (`main.py`) vs Web UI (`app.py` with callbacks)
- **Centralized constants** — All repeated strings and messages in `src/constants.py`

### Key Design Principles

- **Dependency injection** — Services and extractors are passed to components that need them
- **Pluggable backends** — Add new LLM providers or embedding generators via the plugin system
- **Progressive enhancement** — Works without sqlite-vec (with fallback), without embeddings, without metadata
- **Backward compatibility** — SQLite database structure supports existing data
- **Separation of concerns** — CLI, Web UI, and core processing logic are cleanly separated

This organization reduces code duplication and makes the codebase easier to maintain and extend.
