"""Batch processing state persistence for the web UI.

batch_state.json stores the aggregate summary of a batch run (status, counts,
durations).  This is read by the Dash polling callback to drive the UI badge.

Per-image lifecycle tracking is handled by the SimpleProcessingTracker (src/simple_processing_tracker.py).
The database tracker is the recovery mechanism; batch_state.json is the UI status display.

After a batch completes, the final ``"done"`` entry here holds timing stats
(min/max/avg duration, total model time) for display.  The database tracker retains the
per-image completion list so that the next run can resume from where it
stopped.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _state_path(folder: str) -> Path:
    return Path(folder) / ".local-photo-agent" / "batch_state.json"


def write_batch_state(folder: str, status: str, total: int, completed: int, **extra) -> None:
    """Atomically write the aggregate batch processing summary for the web UI.

    Args:
        folder: Absolute path to the folder being processed.
        status: One of ``"running"``, ``"running_all"``, ``"done"``,
            ``"done_all"``, ``"aborted"``.
        total: Total number of images targeted.
        completed: Number of images processed so far (or total at completion).
        **extra: Additional key/value pairs to include (e.g. timing stats).
    """
    state = {"status": status, "total": total, "completed": completed, "folder": folder}
    state.update(extra)
    p = _state_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(p)
    logger.debug("Batch state: %s %s/%s", status, completed, total)


def read_batch_state(folder: str) -> dict | None:
    """Read the current batch processing summary for a folder.

    Returns None if no state file exists or if the file is unreadable.
    """
    p = _state_path(folder)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_batch_state(folder: str) -> None:
    """Remove the batch state file for a folder."""
    p = _state_path(folder)
    if p.exists():
        p.unlink()
        logger.debug("Cleared batch state for %s", folder)
