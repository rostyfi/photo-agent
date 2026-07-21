# Full Processing Plan: BatchCoordinator + "Process All"

## Overview

This plan combines two related features:

1. **BatchCoordinator** (from `coordinator.md`) — a refactored architecture that consolidates three divergent processing loops into one composable pipeline.
2. **"Process All" button** — a new UI control that automates continuous batch processing, removing the need for the user to click "Process Batch" repeatedly.

The coordinator is the foundation; the "Process All" feature is the user-facing behavior built on top.

---

## Current State

The web UI (`callbacks.py:134-199`) processes images in batches of 10 via the "Process Batch" button. After a batch completes, the user must click "Rescan folder" then "Process Batch" again to process the next 10. There is no auto-continuation.

The three processing loops:
| Location | Pattern |
|---|---|
| `main.py:59-74` | CLI: manual for-loop + `extractor.extract()` |
| `callbacks.py:168-198` | Web UI: Dash background callback, inline loop + `encode_image_file` + `extract_b64` |
| `processing.py:65-114` | Web UI: background thread (dead code, not wired to any UI) |

---

## Goal

Add a **"Process All"** button that, when clicked:

1. Processes the first batch of 10 images.
2. Automatically rescans the folder for remaining unprocessed images.
3. Triggers the next batch without user intervention.
4. Repeats until all images are processed or an error/stop condition occurs.
5. Shows live progress: how many batches completed, total images processed, and remaining.
6. Allows the user to stop early via an **"Abort"** button.

---

## Phase 1: Coordinator Foundation (Infrastructure — No Behavior Change)

Implement the `BatchCoordinator` and its supporting classes as designed in `coordinator.md`. This is a prerequisite — the "Process All" loop will be orchestrated through the coordinator.

### 1.1 Create `src/coordinator/` package

```
src/coordinator/
├── __init__.py        # Re-exports BatchCoordinator
├── result.py          # ProcessingResult + BatchStats dataclasses
├── config.py          # ProcessingConfig dataclass
├── source.py          # ImageSource ABC + FolderImageSource / ExplicitPathSource
├── processor.py       # ImageProcessor
├── saver.py           # ResultSaver ABC + SidecarResultSaver / InMemoryCollector
├── reporter.py        # ProgressReporter ABC + FileProgressReporter / NoOpProgressReporter
├── provider.py        # ExtractorProvider
├── resolver.py        # PromptResolver
├── strategy.py        # ProcessingStrategy ABC + SequentialStrategy
└── coordinator.py     # BatchCoordinator (thin orchestrator)
```

### 1.2 Key data types

```python
@dataclass
class ProcessingResult:
    image_path: Optional[str] = None
    filename: Optional[str] = None
    b64: Optional[str] = None
    success: bool = False
    model: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    parsed: Optional[Dict] = None
    total_duration_ms: Optional[float] = None
    eval_count: Optional[int] = None
    done: Optional[bool] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

@dataclass
class BatchStats:
    total: int
    success_count: int
    failure_count: int
    total_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    avg_duration_ms: float

    @classmethod
    def from_results(cls, results: List[ProcessingResult]) -> "BatchStats": ...
```

### 1.3 BatchCoordinator public API

```python
class BatchCoordinator:
    def __init__(self, config: ProcessingConfig, ...):
        ...

    def run_folder_batch(
        self,
        folder_path: str,
        *,
        recursive: bool = True,
        prompt: Optional[str] = None,
        limit: Optional[int] = 10,
        reporter: Optional[ProgressReporter] = None,
        saver: Optional[ResultSaver] = None,
    ) -> BatchStats:
        ...

    def health_check(self) -> bool:
        ...
```

### 1.4 Impact on existing files

| File | Action |
|---|---|
| `plugins/llm/ollama.py` | `extract()` / `extract_b64()` return `ProcessingResult` instead of `Dict` |
| `plugins/llm/base.py` | Remove `can_reuse()` from `BasePhotoExtractor` |
| `src/llm.py` | **Delete** — replaced by `SequentialStrategy` |
| `src/processing.py` | **Delete** — replaced by `BatchCoordinator` + strategy |
| `src/utils.py` | Keep `encode_image_file()`, consumed by `ImageProcessor` |
| `src/sidecar.py` | Keep `SidecarWriter`, wrapped by `SidecarResultSaver` |
| `src/batch_state.py` | Keep, called by `FileProgressReporter` |
| `src/discovery.py` | Keep `PhotoList`, wrapped by `FolderImageSource` |
| `src/config.py` | Add `ProcessingConfig`, keep `AppConfig` for backward compat |
| `main.py` | Refactored to use `BatchCoordinator` |
| `app.py` | Pass `ProcessingConfig`, wire `FileProgressReporter` |
| `src/callbacks.py` | Simplified to delegate to coordinator |

