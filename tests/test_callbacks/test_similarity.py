import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.similarity import (
    register_closest_photos_callback,
    register_clear_closest_photos_callback,
)
from src.sidecar.database import FeaturesDatabase
from tests.test_callbacks import find_callback


class TestClosestPhotosCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="closest-photos-results"),
                html.Div(id="closest-photos-status"),
                html.Div(id="closest-photos-input"),
                html.Button(id="btn-find-closest-photos"),
                html.Button(id="btn-clear-closest-photos"),
                html.Div(id="input-folder"),
            ]
        )
        register_closest_photos_callback(self.app)
        register_clear_closest_photos_callback(self.app)

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(None, None, None)
        self.assertEqual(result, (dash.no_update, dash.no_update))

    def test_no_query_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1, "", "/some/folder")
        self.assertEqual(result, (dash.no_update, dash.no_update))

    def test_no_folder_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1, "some query", "")
        self.assertEqual(result, (dash.no_update, dash.no_update))

    def test_no_db_returns_error(self):
        # Use a folder with no features.db — the callback should detect this
        # and return an error alert without making an HTTP call.
        with tempfile.TemporaryDirectory() as td:
            cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
            result = cb(1, "test query", td)

        # Should return empty div and error alert
        self.assertIsInstance(result[0], html.Div)
        self.assertIsInstance(result[1], dbc.Alert)

    @patch("requests.post")
    def test_with_results_returns_cards(self, mock_post):
        # The callback makes an HTTP POST to /_api/find_similar. Mock the
        # response to return two similar photos.
        image_path1 = "/tmp/photo1.jpg"
        image_path2 = "/tmp/photo2.jpg"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "results": [
                {"image_path": image_path1, "score": 0.95},
                {"image_path": image_path2, "score": 0.85},
            ],
            "count": 2,
        }
        mock_post.return_value = mock_response

        with tempfile.TemporaryDirectory() as td:
            # Create a features.db so the db_path.exists() check passes
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.init_db()
            db.close()

            cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
            result = cb(1, "test query", td)

            # Should return photo cards and success alert
            self.assertIsNotNone(result[0])
            self.assertIsNotNone(result[1])


class TestClearClosestPhotosCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="closest-photos-results"),
                html.Div(id="closest-photos-status"),
                html.Div(id="closest-photos-input"),
                html.Button(id="btn-clear-closest-photos"),
            ]
        )
        register_clear_closest_photos_callback(self.app)

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(None)
        self.assertEqual(result, (dash.no_update, dash.no_update, dash.no_update))

    def test_click_clears_all(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1)

        # Should return empty divs and empty string
        self.assertIsInstance(result[0], html.Div)
        self.assertIsInstance(result[1], html.Div)
        self.assertEqual(result[2], "")


if __name__ == "__main__":
    unittest.main()
