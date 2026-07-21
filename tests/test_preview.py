import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from src.config import AppConfig


class TestPreviewRoute(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.folder = self.tmpdir.name
        self.app, _ = create_app(AppConfig())
        self.client = self.app.server.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_missing_params_returns_404(self):
        resp = self.client.get("/preview")
        self.assertEqual(resp.status_code, 404)

    def test_missing_path_returns_404(self):
        resp = self.client.get(f"/preview?folder={self.folder}")
        self.assertEqual(resp.status_code, 404)

    def test_traversal_blocked(self):
        resp = self.client.get(f"/preview?path=/etc/passwd&folder={self.folder}")
        self.assertEqual(resp.status_code, 404)

    def test_file_outside_folder_blocked(self):
        other = tempfile.mkdtemp()
        try:
            f = Path(other) / "img.jpg"
            f.write_bytes(b"fake")
            resp = self.client.get(f"/preview?path={f}&folder={self.folder}")
            self.assertEqual(resp.status_code, 404)
        finally:
            shutil.rmtree(other)

    def test_missing_file_returns_404(self):
        p = Path(self.folder) / "missing.jpg"
        resp = self.client.get(f"/preview?path={p}&folder={self.folder}")
        self.assertEqual(resp.status_code, 404)

    def test_valid_image_returns_200(self):
        p = Path(self.folder) / "test.jpg"
        # Minimal JPEG header so mimetypes guesses correctly
        p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        resp = self.client.get(f"/preview?path={p}&folder={self.folder}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("image", resp.content_type)

    def test_heic_suffix_returns_jpeg_content_type(self):
        p = Path(self.folder) / "test.heic"
        p.write_bytes(b"anything")
        with patch("app.read_image_bytes", return_value=b"jpegbytes"):
            resp = self.client.get(f"/preview?path={p}&folder={self.folder}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, "image/jpeg")

    def test_size_full_parameter_accepted(self):
        p = Path(self.folder) / "test.png"
        # Minimal PNG header
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        resp = self.client.get(f"/preview?path={p}&folder={self.folder}&size=full")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("image", resp.content_type)


if __name__ == "__main__":
    unittest.main()
