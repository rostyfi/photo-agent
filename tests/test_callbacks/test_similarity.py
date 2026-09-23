"""Tests for src/callbacks/similarity.py — vector similarity search callbacks."""

import contextlib
from unittest.mock import MagicMock, Mock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.similarity as sim_mod
from src.callbacks.similarity import (
    _get_db,
    register_display_similar_photos_callback,
    register_find_similar_callback,
    register_similarity_search_callback,
)
from tests.test_callbacks import find_callback


def _make_app(*component_ids):
    """Create a minimal Dash app with the given component IDs in its layout."""
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = html.Div([html.Div(id=cid) for cid in component_ids])
    return app


class TestGetDb:
    def test_empty_folder_returns_none(self):
        assert _get_db("") is None

    def test_nonexistent_db_returns_none(self, tmp_path):
        result = _get_db(str(tmp_path))
        assert result is None

    def test_existing_db_returns_instance(self, tmp_path):
        from src.sidecar.database import FeaturesDatabase

        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Create an empty DB file
        db = FeaturesDatabase(db_path)
        db.init_db()
        db.close()

        result = _get_db(str(tmp_path))
        assert result is not None
        result.close()


class TestFindSimilarCallback:
    def setUp(self):
        self.app = _make_app(
            "similar-photos-store",
            "btn-find-similar",
            "photo-list-store",
            "input-folder",
        )
        register_find_similar_callback(self.app)

    def _cb(self):
        self.setUp()
        return find_callback(self.app, "similar-photos-store", "data").__wrapped__

    def test_no_clicks_returns_none(self):
        cb = self._cb()
        result = cb(None, {"paths": ["/a.jpg"], "index": 0}, "/folder")
        assert result is None

    def test_no_folder_returns_none(self):
        cb = self._cb()
        result = cb(1, {"paths": ["/a.jpg"], "index": 0}, "")
        assert result is None

    def test_no_store_data_returns_none(self):
        cb = self._cb()
        result = cb(1, None, "/folder")
        assert result is None

    def test_invalid_index_returns_none(self):
        cb = self._cb()
        result = cb(1, {"paths": ["/a.jpg"], "index": 5}, "/folder")
        assert result is None

    def test_none_index_returns_none(self):
        cb = self._cb()
        result = cb(1, {"paths": ["/a.jpg"], "index": None}, "/folder")
        assert result is None

    def test_non_dict_store_data_returns_none(self):
        cb = self._cb()
        result = cb(1, "not-a-dict", "/folder")
        assert result is None

    def test_successful_search(self):
        cb = self._cb()
        store_data = {"paths": ["/photos/a.jpg", "/photos/b.jpg"], "index": 0}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "results": [
                {"image_path": "/photos/b.jpg", "score": 0.95},
            ],
        }

        with (
            patch.object(sim_mod, "_get_app_config") as mock_config,
            patch("src.callbacks.similarity.FeaturesDatabase") as mock_fdb,
            patch("builtins.__import__", side_effect=__import__),
        ):
            mock_config.return_value = MagicMock(dash_port=8050, embedding_model="test", similarity_limit=10)
            mock_fdb.default_db_path.return_value.exists.return_value = True

            # Patch requests.post inside the function
            with patch("requests.post", return_value=mock_response):
                result = cb(1, store_data, "/folder")

        assert result is not None
        assert result["images"] == ["/photos/b.jpg"]
        assert result["scores"] == [0.95]

    def test_api_error_status_returns_none(self):
        cb = self._cb()
        store_data = {"paths": ["/photos/a.jpg"], "index": 0}

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal error"}
        mock_response.text = "Internal error"

        with (
            patch.object(sim_mod, "_get_app_config") as mock_config,
            patch("src.callbacks.similarity.FeaturesDatabase") as mock_fdb,
        ):
            mock_config.return_value = MagicMock(dash_port=8050, embedding_model="test", similarity_limit=10)
            mock_fdb.default_db_path.return_value.exists.return_value = True

            with patch("requests.post", return_value=mock_response):
                result = cb(1, store_data, "/folder")

        assert result is None

    def test_request_exception_returns_none(self):
        import requests

        cb = self._cb()
        store_data = {"paths": ["/photos/a.jpg"], "index": 0}

        with (
            patch.object(sim_mod, "_get_app_config") as mock_config,
            patch("src.callbacks.similarity.FeaturesDatabase") as mock_fdb,
        ):
            mock_config.return_value = MagicMock(dash_port=8050, embedding_model="test", similarity_limit=10)
            mock_fdb.default_db_path.return_value.exists.return_value = True

            with patch("requests.post", side_effect=requests.exceptions.ConnectionError("fail")):
                result = cb(1, store_data, "/folder")

        assert result is None

    def test_no_db_returns_none(self):
        cb = self._cb()
        store_data = {"paths": ["/photos/a.jpg"], "index": 0}

        with (
            patch.object(sim_mod, "_get_app_config") as mock_config,
            patch("src.callbacks.similarity.FeaturesDatabase") as mock_fdb,
        ):
            mock_config.return_value = MagicMock(dash_port=8050, embedding_model="test", similarity_limit=10)
            mock_fdb.default_db_path.return_value.exists.return_value = False

            result = cb(1, store_data, "/folder")

        assert result is None


