import json
import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest

from src.sidecar.database import FeaturesDatabase


class TestInitDb:
    def test_creates_database_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            assert not db_path.exists()

            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            assert db_path.exists()
            assert db_path.is_file()
            db.close()

    def test_creates_raw_features_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_features'"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "raw_features"
            db.close()

    def test_raw_features_has_all_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute("PRAGMA table_info(raw_features)")
            columns = {col[1]: col[2] for col in cursor.fetchall()}

            assert "id" in columns
            assert "image_path" in columns
            assert "model_output" in columns
            assert "success" in columns
            assert "model" in columns
            assert "created_at" in columns
            db.close()

    def test_creates_extracted_features_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='extracted_features'"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "extracted_features"
            db.close()

    def test_creates_feature_tags_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='feature_tags'"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "feature_tags"
            db.close()

    def test_idempotent_on_existing_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db1 = FeaturesDatabase(db_path)
            conn1 = db1.init_db()
            conn1.execute("INSERT INTO raw_features (image_path, model_output) VALUES ('/a.jpg', 'hello')")
            conn1.commit()
            db1.close()

            db2 = FeaturesDatabase(db_path)
            conn2 = db2.init_db()
            cursor = conn2.execute("SELECT model_output FROM raw_features")
            rows = cursor.fetchall()
            assert rows == [("hello",)]
            db2.close()

    def test_default_db_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expected = Path(tmpdir) / ".open-photo-agent" / "features.db"
            assert FeaturesDatabase.default_db_path(tmpdir) == expected

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deep = Path(tmpdir) / "a" / "b" / "c"
            db_path = deep / "features.db"
            assert not deep.exists()

            db = FeaturesDatabase(db_path)
            db.init_db()

            assert deep.exists()
            assert db_path.exists()
            db.close()


class TestSchema:
    def test_unique_index_on_image_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db.close()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_features_image_path'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_feature_tags_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db.close()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_feature_tags_tag'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_fts5_table_created_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db.close()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='extracted_features_fts'"
            )
            row = cursor.fetchone()
            conn.close()

            # Most modern Python builds include FTS5, but tolerate missing.
            if row is not None:
                assert row[0] == "extracted_features_fts"


class TestSaveExtraction:
    def test_insert_new_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "model": "m1"})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT image_path, success, model FROM raw_features")
            row = cursor.fetchone()
            conn.close()

            assert row[0] == "/photos/a.jpg"
            assert row[1] == 1
            assert row[2] == "m1"

    def test_upsert_existing_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "model": "m1"})
            db.save_extraction("/photos/a.jpg", {"success": False, "model": "m2"})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT success, model FROM raw_features WHERE image_path = ?", ("/photos/a.jpg",))
            row = cursor.fetchone()
            conn.close()

            assert row[0] == 0
            assert row[1] == "m2"

    def test_serialises_model_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": {"tags": ["beach"]}})

            data = db.get_extraction("/photos/a.jpg")
            assert data is not None
            assert data["parsed"]["tags"] == ["beach"]

    def test_populates_extracted_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {
                    "description": "A beach sunset",
                    "subjects": ["ocean", "sun"],
                    "mood": "calm",
                    "tags": ["beach", "sunset"],
                },
            })

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT description, subjects, mood, tags FROM extracted_features WHERE image_path = ?", ("/photos/a.jpg",))
            row = cursor.fetchone()
            conn.close()

            assert row[0] == "A beach sunset"
            assert row[1] == "ocean, sun"
            assert row[2] == "calm"
            assert row[3] == "beach sunset"

    def test_populates_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset"]},
            })

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", ("/photos/a.jpg",))
            rows = cursor.fetchall()
            conn.close()

            tags = {r[0] for r in rows}
            assert tags == {"beach", "sunset"}

    def test_replaces_tags_on_upsert(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": {"tags": ["a", "b"]}})
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": {"tags": ["c"]}})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", ("/photos/a.jpg",))
            rows = cursor.fetchall()
            conn.close()

            tags = {r[0] for r in rows}
            assert tags == {"c"}

    def test_handles_missing_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT description FROM extracted_features WHERE image_path = ?", ("/photos/a.jpg",))
            row = cursor.fetchone()
            cursor = conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", ("/photos/a.jpg",))
            tags = cursor.fetchall()
            conn.close()

            assert row[0] is None
            assert tags == []

    def test_handles_malformed_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": "not a dict"})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT description FROM extracted_features WHERE image_path = ?", ("/photos/a.jpg",))
            row = cursor.fetchone()
            cursor = conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", ("/photos/a.jpg",))
            tags = cursor.fetchall()
            conn.close()

            assert row[0] is None
            assert tags == []

    def test_converts_string_tag_to_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": {"tags": "single"}})

            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT tag FROM feature_tags WHERE image_path = ?", ("/photos/a.jpg",))
            rows = cursor.fetchall()
            conn.close()

            assert rows == [("single",)]


