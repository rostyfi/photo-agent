import json
import os
import tempfile
import unittest
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import html

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


class TestPollingCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="queue-status"),
                html.Div(id="batch-progress-overall"),
                html.Div(id="batch-progress-current"),
                html.Div(id="batch-progress-current", style={}),
                html.Div(id="batch-progress-wrapper", style={}),
                html.Div(id="batch-progress-label"),
                html.Div(id="batch-history"),
                html.Div(id="batch-history-wrapper", style={}),
                html.Div(id="pending-count"),
                html.Div(id="poll-interval", n_intervals=0),
                html.Div(id="input-folder", value="/fake/folder"),
                html.Div(id="chk-recursive", value=True),
                html.Div(id="folder-cache", data={}),
            ]
        )
        self.app_config = AppConfig.from_env()
        register_polling_callback(self.app)

    def test_idle_shows_pending_count(self):
        cb = self.app.callback_map[("queue-status", "children")][0].callback
        result = cb(
            1,  # n_intervals
            "/fake/folder",  # folder
            True,  # recursive
            {},  # cache_data
        )
        # Should show idle state with pending count
        self.assertIn("Idle", str(result[0]))

    def test_running_shows_progress(self):
        with tempfile.TemporaryDirectory() as td:
            write_batch_state(td, "running_all", 100, 50, status_msg="Test running")
            cb = self.app.callback_map[("queue-status", "children")][0].callback
            result = cb(
                1,  # n_intervals
                td,  # folder
                True,  # recursive
                {},  # cache_data
            )
            # Should show running state
            self.assertIn("Running", str(result[0]))


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
        cb = self.app.callback_map[("history-collapse", "is_open")][0].callback
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
        cb = self.app.callback_map[("btn-stop-all", "disabled")][0].callback
        result = cb(1)
        self.assertTrue(is_shutdown_requested())
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
