# Reprocess

> **Status:** Draft  
> **Created:** 2026-06-03 11:02:21

## Overview

Add a **Reprocess All** button to the web UI that forces re-extraction of every image in a folder, **ignoring** prior completion state in the WAL, sidecars, and SQLite features database. This gives users a one-click way to regenerate all feature data (e.g., after changing the model or prompt) without having to manually delete `.open-photo-agent/` directories.

## Motivation

Right now the web UI and `FolderImageSource` automatically skip images already marked as `completed` in the WAL, `features.db`, or legacy sidecars. There is no UI equivalent of the CLI flag `--no-resume`. Once a folder has been processed, clicking **Process Batch** or **Process All** silently skips every image. Users who change their prompt/model or want to re-run with different settings have no way to force re-extraction without SSH-ing into the server and deleting state files.

## Requirements

- **UI** – A red/danger-styled **"Reprocess All"** button appears alongside the existing **Process Batch** and **Process All** buttons.
- **No skipping** – When **Reprocess All** is clicked, all discovered images in the folder are fed to the pipeline regardless of WAL, DB, or sidecar completion state.
- **Overwrite** – Existing sidecar JSONs and `features.db` rows are silently overwritten with the new extraction result (this is already the default behaviour of `SidecarWriter` and `FeaturesDatabase.save_extraction`).
- **WAL semantics preserved** – The append-only WAL gets new `pending → in_progress → completed/failed` entries for every reprocessed image. Because `_index` keeps only the latest entry per `image_path`, the old `completed` state is naturally superseded.
- **Batch state** – `batch_state.json` is reset to `"running_all"` at the start, exactly like **Process All**.
- **Stop support** – The existing **Stop** button must abort a reprocess run the same way it aborts a normal process run.
- **Dry-run compatible** – Reprocess must work when **Dry run** is enabled.

## Design / Approach

### How reprocessing works (no WAL reset needed)

The WAL is append-only. `WriteAheadLog._index` is a `Dict[str, Dict]` keyed by `image_path` that always stores only the **latest** entry for each image. Therefore:

1. `FolderImageSource(..., exclude_processed=False)` returns **all** images.
2. `WALSequentialStrategy` appends a new `pending` entry for every image.
3. The index updates: old `completed` → new `pending`.
4. The processing loop then appends `in_progress` → `completed`/`failed`.
5. Sidecars and DB rows are overwritten by the existing `save` logic.

No explicit WAL clearing or pruning is required.

### Files to modify

```
src/components.py          - Add "Reprocess All" button to build_folder_controls()
src/layout.py              - Add btn-reprocess ID to the layout (or reuse components.py)
src/callbacks.py           - Add register_reprocess_callback: queue reprocess batch
src/coordinator/source.py  - FolderImageSource already supports exclude_processed=False
src/coordinator/strategy.py- WALSequentialStrategy already supports re-running images
```

### Database changes (if any)

None. `FeaturesDatabase.save_extraction` already uses `ON CONFLICT(image_path) DO UPDATE SET`.

### API changes (if any)

Dash UI only. No REST API changes.

## Implementation Steps

1. **UI** – In `src/components.py`, add a `dbc.Button("Reprocess All", id="btn-reprocess", color="danger", ...)` next to the **Process All** / **Stop** row.
2. **Callback** – In `src/callbacks.py`:
   - Create `register_reprocess_callback(app, default_prompt, app_config)`.
   - Trigger on `Input("btn-reprocess", "n_clicks")`.
   - Read the same `State` values as `register_process_all_callback`.
   - If `dry_run`, build config with `backend="dry_run"`.
   - Create `FolderImageSource(folder, recursive=..., exclude_processed=False)` directly (or pass a flag through `BatchCoordinator`).
   - Reset shutdown event, write batch state `"running_all"`, run batches identically to **Process All**.
   - Return status messages prefixed with `"Reprocess"`.
3. **BatchCoordinator** (optional) – Check whether `BatchCoordinator.run_folder_batch` needs an `exclude_processed` parameter, or simply instantiate `FolderImageSource` in the callback and pass it to `strategy.execute`. Looking at current code, the cleanest approach is:
   - Add `exclude_processed: bool = True` to `BatchCoordinator.run_folder_batch`.
   - Pass it through to `FolderImageSource(..., exclude_processed=exclude_processed)`.
   This also benefits the CLI if we ever want to refactor `--no-resume` into the coordinator.
4. **Button state** – Add `btn-reprocess` to the `running` disabled list alongside the other process buttons.

## Testing Plan

- [ ] **Unit tests added/updated**
  - `test_coordinator.py` – verify `BatchCoordinator.run_folder_batch(exclude_processed=False)` returns all images.
  - `test_wal.py` – verify that appending `pending` after `completed` correctly supersedes the index entry.
- [ ] **Integration tests pass**
  - `test_cli_integration.py` already covers `--no-resume`; ensure coordinator-level path is exercised.
- [ ] **Manual smoke test**
  - `python app.py` → pick a folder with already-processed images → click **Reprocess All** → verify:
    1. WAL `get_completed_set()` drops to 0 mid-run.
    2. Sidecars/DB rows are updated with new timestamps.
    3. Status badge shows progress over *all* images again.
    4. Stop button works.

## Edge Cases & Risks

| Risk | Mitigation |
|------|------------|
| **Large folders** – Reprocessing thousands of images takes just as long as the first run and is irreversible. | Button is styled `color="danger"`, making it visually distinct. No accidental click protection needed for an internal tool. |
| **Concurrent reprocess + process** – Two tabs/browsers could start overlapping runs. | Same as today: WAL `in_progress` entries are detected on load, and abandoned entries are auto-reset. The UI itself is single-threaded per Dash session. |
| **Sidecar writer race** – Overwriting sidecars mid-read by another process. | Atomic `tempfile.mkstemp + os.replace` already used. |
| **WAL bloat** – Reprocessing the same folder repeatedly appends 3×N new lines. | Existing `auto_compact_if_needed()` trigger plus manual `compact()` handles this. May consider lowering `compact_threshold` if users report bloat. |

## References

- `src/coordinator/source.py` – `FolderImageSource.exclude_processed`
- `src/discovery.py` – `PhotoList._load_processed_set`
- `src/wal.py` – `WriteAheadLog.append`, `_index` semantics
- `src/callbacks.py` – `register_process_all_callback` (model for the new callback)
- CLI `--no-resume` flag in `main.py` (equivalent behaviour)
