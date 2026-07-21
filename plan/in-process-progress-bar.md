# in-process-progress-bar

> **Status:** Draft
> **Created:** 2026-06-03 11:27:16

## Overview

Add a visual progress bar to the Dash web UI that updates **per-image** across all batch-processing operations (`Process Batch`, `Process All`, `Reprocess All`), giving users immediate feedback on long-running jobs.

## Motivation

Currently the UI only shows a text badge in `#queue-status` that updates every 3 s via polling. For `Process All` / `Reprocess All` jobs that process hundreds of images in 10-image sub-batches, the badge jumps in coarse increments (10, 20, 30 …). Users cannot see per-image advancement, making it hard to estimate total runtime or confirm that processing is still alive.

A progress bar that advances image-by-image provides:
- Clearer runtime estimation.
- Visual confirmation that the worker has not stalled.
- Consistent UX across all three process buttons.

## Requirements

- **R1:** Show a `dbc.Progress` component inside the **Process Server Folder** card, above the action buttons.
- **R2:** Progress bar updates **after each image** is processed (not after each batch of 10).
- **R3:** Progress bar works for `Process Batch`, `Process All`, and `Reprocess All`.
- **R4:** Bar is hidden when idle or no folder is selected; visible while running, done, or aborted.
- **R5:** Value is `completed / total * 100` derived from `batch_state.json`.
- **R6:** Keep existing CLI behaviour unchanged.
- **R7:** Keep existing `queue-status` badge text and behaviour unchanged (progress bar supplements it).

## Design / Approach

### Granularity Strategy

`WALSequentialStrategy.execute` already calls `reporter.report_progress(i, result)` after **every image**.
`FileProgressReporter` writes `batch_state.json` per image for single batches (`status == "running"`).

For `Process All` / `Reprocess All`, the outer `while` loop batches groups of 10 and instantiates a fresh `FileProgressReporter` each iteration. We replace it with `BatchProgressReporter(folder, total_all, offset)` that writes `status == "running_all"` with global totals after each image, enabling per-image smooth progress across the entire run.

### Data Flow

```
ImageProcessor.process_path()
  → WALSequentialStrategy.execute() loop
    → BatchProgressReporter.report_progress(i, result)
      → write_batch_state(status="running_all", total=total_all, completed=offset + i)
        ← polling callback every 3 s reads batch_state.json
          → batch-progress.value = (completed / total) * 100
          → batch-progress.style  = {"display": "block"}
```

### Files to modify

```
src/layout.py              - Add dbc.Progress(id="batch-progress") to Process Server Folder card
src/callbacks.py           - Add BatchProgressReporter usage; update polling callback outputs
src/coordinator/reporter.py - Add BatchProgressReporter class
src/coordinator/__init__.py - Re-export BatchProgressReporter
tests/test_layout.py        - Assert "batch-progress" exists in layout
```

### Database changes

None.

### API changes

None.

## Implementation Steps

1. **Reporter** — add `BatchProgressReporter(folder, total, offset)` to `src/coordinator/reporter.py` and re-export it.
2. **Layout** — insert `dbc.Progress(id="batch-progress", ...)` above `#folder-file-list` in `src/layout.py`.
3. **Callbacks** —
   a. Update `register_process_all_callback` and `register_reprocess_callback` to instantiate `BatchProgressReporter(folder, total_all, total_processed)` instead of `FileProgressReporter(folder)`.
   b. Expand `register_polling_callback` outputs to include `batch-progress.value` and `batch-progress.style`; compute and return per-image progress.
4. **Tests** — add `"batch-progress"` to `expected_ids` in `tests/test_layout.py`.
5. **Manual smoke test** — run `python app.py`, pick a folder with 20+ images, click **Process All**, verify the bar advances roughly per image and hits 100 % on completion.

## Testing Plan

- [ ] Unit tests: `tests/test_layout.py` passes (progress bar ID present).
- [ ] Integration: Existing coordinator/reporter tests pass.
- [ ] Manual smoke test:
  - Start app, select folder.
  - Click **Process All**; observe progress bar appears and moves per image.
  - Verify `queue-status` badge still updates.
  - Verify bar hides after selecting a new idle folder.

## Edge Cases & Risks

- **Folder switch mid-run:** Polling callback reads current `input-folder` value; progress bar may show stale folder briefly. This matches existing badge behaviour and is acceptable.
- **Zero total:** Guard against `ZeroDivisionError`; hide bar if `total == 0`.
- **Exception mid-batch:** `WALSequentialStrategy` catches per-image exceptions internally; `BatchProgressReporter` still fires for processed images. Offset remains correct because the outer `total_processed += stats.total` on the next successful batch iteration catches up.
- **Concurrent jobs:** Background callbacks disable action buttons while running, limiting concurrent jobs to one per session. `batch_state.json` is single-file; acceptable risk.

## References

- `src/batch_state.py` — atomic batch state I/O
- `src/coordinator/reporter.py` — `ProgressReporter` / `FileProgressReporter`
- `src/coordinator/strategy.py` — `WALSequentialStrategy.execute` calls `report_progress`
