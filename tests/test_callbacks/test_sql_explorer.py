import tempfile
import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.sql_explorer import register_sql_explorer_callback
from src.sidecar.database import FeaturesDatabase
from tests.test_callbacks import find_callback


class TestSqlExplorerCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="sql-results"),
                html.Div(id="btn-run-sql"),
                html.Div(id="input-folder"),
                html.Div(id="sql-input"),
            ]
        )
        register_sql_explorer_callback(self.app)

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "sql-results", "children").__wrapped__
        result = cb(None, "/tmp", "SELECT 1")
        self.assertEqual(result, dash.no_update)

    def test_no_folder_returns_warning(self):
        cb = find_callback(self.app, "sql-results", "children").__wrapped__
        result = cb(1, "", "SELECT 1")
        self.assertIn("Enter a folder", str(result))
        self.assertIn("warning", str(result))

    def test_no_db_returns_warning(self):
        with tempfile.TemporaryDirectory() as td:
            cb = find_callback(self.app, "sql-results", "children").__wrapped__
            result = cb(1, td, "SELECT 1")
            self.assertIn("No features.db", str(result))
            self.assertIn("warning", str(result))

    def test_valid_query_returns_datatable(self):
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.save_extraction(
                "/fake/img.jpg",
                {
                    "success": True,
                    "model": "test",
                    "response": "{}",
                    "parsed": {"description": "d", "subjects": "s", "tags": ["t"]},
                },
            )
            cb = find_callback(self.app, "sql-results", "children").__wrapped__
            result = cb(1, td, "SELECT image_path FROM raw_features")
            self.assertIn("DataTable", str(type(result)))

    def test_empty_result_returns_message(self):
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.init_db()
            cb = find_callback(self.app, "sql-results", "children").__wrapped__
            result = cb(1, td, "SELECT * FROM raw_features WHERE 1=0")
            self.assertIn("empty", str(result).lower())

    def test_invalid_sql_returns_danger(self):
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.init_db()
            cb = find_callback(self.app, "sql-results", "children").__wrapped__
            result = cb(1, td, "SELECT * FROM does_not_exist")
            self.assertIn("danger", str(result))


if __name__ == "__main__":
    unittest.main()
