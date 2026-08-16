import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.viewer as _viewer
from src.callbacks.viewer import (
    register_detail_modal_callback,
    register_fullscreen_close_callback,
    register_fullscreen_folder_change_callback,
    register_fullscreen_metadata_toggle_callback,
    register_fullscreen_nav_callback,
    register_fullscreen_open_callback,
)
from tests.test_callbacks import find_callback, patch_callback_context


class TestDetailModalCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="detail-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="btn-prev-photo"),
                html.Div(id="btn-next-photo"),
                html.Div(id="btn-close-detail"),
                html.Div(id="input-folder"),
            ]
        )
        register_detail_modal_callback(self.app)

    def test_close_detail(self):
        cb = find_callback(self.app, "detail-modal", "is_open").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-close-detail.n_clicks", "value": 1}]):
            result = cb([], [], [], 1, [], {}, "")
        self.assertFalse(result[0])
        self.assertEqual(result[1], dash.no_update)
        self.assertEqual(result[2], dash.no_update)


class TestFullscreenOpenCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="btn-open-fullscreen"),
                html.Div(id="photo-list-store"),
                html.Div(id="detail-modal"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_open_callback(self.app)

    def test_no_click_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(None, {"paths": [], "index": None}, True, "")
        self.assertEqual(result, (dash.no_update, dash.no_update, dash.no_update))

    def test_no_folder_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(1, {"paths": ["/a.jpg"], "index": 0}, True, "")
        self.assertEqual(result, (dash.no_update, dash.no_update, dash.no_update))


class TestFullscreenNavCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="btn-prev-fullscreen"),
                html.Div(id="btn-next-fullscreen"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_nav_callback(self.app)

    def test_no_trigger_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, []):
            result = cb(None, None, {"paths": [], "index": 0}, "")
        self.assertEqual(result, (dash.no_update, dash.no_update))

    def test_next_wraps(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-next-fullscreen.n_clicks", "value": 1}]):
            result = cb(None, 1, {"paths": ["/a.jpg", "/b.jpg"], "index": 0}, "")
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1]["index"], 1)

    def test_prev_wraps(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-prev-fullscreen.n_clicks", "value": 1}]):
            result = cb(1, None, {"paths": ["/a.jpg", "/b.jpg"], "index": 0}, "")
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1]["index"], 1)


class TestFullscreenCloseCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="btn-close-fullscreen"),
                html.Div(id="photo-list-store"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_close_callback(self.app)

    def test_close_returns_false(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(1, {"paths": ["/a.jpg"], "index": 0}, "")
        self.assertFalse(result[0])
        self.assertTrue(result[1])
        self.assertIsNotNone(result[2])


class TestFullscreenMetadataToggleCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-metadata-overlay"),
                html.Div(id="btn-toggle-metadata-fullscreen"),
            ]
        )
        register_fullscreen_metadata_toggle_callback(self.app)

    def test_toggles_display(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(1, {"display": "block"})
        self.assertEqual(result["display"], "none")

    def test_toggles_back(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(1, {"display": "none"})
        self.assertEqual(result["display"], "block")

    def test_no_click_no_update(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(None, {"display": "block"})
        self.assertEqual(result, dash.no_update)


class TestFullscreenFolderChangeCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_folder_change_callback(self.app)

    def test_closes_on_change(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb("/new/folder")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
