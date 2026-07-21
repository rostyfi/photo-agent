import json
import tempfile
import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.tags import (
    register_tag_cloud_load_callback,
    register_tag_cloud_render_callback,
    register_tag_toggle_callback,
)
from src.sidecar.database import FeaturesDatabase
from tests.test_callbacks import find_callback, patch_callback_context
import src.callbacks.tags as _tags


class TestTagCloudLoadCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="tag-cloud-data-store"),
                html.Div(id="btn-load-tag-cloud"),
                html.Div(id="input-folder"),
            ]
        )
        register_tag_cloud_load_callback(self.app)

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "tag-cloud-data-store", "data").__wrapped__
        result = cb(None, "")
        self.assertEqual(result, dash.no_update)

    def test_no_folder_returns_empty(self):
        cb = find_callback(self.app, "tag-cloud-data-store", "data").__wrapped__
        result = cb(1, "")
        self.assertEqual(result, {"folder": "", "tags": []})

    def test_no_db_returns_empty_tags(self):
        with tempfile.TemporaryDirectory() as td:
            cb = find_callback(self.app, "tag-cloud-data-store", "data").__wrapped__
            result = cb(1, td)
            self.assertEqual(result, {"folder": td, "tags": []})

    def test_with_db_returns_tags(self):
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.save_extraction(
                "/fake/img.jpg",
                {
                    "success": True,
                    "model": "test",
                    "response": "{}",
                    "parsed": {"description": "d", "subjects": "s", "tags": ["tag1", "tag2"]},
                },
            )
            cb = find_callback(self.app, "tag-cloud-data-store", "data").__wrapped__
            result = cb(1, td)
            self.assertEqual(result["folder"], td)
            self.assertEqual(len(result["tags"]), 2)


class TestTagCloudRenderCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="tag-cloud-container"),
                html.Div(id="selected-tags-bar"),
                html.Div(id="tag-cloud-data-store"),
                html.Div(id="selected-tags-store"),
            ]
        )
        register_tag_cloud_render_callback(self.app)

    def test_no_data_returns_empty(self):
        cb = find_callback(self.app, "tag-cloud-container", "children").__wrapped__
        result = cb(None, [])
        self.assertIsInstance(result[0], html.Div)
        self.assertIsInstance(result[1], html.Div)

    def test_no_folder_returns_empty(self):
        cb = find_callback(self.app, "tag-cloud-container", "children").__wrapped__
        result = cb({"folder": ""}, [])
        self.assertIsInstance(result[0], html.Div)
        self.assertIsInstance(result[1], html.Div)

    def test_no_tags_returns_message(self):
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.init_db()
            cb = find_callback(self.app, "tag-cloud-container", "children").__wrapped__
            result = cb({"folder": td, "tags": []}, [])
            self.assertIn("No tags found", str(result[0]))


class TestTagToggleCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="selected-tags-store"),
                html.Div(id="tag-cloud-results"),
                html.Div(id="photo-list-store"),
                html.Div(id="btn-tag-clear-all"),
                html.Div(id="input-folder"),
            ]
        )
        register_tag_toggle_callback(self.app)

    def test_clear_all_returns_empty(self):
        cb = find_callback(self.app, "selected-tags-store", "data").__wrapped__
        with patch_callback_context(_tags, [{"prop_id": "btn-tag-clear-all.n_clicks", "value": 1}]):
            result = cb(None, None, 1, [], [], ["tag1"], "")
        self.assertEqual(result[0], [])
        self.assertIsInstance(result[1], html.Div)
        self.assertEqual(result[2], dash.no_update)

    def test_no_trigger_returns_no_update(self):
        cb = find_callback(self.app, "selected-tags-store", "data").__wrapped__
        result = cb(None, None, None, [], [], [], "")
        self.assertEqual(result, (dash.no_update, dash.no_update, dash.no_update))


if __name__ == "__main__":
    unittest.main()
