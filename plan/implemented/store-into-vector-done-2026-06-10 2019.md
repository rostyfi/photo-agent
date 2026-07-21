# store-into-vector

> **Status:** Approved  
> **Created:** 2026-06-10 18:45:45  
> **Last Updated:** 2026-06-10  
> **Priority:** High  
> **Complexity:** Medium  
> **Decisions:** All E2E implementation, Ollama-only backend, Binary BLOB storage, Cosine similarity, sqlite-vss (hard requirement), User will reload all photos, No embeddings in sidecar JSON, Default model: clip-vit-base-patch32, Ollama v0.1.0+ required

---

## Overview

Add **vector embedding support** to Open Photo Agent, enabling semantic search and similarity matching across photo collections. This feature extends the existing SQLite-based feature storage with a dedicated vector embeddings table and sqlite-vss integration, allowing users to find visually similar images, perform semantic searches, and enable advanced AI-powered features.

**sqlite-vss is a hard requirement** - the system will not function without it for vector search operations.

## Motivation

### Problem Statement
Currently, Open Photo Agent stores structured text features (description, subjects, tags, etc.) and supports full-text search via FTS5. However, text-based search has limitations:
- Cannot find **visually similar** images (e.g., "show me more photos like this sunset")
- Cannot perform **semantic similarity** searches based on image content
- Tags and descriptions are subjective and may not capture all visual nuances
- Misses opportunities for advanced features: clustering, deduplication, recommendations

### Why Vector Embeddings?
Vector embeddings are numerical representations of image content that capture semantic meaning in a high-dimensional space. Similar images have similar vectors, enabling:
- **Semantic search**: Find images similar to a query image or text description
- **Visual similarity**: Discover photos with similar colors, composition, or subjects
- **Clustering**: Group similar photos automatically
- **Deduplication**: Identify near-duplicate images
- **Hybrid search**: Combine text and vector search for better results

### Use Cases
1. **"Find similar photos"** - User selects an image, system returns visually similar ones
2. **"Search by example"** - Upload an image to find matching photos in the collection
3. **"More like this"** - Recommendation engine for photo browsing
4. **Smart albums** - Automatic grouping of similar photos
5. **Duplicate detection** - Identify and flag near-duplicate images

## Requirements

### Functional Requirements

- [ ] **Vector Generation**: Generate embeddings for images using Ollama vision models
  - Configurable embedding model (e.g., models that support embedding output)
  - Batch embedding generation for photo collections
  - Integration with existing image processing pipeline

- [ ] **Vector Storage**: Store embeddings efficiently in SQLite with sqlite-vss
  - New `image_embeddings` table with vector data
  - Binary BLOB storage for efficiency
  - sqlite-vss virtual table for fast similarity search (hard requirement)
  - Support for multiple embedding models per image (future-proofing)

- [ ] **Similarity Search**: Find similar images using cosine similarity via sqlite-vss
  - Configurable top-K results
  - Hybrid search combining text and vector queries (optional, future)

- [ ] **CLI Support**
  - `--no-embeddings` flag to disable embedding generation
  - `--embedding-model` to specify which model to use
  - `--find-similar` to find similar images from CLI

- [ ] **Web UI Support**
  - "Find Similar" button on photo detail view
  - Similar photos carousel/grid display
  - Visual similarity search interface

### Non-Functional Requirements

- [ ] **sqlite-vss is a hard requirement** - System must have sqlite-vss installed and available
- [ ] **Performance**: Similarity search should complete in <500ms for collections of 10,000 images (using sqlite-vss)
- [ ] **Storage Efficiency**: Store vectors as binary blobs (not JSON text)
- [ ] **Ollama Version**: Requires Ollama v0.1.0+ (for `/api/embeddings` endpoint support)