class TestQueryHelpers:
    def test_search_features_returns_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "sunset at the beach", "tags": ["beach"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"description": "mountain hike", "tags": ["nature"]},
            })

            # FTS may need a tiny delay or just works immediately.
            results = db.search_features("beach")
            paths = {r["image_path"] for r in results}
            assert "/photos/a.jpg" in paths
            assert "/photos/b.jpg" not in paths

    def test_search_features_includes_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "a photo", "tags": ["beach", "sunset"]},
            })

            results = db.search_features("sunset")
            assert len(results) == 1
            assert results[0]["tags"] == "beach, sunset"

    def test_list_all_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "parsed": {"tags": ["beach", "sunset"]}})
            db.save_extraction("/photos/b.jpg", {"success": True, "parsed": {"tags": ["mountain", "sunset"]}})

            tags = db.list_all_tags()
            assert tags == ["beach", "mountain", "sunset"]

    def test_list_tag_frequencies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["mountain", "sunset"]},
            })
            db.save_extraction("/photos/c.jpg", {
                "success": True,
                "parsed": {"tags": ["sunset"]},
            })

            freqs = db.list_tag_frequencies()
            assert freqs == [("sunset", 3), ("beach", 1), ("mountain", 1)]

    def test_list_tag_frequencies_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["a", "b", "c"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["b", "c", "d"]},
            })

            freqs = db.list_tag_frequencies(limit=2)
            assert len(freqs) == 2
            assert freqs[0] == ("b", 2)

    def test_list_tag_frequencies_restricted_empty_selection_returns_all(self):
        """Passing an empty list should fall back to list_tag_frequencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["mountain", "sunset"]},
            })

            restricted = db.list_tag_frequencies_restricted([])
            assert restricted == [("sunset", 2), ("beach", 1), ("mountain", 1)]

    def test_list_tag_frequencies_restricted_single_tag(self):
        """Only tags co-occurring with the selected tag are returned, excluding it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset", "ocean"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sand"]},
            })
            db.save_extraction("/photos/c.jpg", {
                "success": True,
                "parsed": {"tags": ["mountain", "sunset"]},
            })

            restricted = db.list_tag_frequencies_restricted(["beach"])
            # 'beach' itself should be excluded; only tags from photos with 'beach'
            tags_only = [tag for tag, _ in restricted]
            assert "beach" not in tags_only
            assert "sunset" in tags_only
            assert "ocean" in tags_only
            assert "sand" in tags_only
            # "mountain" doesn't co-occur with "beach"
            assert "mountain" not in tags_only

    def test_list_tag_frequencies_restricted_multiple_tags(self):
        """AND logic: tags must co-occur with ALL selected tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset", "ocean"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset", "sand"]},
            })
            db.save_extraction("/photos/c.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "hike"]},
            })

            restricted = db.list_tag_frequencies_restricted(["beach", "sunset"])
            tags_only = [tag for tag, _ in restricted]
            assert "beach" not in tags_only
            assert "sunset" not in tags_only
            assert "ocean" in tags_only
            assert "sand" in tags_only
            assert "hike" not in tags_only

    def test_list_tag_frequencies_restricted_case_insensitive(self):
        """Tag comparison should be case-insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["Beach", "Sunset"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"tags": ["BENCH", "Sunset"]},
            })

            restricted = db.list_tag_frequencies_restricted(["beach"])
            tags_only = [tag for tag, _ in restricted]
            assert "Sunset" in tags_only
            assert "Beach" not in tags_only
            # BENCH doesn't co-occur with Beach
            assert "BENCH" not in tags_only

    def test_list_tag_frequencies_restricted_missing_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.list_tag_frequencies_restricted(["beach"]) == []

    def test_list_tag_frequencies_restricted_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/1.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "a"]},
            })
            db.save_extraction("/photos/2.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "b"]},
            })
            db.save_extraction("/photos/3.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "c"]},
            })

            restricted = db.list_tag_frequencies_restricted(["beach"], limit=2)
            assert len(restricted) == 2

    def test_get_features_by_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "beach day", "tags": ["beach"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"description": "mountain day", "tags": ["mountain"]},
            })

            results = db.get_features_by_tag("beach")
            assert len(results) == 1
            assert results[0]["image_path"] == "/photos/a.jpg"
            assert results[0]["description"] == "beach day"

    def test_get_features_by_tags_empty_list_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach", "sunset"]},
            })
            assert db.get_features_by_tags([]) == []

    def test_get_features_by_tags_single_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "beach sunset", "tags": ["beach", "sunset"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"description": "mountain", "tags": ["mountain"]},
            })

            results = db.get_features_by_tags(["beach"])
            assert len(results) == 1
            assert results[0]["image_path"] == "/photos/a.jpg"

    def test_get_features_by_tags_and_logic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "beach sunset", "tags": ["beach", "sunset"]},
            })
            db.save_extraction("/photos/b.jpg", {
                "success": True,
                "parsed": {"description": "beach day", "tags": ["beach"]},
            })
            db.save_extraction("/photos/c.jpg", {
                "success": True,
                "parsed": {"description": "sunset mountain", "tags": ["sunset", "mountain"]},
            })

            results = db.get_features_by_tags(["beach", "sunset"])
            assert len(results) == 1
            assert results[0]["image_path"] == "/photos/a.jpg"

    def test_get_features_by_tags_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "beach sunset", "tags": ["Beach", "Sunset"]},
            })

            results = db.get_features_by_tags(["beach", "SUNSET"])
            assert len(results) == 1
            assert results[0]["image_path"] == "/photos/a.jpg"

    def test_get_features_by_tags_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"tags": ["beach"]},
            })
            assert db.get_features_by_tags(["mountain"]) == []

    def test_get_features_by_tags_missing_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.get_features_by_tags(["beach"]) == []

    def test_get_feature_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "model": "m1",
                "parsed": {"description": "test", "tags": ["tag1", "tag2"]},
            })

            summary = db.get_feature_summary("/photos/a.jpg")
            assert summary is not None
            assert summary["image_path"] == "/photos/a.jpg"
            assert summary["model"] == "m1"
            assert summary["description"] == "test"
            assert summary["tags"] == ["tag1", "tag2"]
            assert summary["success"] is True

    def test_get_feature_summary_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.get_feature_summary("/missing.jpg") is None

    def test_rebuild_fts_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "rebuild test"},
            })
            db.rebuild_fts_index()
            results = db.search_features("rebuild")
            assert len(results) == 1

    def test_fallback_when_fts5_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db._fts5_available = False
            db.save_extraction("/photos/a.jpg", {
                "success": True,
                "parsed": {"description": "fallback test"},
            })
            assert db.search_features("fallback") == []
            db.rebuild_fts_index()  # should be a no-op


