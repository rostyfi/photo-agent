# photos-preview

> **Status:** Draft  
> **Created:** 2026-06-06 13:15:27

## Overview

Add visual image thumbnail previews to the Dash web UI so users can browse, search, and inspect photos without leaving the application. This covers the folder file list, search results, and a detail modal for viewing extracted metadata alongside the full image.

## Motivation

Currently the web UI is entirely text-based: the folder list shows filenames as plain strings, and search results are a text-only DataTable. Users cannot visually verify which images are in a folder or confirm that search results match the intended photo. A preview layer makes the tool significantly more usable for browsing and quality control.

## Requirements

- **R1: Thumbnails in folder list** — Replace the text-only file list under "Process Server Folder" with a responsive grid of image thumbnails (e.g., 80–120 px) capped at the current scan limit. Each thumbnail shows the filename on hover or below the image.
- **R2: Thumbnails in search results** — Keep the existing `dash_table.DataTable` but add a thumbnail column using markdown image syntax (`![alt](/preview?path=...)`) with `presentation='markdown'` so the browser renders a ~100 px thumbnail in each row.
- **R3: Thumbnails in tag cloud results** — The tag cloud result list (which reuses the same search results component) must also show thumbnails. This is achieved by updating the shared `build_search_results()` helper.
- **R4: Detail modal** — Clicking any thumbnail opens a Bootstrap modal containing:
  - A larger preview of the image (max-width constrained, e.g., 400 px).
  - A read-out of the extracted metadata from the sidecar/SQLite: description, subjects, objects, colors, setting, mood, and tags.
  - If no sidecar exists yet, show a "Not yet processed" placeholder.
- **R5: Format support** — Previews must work for all formats the app already supports: JPEG, PNG, WebP, GIF, BMP, TIFF, HEIC/HEIF. HEIC/HEIF must be converted to JPEG on-the-fly for the browser (leveraging the existing `plugins.formats.heic` converter).
- **R6: Graceful fallback** — If an image file cannot be read, is missing, or conversion fails, display a generic placeholder icon instead of breaking the layout.
- **R7: Server-side serving** — Images must be served via a lightweight Flask route (`GET /preview?path=...`) so the browser can load them naturally. Base64 embedding is acceptable only as a fallback for very small thumbnails.
- **R8: Security** — The `/preview` route must validate that the requested path is within the configured/allowed folder scope and reject directory traversal attempts.

## Design / Approach

### High-level flow

1. User scans a folder or runs a search.
2. The callback builds image URLs pointing at `/preview?path=<absolute_path>`.
3. Dash renders thumbnails via `html.Img(src=...)` in the folder grid, and via markdown image tags inside the DataTable for search/tag results.
4. Clicking an image triggers a callback that populates a `dbc.Modal` with the larger image and reads the sidecar/SQLite for metadata.
5. The Flask route reads the file via `plugins.formats.image.read_image_bytes()`, converting HEIC to JPEG bytes if necessary, and returns the appropriate `Content-Type`.

### Files to modify

```
app.py                        - Add Flask /preview route with path validation and HEIC conversion
src/layout.py                 - Add dbc.Modal for detail view; adjust folder card layout
src/components.py             - build_folder_controls() → thumbnail grid; build_search_results() → DataTable with markdown thumbnail column; new build_detail_modal_content()
src/callbacks.py              - Wire modal open/close; update folder/search callbacks to emit thumbnail components
plugins/formats/image.py      - Potentially expose MIME type helpers for the preview route
```

### Database changes (if any)

None. The detail modal reads existing `raw_features` / `extracted_features` tables via `FeaturesDatabase`.

### API changes (if any)

New endpoint:
- `GET /preview?path=/absolute/path/to/image.heic` — returns image bytes (`image/jpeg`, `image/png`, etc.).
  - Query params: `path` (required, absolute server path).
  - Optional future param: `size=thumb|full` (default `thumb`).
  - Returns `404` if file not found or not allowed.
  - Returns `500` on conversion/read errors.

## Implementation Steps

1. **Add `/preview` route** in `app.py` with path validation and HEIC→JPEG fallback.
2. **Create thumbnail helpers** in `src/components.py`: `build_thumbnail_grid(image_paths)`, `build_search_cards(results)`, `build_detail_content(path)`.
3. **Add modal to layout** in `src/layout.py`: single hidden `dbc.Modal` with dynamic content containers.
4. **Update folder callback** in `src/callbacks.py`: return thumbnail grid instead of text list.
5. **Update search callback** in `src/callbacks.py`: `build_search_results()` now includes a markdown thumbnail column (`presentation='markdown'`) using `/preview?path=...` URLs sized to ~100 px.
6. **Add modal callback** in `src/callbacks.py`: open modal on thumbnail click, populate image + metadata.
7. **Manual smoke test** with JPEG, PNG, and HEIC images in a local folder.
8. **Add unit tests** for the `/preview` route (path validation, HEIC conversion path, 404 cases).

## Testing Plan

- [ ] Unit tests added/updated for `/preview` Flask route (`tests/test_preview.py`)
- [ ] Integration tests pass: `python -m pytest tests/`
- [ ] Manual smoke test:
  - [ ] Scan folder with mixed formats (JPG, PNG, HEIC) — thumbnails render
  - [ ] Search photos — results show thumbnails
  - [ ] Click thumbnail — modal opens with larger image and metadata
  - [ ] Click thumbnail for unprocessed image — modal shows "Not yet processed"
  - [ ] Attempt directory traversal via `/preview?path=../../etc/passwd` — blocked with 404/403

## Edge Cases & Risks

- **Large folders / DataTable markdown**: Rendering many markdown images in a DataTable can be heavy. We respect the existing `batch_size` / limit cap (default 10) for the folder grid. For search/tag results, DataTable's native pagination keeps page size manageable.
- **HEIC conversion cost**: On-the-fly HEIC→JPEG conversion for every thumbnail could be slow. Mitigation: limit thumbnail size or add caching later.
- **Path traversal**: The `/preview` route must strictly resolve and check the requested path against allowed roots.
- **Missing sidecars**: The detail modal must handle unprocessed images gracefully without crashing.
- **Browser compatibility**: HEIC is not natively supported in most browsers; the conversion step is mandatory.

## References

- `plugins.formats.heic.converter.convert_heic_to_jpeg_bytes()` — existing HEIC conversion utility
- `plugins.formats.image.read_image_bytes()` — existing format-agnostic reader
- `src.sidecar.database.FeaturesDatabase` — source for extracted metadata in detail modal