## Design / Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Open Photo Agent                             │
├─────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  Image      │    │  LLM        │    │  Embedding      │  │
│  │  Processing │───▶│  Extractor  │───▶│  Generator       │  │
│  │  Pipeline   │    │  (Ollama)   │    │  (Ollama)        │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│           │                  │                    │            │
│           └──────────────────┴────────────────────┘            │
│                        │                                   │
│                        ▼                                   │
│              ┌─────────────────────────┐                     │
│              │   FeaturesDatabase       │                     │
│              │  (SQLite + sqlite-vss)   │◄── HARD REQUIREMENT   │
│              │  - raw_features          │                     │
│              │  - extracted_features     │                     │
│              │  - feature_tags          │                     │
│              │  - image_embeddings      ◄─── NEW              │
│              │  - vss_embeddings    ◄──── NEW (virtual)     │
│              └─────────────────────────┘                     │
│                        │                                   │
│                        ▼                                   │
│              ┌─────────────────────────┐                     │
│              │   Search & Query Layer   │                     │
│              │  - Text search (FTS5)    │                     │
│              │  - Vector search    ◄────┼── NEW (sqlite-vss)  │
│              │  - Hybrid search    ◄────┼── FUTURE            │
│              └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. Embedding Generation

**New Module**: `src/embeddings/`

```
src/embeddings/
├── __init__.py          # Re-exports
├── base.py             # Abstract base class for embedding generators
├── ollama.py           # Ollama-based embedding generator
└── registry.py         # Plugin registry for future backends
```

**Interface**:
```python
class BaseEmbeddingGenerator(ABC):
    """Abstract base for pluggable embedding backends."""
    
    @abstractmethod
    def generate(self, image_path: Union[str, Path]) -> Optional[List[float]]:
        """Generate embedding vector for an image."""
        ...
    
    @abstractmethod
    def generate_b64(self, image_b64: str) -> Optional[List[float]]:
        """Generate embedding vector from base64 image."""
        ...
    
    @abstractmethod
    def dimension(self, model_name: str) -> int:
        """Return the embedding dimension size for a given model."""
        ...
    
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        ...
```

**Ollama Implementation** (`src/embeddings/ollama.py`):
- Uses Ollama's `/api/embeddings` endpoint
- **Requires Ollama v0.1.0+** (documented requirement)
- Handles image encoding and API communication
- Implements retry logic and error handling
- Known working models: `clip-vit-base-patch32` (512 dim), `all-minilm` (384 dim), `nomic-embed-text` (768 dim)

#### 2. Vector Storage with sqlite-vss (Hard Requirement)

**Database Schema Changes** (`src/sidecar/database/db.py`):

```sql
-- Table for storing embedding metadata
CREATE TABLE IF NOT EXISTS image_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    model_name TEXT NOT NULL,          -- e.g., "clip-vit-base-patch32"
    embedding_dimension INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(image_path, model_name)     -- One embedding per model per image
);

-- Indexes for metadata table
CREATE INDEX IF NOT EXISTS idx_image_embeddings_path ON image_embeddings(image_path);
CREATE INDEX IF NOT EXISTS idx_image_embeddings_model ON image_embeddings(model_name);

-- sqlite-vss virtual table for fast vector search (HARD REQUIREMENT)
-- This table MUST exist for vector search to work
CREATE VIRTUAL TABLE IF NOT EXISTS vss_embeddings USING vss0(
    image_path TEXT PRIMARY KEY,
    embedding FLOAT[]
);
```

**Storage Format**:
- Vectors stored as **binary BLOB** in `image_embeddings` table (for metadata and fallback)
- Vectors also stored in `vss_embeddings` virtual table (for fast search via sqlite-vss)
- Each float is 4 bytes (32-bit IEEE 754)
- **Embeddings are NOT stored in sidecar JSON files** (decision: keep SQLite as single source of truth for vectors)

**Helper Methods** (add to `FeaturesDatabase`):
```python
# Initialize vector search - REQUIRES sqlite-vss
# Will raise an exception if sqlite-vss is not available
def init_vector_search(self) -> None:
    """Load sqlite-vss extension. Raises RuntimeError if not available."""
    ...

# Save embedding to both metadata and vss index
def save_embedding(self, image_path: str, model_name: str, vector: List[float]) -> None:
    """Save embedding to both image_embeddings table and vss_embeddings virtual table."""
    ...

# Get embedding
def get_embedding(self, image_path: str, model_name: str) -> Optional[List[float]]:
    """Retrieve embedding vector from vss_embeddings."""
    ...

# Delete embedding
def delete_embedding(self, image_path: str, model_name: str) -> None:
    """Remove embedding from both tables."""
    ...

# Similarity search using sqlite-vss (cosine similarity)
def find_similar(
    self, 
    query_vector: List[float], 
    limit: int = 10
) -> List[Tuple[str, float]]:
    """
    Find images similar to the query vector using cosine similarity.
    Returns list of (image_path, similarity_score) tuples, sorted by score DESC.
    Requires sqlite-vss to be available.
    """
    ...

# Get all embeddings for a model
def get_all_embeddings(self, model_name: str) -> List[Tuple[str, List[float]]]:
    """Retrieve all embeddings for a specific model."""
    ...

# Check if embeddings exist for an image
def has_embedding(self, image_path: str, model_name: str) -> bool:
    """Check if an embedding exists for the given image and model."""
    ...

# Get embedding dimension for a model
def get_embedding_dimension(self, model_name: str) -> Optional[int]:
    """Get the dimension size for a given embedding model."""
    ...
```

