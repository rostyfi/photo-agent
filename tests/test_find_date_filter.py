"""Tests for date-filtered photo search in the DB and FindTool arg parsing."""

import tempfile
from pathlib import Path

import pytest

from src.services.chat_tools.find import FindTool
from src.sidecar.database import FeaturesDatabase


def _save_image(db, path, model, vector, date_taken):
    db.save_embedding(path, model, vector)
    db.save_metadata(path, {"date_taken": date_taken})


class TestDateFilteredSearch:
    @pytest.fixture
    def temp_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FeaturesDatabase(Path(tmpdir) / "test_features.db")
            yield db
            db.close()

    def test_get_embeddings_date_filtered(self, temp_db):
        model = "test-model"
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        vec_c = [0.0, 0.0, 1.0]

        _save_image(temp_db, "/img/summer2025.jpg", model, vec_a, "2025:07:15 10:00:00")
        _save_image(temp_db, "/img/summer2024.jpg", model, vec_b, "2024:07:15 10:00:00")
        _save_image(temp_db, "/img/winter2026.jpg", model, vec_c, "2026:01:15 08:30:00")

        # Summer 2025 window -> only one image
        results = temp_db.get_embeddings_date_filtered(model, "2025-06-01", "2025-08-31")
        assert {p for p, _ in results} == {"/img/summer2025.jpg"}

        # Full 2024-2026 range -> all three
        all_results = temp_db.get_embeddings_date_filtered(model, "2024-01-01", "2026-12-31")
        assert len(all_results) == 3

    def test_find_similar_rest_with_date_filter(self, temp_db):
        model = "test-model"
        # Two near-identical vectors, one far. The near-duplicate outside the
        # date window must be excluded.
        target = [1.0, 0.0, 0.0]
        near = [0.99, 0.01, 0.0]
        far = [0.0, 0.0, 1.0]

        _save_image(temp_db, "/img/in_window.jpg", model, near, "2025:07:01 12:00:00")
        _save_image(temp_db, "/img/out_window.jpg", model, target, "2024:07:01 12:00:00")
        _save_image(temp_db, "/img/far.jpg", model, far, "2025:07:02 12:00:00")

        # Restrict to summer 2025 -> out_window (2024) excluded even though it
        # is the most similar to the query vector.
        results = temp_db.find_similar_rest(
            target, model, limit=10, date_start="2025-06-01", date_end="2025-08-31"
        )
        paths = [p for p, _ in results]
        assert "/img/out_window.jpg" not in paths
        assert "/img/in_window.jpg" in paths
        assert "/img/far.jpg" in paths

    def test_find_similar_rest_without_date_filter_returns_all(self, temp_db):
        model = "test-model"
        _save_image(temp_db, "/img/a.jpg", model, [1.0, 0.0], "2025:07:01 12:00:00")
        _save_image(temp_db, "/img/b.jpg", model, [0.0, 1.0], "2024:07:01 12:00:00")

        results = temp_db.find_similar_rest([1.0, 0.0], model, limit=10)
        assert len(results) == 2

    def test_exif_colon_format_matches(self, temp_db):
        """EXIF stores dates as YYYY:MM:DD ...; ensure colons are normalised."""
        model = "test-model"
        _save_image(temp_db, "/img/x.jpg", model, [1.0], "2025:08:18 14:30:00")
        results = temp_db.get_embeddings_date_filtered(model, "2025-08-01", "2025-08-31")
        assert len(results) == 1
        assert results[0][0] == "/img/x.jpg"


class TestFindToolParseArgs:
    def _tool(self):
        from src.config import AppConfig

        config = AppConfig(
            llm_host="localhost", llm_port=11434, llm_model="test",
            embedding_backend="dry_run", embedding_model="test",
        )
        return FindTool(config)

    def test_plain_description(self):
        desc, limit, ds, de = FindTool._parse_args("car")
        assert desc == "car"
        assert limit == 10
        assert ds is None and de is None

    def test_number_and_description(self):
        desc, limit, ds, de = FindTool._parse_args("5 car")
        assert desc == "car"
        assert limit == 5
        assert ds is None and de is None

    def test_date_filter(self):
        desc, limit, ds, de = FindTool._parse_args("car @last summer")
        assert desc == "car"
        assert limit == 10
        assert ds is not None and de is not None
        # "last summer" relative to the real today; just assert it's a summer
        # window (June-Aug) by month prefix.
        assert ds[5:7] in ("06", "07", "08")
        assert de[5:7] in ("06", "07", "08")

    def test_number_description_and_date(self):
        desc, limit, ds, de = FindTool._parse_args("5 dogs @summer 2024")
        assert desc == "dogs"
        assert limit == 5
        assert ds == "2024-06-01" and de == "2024-08-31"

    def test_unparseable_date_is_ignored(self):
        desc, _limit, ds, de = FindTool._parse_args("car @banana")
        assert desc == "car"
        assert ds is None and de is None

    def test_metadata_mentions_date(self):
        assert "@<date>" in FindTool.metadata.help_text
        assert "@<date>" in FindTool.metadata.usage
