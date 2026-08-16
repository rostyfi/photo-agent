"""Thread-safe shutdown and job cancellation signals for the Dash web UI.

A ``threading.Event`` is shared between the Stop button callback
(which calls ``request_shutdown``) and the Process-All background loop
(which polls ``is_shutdown_requested`` on each iteration).

Because Dash ``background=True`` callbacks run in separate processes
when using ``DiskcacheManager``, the shutdown signal is also persisted
as a temporary file so it is visible across process boundaries.

Per-job cancellation is also supported via ``cancel_job`` and
``is_job_cancelled``, which scope a shutdown event to a specific job ID.
"""

import contextlib
import os
import tempfile
import threading
from pathlib import Path

_SHUTDOWN_FLAG_PATH = Path(tempfile.gettempdir()) / "local_photo_agent_shutdown.flag"

_shutdown_event = threading.Event()

_job_cancel_events: dict[str, threading.Event] = {}
_job_cancel_lock = threading.Lock()


def request_shutdown():
    """Signal all background processing loops to stop."""
    _shutdown_event.set()
    with contextlib.suppress(OSError):
        _SHUTDOWN_FLAG_PATH.write_text("", encoding="utf-8")


def reset_shutdown_event():
    """Clear the shutdown signal (called when a new Process-All starts)."""
    _shutdown_event.clear()
    with contextlib.suppress(FileNotFoundError, OSError):
        os.unlink(_SHUTDOWN_FLAG_PATH)


def is_shutdown_requested():
    """Return True if a shutdown has been requested via the Stop button."""
    return _shutdown_event.is_set() or _SHUTDOWN_FLAG_PATH.exists()


def _cancel_job(job_id: str) -> None:
    """Request cancellation for a specific job. (Internal: used only by tests)

    Args:
        job_id: Unique identifier for the job to cancel.
    """
    with _job_cancel_lock:
        if job_id not in _job_cancel_events:
            _job_cancel_events[job_id] = threading.Event()
        _job_cancel_events[job_id].set()


def is_job_cancelled(job_id: str) -> bool:
    """Return True if cancellation has been requested for the given job."""
    with _job_cancel_lock:
        event = _job_cancel_events.get(job_id)
    if event is None:
        return False
    return event.is_set()


def _remove_job_cancel(job_id: str) -> None:
    """Remove the cancellation tracking for a completed job. (Internal: used only by tests)"""
    with _job_cancel_lock:
        _job_cancel_events.pop(job_id, None)