#### 3. Integration with Existing Pipeline

**Configuration** (`src/config.py`):
```python
@dataclass
class ProcessingConfig:
    """Immutable configuration for an LLM processing run."""
    
    # ... existing fields ...
    
    # New fields for embeddings
    embedding_enabled: bool = True  # Enabled by default
    embedding_model: str = "clip-vit-base-patch32"  # Default model
    embedding_backend: str = "ollama"  # Only Ollama supported
    similarity_limit: int = 10
    similarity_metric: str = "cosine"  # Only cosine supported
```

**Environment Variables**:
```bash
# Enable/disable embedding generation (default: true)
OPEN_PHOTO_AGENT_EMBEDDING_ENABLED=true

# Embedding model to use (default: clip-vit-base-patch32)
OPEN_PHOTO_AGENT_EMBEDDING_MODEL=clip-vit-base-patch32

# Embedding backend (currently only ollama supported)
OPEN_PHOTO_AGENT_EMBEDDING_BACKEND=ollama

# Number of similar results to return (default: 10)
OPEN_PHOTO_AGENT_SIMILARITY_LIMIT=10

# Similarity metric (currently only cosine supported)
OPEN_PHOTO_AGENT_SIMILARITY_METRIC=cosine
```

**Modified Processing Flow**:
```
1. Image discovered by PhotoList
2. Image processed by ImageProcessor (LLM extraction)
3. If embedding_enabled (default: True):
   a. Generate embedding using OllamaEmbeddingGenerator
   b. Save to image_embeddings table AND vss_embeddings virtual table
   c. (Embeddings NOT saved to sidecar JSON - SQLite only)
4. Save extraction results to raw_features (existing)
5. Save to sidecar JSON (existing, without embeddings)
```

**Modified Files**:
- `src/config.py` - Add embedding configuration
- `src/coordinator/coordinator.py` - Integrate embedding generation
- `src/coordinator/processor.py` - Add embedding step after LLM extraction
- `src/sidecar/database/db.py` - Add embedding storage and sqlite-vss search
- `src/sidecar/__init__.py` - Export new embedding functions

#### 4. CLI Integration

**New CLI Options** (`main.py`):
```bash
# Process with embeddings (default: enabled)
python main.py ./photos

# Disable embedding generation
python main.py ./photos --no-embeddings

# Specify embedding model
python main.py ./photos --embedding-model all-minilm

# Find similar images (new command)
python main.py ./photos/photo1.jpg --find-similar --limit 5

# Generate embeddings only for existing photos
python main.py ./photos --embeddings-only

# List available embedding models from Ollama
python main.py --list-embedding-models
```

**CLI Command Structure**:
```
main.py [IMAGE_PATHS/FOLDER] [OPTIONS]

Options:
  --no-embeddings          Disable embedding generation
  --embedding-model MODEL  Specify embedding model (default: clip-vit-base-patch32)
  --find-similar            Find similar images to the first input image
  --similar-limit N        Number of similar images to return (default: 10)
  --embeddings-only         Only generate embeddings, skip LLM extraction
  --list-embedding-models  List available embedding models from Ollama
```

#### 5. Web UI Integration

**New UI Components**:

1. **Detail Modal Enhancement** (`src/components.py`):
   - Add "Find Similar" button next to existing actions
   - Add similar photos carousel below the main image
   - Show similarity scores as percentages

2. **Fullscreen Viewer Enhancement**:
   - Add "Find Similar" button to fullscreen viewer
   - Navigation to similar photos

**New Callbacks** (`src/callbacks/`):