---

## Phase 2: Wire Coordinator Into Existing Flow (Parity)

Before adding "Process All", ensure the refactored single-batch flow works identically to the current behavior.

### 2.1 Modify `callbacks.py`

- `queue_all_images()` delegates to `BatchCoordinator.run_folder_batch()` with `FileProgressReporter`.
- `update_folder_list()` uses `FolderImageSource` to list images.
- `_get_extractor()` replaced by `ExtractorProvider`.

### 2.2 Modify `app.py`

- Create a single `BatchCoordinator` instance (or factory) on startup.
- Pass it to `register_callbacks()`.
- Wire `FileProgressReporter` to `batch_state.py`.

### 2.3 Validate

- "Process Batch" button processes exactly 10 images, produces sidecar JSONs, updates batch state.
- "Rescan folder" correctly shows next pending images.
- Polling interval shows "Idle — N pending" between batches.
- CLI (`main.py`) output is unchanged.

---

## Phase 3: "Process All" Feature (New Behavior)

### 3.1 How It Works

The "Process All" button triggers a Dash background callback that implements a **chained-batch loop**:

```
┌──────────────────────────────────────────────────┐
│  process_all_images(folder)                       │
│    │                                               │
│    ├─► while True:                                │
│    │     ├─► list_photos(folder, limit=10)        │
│    │     │     exclude already-processed          │
│    │     │                                         │
│    │     ├─► if empty: break (all done)           │
│    │     │                                         │
│    │     ├─► coordinator.run_folder_batch(         │
│    │     │     folder, limit=10, reporter=...)     │
│    │     │                                         │
│    │     ├─► write_batch_state("running_all",     │
│    │     │     total_done, total_all)              │
│    │     │                                         │
│    │     └─► check shutdown_event                 │
│    │           if set: break (aborted)             │
│    │                                               │
│    └─► write_batch_state("done_all", ...)         │
│          return final stats                        │
└──────────────────────────────────────────────────┘
```

### 3.2 Layout Changes (`src/layout.py`)

Add two new buttons in the "Process Server Folder" card, below the existing "Process Batch" button area:

```python
# Inside the folder-file-list div, add after the existing batch controls:

dbc.Row(
    [
        dbc.Col(
            dbc.Button(
                "Process All",
                id="btn-process-all",
                color="success",
                size="sm",
                className="w-100",
            ),
            width=4,
        ),
        dbc.Col(
            dbc.Button(
                "Stop",
                id="btn-stop-all",
                color="danger",
                size="sm",
                className="w-100",
                disabled=True,  # enabled only during "Process All"
            ),
            width=4,
        ),
    ],
    className="g-2 mt-2",
),
```

### 3.3 New Callbacks (`src/callbacks.py`)

#### 3.3.1 `process_all` callback

