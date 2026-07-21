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
                html.Input(id="closest-photos-input"),
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
        self.assertEqual(result, dash.no_update)

    def test_no_query_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1, "", "/some/folder")
        self.assertEqual(result, dash.no_update)

    def test_no_folder_returns_no_update(self):
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1, "some query", "")
        self.assertEqual(result, dash.no_update)

    @patch("src.callbacks.similarity.get_vector_search_service")
    @patch("src.callbacks.similarity.AppConfig")
    @patch("src.callbacks.similarity._get_db")
    @patch("src.callbacks.similarity.create_generator")
    def test_no_db_returns_error(self, mock_create_generator, mock_get_db, mock_config, mock_vec_service):
        # Setup mocks
        mock_vec_service.return_value.is_available = True
        mock_config.from_env.return_value.embedding_backend = "ollama"
        mock_config.from_env.return_value.embedding_model = "nomic-embed-text"
        mock_config.from_env.return_value.llm_host = "localhost"
        mock_config.from_env.return_value.llm_port = 11434
        mock_config.from_env.return_value.timeout = 120
        mock_get_db.return_value = None  # No database
        
        cb = find_callback(self.app, "closest-photos-results", "children").__wrapped__
        result = cb(1, "test query", "/some/folder")
        
        # Should return empty div and error alert
        self.assertIsInstance(result[0], html.Div)
        self.assertIsInstance(result[1], dbc.Alert)

    @patch("src.callbacks.similarity.get_vector_search_service")
    @patch("src.callbacks.similarity.AppConfig")
    @patch("src.callbacks.similarity._get_db")
    @patch("src.callbacks.similarity.create_generator")
    def test_with_results_returns_cards(self, mock_create_generator, mock_get_db, mock_config, mock_vec_service):
        # Setup mocks
        mock_vec_service.return_value.is_available = True
        mock_vec_service.return_value.not_available_message = ""
        
        mock_config.from_env.return_value.embedding_backend = "ollama"
        mock_config.from_env.return_value.embedding_model = "nomic-embed-text"
        mock_config.from_env.return_value.llm_host = "localhost"
        mock_config.from_env.return_value.llm_port = 11434
        mock_config.from_env.return_value.timeout = 120
        
        # Create a temporary database with test data
        with tempfile.TemporaryDirectory() as td:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
            db.init_db()
            db.init_vector_search()
            
            # Add some test images
            image_path1 = os.path.join(td, "photo1.jpg")
            image_path2 = os.path.join(td, "photo2.jpg")
            
            # Save extractions
            db.save_extraction(image_path1, {
                "image_path": image_path1,
                "success": True,
                "parsed": {"description": "A dog running on the beach"}
            })
            db.save_extraction(image_path2, {
                "image_path": image_path2,
                "success": True,
                "parsed": {"description": "A cat sleeping on a couch"}
            })
            
            # Save embeddings
            db.save_embedding(image_path1, "nomic-embed-text", [0.1, 0.2, 0.3])
            db.save_embedding(image_path2, "nomic-embed-text", [0.4, 0.5, 0.6])
            
            db.close()
            
            # Mock the database getter to return our test db
            mock_get_db.return_value = db
            
            # Mock the generator to return a query embedding
            mock_generator = MagicMock()
            mock_generator.generate_from_text.return_value = [0.15, 0.25, 0.35]
            mock_create_generator.return_value = mock_generator
            
            # Mock find_similar to return results
            mock_db = MagicMock()
            mock_db.find_similar.return_value = [
                (image_path1, 0.95),
                (image_path2, 0.85),
            ]
            mock_db.close = MagicMock()
            mock_get_db.return_value = mock_db
            
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
                html.Input(id="closest-photos-input"),
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
        self.assertEqual(result[0], html.Div())
        self.assertEqual(result[1], html.Div())
        self.assertEqual(result[2], "")


if __name__ == "__main__":
    unittest.main()