1. **`similarity.py`** (new file):
   ```python
   def register_find_similar_callback(app, db_factory):
       """Register callback to find similar photos for a given image."""
       ...
   
   def register_similarity_search_callback(app, db_factory):
       """Register callback for image-based similarity search."""
       ...
   
   def register_embedding_status_callback(app, db_factory):
       """Register callback to check embedding generation status."""
       ...
   ```

2. **Modify `viewer.py`**:
   - Add callback for "Find Similar" button in detail modal
   - Add callback for "Find Similar" button in fullscreen viewer

3. **Modify `components.py`**:
   - Add `build_similar_photos_carousel(images_with_scores)` component
   - Modify `build_detail_modal_content()` to include similar photos section
   - Modify `build_fullscreen_viewer()` to add "Find Similar" button

4. **Modify `layout.py`**:
   - Add similar photos section to detail modal layout
   - Add hidden div for storing current image path

### Files to Modify

```
# Configuration
src/config.py
  - Add embedding_enabled, embedding_model, embedding_backend, similarity_limit, similarity_metric to ProcessingConfig
  - Add same fields to AppConfig
  - Add environment variable parsing for embedding settings
  - Add validation for embedding parameters

# Database
src/sidecar/database/db.py
  - Add image_embeddings table schema
  - Add vss_embeddings virtual table creation
  - Add sqlite-vss extension loading (HARD REQUIREMENT - will raise if not available)
  - Implement save_embedding(), get_embedding(), find_similar() methods
  - Implement delete_embedding(), has_embedding(), get_all_embeddings() methods
  - Add binary vector serialization/deserialization helpers

src/sidecar/__init__.py
  - Export new embedding-related functions

# Coordinator
src/coordinator/coordinator.py
  - Add embedding configuration to BatchCoordinator
  - Pass embedding config through to ImageProcessor
  - Add embedding generation to run_folder_batch() and run_paths_batch()

src/coordinator/processor.py
  - Import OllamaEmbeddingGenerator
  - Add generate_embedding() method
  - Modify process_image() to generate and save embeddings when enabled

src/coordinator/saver.py
  - No changes needed (embeddings stored directly to DB, not via saver)

# Main CLI
main.py
  - Add --no-embeddings, --embedding-model flags
  - Add --find-similar, --similar-limit flags
  - Add --embeddings-only flag
  - Add --list-embedding-models flag
  - Add embedding generation logic to CLI processing
  - Add find_similar command implementation

# Web UI
app.py
  - No changes needed (uses callbacks)

src/callbacks/__init__.py
  - Import and register new similarity callbacks

src/callbacks/similarity.py (NEW)
  - register_find_similar_callback() - Find similar photos for displayed image
  - register_similarity_search_callback() - Search by uploaded image
  - register_embedding_status_callback() - Check if embeddings exist

src/callbacks/viewer.py
  - Modify register_detail_modal_callback() to handle "Find Similar" clicks
  - Modify register_fullscreen_open_callback() to include similar photos data

src/components.py
  - Add build_similar_photos_carousel() - Create carousel of similar photos
  - Modify build_detail_modal_content() - Add similar photos section
  - Modify build_fullscreen_viewer() - Add "Find Similar" button

src/layout.py
  - Add similar photos section to detail modal layout
  - Add dcc.Store for similar photos data

# New Modules
src/embeddings/
  ├── __init__.py
  │   - Re-export BaseEmbeddingGenerator, OllamaEmbeddingGenerator, create_generator
  │   - Document sqlite-vss hard requirement
  ├── base.py
  │   - BaseEmbeddingGenerator abstract class
  ├── ollama.py
  │   - OllamaEmbeddingGenerator implementation
  │   - Uses /api/embeddings endpoint
  │   - Requires Ollama v0.1.0+
  │   - Handles image encoding and API communication
  │   - Implements retry logic and error handling
  │   - Known models: clip-vit-base-patch32 (default), all-minilm, nomic-embed-text
  └── registry.py
      - register_embedding_backend() / get_embedding_backend()
      - Auto-discovery of embedding backends (for future extensibility)

# Tests
tests/
  ├── test_embeddings.py (NEW)
  │   - Test OllamaEmbeddingGenerator
  │   - Test embedding generation with mocked Ollama
  │   - Test dimension validation
  │   - Test error handling
  │   - Test sqlite-vss requirement check
  ├── test_vector_search.py (NEW)
  │   - Test sqlite-vss integration
  │   - Test find_similar() accuracy with known vectors
  │   - Test cosine similarity
  │   - Test edge cases (empty DB, single image, etc.)
  │   - Test error when sqlite-vss not available
  └── test_db.py (EXTEND)
      - Test image_embeddings table creation
      - Test vss_embeddings virtual table creation
      - Test save_embedding() and get_embedding()
      - Test find_similar() with known vectors
      - Test binary vector storage/retrieval
      - Test UNIQUE constraint on (image_path, model_name)

plan/store-into-vector.md (this file)
```

