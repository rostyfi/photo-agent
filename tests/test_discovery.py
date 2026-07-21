import json
import os
import tempfile
import unittest
from pathlib import Path

from src.discovery import PhotoList
from src.sidecar.database import FeaturesDatabase


class TestPhotoList(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_file(self, rel_path: str) -> str:
        full = self.base / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.touch()
        return str(full)

    def _create_dir(self, rel_path: str) -> str:
        full = self.base / rel_path
        full.mkdir(parents=True, exist_ok=True)
        return str(full)

    def test_list_photos_recursive(self):
        self._create_file("a.jpg")
        self._create_file("b/c.png")
        self._create_file("d/e/f.gif")

        pl = PhotoList(recursive=True)
        result = pl.list_photos([str(self.base)])
        self.assertEqual(len(result), 3)

    def test_list_photos_non_recursive(self):
        self._create_file("a.jpg")
        self._create_file("b/c.png")
        self._create_file("d/e/f.gif")

        pl = PhotoList(recursive=False)
        result = pl.list_photos([str(self.base)])
        self.assertEqual(len(result), 1)
        self.assertIn("a.jpg", result[0])

    def test_list_photos_only_image_extensions(self):
        self._create_file("photo.jpg")
        self._create_file("doc.txt")
        self._create_file("script.py")
        self._create_file("image.heic")

        pl = PhotoList(recursive=True)
        result = pl.list_photos([str(self.base)])
        self.assertEqual(len(result), 2)
        suffixes = [Path(p).suffix for p in result]
        self.assertIn(".jpg", suffixes)
        self.assertIn(".heic", suffixes)

    def test_list_photos_custom_extensions(self):
        self._create_file("photo.jpg")
        self._create_file("image.png")

        pl = PhotoList(recursive=True, extensions={".png"})
        result = pl.list_photos([str(self.base)])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].endswith(".png"))

    def test_list_photos_with_limit(self):
        self._create_file("a.jpg")
        self._create_file("b.jpg")
        self._create_file("c.jpg")

        pl = PhotoList(recursive=True)
        result = pl.list_photos([str(self.base)], limit=2)
        self.assertEqual(len(result), 2)

    def test_list_photos_single_file_input(self):
        path = self._create_file("single.jpg")

        pl = PhotoList(recursive=True)
        result = pl.list_photos([path])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], path)

    def test_list_photos_nonexistent_path(self):
        pl = PhotoList(recursive=True)
        result = pl.list_photos(["/nonexistent/path"])
        self.assertEqual(len(result), 0)

    def test_list_photos_multiple_paths(self):
        p1 = self._create_file("dir1/a.jpg")
        p2 = self._create_file("dir2/b.png")

        pl = PhotoList(recursive=True)
        result = pl.list_photos([str(self.base / "dir1"), str(self.base / "dir2")])
        self.assertEqual(len(result), 2)

    def test_exclude_processed_from_no_sidecar_dir(self):
        self._create_file("photo.jpg")

        pl = PhotoList(recursive=True)
        result = pl.list_photos(
            [str(self.base)],
            exclude_processed_from=str(self.base),
        )
        self.assertEqual(len(result), 1)

    def test_exclude_processed_from_db_tracker(self):
        self._create_file("photo.jpg")
        self._create_file("photo2.jpg")

        # Use the new database-based tracker instead of WAL file
        from src.simple_processing_tracker import SimpleProcessingTracker
        tracker = SimpleProcessingTracker(str(self.base))
        tracker.mark_completed(str(self.base / "photo.jpg"))

        pl = PhotoList(recursive=True)
        result = pl.list_photos(
            [str(self.base)],
            exclude_processed_from=str(self.base),
        )
        self.assertEqual(len(result), 1)
        self.assertIn("photo2.jpg", result[0])

    def test_exclude_processed_from_db_tracker_no_sidecars(self):
        self._create_file("photo.jpg")

        # Use the new database-based tracker instead of WAL file
        from src.simple_processing_tracker import SimpleProcessingTracker
        tracker = SimpleProcessingTracker(str(self.base))
        tracker.mark_completed(str(self.base / "photo.jpg"))

        pl = PhotoList(recursive=True)
        result = pl.list_photos(
            [str(self.base)],
            exclude_processed_from=str(self.base),
        )
        self.assertEqual(len(result), 0)


    def test_exclude_processed_from_db(self):
        self._create_file("photo.jpg")
        self._create_file("photo2.jpg")

        db_path = FeaturesDatabase.default_db_path(self.base)
        db = FeaturesDatabase(db_path)
        db.init_db()
        db.save_extraction(str(self.base / "photo.jpg"), {"success": True, "image_path": str(self.base / "photo.jpg")})
        db.close()

        pl = PhotoList(recursive=True)
        result = pl.list_photos(
            [str(self.base)],
            exclude_processed_from=str(self.base),
        )
        self.assertEqual(len(result), 1)
        self.assertIn("photo2.jpg", result[0])

    def test_exclude_processed_from_db_no_wal(self):
        self._create_file("photo.jpg")

        db_path = FeaturesDatabase.default_db_path(self.base)
        db = FeaturesDatabase(db_path)
        db.init_db()
        db.save_extraction(str(self.base / "photo.jpg"), {"success": True, "image_path": str(self.base / "photo.jpg")})
        db.close()

        pl = PhotoList(recursive=True)
        result = pl.list_photos(
            [str(self.base)],
            exclude_processed_from=str(self.base),
        )
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
