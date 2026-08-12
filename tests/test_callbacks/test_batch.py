import json
import os
import tempfile
import unittest
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from src.batch_state import read_batch_state, write_batch_state
from src.callbacks.batch import (
    register_process_callback,
    register_history_toggle_callback,
    register_polling_callback,
    register_process_all_callback,
    register_reprocess_callback,
    register_stop_callback,
)
from src.config import AppConfig
from tests.test_callbacks import find_callback


class TestPollingCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="queue-status"),
                html.Div(id="batch-progress-overall"),
                html.Div(id="batch-progress-current"),
                html.Div(id="batch-progress-wrapper", style={}),
                html.Div(id="batch-progress-label"),
                html.Div(id="batch-history"),
                html.Div(id="batch-history-wrapper", style={}),
                html.Div(id="pending-count"),
                dcc.Interval(id="poll-interval", interval=5000, n_intervals=0),
                dcc.Input(id="input-folder", value="/fake/folder"),
                dcc.Checklist(id="chk-recursive", options=[], value=[1]),
                dcc.Store(id="folder-cache", data={}),
            ]
        )
        self.app_config = AppConfig.from_env()
        register_polling_callback(self.app)

    def test_idle_shows_pending_count(self):
        # Use a real temp folder with no images — the callback should report
        # no images found (idle-equivalent state).
        with tempfile.TemporaryDirectory() as td:
            cb = find_callback(self.app, "queue-status", "children").__wrapped__
            result = cb(
                1,  # n_intervals
                td,  # folder
                True,  # recursive
                {},  # cache_data
            )
            # Should show a "no images" badge when the folder is empty
            self.assertIn("No images found", str(result[0]))

    def test_running_shows_progress(self):
        with tempfile.TemporaryDirectory() as td:
            write_batch_state(td, "running_all", 100, 50, status_msg="Test running")
            cb = find_callback(self.app, "queue-status", "children").__wrapped__
            result = cb(
                1,  # n_intervals
                td,  # folder
                True,  # recursive
                {},  # cache_data
            )
            # Should show the running status message
            self.assertIn("running", str(result[0]).lower())


class TestHistoryToggleCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="history-collapse"),
                html.Div(id="btn-toggle-history"),
            ]
        )
        register_history_toggle_callback(self.app)

    def test_toggles_history(self):
        cb = find_callback(self.app, "history-collapse", "is_open").__wrapped__
        # Start closed
        result = cb(1, False)
        self.assertTrue(result)
        # Toggle back
        result = cb(2, True)
        self.assertFalse(result)


class TestStopCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="btn-stop-all"),
            ]
        )
        register_stop_callback(self.app)

    def test_stops_processing(self):
        from src.state import is_shutdown_requested
        cb = find_callback(self.app, "btn-stop-all", "disabled").__wrapped__
        result = cb(1)
        self.assertTrue(is_shutdown_requested())
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