### Database Changes

**New Tables**:

```sql
-- Metadata table for embeddings
CREATE TABLE IF NOT EXISTS image_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    model_name TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(image_path, model_name)
);

-- Indexes for metadata table
CREATE INDEX IF NOT EXISTS idx_image_embeddings_path ON image_embeddings(image_path);
CREATE INDEX IF NOT EXISTS idx_image_embeddings_model ON image_embeddings(model_name);

-- sqlite-vss virtual table for fast vector search (HARD REQUIREMENT)
-- This virtual table is REQUIRED for vector search functionality
CREATE VIRTUAL TABLE IF NOT EXISTS vss_embeddings USING vss0(
    image_path TEXT PRIMARY KEY,
    embedding FLOAT[]
);
```

**Note on sqlite-vss**:
- The extension MUST be loaded at runtime
- Loading: `conn.enable_load_extension(True)` then `conn.load_extension("vss")`
- The virtual table name (`vss0`) is the standard for sqlite-vss
- If sqlite-vss is not available, vector search operations will raise an exception

### API Changes

**New Python API**:

```python
# Configuration
from src.config import ProcessingConfig
config = ProcessingConfig.from_env()

# Generate embeddings
from src.embeddings import create_generator

generator = create_generator(
    backend="ollama",
    host=config.host,
    port=config.port,
    model=config.embedding_model
)

# Generate embedding for an image
embedding = generator.generate("photo.jpg")  # Returns List[float] or None

# Database operations
from src.sidecar.database import FeaturesDatabase
db = FeaturesDatabase("/photos/.open-photo-agent/features.db")

# Initialize vector search - will raise if sqlite-vss not available
db.init_vector_search()

# Save embedding
db.save_embedding("photo.jpg", "clip-vit-base-patch32", embedding)

# Find similar images
similar = db.find_similar(query_embedding, limit=10)
# Returns: [("photo1.jpg", 0.95), ("photo2.jpg", 0.92), ...]

# Check if embedding exists
has_emb = db.has_embedding("photo.jpg", "clip-vit-base-patch32")
```

## Implementation Steps (All E2E)

### Step 1: Core Embedding Infrastructure

1. **Create embedding module**
   - [ ] Create `src/embeddings/` directory with `__init__.py`
   - [ ] Implement `BaseEmbeddingGenerator` abstract class in `base.py`
   - [ ] Implement `OllamaEmbeddingGenerator` in `ollama.py`
   - [ ] Document Ollama v0.1.0+ requirement
   - [ ] Document sqlite-vss hard requirement
   - [ ] Implement plugin registry in `registry.py`
   - [ ] Create factory function `create_generator()` in `__init__.py`

2. **Add embedding configuration**
   - [ ] Extend `ProcessingConfig` in `src/config.py`
   - [ ] Extend `AppConfig` in `src/config.py`
   - [ ] Add environment variable support
   - [ ] Add validation for embedding parameters
   - [ ] Document all requirements

### Step 2: Database Extension with sqlite-vss

3. **Extend database schema**
   - [ ] Add `image_embeddings` table to `FeaturesDatabase`
   - [ ] Add sqlite-vss extension loading with error handling
   - [ ] Add `vss_embeddings` virtual table creation
   - [ ] Implement `init_vector_search()` - raises if sqlite-vss not available
   - [ ] Implement `save_embedding()` method
   - [ ] Implement `get_embedding()` method
   - [ ] Implement `find_similar()` method using sqlite-vss
   - [ ] Implement `delete_embedding()`, `has_embedding()`, `get_all_embeddings()`
   - [ ] Add binary vector serialization helpers

### Step 3: Processing Pipeline Integration

4. **Integrate with coordinator**
   - [ ] Modify `BatchCoordinator` to accept embedding configuration
   - [ ] Pass embedding config through to `ImageProcessor`

