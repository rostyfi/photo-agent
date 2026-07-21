# tags-chaining

> **Status:** Draft  
> **Created:** 2026-06-07 15:33:35

## Overview

Allow users to **progressively filter photos by chaining multiple tags together with AND semantics**. Clicking a tag in the cloud adds it as an active filter; the result set narrows to only photos that contain **all** selected tags. Active filters are shown as removable pills.

## Motivation

Right now clicking a tag in the cloud shows every photo with that tag, but there's no way to narrow down further (e.g., "show me photos that are tagged `beach` **and** `sunset`"). Multi-tag chaining is a common pattern in photo-management apps and makes browsing large libraries far more useful.

## Requirements

- The tag cloud must be **clickable/toggleable**: clicking a tag adds it to the active chain; clicking it again removes it.
- A **selected-tags bar** must display the active chain with a small ✕ (remove) button on each tag.
- The **results area** (below the tag cloud) must refresh whenever the chain changes, showing only photos that have **every** active tag.
- Selection state must survive UI refreshes (use a `dcc.Store`).
- Changing the folder must **clear** the tag chain.
- The database must expose a new method to query photos by multiple tags using **AND** logic.
- Tag comparisons should be **case-insensitive** (matching current behaviour implied by `tag COLLATE NOCASE` elsewhere).
- Keyboard/mouse navigation (detail modal, fullscreen viewer) must continue to work on the chained result set.

## Design / Approach

### Data flow

1. User clicks a tag cloud button → Dash callback updates `selected-tags-store`.  
2. Same callback (or chained callback) queries `FeaturesDatabase.get_features_by_tags(selected_tags)`.  
3. Results are rendered into `tag-cloud-results` and `photo-list-store` is updated so the detail/fullscreen viewers know the current subset.  
4. A **Clear all** button resets the store and clears results.  
5. On `input-folder` change, another callback resets the store.

### Database query strategy

Use a standard relational "intersection" query:

```sql
SELECT e.image_path, ...
FROM extracted_features e
JOIN feature_tags t ON e.image_path = t.image_path
WHERE t.tag IN (?, ?, ?)
GROUP BY e.image_path
HAVING COUNT(DISTINCT t.tag) = ?
```

This naturally enforces **AND** semantics without relying on sub-queries per tag.

### UI colour/state encoding

- Tag cloud buttons use Bootstrap `color="light"` when **inactive** and `color="primary"` when **active**.
- Font-size scaling remains unchanged.
- Selected tags bar renders small `dbc.Badge(..., pill=True)` with a close/not-close button styled using `dbc.Button("×", size="sm", ...)`.

### Files to modify

```
src/sidecar/database/db.py     - Add get_features_by_tags(tags) method
tests/test_db.py                - Unit tests for get_features_by_tags
src/layout.py                   - Add dcc.Store("selected-tags-store") + Clear filters button
src/components.py               - Extend build_tag_cloud(selected_tags) + new build_selected_tags_bar
src/callbacks.py              - Refactor tag cloud/tag-list click handling into chain-aware callbacks;
                                add folder-change reset; update photo-list-store
```

### Database changes (if any)

None. New query only; no schema changes.

### API changes (if any)

None. Internal Python API only.

## Implementation Steps

1. **Backend**
   - Add `FeaturesDatabase.get_features_by_tags(tags: List[str]) -> List[Dict]` (AND logic).
   - Add unit tests in `tests/test_db.py`.
2. **Components**
   - Update `build_tag_cloud(tags_with_counts, max_tags, selected_tags)` to highlight active tags.
   - Add `build_selected_tags_bar(selected_tags)` returning a row of removable pills.
   - Optionally make tag badges inside `build_photo_cards` / `build_detail_modal_content` clickable (nice-to-have).
3. **Layout**
   - Insert `dcc.Store(id="selected-tags-store", data=[])`.
   - Add a "Clear filters" `dbc.Button` and `html.Div(id="selected-tags-bar")` inside the Tag Cloud card.
4. **Callbacks**
   - Rewrite `register_tag_click_callback` → `register_tag_chain_callbacks(app)` that takes:
     - `Input({"type": "tag-cloud-btn", ...}, "n_clicks")` → toggle in store.
     - `State("selected-tags-store", "data")`, `State("input-folder", "value")`.
   - Output: 
     - `tag-cloud-results.children` (filtered photo cards).
     - `photo-list-store.data` (paths for viewer).
     - `tag-cloud-container.children` (re-rendered cloud with active states).
     - `selected-tags-bar.children` (selected pills).
   - Add `register_tag_clear_callback(app)` listening to a clear button that resets the store.
   - Add `register_folder_change_clear_callback(app)` listening to `input-folder.value` that resets the tag store when folder changes.
5. **Testing**
   - Run `python -m pytest tests/test_db.py -v`.
   - Launch `app.py`, process a folder with varied tags, click multiple tags and verify result count drops.
   - Remove one tag and verify result count grows.
   - Click detail modal in the chained result set and verify prev/next only cycles within the chain.
   - Change folder and verify tag chain is cleared.

## Testing Plan

- [ ] `tests/test_db.py` updated with `get_features_by_tags` unit tests (AND logic, empty list, missing tags, case-insensitivity).
- [ ] Existing integration tests (`tests/test_db.py` + coordinator) still pass.
- [ ] Manual smoke test via `python app.py`:
  - Load folder, open tag cloud, click one tag (result set shows).
  - Click second tag (result set narrows).
  - Remove first tag (result set expands back to single-tag scope).
  - Clear all (results disappear / show all).
  - Verify detail modal and fullscreen viewer respect the current subset.

## Edge Cases & Risks

| Edge case | Mitigation |
|---|---|
| **No photos match the tag intersection** | Show "No photos match all selected tags." in the results area. |
| **Case sensitivity** | Use `tag COLLATE NOCASE` in the SQL `WHERE` clause to match existing sorting behaviour. |
| **Tag cloud re-rendering on every click** | Acceptable for ~100 tags. If performance degrades we can virtualise later. |
| **Dash `callback_context.triggered_id` with pattern-matching** | Need robust JSON parsing in the callback (same pattern already used in `register_tag_click_callback`). |
| **Folder change while tag chain active** | Add a dedicated callback that resets `selected-tags-store` whenever `input-folder` changes. |
| **Long tag chains (10+ tags)** | UI pills wrap via `flex-wrap`. SQL query is still a single indexed `JOIN`, so performance is fine. |
| **FTS search + tag chain interaction** | Keep them orthogonal for now (i.e., FTS search does not obey tag chain). This avoids confusing nested filtering in the first iteration. |

## References

- `src/callbacks.py::register_tag_click_callback` — existing single-tag click handler to refactor.  
- `src/sidecar/database/db.py::get_features_by_tag` — existing single-tag query to extend.  
- `src/components.py::build_tag_cloud` — current cloud builder.  

