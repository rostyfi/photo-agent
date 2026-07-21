import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.folder import register_folder_callback, register_toggle_callback
from tests.test_callbacks import find_callback


class TestFolderCallbacks(unittest.TestCase):
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
                html.Div(id="input-folder"),
                html.Div(id="btn-rescan"),
                html.Div(id="input-batch-size"),
                html.Div(id="chk-recursive"),
                html.Div(id="folder-files-collapse"),
                html.Div(id="btn-toggle-files"),
            ]
        )
        register_folder_callback(self.app)
        register_toggle_callback(self.app)

    def test_toggle_callback_toggles(self):
        cb = find_callback(self.app, "folder-files-collapse", "is_open").__wrapped__
        self.assertFalse(cb(1, True))
        self.assertTrue(cb(1, False))

    def test_toggle_callback_no_click(self):
        cb = find_callback(self.app, "folder-files-collapse", "is_open").__wrapped__
        self.assertEqual(cb(None, True), dash.no_update)

    def test_folder_callback_registered(self):
        cb = find_callback(self.app, "folder-file-list", "children")
        self.assertIsNotNone(cb)


if __name__ == "__main__":
    unittest.main()