class TestGetExtraction:
    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.get_extraction("/photos/missing.jpg") is None

    def test_returns_dict_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "model": "m1"})

            data = db.get_extraction("/photos/a.jpg")
            assert data is not None
            assert data["success"] is True
            assert data["model"] == "m1"


class TestIsProcessed:
    def test_false_when_db_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.is_processed("/photos/a.jpg") is False

    def test_false_when_row_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True})
            assert db.is_processed("/photos/b.jpg") is False

    def test_true_when_row_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True})
            assert db.is_processed("/photos/a.jpg") is True


class TestListExtractions:
    def test_empty_when_db_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            assert db.list_extractions() == []

    def test_returns_all_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.save_extraction("/photos/a.jpg", {"success": True, "image_path": "/photos/a.jpg"})
            db.save_extraction("/photos/b.jpg", {"success": False, "image_path": "/photos/b.jpg"})

            rows = db.list_extractions()
            assert len(rows) == 2
            paths = {r["image_path"] for r in rows}
            assert paths == {"/photos/a.jpg", "/photos/b.jpg"}


class TestThreadSafety:
    def test_concurrent_writes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            errors = []

            def save_many(start, count):
                try:
                    for i in range(start, start + count):
                        db.save_extraction(f"/photos/img_{i}.jpg", {"success": True, "id": i})
                except Exception as e:
                    errors.append(str(e))

            threads = []
            for t in range(4):
                t = threading.Thread(target=save_many, args=(t * 25, 25))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            assert not errors
            rows = db.list_extractions()
            assert len(rows) == 100


class TestExecuteQuery:
    def test_returns_columns_and_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()
            conn.execute("INSERT INTO raw_features (image_path, model_output) VALUES ('/a.jpg', 'hello')")
            conn.execute("INSERT INTO raw_features (image_path, model_output) VALUES ('/b.jpg', 'world')")
            conn.commit()
            db.close()

            db2 = FeaturesDatabase(db_path)
            columns, rows = db2.execute_query("SELECT id, model_output FROM raw_features ORDER BY id")

            assert "id" in columns
            assert "model_output" in columns
            assert rows == [(1, "hello"), (2, "world")]

    def test_empty_result_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db.close()

            columns, rows = db.execute_query("SELECT id, model_output FROM raw_features")
            assert "id" in columns
            assert "model_output" in columns
            assert rows == []

    def test_raises_on_missing_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            with pytest.raises(FileNotFoundError):
                db.execute_query("SELECT 1")

    def test_raises_on_invalid_sql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            db.init_db()
            db.close()

            with pytest.raises(sqlite3.Error):
                db.execute_query("SELECT * FROM missing_table")


