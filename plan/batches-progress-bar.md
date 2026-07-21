# batches-progress-bar

> **Status:** Implemented  
> **Created:** 2026-06-04 21:35:29

## Overview

Enhance the existing Dash progress indicator so it is **batch-aware** during multi-batch operations ("Process All", "Reprocess All"). The UI now displays both **overall job progress** and **current sub-batch progress**, plus a collapsible history of recent micro-batches read from the WAL.

## Motivation

When users run "Process All" they previously saw a single progress bar that advanced across the entire run, but:
- The label was only a raw percentage (e.g. `"45%"`) with no batch context.
- Users could not see how many sub-batches remained or which one was currently running.
- The badge text (e.g. `"Batch 3: 45/120"`) and the progress bar were visually disconnected.
- After a job finished there was no compact summary of how many batches completed.

This feature gives users real visibility into long multi-batch runs without changing the single-batch ("Process Batch") experience.

## Requirements

- [x] **R1 — Dual progress bars:** During `status="running_all"` the UI shows two stacked `dbc.Progress` bars:
  - **Primary (overall):** percentage across the *entire* multi-batch run.
  - **Secondary (current batch):** percentage within the *current* sub-batch only.
- [x] **R2 — Rich labels:** When `batch_num` and `batch_total` are available, the primary label reads `"Batch {n} of {total} — {pct}%"`; the secondary label reads `"{current_batch_completed}/{current_batch_total}"`.
- [x] **R3 — Batch state enrichment:** `BatchProgressReporter` writes `batch_num`, `batch_total`, `batch_size`, and `batch_offset` into `batch_state.json`. Single-batch (`FileProgressReporter`) runs remain unchanged.
- [x] **R4 — Micro-batch history:** A collapsible list below the bars displays recent micro-batches from the WAL (microbatch ID, image count, completed/failed/pending counts).
- [x] **R5 — Idle summary:** When `status="done_all"`, a compact summary line is shown such as `"Complete — 120 images processed in 12 batches"`.
- [x] **R6 — Backward compatibility:** "Process Batch" (single batch, `status="running"`) continues to render exactly one progress bar.

## Design / Approach

### Data flow

```
Background callback (Process All)
  └─> BatchProgressReporter(folder, total_all, offset, batch_num, batch_total, batch_size)
        └─> write_batch_state(..., batch_num=3, batch_total=12, batch_size=10, batch_offset=20)
               └─> batch_state.json

Polling callback (1s interval)
  └─> read_batch_state(folder)
        └─> Compute overall_pct = completed / total
             Compute batch_pct   = (completed - batch_offset) / batch_size
             Read WAL microbatch list for history
        └─> Update dual progress bars + label + history list
```

### UI layout changes (Process Server Folder card)

Replaced the single `dbc.Progress` inside `batch-progress-wrapper` with:

```
batch-progress-wrapper
  ├─ dbc.Progress (id="batch-progress-overall",  primary,  height 20px)
  ├─ dbc.Progress (id="batch-progress-current", secondary, height 12px, striped, animated)
  ├─ html.Div (id="batch-progress-label", small muted text)
  └─ html.Div (id="batch-history-wrapper")
       ├─ dbc.Button "Show batch history" (toggle)
       └─ dbc.Collapse
            └─ html.Div (id="batch-history")
```

- The wrapper remains hidden when no batch is active, **except** when `status="done_all"` — then the label + history summary are shown.
- The secondary bar is only rendered when `batch_total > 1`.

### WAL history read

The polling callback calls `WriteAheadLog.get_microbatch_summary(limit=5)` which returns a lightweight, read-only summary of recent micro-batches. Results are mtime-cached in `_WAL_STATS_CACHE` to avoid re-reading the WAL file every poll.

## Files to modify

```
src/layout.py
  - Replaced single progress bar with dual-progress wrapper + history container.

src/callbacks.py
  - register_polling_callback: 9 outputs instead of 5; dual-bar logic, history rendering,
    label updates, WAL microbatch query.
  - register_process_all_callback / register_reprocess_callback:
    compute estimated batch_total and pass to BatchProgressReporter.
  - register_history_toggle_callback: new toggle for collapsible history.

src/coordinator/reporter.py
  - BatchProgressReporter.__init__: accepts optional batch_num / batch_total / batch_size.
  - BatchProgressReporter.report_progress: writes batch metadata into batch_state extra.

src/batch_state.py
  - No schema change required (dynamic **extra), but new optional keys documented.

src/wal.py
  - Added get_microbatch_summary(limit=5) for lightweight history queries.

src/components.py
  - Added build_batch_history(microbatches) helper.
```

### Database changes

None. The feature reads from the existing WAL (`wal.jsonl`) and `batch_state.json`.

### API changes

None. This is a UI-only enhancement.

## Implementation Steps

1. ✅ Backend — Enrich reporters & WAL
2. ✅ Backend — Wire callbacks (Process All / Reprocess All)
3. ✅ Frontend — Layout (dual bars + history)
4. ✅ Frontend — Polling logic
5. ✅ Styling / polish
6. ✅ Tests

## Testing Plan

- [x] Unit tests added/updated for `BatchProgressReporter` and WAL microbatch query.
- [x] Integration tests pass (`pytest tests/` — 271 passed, 1 skipped, 35 subtests).
- [x] Manual smoke test (Dash app imports and starts cleanly).

## Edge Cases & Risks

- **Dynamic total changes:** If new images are added while "Process All" is running, `total_all` is fixed at start, so the overall bar may reach 100% before the last batch. This is acceptable — totals are snapshotted at start.
- **Batch size = 0 / None:** When `batch_size` is `None` (no limit), there is only one batch. Dual bars degrade gracefully to a single bar.
- **WAL read cost:** `get_microbatch_summary()` scans the WAL file every poll. Mitigation: mtime-based caching in `_WAL_STATS_CACHE`.
- **Legacy batch state:** Old `batch_state.json` files without `batch_num`/`batch_total` still render; missing fields trigger single-batch mode.
- **Stop button:** If the user clicks Stop, the background callback exits and the polling callback sees `status="aborted"`. The dual bars freeze at their last known values.

## References

- `src/callbacks.py` — `register_polling_callback`, `register_process_all_callback`, `register_reprocess_callback`
- `src/coordinator/reporter.py` — `BatchProgressReporter`
- `src/batch_state.py` — `write_batch_state` / `read_batch_state`
- `src/wal.py` — `WriteAheadLog`
- `src/layout.py` — existing `batch-progress-wrapper` / `batch-progress`
