"""Tests for src/callbacks/metadata_tester.py — metadata extraction UI."""

import base64
from unittest.mock import MagicMock, Mock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.metadata_tester import build_metadata_result, register_metadata_tester_callbacks
from src.metadata import ImageMetadata
from tests.test_callbacks import find_callback


def _make_app():
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = html.Div(
        [
            html.Div(id="metadata-tester-store"),
            html.Div(id="metadata-tester-filename"),
            html.Div(id="metadata-tester-progress"),
            html.Div(id="metadata-tester-result"),
            html.Div(id="metadata-tester-running"),
            html.Div(id="metadata-tester-upload"),
            html.Div(id="btn-metadata-tester-extract"),
        ]
    )
    register_metadata_tester_callbacks(app)
    return app


class TestBuildMetadataResult:
    def test_no_metadata_shows_alert(self):
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", None)
        rendered = str(result)
        assert "No metadata found" in rendered

    def test_empty_metadata_shows_alert(self):
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", {})
        rendered = str(result)
        assert "No metadata found" in rendered

    def test_with_file_size_mb(self):
        metadata = {"file_size_bytes": 2 * 1024 * 1024, "file_extension": ".jpg"}
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "File Size:" in rendered
        assert "MB" in rendered

    def test_with_file_size_kb(self):
        metadata = {"file_size_bytes": 512 * 1024}
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "KB" in rendered

    def test_with_dimensions(self):
        metadata = {"width": 1920, "height": 1080, "aspect_ratio": 1.78}
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "1920px" in rendered
        assert "1080px" in rendered
        assert "1.78" in rendered

    def test_with_camera_info(self):
        metadata = {"make": "Canon", "model": "EOS R5", "lens_model": "24-70mm"}
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "Canon" in rendered
        assert "EOS R5" in rendered
        assert "24-70mm" in rendered

    def test_with_exposure_info(self):
        metadata = {
            "exposure_time": "1/200",
            "f_number": 2.8,
            "iso_speed": 400,
            "focal_length": 50,
        }
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "1/200" in rendered
        assert "2.8" in rendered
        assert "400" in rendered
        assert "50" in rendered

    def test_with_date_info(self):
        metadata = {
            "date_taken": "2026:01:15 10:30:00",
            "date_created": "2026:01:15 10:30:00",
            "date_modified": "2026:01:20 12:00:00",
        }
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "Date Taken" in rendered
        assert "Date Created" in rendered
        assert "Date Modified" in rendered

    def test_with_gps_info(self):
        metadata = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 10.0,
            "location_name": "San Francisco",
        }
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "37.774900" in rendered
        assert "-122.419400" in rendered
        assert "10.0m" in rendered
        assert "San Francisco" in rendered

    def test_with_other_metadata(self):
        metadata = {
            "color_space": "sRGB",
            "orientation": "Horizontal",
            "software": "Lightroom",
            "copyright": "(c) 2026",
            "artist": "Photographer",
            "title": "Sunset",
            "image_description": "A beautiful sunset",
        }
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", metadata)
        rendered = str(result)
        assert "sRGB" in rendered
        assert "Lightroom" in rendered
        assert "Sunset" in rendered

    def test_image_preview_always_present(self):
        result = build_metadata_result("data:image/png;base64,abc", "test.jpg", None)
        rendered = str(result)
        assert "Image Preview" in rendered
        assert "test.jpg" in rendered


class TestStoreUploadCallback:
    def test_none_contents_returns_no_update(self):
        app = _make_app()
        cb = find_callback(app, "metadata-tester-store", "data").__wrapped__
        result = cb(None, "test.jpg")
        assert result == (dash.no_update, dash.no_update)

    def test_with_contents(self):
        app = _make_app()
        cb = find_callback(app, "metadata-tester-store", "data").__wrapped__
        result = cb("data:image/png;base64,abc", "test.jpg")
        assert result[0] == "data:image/png;base64,abc"
        assert "test.jpg" in result[1]


class TestExtractMetadataCallback:
    def _cb(self):
        app = _make_app()
        return find_callback(app, "metadata-tester-running", "data").__wrapped__

    def _extract_cb(self):
        app = _make_app()
        # The extract callback outputs to metadata-tester-progress, result, running
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "metadata-tester-result" and cprop == "children":
                    return v["callback"].__wrapped__
        raise KeyError("extract callback not found")

    def test_no_clicks_returns_no_update(self):
        cb = self._extract_cb()
        result = cb(None, None, None)
        assert result == (dash.no_update, dash.no_update, dash.no_update)

    def test_no_contents_returns_error(self):
        cb = self._extract_cb()
        result = cb(1, None, None)
        assert result[2] is False
        assert "No image uploaded" in str(result[1])

    def test_successful_extraction(self, tmp_path):
        cb = self._extract_cb()
        # Create a minimal image file
        import tempfile

        # Create a 1x1 PNG
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )

        contents = f"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        mock_metadata = ImageMetadata()
        mock_metadata.file_size_bytes = len(png_bytes)
        mock_metadata.file_extension = ".png"

        with (
            patch("src.callbacks.metadata_tester.extract_metadata", return_value=mock_metadata),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.png")
            mock_file.__enter__ = lambda self: mock_file
            mock_file.__exit__ = lambda self, *a: None
            mock_tmp.return_value = mock_file

            result = cb(1, contents, "test.png")

        assert result[2] is False  # running = False
        assert "Extracted Metadata" in str(result[1])

    def test_extraction_exception(self):
        cb = self._extract_cb()
        contents = "data:image/png;base64,abc"

        with (
            patch("src.callbacks.metadata_tester.extract_metadata", side_effect=Exception("parse error")),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/test.png"
            mock_file.__enter__ = lambda self: mock_file
            mock_file.__exit__ = lambda self, *a: None
            mock_tmp.return_value = mock_file

            result = cb(1, contents, "test.png")

        assert result[2] is False
        assert "Metadata Extraction Failed" in str(result[1])
