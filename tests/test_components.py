"""Tests for src/components.py — UI component builders."""

import datetime

import dash_bootstrap_components as dbc
from dash import html

from src.components import (
    _preview_url,
    build_chat_interface,
    build_detail_modal_content,
    build_errors_display,
    build_fullscreen_viewer,
    build_similar_photos_carousel,
)


class TestPreviewUrl:
    def test_basic_url(self):
        url = _preview_url("/photos/cat.jpg", "/folder", "thumb")
        assert "/preview" in url
        assert "path=" in url
        assert "folder=" in url
        assert "size=thumb" in url

    def test_default_size_is_thumb(self):
        url = _preview_url("/photos/cat.jpg", "/folder")
        assert "size=thumb" in url

    def test_full_size(self):
        url = _preview_url("/photos/cat.jpg", "/folder", "full")
        assert "size=full" in url

    def test_special_chars_quoted(self):
        url = _preview_url("/photos/my file.jpg", "/my folder")
        assert "my%20file.jpg" in url
        assert "my%20folder" in url


class TestBuildDetailModalContent:
    def test_no_metadata_shows_not_processed(self):
        result = build_detail_modal_content("/img.jpg", "/folder", None)
        # Should contain "Not yet processed"
        rendered = str(result)
        assert "Not yet processed" in rendered

    def test_with_metadata_shows_fields(self):
        metadata = {
            "description": "A cat on a sofa",
            "subjects": "cat",
            "objects": "sofa",
            "colors": "brown",
            "setting": "living room",
            "mood": "calm",
            "tags": ["animal", "pet"],
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "A cat on a sofa" in rendered
        assert "Tags:" in rendered
        assert "animal" in rendered

    def test_with_embedding(self):
        metadata = {"description": "test", "success": True}
        embedding = [0.1, 0.2, 0.3]
        result = build_detail_modal_content("/img.jpg", "/folder", metadata, embedding=embedding)
        rendered = str(result)
        assert "0.1000" in rendered

    def test_with_long_embedding_truncates(self):
        metadata = {"description": "test", "success": True}
        embedding = [float(i) for i in range(20)]
        result = build_detail_modal_content("/img.jpg", "/folder", metadata, embedding=embedding)
        rendered = str(result)
        assert "20 total" in rendered

    def test_with_embedding_error(self):
        metadata = {"description": "test", "success": True}
        result = build_detail_modal_content("/img.jpg", "/folder", metadata, embedding_error="OOM")
        rendered = str(result)
        assert "Error: OOM" in rendered

    def test_no_embedding_shows_warning(self):
        metadata = {"description": "test", "success": True}
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "Not generated" in rendered

    def test_no_embedding_with_model_output_error(self):
        metadata = {
            "description": "test",
            "success": True,
            "model_output": {"embedding_error": "Connection refused"},
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "Generation failed" in rendered

    def test_no_embedding_with_model_output_json_string(self):
        import json

        metadata = {
            "description": "test",
            "success": True,
            "model_output": json.dumps({"embedding_error": "timeout"}),
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "Generation failed" in rendered

    def test_no_folder_no_preview_url(self):
        result = build_detail_modal_content("/img.jpg", "", None)
        rendered = str(result)
        # Should still render, just with empty src
        assert "Not yet processed" in rendered

    def test_find_similar_button_present(self):
        result = build_detail_modal_content("/img.jpg", "/folder", None)
        rendered = str(result)
        assert "btn-find-similar" in rendered
        assert "btn-open-fullscreen" in rendered

    def test_metadata_with_image_metadata_dict(self):
        metadata = {
            "description": "test",
            "success": True,
            "metadata": {"camera_make": "Canon", "iso": 100},
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "Image Metadata" in rendered

    def test_metadata_with_empty_image_metadata(self):
        metadata = {
            "description": "test",
            "success": True,
            "metadata": {},
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        rendered = str(result)
        # Should not show Image Metadata section for empty dict
        assert "Image Metadata" not in rendered

    def test_metadata_with_none_image_metadata(self):
        metadata = {
            "description": "test",
            "success": True,
            "metadata": None,
        }
        result = build_detail_modal_content("/img.jpg", "/folder", metadata)
        # Should not crash
        assert result is not None


class TestBuildSimilarPhotosCarousel:
    def test_no_data_returns_empty(self):
        result = build_similar_photos_carousel(None, "/folder")
        assert isinstance(result, html.Div)
        assert result.children is None

    def test_empty_images_returns_empty(self):
        result = build_similar_photos_carousel({"images": [], "scores": []}, "/folder")
        assert isinstance(result, html.Div)
        assert result.children is None

    def test_with_images(self):
        data = {
            "images": ["/photos/a.jpg", "/photos/b.jpg"],
            "scores": [0.95, 0.85],
        }
        result = build_similar_photos_carousel(data, "/folder")
        rendered = str(result)
        assert "Similar Photos" in rendered
        assert "95.0%" in rendered
        assert "85.0%" in rendered
        assert "a.jpg" in rendered

    def test_filename_without_slash(self):
        data = {"images": ["photo.jpg"], "scores": [0.5]}
        result = build_similar_photos_carousel(data, "/folder")
        rendered = str(result)
        assert "photo.jpg" in rendered


class TestBuildFullscreenViewer:
    def test_no_metadata(self):
        result = build_fullscreen_viewer("/img.jpg", "/folder", None)
        rendered = str(result)
        assert "Not yet processed" in rendered

    def test_with_metadata(self):
        metadata = {"description": "sunset", "tags": ["nature"]}
        result = build_fullscreen_viewer("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "sunset" in rendered
        assert "nature" in rendered

    def test_with_embedding(self):
        metadata = {"description": "test", "success": True}
        embedding = [0.1, 0.2]
        result = build_fullscreen_viewer("/img.jpg", "/folder", metadata, embedding=embedding)
        rendered = str(result)
        assert "0.1000" in rendered

    def test_with_embedding_error(self):
        metadata = {"description": "test", "success": True}
        result = build_fullscreen_viewer("/img.jpg", "/folder", metadata, embedding_error="fail")
        rendered = str(result)
        assert "Error: fail" in rendered

    def test_no_embedding_warning(self):
        metadata = {"description": "test", "success": True}
        result = build_fullscreen_viewer("/img.jpg", "/folder", metadata)
        rendered = str(result)
        assert "Not generated" in rendered

    def test_no_folder_empty_preview(self):
        result = build_fullscreen_viewer("/img.jpg", "", None)
        assert result is not None


class TestBuildErrorsDisplay:
    def test_no_errors(self):
        result = build_errors_display([], "/folder")
        rendered = str(result)
        assert "No errors found" in rendered
        assert "success" in rendered

    def test_with_errors(self):
        errors = [
            {
                "image_path": "/photos/bad.jpg",
                "error_code": "LLM_ERROR",
                "error_msg": "Connection refused",
                "ts": "2026-01-15T10:30:00Z",
            }
        ]
        result = build_errors_display(errors, "/folder")
        rendered = str(result)
        assert "bad.jpg" in rendered
        assert "LLM_ERROR" in rendered
        assert "Connection refused" in rendered
        assert "2026-01-15" in rendered

    def test_errors_sorted_by_ts_descending(self):
        errors = [
            {
                "image_path": "/old.jpg",
                "error_code": "ERR",
                "error_msg": "old error",
                "ts": "2026-01-01T00:00:00Z",
            },
            {
                "image_path": "/new.jpg",
                "error_code": "ERR",
                "error_msg": "new error",
                "ts": "2026-02-01T00:00:00Z",
            },
        ]
        result = build_errors_display(errors, "/folder")
        rendered = str(result)
        # Newer error should appear first
        assert rendered.index("new.jpg") < rendered.index("old.jpg")

    def test_error_with_bad_timestamp(self):
        errors = [
            {
                "image_path": "/bad.jpg",
                "error_code": "ERR",
                "error_msg": "fail",
                "ts": "not-a-date",
            }
        ]
        result = build_errors_display(errors, "/folder")
        rendered = str(result)
        assert "bad.jpg" in rendered

    def test_error_with_empty_timestamp(self):
        errors = [
            {
                "image_path": "/bad.jpg",
                "error_code": "ERR",
                "error_msg": "fail",
                "ts": "",
            }
        ]
        result = build_errors_display(errors, "/folder")
        rendered = str(result)
        assert "bad.jpg" in rendered


class TestBuildChatInterface:
    def test_returns_card(self):
        result = build_chat_interface()
        rendered = str(result)
        assert "Chat with your photos" in rendered
        assert "chat-input" in rendered
        assert "chat-send" in rendered
        assert "btn-clear-chat" in rendered
