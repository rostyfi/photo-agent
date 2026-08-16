import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks import (
    register_all_errors_callbacks,
    register_callbacks,
    register_chat_callback,
    register_chat_endpoint_test_callback,
    register_chat_history_init_callback,
    register_chat_history_navigation_callback,
    register_chat_scroll_callback,
    register_chat_stream_callback,
    register_chat_tag_clear_callback,
    register_chat_tag_click_callback,
    register_chat_tag_remove_callback,
    register_clear_chat_callback,
    register_detail_modal_callback,
    register_display_similar_photos_callback,
    register_find_similar_callback,
    register_fullscreen_close_callback,
    register_fullscreen_find_similar_callback,
    register_fullscreen_folder_change_callback,
    register_fullscreen_metadata_toggle_callback,
    register_fullscreen_nav_callback,
    register_fullscreen_open_callback,
    register_health_callback,
    register_reveal_callbacks,
    register_settings_modal_callback,
    register_similarity_search_callback,
    register_sql_explorer_callback,
)
from src.config import AppConfig


class TestReExports(unittest.TestCase):
    def test_all_register_functions_are_importable(self):
        # If this module loads, every function in __all__ imported successfully
        self.assertTrue(callable(register_callbacks))
        self.assertTrue(callable(register_health_callback))
        self.assertTrue(callable(register_settings_modal_callback))
        self.assertTrue(callable(register_sql_explorer_callback))
        self.assertTrue(callable(register_chat_callback))
        self.assertTrue(callable(register_chat_stream_callback))
        self.assertTrue(callable(register_clear_chat_callback))
        self.assertTrue(callable(register_chat_endpoint_test_callback))
        self.assertTrue(callable(register_chat_history_init_callback))
        self.assertTrue(callable(register_chat_history_navigation_callback))
        self.assertTrue(callable(register_chat_scroll_callback))
        self.assertTrue(callable(register_chat_tag_click_callback))
        self.assertTrue(callable(register_chat_tag_clear_callback))
        self.assertTrue(callable(register_chat_tag_remove_callback))
        self.assertTrue(callable(register_detail_modal_callback))
        self.assertTrue(callable(register_fullscreen_open_callback))
        self.assertTrue(callable(register_fullscreen_nav_callback))
        self.assertTrue(callable(register_fullscreen_close_callback))
        self.assertTrue(callable(register_fullscreen_metadata_toggle_callback))
        self.assertTrue(callable(register_fullscreen_folder_change_callback))
        self.assertTrue(callable(register_fullscreen_find_similar_callback))
        self.assertTrue(callable(register_reveal_callbacks))
        self.assertTrue(callable(register_find_similar_callback))
        self.assertTrue(callable(register_similarity_search_callback))
        self.assertTrue(callable(register_display_similar_photos_callback))
        self.assertTrue(callable(register_all_errors_callbacks))


class TestRegisterCallbacksWiring(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="photo-list-store"),
                html.Div(id="similar-photos-store"),
                html.Div(id="errors-store"),
                html.Div(id="chat-history-store"),
                html.Div(id="chat-pending-request"),
                html.Div(id="health-status"),
                html.Div(id="sql-results"),
                html.Div(id="detail-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="fullscreen-modal"),
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="fullscreen-metadata-overlay"),
                html.Div(id="settings-modal"),
                html.Div(id="keyboard-dummy"),
                html.Div(id="input-folder"),
                html.Div(id="btn-health"),
                html.Div(id="btn-settings"),
                html.Div(id="btn-close-settings"),
                html.Div(id="btn-run-sql"),
                html.Div(id="btn-prev-photo"),
                html.Div(id="btn-next-photo"),
                html.Div(id="btn-close-detail"),
                html.Div(id="btn-open-fullscreen"),
                html.Div(id="btn-prev-fullscreen"),
                html.Div(id="btn-next-fullscreen"),
                html.Div(id="btn-close-fullscreen"),
                html.Div(id="btn-toggle-metadata-fullscreen"),
                html.Div(id="btn-find-similar"),
                html.Div(id="btn-find-similar-fullscreen"),
                html.Div(id="similar-photos-container"),
                html.Div(id="poll-interval"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-model"),
                html.Div(id="input-backend"),
                html.Div(id="input-timeout"),
                html.Div(id="chk-dry-run"),
                html.Div(id="chk-recursive"),
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

    def test_chat_callback_registered(self):
        # The chat send callback targets the chat-history-store
        keys = list(self.app.callback_map.keys())
        self.assertTrue(any("chat-history-store.data" in k for k in keys))


if __name__ == "__main__":
    unittest.main()
