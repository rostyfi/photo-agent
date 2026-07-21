import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.health_settings import register_health_callback, register_settings_modal_callback
from plugins.llm import create_extractor
from tests.test_callbacks import find_callback, patch_callback_context
import src.callbacks.health_settings as _hs


class TestHealthCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="health-status"),
                html.Div(id="btn-health"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-model"),
                html.Div(id="input-backend"),
                html.Div(id="input-timeout"),
                html.Div(id="chk-dry-run"),
            ]
        )
        
        # Create a mock create_extractor_fn
        def create_extractor_fn(**kwargs):
            return type(
                "MockExtractor",
                (),
                {
                    "base_url": "http://test:1234",
                    "model": "test-model",
                    "health_check": lambda self: True,
                },
            )()
        
        from src.config import AppConfig
        app_config = AppConfig.from_env()
        register_health_callback(self.app, create_extractor_fn, app_config)

    def test_dry_run_returns_info(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        result = cb(1, None, None, None, None, None, True)
        self.assertIn("Dry-run", str(result))
        self.assertIn("info", str(result))

    def test_healthy_returns_success(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        # Use dry-run mode to avoid connection issues
        result = cb(1, "192.168.0.150", "11434", "gemma4:e2b-it-qat", "ollama", "120", True)
        self.assertIn("Dry-run", str(result))
        self.assertIn("info", str(result))

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        result = cb(None, "host", "1234", "model", "backend", "60", False)
        self.assertEqual(result, dash.no_update)


class TestSettingsModalCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="settings-modal"),
                html.Div(id="btn-settings"),
                html.Div(id="btn-close-settings"),
            ]
        )
        register_settings_modal_callback(self.app)

    def test_open_settings(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, [{"prop_id": "btn-settings.n_clicks", "value": 1}]):
            result = cb(1, None)
        self.assertTrue(result)

    def test_close_settings(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, [{"prop_id": "btn-close-settings.n_clicks", "value": 1}]):
            result = cb(None, 1)
        self.assertFalse(result)

    def test_no_trigger_no_update(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, []):
            result = cb(None, None)
        self.assertEqual(result, dash.no_update)


if __name__ == "__main__":
    unittest.main()