5. **Modify image processor**
   - [ ] Import `OllamaEmbeddingGenerator`
   - [ ] Add `generate_embedding()` method
   - [ ] Modify `process_image()` to generate and save embeddings when enabled

### Step 4: CLI Integration

6. **Add CLI options**
   - [ ] Add `--no-embeddings` flag
   - [ ] Add `--embedding-model` flag
   - [ ] Add `--find-similar` command
   - [ ] Add `--similar-limit` flag
   - [ ] Add `--embeddings-only` flag
   - [ ] Add `--list-embedding-models` flag

7. **Implement CLI logic**
   - [ ] Add embedding generation to folder processing
   - [ ] Add embedding generation to single image processing
   - [ ] Implement `--find-similar` command
   - [ ] Implement `--embeddings-only` command
   - [ ] Implement `--list-embedding-models` command

### Step 5: Web UI Integration

8. **Create UI components**
   - [ ] Add `build_similar_photos_carousel()` in `components.py`
   - [ ] Modify `build_detail_modal_content()` to include similar photos
   - [ ] Modify `build_fullscreen_viewer()` to add "Find Similar" button

9. **Update layout**
    - [ ] Add similar photos section to detail modal in `layout.py`
    - [ ] Add dcc.Store for similar photos data

10. **Create callbacks**
    - [ ] Create `src/callbacks/similarity.py`
    - [ ] Implement `register_find_similar_callback()`
    - [ ] Implement `register_similarity_search_callback()`
    - [ ] Implement `register_embedding_status_callback()`

11. **Register callbacks**
    - [ ] Import and register new callbacks in `src/callbacks/__init__.py`
    - [ ] Modify existing callbacks if needed

### Step 6: Testing

12. **Unit tests**
    - [ ] Create `tests/test_embeddings.py`
    - [ ] Create `tests/test_vector_search.py`
    - [ ] Extend `tests/test_db.py` with embedding tests

13. **Integration tests**
    - [ ] Test embedding generation during batch processing
    - [ ] Test CLI `--find-similar` command
    - [ ] Test CLI `--embeddings-only` command
    - [ ] Test Web UI similar photos display

14. **Manual smoke tests**
    - [ ] Process folder with embeddings via CLI
    - [ ] Verify embeddings in database
    - [ ] Test similarity search via CLI
    - [ ] Process folder via Web UI with embeddings
    - [ ] Test "Find Similar" in Web UI

15. **Requirements validation**
    - [ ] Verify sqlite-vss hard requirement is enforced
    - [ ] Verify Ollama v0.1.0+ requirement is documented
    - [ ] Verify performance meets <500ms for 10K images

## Testing Plan

### Unit Tests

**`tests/test_embeddings.py`**:
```python
class TestOllamaEmbeddingGenerator:
    def test_generate_embedding(self, mock_ollama):
        # Test embedding generation with mocked Ollama
        ...
    
    def test_generate_b64(self, mock_ollama):
        # Test embedding from base64
        ...
    
    def test_dimension(self):
        # Test dimension reporting for different models
        assert generator.dimension("clip-vit-base-patch32") == 512
        assert generator.dimension("all-minilm") == 384
        ...
    
    def test_error_handling(self, mock_ollama_error):
        # Test error handling
        ...

class TestCreateGenerator:
    def test_creates_ollama_generator(self):
        # Test factory function
        ...
    
    def test_requires_ollama_v010(self):
        # Test that Ollama version requirement is checked
        ...
```

**`tests/test_vector_search.py`**:
```python
class TestVectorSearch:
    def test_save_and_retrieve_embedding(self, tmpdir):
        # Test saving and retrieving embeddings
        ...
    
    def test_find_similar_cosine(self, tmpdir):
        # Test similarity search with known vectors
        # Create test vectors with known cosine similarities
        # Vector A: [1, 0, 0]
        # Vector B: [0.9, 0.1, 0] -> cosine similarity = 0.9
        # Verify results are sorted by similarity
        ...
    
    def test_vss_index_creation(self, tmpdir):
        # Test vss index is created
        ...
    
    def test_binary_storage(self, tmpdir):
        # Test binary BLOB storage
        ...
    
    def test_requires_sqlite_vss(self, tmpdir, monkeypatch):
        # Test that operations fail gracefully if sqlite-vss not available
        # Mock the extension loading to fail
        ...
```

