# cloud-of-tags

> **Status:** Draft  
> **Created:** 2026-06-06 13:06:00

## Overview

A visual **tag cloud** UI that displays all extracted photo tags from a folder's `features.db`, sized by frequency (popularity). Clicking any tag instantly filters and shows the matching photos. This gives users a fast, visual way to browse their collection by subject matter without typing search queries.

## Motivation

The current "Search Photos" card requires users to type free-text queries and know what they're looking for. A tag cloud provides:
- **Discovery**: Users can see at a glance what subjects, objects, and themes exist in their collection.
- **One-click exploration**: No typing required to drill into a specific tag.
- **Visual density**: Popular tags (e.g., "sunset", "dog", "beach") stand out, guiding attention.

## Requirements

- Display every distinct tag from `feature_tags` for the selected folder, or the top-N most frequent.
- Tag size (font size) must scale relative to the tag's frequency count.
- Clicking a tag must display all photos associated with that tag in a sortable table (same columns as Search Photos).
- Tag cloud must refresh from the database on demand via a button; it must not block the UI.
- If no tags exist (empty or unprocessed folder), show a helpful empty state.
- Must gracefully handle folders with no `features.db` yet.

## Design / Approach

### Backend
- Add `list_tag_frequencies(limit=100) -> List[Tuple[str, int]]` to `FeaturesDatabase`.
  - SQL: `SELECT tag, COUNT(*) as count FROM feature_tags GROUP BY tag ORDER BY count DESC, tag COLLATE NOCASE LIMIT ?`
  - Returns tag name + occurrence count so the UI can scale font sizes.
- Re-use existing `get_features_by_tag(tag: str) -> List[Dict]` for click-to-filter results.

### UI / Layout (`src/layout.py`)
- Add a new **"Tag Cloud"** `dbc.Card` below the existing "Search Photos" card.
- Contains:
  1. A "Load Tag Cloud" `dbc.Button` to trigger population.
  2. A container `html.Div(id="tag-cloud-container")` for the rendered cloud.
  3. A results container `html.Div(id="tag-cloud-results")` for the matching-photo table.

### Components (`src/components.py`)
- Add `build_tag_cloud(tags_with_counts: List[Tuple[str, int]], max_tags: int = 100) -> html.Div`:
  - If empty → return `html.Div("No tags found.", className="text-muted")`.
  - Compute `min_count` and `max_count`.
  - Map each tag to a `dbc.Button` with:
    - `id={"type": "tag-cloud-btn", "index": tag}` (Dash pattern-matching ID).
    - `color="light"`, `size="sm"`, `className="me-1 mb-1"`.
    - Inline `style` setting `fontSize` between **12 px** (min) and **32 px** (max), linearly scaled by count.
    - Label: `f"{tag} ({count})"`.
  - Wrap in a flex container: `html.Div(..., className="d-flex flex-wrap align-items-center")`.

### Callbacks (`src/callbacks.py`)
1. **Load callback**  
   `Output("tag-cloud-container", "children")`  
   `Input("btn-load-tag-cloud", "n_clicks")`  
   `State("input-folder", "value")`
   - Validates folder and `features.db` existence.
   - Calls `db.list_tag_frequencies()`.
   - Returns `build_tag_cloud(tags_with_counts)`.

2. **Click callback** (pattern-matching)  
   `Output("tag-cloud-results", "children")`  
   `Input({"type": "tag-cloud-btn", "index": dash.ALL}, "n_clicks")`  
   `State({"type": "tag-cloud-btn", "index": dash.ALL}, "id")`  
   `State("input-folder", "value")`  
   `prevent_initial_call=True`
   - Identifies the clicked tag from `callback_context.triggered`.
   - Calls `db.get_features_by_tag(tag)`.
   - Returns a wrapper `html.Div` containing:
     - A small header: `dbc.Alert(f"Photos tagged with '{tag}'", color="info", dismissable=False)`.
     - `build_search_results(results)` table (or a "No photos found" message).

3. **Import additions** in `src/callbacks.py`: add `dash.ALL` to the existing `dash` imports (or reference as `dash.ALL`).

### Files to modify

```
src/sidecar/database/db.py    - Add list_tag_frequencies() method
src/components.py            - Add build_tag_cloud()
src/layout.py                - Add Tag Cloud card with btn-load-tag-cloud, tag-cloud-container, tag-cloud-results
src/callbacks.py             - Add register_tag_cloud_callback() and register_tag_click_callback(); wire into register_callbacks()
```

### Database changes (if any)

No schema migrations. The new method is a read-only aggregation query against the existing `feature_tags` table. No new tables or columns.

### API changes (if any)

No external API changes. Purely internal UI feature.

## Implementation Steps

1. **Backend** — Add `list_tag_frequencies(limit=100)` to `FeaturesDatabase` with parameterized SQL and a unit test in `tests/test_db.py`.
2. **Component** — Implement `build_tag_cloud()` in `src/components.py` with min/max font-size scaling logic.
3. **Layout** — Insert the Tag Cloud card into `src/layout.py`.
4. **Callbacks** — Register the load and pattern-matching click callbacks in `src/callbacks.py`, then wire them into `register_callbacks()`.
5. **Testing** — Run the test suite, verify manual smoke test in the Dash UI.

## Testing Plan

- [ ] **Unit tests added/updated**: `test_db.py` — assert `list_tag_frequencies()` returns correct `(tag, count)` tuples ordered by count desc.
- [ ] **Unit tests added/updated**: `test_layout.py` — assert the new Tag Cloud card and its IDs exist in the layout.
- [ ] **Integration tests pass**: `pytest tests/` — no regressions in existing search or batch processing.
- [ ] **Manual smoke test**:
  1. Start `python app.py`.
  2. Process a folder with diverse tags.
  3. Click **Load Tag Cloud** — verify tags appear with varying font sizes.
  4. Click a large tag — verify a results table appears showing only photos with that tag.
  5. Switch to an empty/unprocessed folder — verify empty-state message appears.

## Edge Cases & Risks

| Risk / Edge Case | Mitigation |
|---|---|
| **Folders with thousands of distinct tags** | `list_tag_frequencies` defaults to `LIMIT 100`. If a folder has 10k+ tags, only the top 100 are shown, keeping render time fast. |
| **Special characters in tag names** | Dash pattern-matching IDs use JSON-encoded dicts; special chars in the `"index"` field are handled natively by Dash. |
| **No `features.db` yet** | Callback returns a `dbc.Alert("No features.db found...", color="warning")` and does not crash. |
| **Tag count = 1 across the board** | Font-size formula falls back to a midpoint (e.g., 16 px) when `max_count == min_count`. |
| **Pattern-matching callback fired on layout init** | `prevent_initial_call=True` on the click callback. |
| **User clicks multiple tags rapidly** | The callback naturally handles the last-triggered click via `callback_context.triggered`. Old results are replaced. |

## References

- Existing tag infrastructure: `src/sidecar/database/db.py` (`feature_tags`, `list_all_tags()`, `get_features_by_tag()`)
- Existing search UI: `src/layout.py` (Search Photos card), `src/callbacks.py` (`register_search_callback`)
- Dash pattern-matching callbacks docs: https://dash.plotly.com/pattern-matching-callbacks