class TestImageEmbeddings:
    """Tests for image_embeddings table and vector operations."""

    def test_image_embeddings_table_created(self):
        """Test that image_embeddings table is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='image_embeddings'"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "image_embeddings"
            db.close()

    def test_image_embeddings_has_all_columns(self):
        """Test that image_embeddings table has all required columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            cursor = conn.execute("PRAGMA table_info(image_embeddings)")
            columns = {col[1]: col[2] for col in cursor.fetchall()}

            assert "id" in columns
            assert "image_path" in columns
            assert "model_name" in columns
            assert "embedding_dimension" in columns
            assert "created_at" in columns
            db.close()

    def test_image_embeddings_indexes(self):
        """Test that indexes are created for image_embeddings table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            # Check path index
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_image_embeddings_path'"
            )
            row = cursor.fetchone()
            assert row is not None

            # Check model index
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_image_embeddings_model'"
            )
            row = cursor.fetchone()
            assert row is not None
            db.close()

    def test_unique_constraint(self):
        """Test UNIQUE constraint on (image_path, model_name)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            # Try to insert duplicate with ON CONFLICT clause
            conn.execute(
                """
                INSERT INTO image_embeddings (image_path, model_name, embedding_dimension, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("/test.jpg", "model1", 512, "2024-01-01")
            )

            # This should not raise an error due to ON CONFLICT clause
            conn.execute(
                """
                INSERT INTO image_embeddings (image_path, model_name, embedding_dimension, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(image_path, model_name) DO UPDATE SET
                    embedding_dimension=excluded.embedding_dimension,
                    created_at=excluded.created_at
                """,
                ("/test.jpg", "model1", 384, "2024-01-02")
            )

            # Check that only one row exists
            cursor = conn.execute(
                "SELECT COUNT(*) FROM image_embeddings WHERE image_path = ? AND model_name = ?",
                ("/test.jpg", "model1")
            )
            count = cursor.fetchone()[0]
            assert count == 1

            # Check that the second insert updated the row
            cursor = conn.execute(
                "SELECT embedding_dimension FROM image_embeddings WHERE image_path = ? AND model_name = ?",
                ("/test.jpg", "model1")
            )
            dimension = cursor.fetchone()[0]
            assert dimension == 384

            db.close()

    def test_multiple_models_same_image(self):
        """Test that multiple models can have embeddings for the same image."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "features.db"
            db = FeaturesDatabase(db_path)
            conn = db.init_db()

            # Insert embeddings from different models
            conn.execute(
                "INSERT INTO image_embeddings (image_path, model_name, embedding_dimension, created_at) VALUES (?, ?, ?, ?)",
                ("/test.jpg", "model1", 512, "2024-01-01")
            )
            conn.execute(
                "INSERT INTO image_embeddings (image_path, model_name, embedding_dimension, created_at) VALUES (?, ?, ?, ?)",
                ("/test.jpg", "model2", 384, "2024-01-01")
            )

            # Check both exist
            cursor = conn.execute(
                "SELECT COUNT(*) FROM image_embeddings WHERE image_path = ?",
                ("/test.jpg",)
            )
            count = cursor.fetchone()[0]
            assert count == 2

            db.close()

    def test_binary_vector_serialization(self):
        """Test binary vector serialization/deserialization."""
        from src.sidecar.database import FeaturesDatabase

        # Test vector to blob
        vector = [1.0, 2.0, 3.0, 4.0, 5.0]
        blob = FeaturesDatabase.vector_to_blob(vector)
        assert len(blob) == len(vector) * 4  # 4 bytes per float

        # Test blob to vector
        converted = FeaturesDatabase.blob_to_vector(blob, len(vector))
        assert len(converted) == len(vector)
        for i, val in enumerate(vector):
            assert abs(converted[i] - val) < 1e-6

    def test_binary_vector_wrong_size(self):
        """Test that blob_to_vector raises on wrong blob size."""
        from src.sidecar.database import FeaturesDatabase
        
        # Create a blob with wrong size
        import struct
        blob = struct.pack("!f", 1.0)  # Only 1 float
        
        with pytest.raises(ValueError):
            FeaturesDatabase.blob_to_vector(blob, 2)  # Expecting 2 floats