**Extend `tests/test_db.py`**:
```python
class TestImageEmbeddings:
    def test_table_creation(self, tmpdir):
        # Test image_embeddings table is created
        ...
    
    def test_vss_table_creation(self, tmpdir):
        # Test vss_embeddings virtual table is created
        ...
    
    def test_unique_constraint(self, tmpdir):
        # Test UNIQUE(image_path, model_name) constraint
        ...
    
    def test_find_similar_returns_correct_results(self, tmpdir):
        # Test find_similar with known vectors
        ...
```

### Integration Tests

- [ ] Test embedding generation during batch processing
- [ ] Test CLI `--find-similar` with known similar images
- [ ] Test CLI `--embeddings-only` on existing photos
- [ ] Test Web UI similar photos functionality
- [ ] Test that all operations fail clearly if sqlite-vss not available

### Manual Smoke Tests

1. **CLI Test**
   ```bash
   # Process folder with embeddings (default: enabled)
   python main.py ./test-photos
   
   # Verify embeddings were created
   sqlite3 ./test-photos/.open-photo-agent/features.db \
       "SELECT COUNT(*) FROM image_embeddings;"
   sqlite3 ./test-photos/.open-photo-agent/features.db \
       "SELECT COUNT(*) FROM vss_embeddings;"
   
   # Find similar images
   python main.py ./test-photos/photo1.jpg --find-similar --limit 5
   
   # List embedding models (requires Ollama running)
   python main.py --list-embedding-models
   
   # Generate embeddings only
   python main.py ./existing-photos --embeddings-only
   
   # Disable embeddings
   python main.py ./test-photos --no-embeddings
   ```

2. **Web UI Test**
   - Start the app: `python app.py`
   - Navigate to http://localhost:8050
   - Process a folder with photos
   - Open a photo detail modal
   - Click "Find Similar" button
   - Verify similar photos are displayed in carousel
   - Verify similarity scores are shown
   - Navigate through similar photos
   - Test in fullscreen viewer

3. **Performance Test**
   - Process 1000+ images with embeddings
   - Measure time for embedding generation
   - Measure time for similarity search
   - Verify sqlite-vss is being used
   - Verify performance meets <500ms requirement for 10K images

4. **Requirement Validation Test**
   - Test without sqlite-vss installed
   - Verify clear error message
   - Verify application does not start vector operations

## Edge Cases & Risks

### Edge Cases to Handle

1. **sqlite-vss Not Available**
   - **Hard requirement**: Application will raise clear error on startup or first vector operation
   - Error message must include installation instructions
   - Example: "sqlite-vss is required. Install with: pip install sqlite-vss"

2. **Ollama Version Too Old**
   - `/api/embeddings` endpoint not available in Ollama < v0.1.0
   - Need to check Ollama version or endpoint availability
   - Provide clear error message with version requirement

3. **Ollama Not Running**
   - Connection errors when generating embeddings
   - Retry logic already exists in OllamaPhotoExtractor
   - Clear error messages

4. **Model Not Available**
   - Requested embedding model not pulled in Ollama
   - Provide `--list-embedding-models` to show available models
   - Clear error message: "Model 'xyz' not found. Available models: ..."

5. **Storage Limits**
   - Large collections with many embeddings
   - sqlite-vss handles this efficiently
   - Monitor database size in logs

6. **Concurrent Access**
   - Multiple processes may access the database
   - SQLite WAL mode already configured
   - sqlite-vss handles concurrent reads

7. **Data Consistency**
   - Embedding generation may fail for some images
   - Continue processing on failure
   - Log errors for manual review
   - Partial embeddings are acceptable (user will reload all photos)

### Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| sqlite-vss not installed | Medium | High | **Hard requirement** - Clear error on startup with installation instructions. Application refuses to perform vector operations. |
| Ollama v0.1.0+ not available | Medium | High | Check version/endpoint before processing. Clear error with version requirement. |
| Embedding model not available | Medium | Medium | Validate model before processing. Provide --list-embedding-models. |
| Performance issues | Low | Medium | sqlite-vss is optimized. Test with 10K images before release. |
| Breaking existing functionality | Low | High | Comprehensive testing. All existing tests must pass. Embedding generation is separate from existing pipeline. |

