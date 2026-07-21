# callbacks-split

> **Status:** Draft  
> **Created:** 2026-06-09 22:17:26

## Overview

Refactor the monolithic `src/callbacks.py` (~1,350 lines, ~20 callback registration functions) into a focused `src/callbacks/` package. The public API surface — specifically `register_callbacks(app, ...)` — remains unchanged so that `app.py` and existing tests continue to work without modification.

## Motivation

`src/callbacks.py` has grown into a kitchen-sink module that mixes folder discovery, batch orchestration, health checks, SQL exploration, full-text search, tag-cloud filtering, and photo-viewer navigation. This creates several problems:

1. **Cognitive overload** — Finding a specific callback requires scrolling through 1,300+ lines of unrelated logic.
2. **Merge conflicts** — Multiple features touching the same file increase the chance of conflicts.
3. **Testability** — Unit tests for polling logic must import the entire callbacks module, pulling in heavy Dash dependencies for unrelated subsystems.
4. **Reusability** — Shared helpers (`_db_session`, `_run_batch_loop`, etc.) are private to the monolith and hard to unit-test in isolation.

Splitting by domain makes each module small enough to fit in working memory, enables targeted testing, and sets a precedent for future UI work.

## Requirements

1. **Preserve imports** — `from src.callbacks import register_callbacks` must continue to work. `from src.callbacks import register_polling_callback` (used by `tests/test_polling_callback.py`) must also continue to work.
2. **Zero functional change** — No callback signatures, outputs/inputs, or behaviour may change. This is a pure code-move refactor.
3. **Single registration entry point** — `register_callbacks` in `src/callbacks/__init__.py` still wires every callback onto the Dash app.
4. **Clientside keyboard navigation stays intact** — The existing `clientside_callback` for arrow-key/Escape/`i` handling moves into `__init__.py` alongside `register_callbacks`.
5. **Shared state isolated** — The module-level `_WAL_STATS_CACHE` dict and shared helper functions move to a dedicated `common.py` module to avoid duplication and circular imports.

## Design / Approach

Create a `src/callbacks/` package with one submodule per domain. Each submodule exports `register_*_callback(app, ...)` functions exactly as they exist today.

### Package structure

```
src/callbacks/
├── __init__.py          # register_callbacks() + re-exports for backward compat
├── common.py            # _WAL_STATS_CACHE, _db_session, _get_extractor,
│                        # _make_processing_config, _make_wal_strategy,
│                        # _run_batch_loop, _open_modal, _open_fullscreen_content
├── folder.py            # register_folder_callback, register_toggle_callback
├── batch.py             # register_batch_callback, register_process_all_callback,
│                        # register_reprocess_callback, register_stop_callback,
│                        # register_polling_callback, register_history_toggle_callback
├── health_settings.py   # register_health_callback, register_settings_modal_callback
├── sql_explorer.py      # register_sql_explorer_callback
├── search.py            # register_search_callback
├── tags.py              # register_tag_cloud_load_callback,
│                        # register_tag_cloud_render_callback,
│                        # register_tag_toggle_callback
└── viewer.py            # register_detail_modal_callback,
                         # register_fullscreen_open_callback,
                         # register_fullscreen_nav_callback,
                         # register_fullscreen_close_callback,
                         # register_fullscreen_metadata_toggle_callback,
                         # register_fullscreen_folder_change_callback
```

### Dependency graph (must be acyclic)

```
__init__.py ──► folder.py
            ──► batch.py
            ──► health_settings.py
            ──► sql_explorer.py
            ──► search.py
            ──► tags.py
            ──► viewer.py

common.py ◄─── (imported by all submodules that need helpers)
```

No submodule imports another submodule; they all import `common` and standard library / third-party / `src.*` modules only.

### Files to modify

```
src/callbacks.py          - Delete after verifying package works
src/callbacks/__init__.py - New. Re-exports + register_callbacks wiring
src/callbacks/common.py   - New. Shared helpers + _WAL_STATS_CACHE
src/callbacks/folder.py   - New. Extracted from callbacks.py
src/callbacks/batch.py    - New. Extracted from callbacks.py
src/callbacks/health_settings.py - New. Extracted from callbacks.py
src/callbacks/sql_explorer.py  - New. Extracted from callbacks.py
src/callbacks/search.py   - New. Extracted from callbacks.py
src/callbacks/tags.py     - New. Extracted from callbacks.py
src/callbacks/viewer.py   - New. Extracted from callbacks.py
tests/test_polling_callback.py - Update import path (optional, if re-export used)
```

### Database changes

None.

### API changes

None. The only external API — `register_callbacks(app, create_extractor_fn, processing_config, app_config)` — keeps the same signature and semantics.

## Implementation Steps

1. **Create `src/callbacks/` package**
   - `mkdir -p src/callbacks`
   - Add `src/callbacks/__init__.py` with re-exports from each submodule and the master `register_callbacks` function.

2. **Extract shared helpers to `common.py`**
   - Move `_WAL_STATS_CACHE`, `_db_session`, `_get_extractor`, `_make_processing_config`, `_make_wal_strategy`, `_run_batch_loop`, `_open_modal`, `_open_fullscreen_content`.
   - Import necessary types (`AppConfig`, `ProcessingConfig`, `FeaturesDatabase`, etc.).

3. **Extract domain-specific callbacks**
   - For each submodule, copy the relevant `register_*_callback` functions from `src/callbacks.py`.
   - Update their internal imports to pull shared helpers from `.common`.
   - Keep `Output`, `Input`, `State`, `dash`, `html`, etc. imports local to each file where they are used (avoids unused imports).

4. **Wire `register_callbacks` in `__init__.py`**
   - Import all `register_*_callback` functions from submodules.
   - Call them in the same order as today.
   - Keep the `clientside_callback` block exactly as-is.

5. **Remove old `src/callbacks.py`**
   - Delete the file once the package is verified.

6. **Run tests**
   - `python -m pytest tests/test_polling_callback.py` must pass.
   - `python -m pytest tests/` must pass in full.
   - Manual smoke test of the Dash app (`python app.py`) to ensure callbacks still fire.

## Testing Plan

- [ ] `python -m pytest tests/test_polling_callback.py` passes without modification (re-export compatibility).
- [ ] `python -m pytest tests/` full suite passes.
- [ ] Manual smoke test: start `python app.py`, pick a folder, verify **Rescan**, **Process All**, **Health Check**, **Search**, **Tag Cloud**, **SQL Explorer**, **detail modal**, and **fullscreen viewer** all still function.
- [ ] Keyboard navigation (arrow keys, Escape, `i`) in fullscreen verified.

## Edge Cases & Risks

| Risk | Mitigation |
|------|------------|
| **Circular imports** between submodules | Strict rule: submodules only import `common`, never each other. `__init__.py` orchestrates. |
| **Lost `clientside_callback` wiring** | Keep it inside `register_callbacks` in `__init__.py` so it is registered exactly once. |
| **Import drift in tests** | `__init__.py` re-exports `register_polling_callback` (and any other individual callbacks) so legacy imports keep working. |
| **Shared mutable state (`_WAL_STATS_CACHE`)** | Lives in exactly one place — `common.py` — and is imported by reference into `batch.py`. No copying. |
| **Background callback (`background=True`) regressions** | No logic changes; only file moves. Existing Dash background-callback manager registration in `app.py` is untouched. |

## References

- `src/callbacks.py` — source monolith to be split
- `app.py` — consumer of `register_callbacks`
- `tests/test_polling_callback.py` — direct consumer of `register_polling_callback`
- `src/layout.py` — defines the component IDs wired by these callbacks

