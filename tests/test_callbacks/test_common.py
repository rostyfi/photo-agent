import tempfile
import unittest
from pathlib import Path

from plugins.llm import create_extractor
from src.callbacks.common import (
    SORT_KEY_DATE,
    SORT_KEY_DATE_TAKEN,
    SORT_KEY_NAME,
    SORT_KEY_RELEVANCE,
    _db_session,
    _get_extractor,
    _open_fullscreen_content,
    _open_modal,
    sort_paths,
)
from src.config import AppConfig
from src.constants import SORT_ORDER_ASC, SORT_ORDER_DESC


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


class TestOpenModal(unittest.TestCase):
    def test_returns_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            is_open, body, store = _open_modal("/fake/path.jpg", td, 0, ["/fake/path.jpg"])
            self.assertTrue(is_open)
            self.assertIsNotNone(body)
            self.assertEqual(
                store,
                {"paths": ["/fake/path.jpg"], "original_paths": ["/fake/path.jpg"], "index": 0},
            )


class TestOpenFullscreenContent(unittest.TestCase):
    def test_returns_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            content, store = _open_fullscreen_content("/fake/path.jpg", td, 1, ["/a.jpg", "/fake/path.jpg"])
            self.assertIsNotNone(content)
            self.assertEqual(
                store,
                {
                    "paths": ["/a.jpg", "/fake/path.jpg"],
                    "original_paths": ["/a.jpg", "/fake/path.jpg"],
                    "index": 1,
                },
            )


class TestSortPaths(unittest.TestCase):
    """Exercise sort_paths against a temp folder with a real features.db."""

    def _make_db(self, td):
        from src.sidecar.database import FeaturesDatabase

        db = FeaturesDatabase(FeaturesDatabase.default_db_path(td))
        db.init_db()
        rows = [
            ("/photos/zebra.jpg", "2023:05:01 10:00:00", "2024-01-01T00:00:00", "zebra.jpg"),
            ("/photos/apple.jpg", None, "2022-03-02T00:00:00", "apple.jpg"),
            ("/photos/mango.jpg", "2021:12:25 08:30:00", "2021-12-20T00:00:00", "mango.jpg"),
        ]
        with db.get_connection() as conn:
            for path, date_taken, date_modified, file_name in rows:
                conn.execute(
                    "INSERT INTO image_metadata (image_path, date_taken, date_modified, file_name) "
                    "VALUES (?, ?, ?, ?)",
                    (path, date_taken, date_modified, file_name),
                )
            conn.commit()
        db.close()

    def test_name_sort_ascending(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(paths, SORT_KEY_NAME, td, original_paths=paths)
            self.assertEqual(result, ["/photos/apple.jpg", "/photos/mango.jpg", "/photos/zebra.jpg"])

    def test_date_taken_sort_with_missing_last(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(paths, SORT_KEY_DATE_TAKEN, td, original_paths=paths)
            # date_taken (falling back to date_modified when missing):
            # mango (2021-12-25) < apple (2022-03-02 via date_modified) < zebra (2023-05-01)
            self.assertEqual(result, ["/photos/mango.jpg", "/photos/apple.jpg", "/photos/zebra.jpg"])

    def test_date_sort_uses_file_modified(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(paths, SORT_KEY_DATE, td, original_paths=paths)
            # date_modified: mango(2021) < apple(2022) < zebra(2024)
            self.assertEqual(result, ["/photos/mango.jpg", "/photos/apple.jpg", "/photos/zebra.jpg"])

    def test_relevance_sort_uses_scores_desc(self):
        paths = ["/photos/a.jpg", "/photos/b.jpg", "/photos/c.jpg"]
        scores = {"/photos/a.jpg": 0.1, "/photos/b.jpg": 0.9, "/photos/c.jpg": 0.5}
        result = sort_paths(paths, SORT_KEY_RELEVANCE, None, original_paths=paths, scores=scores)
        self.assertEqual(result, ["/photos/b.jpg", "/photos/c.jpg", "/photos/a.jpg"])

    def test_relevance_without_scores_preserves_original(self):
        paths = ["/photos/a.jpg", "/photos/b.jpg", "/photos/c.jpg"]
        result = sort_paths(list(reversed(paths)), SORT_KEY_RELEVANCE, None, original_paths=paths)
        self.assertEqual(result, paths)

    def test_unknown_key_preserves_original(self):
        paths = ["/photos/a.jpg", "/photos/b.jpg"]
        result = sort_paths(list(reversed(paths)), "bogus", None, original_paths=paths)
        self.assertEqual(result, paths)

    def test_name_sort_descending(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(
                paths, SORT_KEY_NAME, td, original_paths=paths, order=SORT_ORDER_DESC
            )
            self.assertEqual(result, ["/photos/zebra.jpg", "/photos/mango.jpg", "/photos/apple.jpg"])

    def test_date_sort_descending_missing_last(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(
                paths, SORT_KEY_DATE, td, original_paths=paths, order=SORT_ORDER_DESC
            )
            # date_modified desc: zebra(2024) > apple(2022) > mango(2021); apple has
            # no date_taken but has date_modified, so it is not "missing".
            self.assertEqual(result, ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"])

    def test_date_taken_sort_descending_missing_last(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_db(td)
            paths = ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"]
            result = sort_paths(
                paths, SORT_KEY_DATE_TAKEN, td, original_paths=paths, order=SORT_ORDER_DESC
            )
            # date_taken desc: zebra(2023) > mango(2021); apple has no date_taken but
            # falls back to date_modified (2022), so it is present, not missing.
            self.assertEqual(result, ["/photos/zebra.jpg", "/photos/apple.jpg", "/photos/mango.jpg"])

    def test_relevance_sort_ascending(self):
        paths = ["/photos/a.jpg", "/photos/b.jpg", "/photos/c.jpg"]
        scores = {"/photos/a.jpg": 0.1, "/photos/b.jpg": 0.9, "/photos/c.jpg": 0.5}
        result = sort_paths(
            paths, SORT_KEY_RELEVANCE, None, original_paths=paths, scores=scores,
            order=SORT_ORDER_ASC,
        )
        self.assertEqual(result, ["/photos/a.jpg", "/photos/c.jpg", "/photos/b.jpg"])

    def test_default_order_for_relevance_is_desc(self):
        # order=None should default to desc for relevance.
        paths = ["/photos/a.jpg", "/photos/b.jpg", "/photos/c.jpg"]
        scores = {"/photos/a.jpg": 0.1, "/photos/b.jpg": 0.9, "/photos/c.jpg": 0.5}
        result = sort_paths(paths, SORT_KEY_RELEVANCE, None, original_paths=paths, scores=scores)
        self.assertEqual(result, ["/photos/b.jpg", "/photos/c.jpg", "/photos/a.jpg"])