### Dependencies

**Required (Hard Requirements)**:
- `sqlite-vss` - SQLite extension for vector search
  - Install: `pip install sqlite-vss`
  - Pre-built binaries available for Windows, macOS, Linux
  - Must be available at runtime

- `Ollama v0.1.0+` - For `/api/embeddings` endpoint
  - Check with: `ollama --version`
  - Upgrade if needed: follow Ollama upgrade instructions

**Already Present**:
- `requests` - For Ollama API calls
- `pillow` - For image handling (if needed for preprocessing)

## Configuration Reference

### Environment Variables

```bash
# Enable/disable embedding generation (default: true)
OPEN_PHOTO_AGENT_EMBEDDING_ENABLED=true

# Embedding model to use (default: clip-vit-base-patch32)
OPEN_PHOTO_AGENT_EMBEDDING_MODEL=clip-vit-base-patch32

# Embedding backend (currently only ollama supported)
OPEN_PHOTO_AGENT_EMBEDDING_BACKEND=ollama

# Number of similar results to return (default: 10)
OPEN_PHOTO_AGENT_SIMILARITY_LIMIT=10

# Similarity metric (currently only cosine supported)
OPEN_PHOTO_AGENT_SIMILARITY_METRIC=cosine
```

### Example `.env` Addition

```bash
# Vector Embedding Settings
# sqlite-vss and Ollama v0.1.0+ are HARD REQUIREMENTS
OPEN_PHOTO_AGENT_EMBEDDING_ENABLED=true
OPEN_PHOTO_AGENT_EMBEDDING_MODEL=clip-vit-base-patch32
OPEN_PHOTO_AGENT_EMBEDDING_BACKEND=ollama
OPEN_PHOTO_AGENT_SIMILARITY_LIMIT=10
OPEN_PHOTO_AGENT_SIMILARITY_METRIC=cosine
```

### Docker Considerations

The Docker image MUST have sqlite-vss pre-installed:

```dockerfile
# In Dockerfile
# sqlite-vss is a HARD REQUIREMENT
RUN pip install sqlite-vss
```

This installs the Python package which includes pre-built extensions for most platforms.

## Success Criteria

- [ ] Embeddings are generated for all images during processing (enabled by default)
- [ ] Embeddings are stored in SQLite with sqlite-vss
- [ ] Similarity search returns accurate results using cosine similarity
- [ ] CLI supports `--find-similar` and `--embeddings-only` commands
- [ ] Web UI displays "Find Similar" button and similar photos carousel
- [ ] Performance meets requirements (<500ms search for 10K images)
- [ ] **sqlite-vss hard requirement is enforced** - clear errors if not available
- [ ] **Ollama v0.1.0+ requirement is documented**
- [ ] All existing tests continue to pass
- [ ] New tests cover embedding generation and vector search
- [ ] Embeddings are NOT stored in sidecar JSON (SQLite only)

## Decisions Made

Based on your requirements and my recommendations:

1. **✅ All E2E Implementation**: All phases will be implemented together, not incrementally
2. **✅ Ollama-only Backend**: Only Ollama for embedding generation
3. **✅ Binary BLOB Storage**: Vectors stored as binary BLOBs in SQLite
4. **✅ Cosine Similarity**: Only cosine similarity metric
5. **✅ sqlite-vss (Hard Requirement)**: sqlite-vss is mandatory, not optional
6. **✅ User will reload all photos**: No backward compatibility concerns - embeddings enabled by default
7. **✅ No embeddings in sidecar JSON**: Embeddings stored in SQLite only for efficiency
8. **✅ Default model: clip-vit-base-patch32**: 512 dimensions, widely used and tested
9. **✅ Ollama v0.1.0+ required**: Minimum version for `/api/embeddings` endpoint

## Next Steps

1. **Final review** of this plan
2. **Set up development environment** with sqlite-vss and Ollama v0.1.0+
3. **Implement in the order specified** above (Steps 1-6)
4. **Test thoroughly** at each step
5. **Update documentation** (README.md, Dockerfile, etc.)

---

*Last updated: 2026-06-10*
*Decisions: All E2E, Ollama-only, Binary BLOB, Cosine, sqlite-vss (HARD), User reloads all, No sidecar embeddings, clip-vit-base-patch32 default, Ollama v0.1.0+*
