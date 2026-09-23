"""Tests for src/callbacks/prompt_tester.py — prompt testing UI."""

from unittest.mock import MagicMock, Mock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

from src.callbacks.prompt_tester import build_extraction_result, register_prompt_tester_callbacks
from src.interfaces import ProcessingResult
from tests.test_callbacks import find_callback


def _make_app():
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = html.Div(
        [
            html.Div(id="prompt-tester-store"),
            html.Div(id="prompt-tester-filename"),
            html.Div(id="prompt-tester-progress"),
            html.Div(id="prompt-tester-result"),
            html.Div(id="prompt-tester-running"),
            html.Div(id="btn-prompt-tester-extract"),
            html.Div(id="prompt-tester-upload"),
            html.Div(id="prompt-tester-prompt"),
            html.Div(id="input-host"),
            html.Div(id="input-port"),
            html.Div(id="input-model"),
            html.Div(id="input-backend"),
            html.Div(id="input-timeout"),
            html.Div(id="chk-dry-run"),
            html.Div(id="collapse-raw-response"),
            html.Div(id="btn-toggle-raw-response"),
        ]
    )

    mock_create_fn = MagicMock()
    mock_config = MagicMock()
    mock_config.default_prompt = "default prompt"
    register_prompt_tester_callbacks(app, mock_create_fn, mock_config)
    return app


class TestBuildExtractionResult:
    def _result(self, **kwargs):
        defaults = {
            "image_path": "/test.jpg",
            "success": True,
            "response": '{"description": "a cat"}',
            "model": "test-model",
            "parsed": {"description": "a cat"},
        }
        defaults.update(kwargs)
        return ProcessingResult(**defaults)

    def test_basic_result(self):
        result = self._result()
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "Image Preview" in rendered
        assert "test.jpg" in rendered
        assert "test-model" in rendered

    def test_with_duration(self):
        result = self._result(total_duration_ms=1234.5)
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "1234.5ms" in rendered

    def test_no_duration(self):
        result = self._result(total_duration_ms=None)
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "N/A" in rendered

    def test_with_eval_count(self):
        result = self._result(eval_count=42)
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "42" in rendered

    def test_parsed_features(self):
        result = self._result(parsed={"description": "a cat", "mood": "happy"})
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "Parsed Features" in rendered
        assert "a cat" in rendered

    def test_no_parsed(self):
        result = self._result(parsed=None)
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "Parsed Features" not in rendered

    def test_with_error(self):
        result = self._result(error="Something went wrong")
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "Error" in rendered
        assert "Something went wrong" in rendered

    def test_dry_run_notice(self):
        result = self._result()
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result, dry_run=True)
        rendered = str(component)
        assert "dry-run" in rendered.lower()

    def test_raw_response_section(self):
        result = self._result(response="raw text output")
        component = build_extraction_result("data:image/png;base64,abc", "test.jpg", result)
        rendered = str(component)
        assert "Raw Response" in rendered
        assert "raw text output" in rendered


class TestStoreUploadCallback:
    def test_none_contents(self):
        app = _make_app()
        cb = find_callback(app, "prompt-tester-store", "data").__wrapped__
        result = cb(None, "test.jpg")
        assert result == (dash.no_update, dash.no_update)

    def test_with_contents(self):
        app = _make_app()
        cb = find_callback(app, "prompt-tester-store", "data").__wrapped__
        result = cb("data:image/png;base64,abc", "test.jpg")
        assert result[0] == "data:image/png;base64,abc"
        assert "test.jpg" in result[1]


class TestSetRunningState:
    def test_no_clicks(self):
        app = _make_app()
        cb = find_callback(app, "prompt-tester-running", "data").__wrapped__
        result = cb(None)
        assert result == dash.no_update

    def test_with_clicks(self):
        app = _make_app()
        cb = find_callback(app, "prompt-tester-running", "data").__wrapped__
        result = cb(1)
        assert result is True


class TestUpdateExtractButtonText:
    def test_no_update_when_none(self):
        app = _make_app()
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "btn-prompt-tester-extract" and cprop == "children":
                    cb = v["callback"].__wrapped__
                    break

        result = cb(None)
        assert result == dash.no_update

    def test_running_shows_running_text(self):
        app = _make_app()
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "btn-prompt-tester-extract" and cprop == "children":
                    cb = v["callback"].__wrapped__
                    break

        result = cb(True)
        assert "Running" in result

    def test_not_running_shows_extract_text(self):
        app = _make_app()
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "btn-prompt-tester-extract" and cprop == "children":
                    cb = v["callback"].__wrapped__
                    break

        result = cb(False)
        assert "Extract Features" in result


class TestToggleRawResponse:
    def _cb(self):
        app = _make_app()
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "collapse-raw-response" and cprop == "is_open":
                    return v["callback"].__wrapped__
        raise KeyError("toggle callback not found")

    def test_no_clicks(self):
        cb = self._cb()
        result = cb(None, False)
        assert result == (dash.no_update, dash.no_update)

    def test_open_to_close(self):
        cb = self._cb()
        result = cb(1, True)
        assert result[0] is False
        assert "Show" in result[1]

    def test_close_to_open(self):
        cb = self._cb()
        result = cb(1, False)
        assert result[0] is True
        assert "Hide" in result[1]


class TestExtractFeatures:
    def _cb(self):
        app = _make_app()
        for _k, v in app.callback_map.items():
            out = v.get("output")
            outs = out if isinstance(out, list) else [out]
            for o in outs:
                cid = getattr(o, "component_id", o)
                cprop = getattr(o, "component_property", o)
                if cid == "prompt-tester-result" and cprop == "children":
                    return v["callback"].__wrapped__
        raise KeyError("extract callback not found")

    def test_no_clicks(self):
        cb = self._cb()
        result = cb(None, None, None, None, None, None, None, None, None, None)
        assert result == (dash.no_update, dash.no_update, dash.no_update)

    def test_no_contents_returns_error(self):
        cb = self._cb()
        result = cb(1, None, None, None, None, None, None, None, None, None)
        assert result[2] is False
        assert "No image uploaded" in str(result[1])

    def test_dry_run_extraction(self):
        cb = self._cb()
        contents = "data:image/png;base64,abc"

        mock_extractor = MagicMock()
        mock_result = ProcessingResult(
            image_path="/test.jpg",
            success=True,
            response='{"description": "test"}',
            model="dry_run",
            parsed={"description": "test"},
        )
        mock_extractor.extract_b64.return_value = mock_result

        with patch("src.callbacks.prompt_tester.create_extractor", return_value=mock_extractor):
            result = cb(
                1,  # n_clicks
                contents,  # contents
                "test.jpg",  # filename
                None,  # custom_prompt
                None, None, None, None, None,  # host, port, model, backend, timeout
                True,  # dry_run
            )

        assert result[2] is False
        assert "Extraction Result" in str(result[1])

    def test_extraction_exception(self):
        cb = self._cb()
        contents = "data:image/png;base64,abc"

        with patch("src.callbacks.prompt_tester.create_extractor", side_effect=Exception("conn error")):
            result = cb(
                1,
                contents,
                "test.jpg",
                None,
                "host", "port", "model", "backend", "60",
                False,
            )

        assert result[2] is False
        assert "Extraction Failed" in str(result[1])
