# dry-run

> **Status:** Implemented  
> **Created:** 2026-05-31 15:31:31

## Overview

Add a **Dry-run** toggle to the Dash web UI (and a `--dry-run` CLI flag) that simulates the entire discovery-and-processing pipeline **without calling the LLM backend**, while still persisting sidecar JSON files and WAL entries exactly like a live run.

## Motivation

Users want to test the full pipeline — folder discovery, WAL tracking, sidecar file placement, and progress reporting — without burning GPU time or waiting for model inference. Dry-run lets them verify that their setup works end-to-end and preview what the sidecar output structure looks like.

## Requirements

1. **UI Toggle:** A checkbox labeled *"Dry run (no LLM calls — writes placeholder sidecars + WAL)"* in the **Process Server Folder** card.
2. **Discovery intact:** Folder scanning, recursion, and `exclude_processed` logic must run exactly as in live mode.
3. **No network calls:** Ollama `extract()` / `extract_b64()` must never be invoked.
4. **Full persistence:** WAL entries (pending → in_progress → completed) and sidecar `.json` files **must** be written, identical paths to a live run.
5. **Synthetic results:** `DryRunPhotoExtractor` returns `ProcessingResult` objects with `success=True`, `total_duration_ms=0`, a placeholder `response`, and the real model/prompt metadata so sidecars are informative.
6. **Status indication:** The UI must clearly show *"Dry-run complete — X images processed (no LLM calls)"*.
7. **CLI parity:** `main.py` accepts `--dry-run`. When set, health check is skipped and the backend becomes `dry_run`.
8. **Backward compatibility:** Default behavior (toggle off / flag absent) must be identical to today.

## Design / Approach

Dry-run is implemented as a **pluggable LLM backend** — a new `BasePhotoExtractor` subclass living in `plugins/llm/dry_run.py` and registered under the name `dry_run` in `plugins/llm/backends/dry_run/`. The coordinator, strategies, savers, and reporters require **zero changes**; we simply override the `backend` field in `ProcessingConfig` to `"dry_run"`.

### High-level flow

```
[UI toggle on / --dry-run]
  → Discovery runs normally (PhotoList / FolderImageSource)
  → WALSequentialStrategy writes WAL entries (pending → in_progress → completed)
  → DryRunPhotoExtractor produces synthetic ProcessingResult per image
  → SidecarResultSaver writes .open-photo-agent/data/<image>.json
  → FileProgressReporter writes batch_state.json
  → UI shows dry-run-specific completion message
```

### Dry-run result shape

The synthetic sidecar JSON will contain:

```json
{
  "image_path": "/path/to/photo.jpg",
  "success": true,
  "model": "gemma4:e2b-it-qat",
  "prompt": "Describe this image in detail...",
  "response": "[DRY RUN] No LLM call was made. This is a placeholder result.",
  "parsed": null,
  "total_duration_ms": 0,
  "eval_count": 0,
  "done": true,
  "error": null
}
```

### Files changed

```
plugins/llm/dry_run.py                    - New DryRunPhotoExtractor implementation
plugins/llm/backends/dry_run/__init__.py  - Backend registration
plugins/llm/__init__.py                   - Re-export DryRunPhotoExtractor
src/layout.py                             - Add "chk-dry-run" checkbox
src/callbacks.py                          - Wire dry-run state into callbacks, override backend
main.py                                   - Add --dry-run flag, skip health check, override backend
tests/test_layout.py                      - Add "chk-dry-run" to expected IDs
```

## Implementation Steps

1. Create `plugins/llm/dry_run.py` with `DryRunPhotoExtractor` that returns synthetic `ProcessingResult` objects.
2. Create `plugins/llm/backends/dry_run/__init__.py` to register the backend.
3. Re-export `DryRunPhotoExtractor` from `plugins/llm/__init__.py`.
4. Add `dbc.Checkbox(id="chk-dry-run", ...)` to `src/layout.py` inside the Process Server Folder card.
5. Update `src/callbacks.py`:
   - Accept `State("chk-dry-run", "value")` in batch, process-all, and health callbacks.
   - Override `backend` to `"dry_run"` in `_make_processing_config` when the flag is set.
   - Prefix status messages with `"Dry-run"` when the flag is set.
   - Health check shows an informative message in dry-run mode instead of pinging a server.
6. Update `main.py`:
   - Add `--dry-run` argument.
   - Skip `extractor.health_check()` when dry-run.
   - Override `backend` to `"dry_run"` in both `create_extractor` and `ProcessingConfig`.
7. Update `tests/test_layout.py` to expect `chk-dry-run`.

## Testing Plan

- [x] Unit tests updated (`tests/test_layout.py` includes `chk-dry-run`)
- [ ] Manual smoke test: enable dry-run in UI, process a folder, verify sidecar JSONs contain the placeholder response and `total_duration_ms: 0`.
- [ ] Manual smoke test: run `python main.py ./photos --dry-run`, verify no health check is performed and sidecars are written.
- [ ] Verify that toggling dry-run **off** restores normal behavior (WAL + sidecars + real LLM calls).
- [ ] Verify that the Process All loop works with dry-run: it completes in a single iteration because all images are immediately marked completed.

## Edge Cases & Risks

- **Images already processed in a prior dry-run** will be skipped on the next real run because the WAL/sidecars treat them as completed. This is intentional — dry-run is meant to fully simulate the pipeline — but should be documented clearly.
- **Process All + Dry-run:** The while-loop naturally exits after the first batch (all images become "completed" in the WAL, so the next iteration finds zero pending images). No special short-circuiting needed.
- **Empty folders / no images:** Should still produce "No new images to process" message, unchanged.
- **Sidecar result format compatibility:** The placeholder sidecar must not break any downstream consumers that expect `response` to be a string. It is a string.

## References

- `plugins/llm/dry_run.py` — `DryRunPhotoExtractor` class
- `plugins/llm/backends/dry_run/__init__.py` — backend registration
- `src/callbacks.py` — batch and process-all callback registration
- `src/layout.py` — Dash UI layout
- `main.py` — CLI entry point
