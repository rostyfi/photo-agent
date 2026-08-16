"""Thread-safe shutdown signal for the Dash web UI.

A ``threading.Event`` is set by the SIGINT/SIGTERM handler in ``app.py``
(which calls ``request_shutdown``) and persisted as a temporary file so
it is visible across process boundaries (Dash ``background=True``
callbacks run in separate processes when using ``DiskcacheManager``).
"""

import contextlib
import tempfile
import threading
from pathlib import Path

_SHUTDOWN_FLAG_PATH = Path(tempfile.gettempdir()) / "local_photo_agent_shutdown.flag"

_shutdown_event = threading.Event()


def request_shutdown():
    """Signal all background processing loops to stop."""
    _shutdown_event.set()
    with contextlib.suppress(OSError):
        _SHUTDOWN_FLAG_PATH.write_text("", encoding="utf-8")
