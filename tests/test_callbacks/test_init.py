import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks import (
    register_callbacks,
    register_polling_callback,
    register_folder_callback,
    register_toggle_callback,
    register_process_callback,
    register_process_all_callback,
    register_reprocess_callback,
    register_stop_callback,
    register_health_callback,
    register_history_toggle_callback,
    register_settings_modal_callback,
    register_sql_explorer_callback,
    register_tag_cloud_load_callback,
    register_tag_cloud_render_callback,
    register_tag_toggle_callback,
    register_detail_modal_callback,
    register_fullscreen_open_callback,
    register_fullscreen_nav_callback,
    register_fullscreen_close_callback,
    register_fullscreen_metadata_toggle_callback,
    register_fullscreen_folder_change_callback,
)
from src.config import AppConfig


class TestReExports(unittest.TestCase):
    def test_all_register_functions_are_importable(self):
        # If this module loads, every function in __all__ imported successfully
        self.assertTrue(callable(register_callbacks))
        self.assertTrue(callable(register_polling_callback))
        self.assertTrue(callable(register_folder_callback))
        self.assertTrue(callable(register_toggle_callback))
        self.assertTrue(callable(register_process_callback))
        self.assertTrue(callable(register_process_all_callback))
        self.assertTrue(callable(register_reprocess_callback))
        self.assertTrue(callable(register_stop_callback))
        self.assertTrue(callable(register_health_callback))
        self.assertTrue(callable(register_history_toggle_callback))
        self.assertTrue(callable(register_settings_modal_callback))
        self.assertTrue(callable(register_sql_explorer_callback))
        self.assertTrue(callable(register_tag_cloud_load_callback))
        self.assertTrue(callable(register_tag_cloud_render_callback))
        self.assertTrue(callable(register_tag_toggle_callback))
        self.assertTrue(callable(register_detail_modal_callback))
        self.assertTrue(callable(register_fullscreen_open_callback))
        self.assertTrue(callable(register_fullscreen_nav_callback))
        self.assertTrue(callable(register_fullscreen_close_callback))
        self.assertTrue(callable(register_fullscreen_metadata_toggle_callback))
        self.assertTrue(callable(register_fullscreen_folder_change_callback))


class TestRegisterCallbacksWiring(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="folder-file-list"),
                html.Div(id="folder-cache"),
                html.Div(id="photo-list-store"),
                html.Div(id="selected-tags-store"),
                html.Div(id="tag-cloud-data-store"),
                html.Div(id="tag-cloud-results"),
                html.Div(id="tag-cloud-container"),
                html.Div(id="selected-tags-bar"),
                html.Div(id="processing-status"),
                html.Div(id="queue-status"),
                html.Div(id="batch-progress-overall"),
                html.Div(id="batch-progress-current"),
                html.Div(id="batch-progress-wrapper"),
                html.Div(id="batch-progress-label"),
                html.Div(id="batch-history"),
                html.Div(id="batch-history-wrapper"),
                html.Div(id="pending-count"),
                html.Div(id="health-status"),
                html.Div(id="sql-results"),
                html.Div(id="detail-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="fullscreen-modal"),
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="fullscreen-metadata-overlay"),
                html.Div(id="settings-modal"),
                html.Div(id="history-collapse"),
                html.Div(id="folder-files-collapse"),
                html.Div(id="keyboard-dummy"),
                html.Div(id="input-folder"),
                html.Div(id="btn-rescan"),
                html.Div(id="btn-process-batch"),
                html.Div(id="btn-process-all"),
                html.Div(id="btn-reprocess"),
                html.Div(id="btn-stop-all"),
                html.Div(id="btn-health"),
                html.Div(id="btn-settings"),
                html.Div(id="btn-close-settings"),
                html.Div(id="btn-run-sql"),
                html.Div(id="btn-load-tag-cloud"),
                html.Div(id="btn-tag-clear-all"),
                html.Div(id="btn-prev-photo"),
                html.Div(id="btn-next-photo"),
                html.Div(id="btn-close-detail"),
                html.Div(id="btn-open-fullscreen"),
                html.Div(id="btn-prev-fullscreen"),
                html.Div(id="btn-next-fullscreen"),
                html.Div(id="btn-close-fullscreen"),
                html.Div(id="btn-toggle-metadata-fullscreen"),
                html.Div(id="btn-toggle-files"),
                html.Div(id="btn-toggle-history"),
                html.Div(id="poll-interval"),
                html.Div(id="input-batch-size"),
                html.Div(id="chk-recursive"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-model"),
                html.Div(id="input-backend"),
                html.Div(id="input-timeout"),
                html.Div(id="chk-dry-run"),
                html.Div(id="sql-input"),
            ]
        )
        cfg = AppConfig.from_env()

        def _make_extractor(**kwargs):
            return type(
                "MockExtractor",
                (),
                {
                    "base_url": "http://test:1234",
                    "model": kwargs.get("model"),
                    "health_check": lambda: True,
                },
            )()

        register_callbacks(self.app, _make_extractor, cfg.to_processing_config(), cfg)

    def test_clientside_callback_registered(self):
        # clientside callbacks don't appear in callback_map; they are in _callback_list
        client_keys = [c.get("clientside_function") for c in self.app._callback_list]
        self.assertTrue(any(k is not None for k in client_keys))

    def test_all_server_callbacks_registered(self):
        # Verify at least the known polling callback key is present
        key = (
            "..queue-status.children...batch-progress-overall.value..."
            "batch-progress-current.value...batch-progress-current.style..."
            "batch-progress-wrapper.style...batch-progress-label.children..."
            "batch-history.children...batch-history-wrapper.style...pending-count.children.."
        )
        self.assertIn(key, self.app.callback_map)


if __name__ == "__main__":
    unittest.main()