class TestSimilaritySearchCallback:
    def _cb(self):
        app = _make_app(
            "similarity-search-results",
            "btn-similarity-search",
            "upload-similarity-image",
            "input-folder",
        )
        register_similarity_search_callback(app)
        return find_callback(app, "similarity-search-results", "children").__wrapped__

    def test_no_clicks_returns_prompt(self):
        cb = self._cb()
        result = cb(None, None, "/folder")
        assert "Upload an image" in str(result)

    def test_no_contents_returns_prompt(self):
        cb = self._cb()
        result = cb(1, None, "/folder")
        assert "Upload an image" in str(result)

    def test_no_folder_returns_prompt(self):
        cb = self._cb()
        result = cb(1, "data:image/png;base64,abc", "")
        assert "Upload an image" in str(result)

    def test_no_db_returns_error(self):
        cb = self._cb()
        with (
            patch.object(sim_mod, "_get_app_config") as mock_config,
            patch("src.callbacks.similarity.FeaturesDatabase") as mock_fdb,
            patch("tempfile.NamedTemporaryFile"),
            patch("base64.b64decode", return_value=b"image"),
        ):
            mock_config.return_value = MagicMock(dash_port=8050, embedding_model="test", similarity_limit=10)
            mock_fdb.default_db_path.return_value.exists.return_value = False

            result = cb(1, "data:image/png;base64,abc", "/folder")
        assert "No database found" in str(result)


class TestDisplaySimilarPhotosCallback:
    def _cb(self):
        app = _make_app(
            "similar-photos-container",
            "similar-photos-store",
            "input-folder",
        )
        register_display_similar_photos_callback(app)
        return find_callback(app, "similar-photos-container", "children").__wrapped__

    def test_no_data_returns_empty_div(self):
        cb = self._cb()
        result = cb(None, "/folder")
        assert isinstance(result, html.Div)
        assert result.children is None

    def test_no_folder_returns_empty_div(self):
        cb = self._cb()
        result = cb({"images": ["/a.jpg"], "scores": [0.9]}, "")
        assert isinstance(result, html.Div)
        assert result.children is None

    def test_with_data_builds_carousel(self):
        cb = self._cb()
        data = {"images": ["/photos/a.jpg"], "scores": [0.9]}
        with patch("src.callbacks.similarity.build_similar_photos_carousel") as mock_build:
            mock_build.return_value = html.Div("carousel")
            result = cb(data, "/folder")
        mock_build.assert_called_once_with(data, "/folder")
