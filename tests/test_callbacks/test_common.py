import tempfile
import unittest
from pathlib import Path

from plugins.llm import create_extractor
from src.callbacks.common import (
    _db_session,
    _get_extractor,
    _make_processing_config,
    _open_fullscreen_content,
    _open_modal,
)
from src.config import AppConfig


class TestDbSession(unittest.TestCase):
    def test_yields_none_when_no_db(self):
        with tempfile.TemporaryDirectory() as td, _db_session(td) as db:
            self.assertIsNone(db)

    def test_yields_db_when_file_exists(self):
        with tempfile.TemporaryDirectory() as td:
            from src.sidecar.database import FeaturesDatabase

            db_path = FeaturesDatabase.default_db_path(td)
            db = FeaturesDatabase(db_path)
            db.init_db()
            with _db_session(td) as db:
                self.assertIsNotNone(db)


class TestGetExtractor(unittest.TestCase):
    def test_coerces_defaults(self):
        # Test that _get_extractor creates an extractor with default values
        # We'll use create_extractor directly since we no longer use ExtractorProvider
        ext = _get_extractor("", "", "", "", "", "test prompt")
        self.assertEqual(ext.base_url, "http://127.0.0.1:11434")
        self.assertEqual(ext.model, "gemma4:e2b-it-qat")

    def test_uses_provided_values(self):
        # Test that _get_extractor uses provided values
        ext = _get_extractor("1.2.3.4", "9999", "mymodel", "ollama", "30", "test prompt")
        self.assertEqual(ext.base_url, "http://1.2.3.4:9999")
        self.assertEqual(ext.model, "mymodel")


class TestMakeProcessingConfig(unittest.TestCase):
    def test_defaults(self):
        pc = _make_processing_config("h", "1234", "m", "b", "60", "prompt")
        self.assertEqual(pc.backend, "b")
        self.assertEqual(pc.host, "h")
        self.assertEqual(pc.port, 1234)
        self.assertEqual(pc.model, "m")
        self.assertEqual(pc.timeout, 60)
        self.assertEqual(pc.default_prompt, "prompt")

    def test_dry_run_forces_dry_run_backend(self):
        pc = _make_processing_config("h", "1234", "m", "b", "60", "prompt", dry_run=True)
        self.assertEqual(pc.backend, "dry_run")

    def test_empty_port_timeout_fallback(self):
        pc = _make_processing_config("h", "", "m", "b", "", "prompt")
        self.assertEqual(pc.port, 11434)
        self.assertEqual(pc.timeout, 120)


class TestOpenModal(unittest.TestCase):
    def test_returns_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            is_open, body, store = _open_modal("/fake/path.jpg", td, 0, ["/fake/path.jpg"])
            self.assertTrue(is_open)
            self.assertIsNotNone(body)
            self.assertEqual(store, {"paths": ["/fake/path.jpg"], "index": 0})


class TestOpenFullscreenContent(unittest.TestCase):
    def test_returns_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            content, store = _open_fullscreen_content("/fake/path.jpg", td, 1, ["/a.jpg", "/fake/path.jpg"])
            self.assertIsNotNone(content)
            self.assertEqual(store, {"paths": ["/a.jpg", "/fake/path.jpg"], "index": 1})