```python
@app.callback(
    Output("processing-status", "children", allow_duplicate=True),
    Input("btn-process-all", "n_clicks"),
    State("input-folder", "value"),
    State("chk-recursive", "value"),
    State("input-prompt", "value"),
    State("input-host", "value"),
    State("input-port", "value"),
    State("input-model", "value"),
    State("input-backend", "value"),
    State("input-timeout", "value"),
    background=True,
    prevent_initial_call=True,
    running=[
        (Output("btn-process-all", "disabled"), True, False),
        (Output("btn-process-batch", "disabled"), True, False),
        (Output("btn-stop-all", "disabled"), False, True),
    ],
)
def process_all_images(n_clicks, folder, recursive, prompt, host, port, model, backend, timeout):
    if not n_clicks or not folder:
        return dash.no_update

    used_extractor = _get_extractor(...)
    prmt = prompt or default_prompt

    total_all = len(PhotoList(recursive).list_photos([folder], exclude_processed_from=None))
    write_batch_state(folder, "running_all", total_all, 0,
                       status_msg="Process All started")

    batch_num = 0
    total_processed = 0
    all_durations = []

    while True:
        if _shutdown_event.is_set():
            write_batch_state(folder, "aborted", total_all, total_processed,
                               status_msg="Process All aborted by user")
            return "Process All aborted."

        # Scan for next batch
        image_paths = PhotoList(recursive).list_photos(
            [folder], exclude_processed_from=folder, limit=10
        )
        if not image_paths:
            break  # All done

        batch_num += 1
        batch_size = len(image_paths)

        write_batch_state(folder, "running_all", total_all, total_processed,
                           status_msg=f"Processing batch {batch_num} ({batch_size} images)")

        for i, path in enumerate(image_paths, 1):
            if _shutdown_event.is_set():
                break

            try:
                b64 = encode_image_file(path)
                result = used_extractor.extract_b64(b64, prompt=prmt)
                result["image_path"] = path
                SidecarWriter().save(path, result)
                if result.get("success") and result.get("total_duration_ms"):
                    all_durations.append(result["total_duration_ms"])
            except Exception as exc:
                logger.error(f"Error processing {path}: {exc}")
                error_result = {
                    "success": False,
                    "error_code": ErrorCode.PROCESSING_ERROR.value,
                    "error": str(exc),
                    "image_path": path,
                }
                SidecarWriter().save(path, error_result)

            total_processed += 1
            write_batch_state(folder, "running_all", total_all, total_processed,
                               status_msg=f"Batch {batch_num}: {total_processed}/{total_all}")

        # After each batch, allow the UI to update (the background callback
        # naturally yields between batches since Dash runs it in a thread)

    # Final stats
    if all_durations:
        avg_ms = sum(all_durations) / len(all_durations)
        total_s = sum(all_durations) / 1000
    else:
        avg_ms = total_s = 0

    write_batch_state(folder, "done_all", total_all, total_processed,
                       avg_duration_ms=avg_ms,
                       total_model_time_s=total_s,
                       status_msg=f"All {total_processed} images processed")
    return f"Process All complete. {total_processed} images processed."
```

#### 3.3.2 `stop_all` callback

```python
@app.callback(
    Output("btn-stop-all", "disabled"),
    Input("btn-stop-all", "n_clicks"),
    prevent_initial_call=True,
)
def stop_all(n_clicks):
    if n_clicks:
        _shutdown_event.set()
    return True  # Disable stop button after click
```

#### 3.3.3 Updated polling callback

The existing `poll_queue_status` callback needs to handle new state values:

| State value | Display |
|---|---|
| `running_all` | `Processing All — {completed}/{total} · Batch {N}` |
| `done_all` | `Complete — {total} processed · avg {X}ms/photo` |
| `aborted` | `Aborted — {completed}/{total} processed` |

### 3.4 Shutdown Event

The `_shutdown_event` from `src/processing.py` moves into a shared location (e.g., `src/coordinator/` or remains in a new top-level `src/state.py`):

```python
# src/state.py
import threading

_shutdown_event = threading.Event()

def request_shutdown():
    _shutdown_event.set()

def reset_shutdown_event():
    _shutdown_event.clear()

def is_shutdown_requested():
    return _shutdown_event.is_set()
```

- `btn-stop-all` calls `request_shutdown()`.
- When "Process All" starts, it calls `reset_shutdown_event()`.
- Each batch loop checks `is_shutdown_requested()`.

### 3.5 Button State Management

During "Process All":
| Button | State |
|---|---|
| `btn-process-all` | Disabled (running spinner) |
| `btn-process-batch` | Disabled |
| `btn-stop-all` | Enabled |
| `btn-rescan` | Disabled |

On completion/abort:
| Button | State |
|---|---|
| `btn-process-all` | Enabled |
| `btn-process-batch` | Enabled |
| `btn-stop-all` | Disabled |
| `btn-rescan` | Enabled |

Achieved via the `running` parameter in the background callback and a separate "done" callback or chained output.

---

## Phase 4: Edge Cases & Robustness

### 4.1 Server-side state persistence

Store "Process All" progress in `batch_state.json` with a `mode` field to distinguish from single-batch runs:

```json
{
  "status": "running_all",
  "mode": "process_all",
  "total": 150,
  "completed": 45,
  "batch_num": 4,
  "status_msg": "Batch 4: 45/150"
}
```

If the server restarts mid-run, the polling callback reads this state and shows accurate progress. On next "Process All" click, sidecar files are checked to skip already-processed images.

### 4.2 Network errors mid-batch

If a single image fails with a network error, the loop should:
- Log the error and save a failure sidecar JSON.
- Increment `total_processed`.
- Continue to the next image (do not abort the entire "Process All" run).

Distinguish transient from fatal errors:
- `NETWORK_ERROR` / `TIMEOUT` on a single image → log, continue.
- `NETWORK_ERROR` on 3+ consecutive images → abort (server likely down).

