# closest-photos

> **Status:** Implemented  
> **Created:** 2026-06-15 20:41:50  
> **Implemented:** 2026-06-15

## Overview

A semantic search feature that allows users to input a natural language phrase and find the most relevant photos within the current folder based on their descriptions. It leverages vector embeddings for high-accuracy similarity matching.

## Motivation

Current FTS (Full-Text Search) is great for explicit keyword matches, but "closest-photos" enables more intuitive discovery by understanding context and concepts in photo descriptions. This allows users to find photos using natural language queries like "a cozy cabin in the snow" rather than just keyword matching.

## Requirements

- **Input:** A text input field where users can type descriptive phrases (e.g., "a cozy cabin in the snow")
- **Scope:** Only search photos belonging to the currently active folder
- **Accuracy:** Use vector embeddings from `sqlite-vec` to find results based on description proximity
- **Display:** A grid of the Top 10 closest matches with similarity scores
- **Interactivity:** Clicking a photo in the result grid must open the photo detail/fullscreen view

## Design / Approach

### UI Components
- Added a new card/section in the main layout featuring:
  - `dcc.Input` for the search query
  - A "Find Similar" button to trigger the embedding/search operation
  - A "Clear" button to reset the search
  - A result grid displaying top 10 matches with similarity percentages
  - Status messages for feedback

### Data Flow
1. User submits phrase -> Dash callback triggered
2. Callback calls `EmbeddingService` (via `create_generator`) to generate a vector for the input string
3. Callback calls `FeaturesDatabase.find_similar()` to perform a similarity search filtered by the current folder
4. Top 10 photo paths are returned with similarity scores and rendered in the grid

### Files Modified

```
src/components.py - Added build_closest_photos_input() function
src/layout.py - Added Closest Photos section to layout, imported build_closest_photos_input
src/callbacks/similarity.py - Added register_closest_photos_callback() and register_clear_closest_photos_callback()
src/callbacks/__init__.py - Registered new callbacks, added to __all__ list
```

### Database changes (if any)

None required; reusing existing `image_embeddings` and `vec_embeddings` tables.

### API changes (if any)

None - this is a UI-only feature using existing backend services.

## Implementation Steps

1. ✅ Created UI components for the search input and result grid in `src/components.py`
2. ✅ Integrated these components into the Dash layout in `src/layout.py`
3. ✅ Implemented the callback to:
   - Generate query embedding using `create_generator().generate_from_text()`
   - Perform vector similarity search within folder scope using `db.find_similar()`
   - Update UI state with results
4. ✅ Linked grid items to existing detail modal/fullscreen viewer logic (via thumbnail IDs with source="closest")

## Testing Plan

- [ ] **Unit tests:** Verify embedding generation produces consistent vectors for similar phrases
- [ ] **Integration tests:** Test "Find Similar" button returns photos from correct folder and ignores others
- [ ] **Manual smoke test:** Try diverse queries (e.g., "nature", "people", "blue colors") and verify:
  - Results are returned
  - Results are from the correct folder
  - Similarity scores are displayed
  - Clicking a result opens the detail view
  - Clear button works
  - Error handling for missing database/embeddings

## Edge Cases & Risks

- **No results:** Handled - shows "No similar photos found" message
- **Query too long:** Handled by embedding generator
- **Folder filtering:** Handled - search is scoped to current folder's database
- **No embeddings:** Handled - shows appropriate error message
- **sqlite-vec not available:** Handled - shows error message with requirement note

## References

- [src/services/embedding.py]
- [src/services/database.py]
- [src/sidecar/database/db.py]
- [src/embeddings/ollama.py]
