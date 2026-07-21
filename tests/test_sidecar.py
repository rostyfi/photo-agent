import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sidecar import DatabaseSidecarStore, get_writer
from src.sidecar.database import FeaturesDatabase


class TestGetWriter(unittest.TestCase):
    def test_get_writer_returns_database_store(self):
        writer = get_writer()
        self.assertIsInstance(writer, DatabaseSidecarStore)

    def test_get_writer_returns_same_instance(self):
        w1 = get_writer()
        w2 = get_writer()
        self.assertIs(w1, w2)


class TestDatabaseSidecarStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.image_path = os.path.join(self.tmpdir.name, "subdir", "test_photo.jpg")
        os.makedirs(os.path.dirname(self.image_path), exist_ok=True)
        Path(self.image_path).write_bytes(b"fake-image-data")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_save_creates_db_file(self):
        writer = DatabaseSidecarStore()
        result = {"success": True, "model": "test-model"}
        path = writer.save(self.image_path, result)

        self.assertTrue(os.path.isfile(path))
        expected_path = FeaturesDatabase.default_db_path(Path(self.image_path).parent)
        self.assertEqual(Path(path), expected_path)

    def test_save_and_load(self):
        writer = DatabaseSidecarStore()
        result = {"success": True, "model": "test-model", "parsed": {"a": 1}}
        writer.save(self.image_path, result)

        data = writer.load(self.image_path)
        self.assertIsNotNone(data)
        self.assertTrue(data["success"])
        self.assertEqual(data["model"], "test-model")
        self.assertEqual(data["parsed"], {"a": 1})

    def test_exists(self):
        writer = DatabaseSidecarStore()
        self.assertFalse(writer.exists(self.image_path))
        writer.save(self.image_path, {"success": True})
        self.assertTrue(writer.exists(self.image_path))

    def test_load_returns_none_when_missing(self):
        writer = DatabaseSidecarStore()
        self.assertIsNone(writer.load(self.image_path))

    def test_sidecar_path_returns_db_path(self):
        sp = DatabaseSidecarStore.sidecar_path(self.image_path)
        expected = FeaturesDatabase.default_db_path(Path(self.image_path).parent)
        self.assertEqual(sp, expected)


if __name__ == "__main__":
    unittest.main()