```python
consecutive_errors = 0
MAX_CONSECUTIVE_ERRORS = 3

# Inside the processing loop:
if result.success:
    consecutive_errors = 0
else:
    consecutive_errors += 1
    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        logger.error("Too many consecutive errors, aborting.")
        _shutdown_event.set()
        break
```

### 4.3 New images added during processing

If new images are added to the folder while "Process All" is running, the `PhotoList` at the start of each batch loop will discover them. This is **desirable behavior** — they get picked up in a subsequent batch.

The `total_all` in the progress display will be inaccurate (underestimated), but this is acceptable. The display shows `completed / total` where `total` is the count at start time.

Alternatively, recalculate `total_all` at each batch scan and update the display.

### 4.4 Race condition: two "Process All" on same folder

Prevent by checking batch state before starting:

```python
existing_state = read_batch_state(folder)
if existing_state and existing_state.get("status") in ("running_all", "running"):
    return "A batch is already running for this folder."
```

---

## Phase 5: Migration Path Summary

| Step | Description | Risk |
|---|---|---|
| 1 | Create `src/coordinator/` with all dataclasses and interfaces | Low — new code, unused |
| 2 | Add `ProcessingConfig` to `src/config.py` | Low |
| 3 | Return `ProcessingResult` from `OllamaPhotoExtractor.extract()` / `extract_b64()` | Medium — changes return type |
| 4 | Refactor `main.py` to use `BatchCoordinator` | Medium — validates CLI path |
| 5 | Delete `src/llm.py` | Low |
| 6 | Remove `can_reuse()` from `BasePhotoExtractor`, add `ExtractorProvider` | Low |
| 7 | Refactor `callbacks.py` to use coordinator for single batch | Medium — validates web UI |
| 8 | Delete `src/processing.py` | Low |
| 9 | Add "Process All" button and `btn-stop-all` to layout | Low |
| 10 | Implement `process_all_images` and `stop_all` callbacks | Medium — new feature |
| 11 | Update polling callback for new state values | Low |
| 12 | Add edge-case handling (consecutive errors, double-click guard) | Low |
| 13 | Run full test suite, verify no regressions | — |

---

## Behavior Specification: "Process All" End-to-End

### Happy Path

1. User navigates to web UI, enters folder `/photos`, checks "Recursive".
2. Clicks **"Rescan folder"** → sees e.g. "47/150 pending".
3. Clicks **"Process All"**.
4. Button changes to spinner. "Stop" button becomes red and clickable.
5. Status shows: `Processing All — 5/150 · Batch 1` ... `10/150 · Batch 1 complete`.
6. Automatically rescans → `Processing All — 20/150 · Batch 2` ... etc.
7. Final batch: `Processing All — 47/150 · Batch 5` ... `47/47 complete`.
8. "Process All" button re-enables. "Stop" button disables.
9. Status shows: `Complete — 47 processed · avg 1234 ms/photo`.

### Abort Path

1. User clicks **"Stop"** during batch 3 (25/150 processed).
2. Current image finishes processing. Loop sees `shutdown_event` is set.
3. Loop breaks. Status: `Aborted — 27/150 processed`.
4. User can click "Process All" again to resume (sidecar files skip already-processed images).

### Error Path

1. During batch 2, one image causes a timeout.
2. Error is logged, failure sidecar written, loop continues.
3. If 3 consecutive images fail → loop aborts automatically.
4. Status: `Aborted — 15/150 processed (network error)`.

---

## Files Changed (Summary)

| File | Change |
|---|---|
| `src/coordinator/*` | **New** — 10 files, ~500 lines |
| `src/state.py` | **New** — shared shutdown event ~20 lines |
| `src/config.py` | Add `ProcessingConfig` (~20 lines) |
| `plugins/llm/base.py` | Remove `can_reuse()`, update abstract return type |
| `plugins/llm/ollama.py` | Return `ProcessingResult`, remove `_encode_image()` |
| `src/llm.py` | **Delete** |
| `src/processing.py` | **Delete** |
| `src/callbacks.py` | Refactor (~-60 lines, +80 lines) |
| `src/layout.py` | Add "Process All" + "Stop" buttons (~20 lines) |
| `main.py` | Refactor to use coordinator (~-20 lines, +15 lines) |
| `app.py` | Wire coordinator, pass to callbacks (~10 lines) |
| `full-processing-plan.md` | **This file** |
