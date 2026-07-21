# variable-batch-size

> **Status:** Draft  
> **Created:** 2026-06-03 11:53:21

## Overview

Allow users to configure how many images are processed in a single batch. Replace the hardcoded `limit=10` with a user-configurable batch size that is respected end-to-end by the coordinator, strategy, and image source.

> **Note:** `BatchCoordinator.run_folder_batch()` already accepts `limit=10`, but the parameter is **not wired through** to `ProcessingStrategy.execute()` or `ImageSource.list_images()`. This plan fixes that latent bug as part of the feature.

## Motivation

- The web UI hardcodes 10 images per batch with no way to tune it.
- Users with powerful GPUs may want 50–100 image chunks; users with memory constraints may want 5.
- The CLI processes entire folders in one go, offering no incremental control.
- Fixing the dead `limit` parameter makes the "Process Batch" button actually behave as advertised.

## Requirements

1. `ProcessingStrategy.execute()` must accept an optional `limit` parameter and pass it to `source.list_images(limit)`.
2. `BatchCoordinator.run_folder_batch()` and `run_paths_batch()` must thread `limit` through to `strategy.execute(..., limit=limit)`.
3. Add `--batch-size` CLI argument to `main.py` (default 10; `0` means "no limit").
4. Add `batch_size` to `AppConfig` / `ProcessingConfig`, loadable via `OPEN_PHOTO_AGENT_BATCH_SIZE` (default 10).
5. Add a "Batch Size" number input to the Dash web UI layout (near Settings).
6. Update all Dash callbacks that invoke batch processing to accept and pass the user-selected batch size.
7. Validate batch size: positive integer, capped at a reasonable max (e.g., 500).
8. Maintain backward compatibility: existing code paths without an explicit limit must continue to work (default `None` → no limit).

## Design / Approach

### Architecture

The batch size flows through four layers:

1. **User input** → CLI flag or web UI field / env var.
2. **Config** → `AppConfig.batch_size` / `ProcessingConfig.batch_size`.
3. **Coordinator** → `BatchCoordinator.run_*_batch(..., limit=batch_size)` creates the source and hands `limit` to the strategy.
4. **Strategy** → `execute(source, ..., limit=limit)` calls `source.list_images(limit)` so only that many images are iterated.

### Files to modify

```
src/coordinator/strategy.py      - Add limit param to execute() signatures; pass to source.list_images()
src/coordinator/coordinator.py    - Pass limit through to strategy.execute()
src/config.py                     - Add batch_size to AppConfig & ProcessingConfig
src/layout.py                     - Add batch-size Input to Settings card
src/callbacks.py                  - Accept batch-size state; pass to coordinator for Process Batch / Process All / Reprocess
main.py                           - Add --batch-size argument; pass to run_folder_batch / run_paths_batch
.env.example                      - Document OPEN_PHOTO_AGENT_BATCH_SIZE
README.md                         - Document --batch-size and UI control
tests/test_coordinator.py         - Add assertions that limit is respected end-to-end
tests/test_layout.py              - Update component count / ID checks if needed
```

### Database changes (if any)

None. Sidecar and WAL schemas are unchanged.

### API changes (if any)

No external API changes. Internal Python API changes:

- `ProcessingStrategy.execute(..., limit: Optional[int] = None)` — new keyword-only parameter.
- `BatchCoordinator.run_folder_batch(..., limit: Optional[int] = 10)` — already present, now actually used.
- `BatchCoordinator.run_paths_batch(..., limit: Optional[int] = None)` — new parameter.

## Implementation Steps

1. **Strategy layer:** Update `ProcessingStrategy.execute()` ABC to accept `limit: Optional[int] = None`. Update `SequentialStrategy.execute()` and `WALSequentialStrategy.execute()` to call `source.list_images(limit=limit)`.
2. **Coordinator layer:** Update `BatchCoordinator.run_folder_batch()` to pass `limit=limit` into `strategy.execute()`. Add `limit` parameter to `run_paths_batch()` and pass it through.
3. **Config layer:** Add `batch_size: int = 10` to `ProcessingConfig` and `AppConfig`, reading from `OPEN_PHOTO_AGENT_BATCH_SIZE`. Add validation (`_validate_positive`).
4. **CLI layer:** Add `--batch-size` argument to `main.py` argparse (type=int, default from config). Pass it to `BatchCoordinator` calls.
5. **UI layer:** Add `dbc.Input(id="input-batch-size", type="number", ...)` to `src/layout.py` in the Settings card. Update `src/callbacks.py` to read `State("input-batch-size", "value")` in `register_batch_callback`, `register_process_all_callback`, and `register_reprocess_callback`, then pass it as `limit`.
6. **Tests:** Update `test_coordinator.py` mocks to assert `strategy.execute(..., limit=...)` is called with the expected value. Add a test proving a batch size of 2 only processes 2 images.
7. **Docs:** Update `.env.example` and `README.md`.

## Testing Plan

- [ ] Unit tests added/updated for `SequentialStrategy` and `WALSequentialStrategy` respecting `limit`.
- [ ] Unit tests added for `BatchCoordinator` passing `limit` end-to-end.
- [ ] Unit tests for `AppConfig`/`ProcessingConfig` loading `OPEN_PHOTO_AGENT_BATCH_SIZE`.
- [ ] `tests/test_layout.py` updated if component IDs changed.
- [ ] Integration tests pass (`python -m pytest tests/`).
- [ ] Manual smoke test: CLI with `--batch-size 2` on a folder of 5 images → verify only 2 sidecars created (rest remain pending).
- [ ] Manual smoke test: Web UI set batch size to 3 → "Process Batch" creates 3 sidecars.

## Edge Cases & Risks

- **Batch size = 0 or negative:** Validate in config and CLI; reject or clamp to 1. Do not pass `0` to source slicing.
- **Batch size > total pending images:** Source already handles this gracefully (returns all available).
- **Process All with very large batch size:** The while-loop in `register_process_all_callback` will run once and finish. No risk.
- **Backward compatibility:** Existing callers of `strategy.execute()` without `limit` must still work. Using a keyword-only arg with default `None` ensures this.
- **WAL lifecycle:** In `WALSequentialStrategy`, if `limit=2`, only 2 images are appended as `pending` and tracked. This is correct — we only WAL-track what we actually attempt.
- **Dead-code fix side effect:** Because `limit` was previously ignored, "Process Batch" accidentally processed all images. After this fix, it will truly process only the batch size. This is the *intended* behavior, but users may notice the change.

## References

<!-- Links to docs, issues, related PRs -->

