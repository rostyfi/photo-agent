"""Tests for src/state.py — shutdown signal mechanism."""

import contextlib
import os
from pathlib import Path
from unittest.mock import patch

import src.state as state_mod


def test_request_shutdown_sets_event():
    """request_shutdown sets the internal threading.Event."""
    state_mod._shutdown_event.clear()
    assert not state_mod._shutdown_event.is_set()
    state_mod.request_shutdown()
    assert state_mod._shutdown_event.is_set()
    state_mod._shutdown_event.clear()


def test_request_shutdown_writes_flag_file(tmp_path):
    """request_shutdown writes a flag file to the temp directory."""
    flag_path = tmp_path / "local_photo_agent_shutdown.flag"
    state_mod._shutdown_event.clear()
    with patch.object(state_mod, "_SHUTDOWN_FLAG_PATH", flag_path):
        state_mod.request_shutdown()
    assert flag_path.exists()
    assert flag_path.read_text(encoding="utf-8") == ""
    state_mod._shutdown_event.clear()


def test_request_shutdown_suppresses_os_error():
    """request_shutdown silently ignores OSError when writing the flag file."""
    state_mod._shutdown_event.clear()
    with patch.object(state_mod, "_SHUTDOWN_FLAG_PATH", Path("/nonexistent/dir/shutdown.flag")):
        # Should not raise
        state_mod.request_shutdown()
    assert state_mod._shutdown_event.is_set()
    state_mod._shutdown_event.clear()
