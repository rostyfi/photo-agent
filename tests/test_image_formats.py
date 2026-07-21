import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.formats.image import read_image_bytes, _detect_extension_by_magic
from plugins.formats.registry import register_format, get_reader, unregister_format
from plugins.formats.heic.converter import (
    convert_heic_to_jpeg_bytes,
    validate_heic_integrity,
    PIL_AVAILABLE,
    HEIF_AVAILABLE,
)


class TestImageBytesReading(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures"
        self.sample_jpg = self.fixtures_dir / "sample.jpg"

    def test_read_image_bytes_jpg(self):
        raw = read_image_bytes(self.sample_jpg)
        self.assertIsInstance(raw, bytes)
        self.assertGreater(len(raw), 0)
        self.assertEqual(raw[:3], b"\xff\xd8\xff")

    def test_read_image_bytes_nonexistent(self):
        with self.assertRaises(FileNotFoundError):
            read_image_bytes("/nonexistent/path.jpg")

    def test_read_image_bytes_unknown_format_fallback(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test data")
            tmp_path = f.name

        try:
            raw = read_image_bytes(tmp_path)
            self.assertEqual(raw, b"test data")
        finally:
            os.unlink(tmp_path)

    def test_read_image_bytes_registered_format(self):
        registered = []

        def fake_reader(path):
            registered.append(str(path))
            return b"processed"

        register_format((".foo",), fake_reader)

        with tempfile.NamedTemporaryFile(suffix=".foo", delete=False) as f:
            f.write(b"test")
            tmp_path = f.name

        try:
            raw = read_image_bytes(tmp_path)
            self.assertEqual(raw, b"processed")
            self.assertIn(tmp_path, registered)
        finally:
            os.unlink(tmp_path)
            unregister_format((".foo",))

    def test_get_reader_registered(self):
        def dummy(path):
            return b""
        register_format((".testext",), dummy)
        self.assertIsNotNone(get_reader(".testext"))
        unregister_format((".testext",))

    def test_get_reader_unregistered(self):
        self.assertIsNone(get_reader(".nonexistent"))


class TestMagicByteDetection(unittest.TestCase):
    def test_detect_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".png")
        finally:
            os.unlink(tmp)

    def test_detect_gif_87a(self):
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(b"GIF87a\x00\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".gif")
        finally:
            os.unlink(tmp)

    def test_detect_gif_89a(self):
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(b"GIF89a\x00\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".gif")
        finally:
            os.unlink(tmp)

    def test_detect_bmp(self):
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            f.write(b"BM\x00\x00\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".bmp")
        finally:
            os.unlink(tmp)

    def test_detect_webp(self):
        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as f:
            f.write(b"RIFF\x00\x00\x00\x00WEBP")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".webp")
        finally:
            os.unlink(tmp)

    def test_detect_tif_little_endian(self):
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
            f.write(b"II*\x00\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".tif")
        finally:
            os.unlink(tmp)

    def test_detect_tif_big_endian(self):
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
            f.write(b"MM\x00*\x00\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".tif")
        finally:
            os.unlink(tmp)

    def test_detect_heic(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x00ftypheic\x00\x00")
            tmp = f.name
        try:
            self.assertEqual(_detect_extension_by_magic(Path(tmp)), ".heic")
        finally:
            os.unlink(tmp)

    def test_detect_heif(self):
        with tempfile.NamedTemporaryFile(suffix=".heif", delete=False) as f:
            f.write(b"\x00\x00\x00\x00ftypmif1\x00\x00")
            tmp = f.name
        try:
            result = _detect_extension_by_magic(Path(tmp))
            # "mif1" does not contain "heif", so this won't match
            self.assertIsNone(result)
        finally:
            os.unlink(tmp)

    def test_detect_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertIsNone(_detect_extension_by_magic(Path(tmp)))
        finally:
            os.unlink(tmp)


class TestHeicConverter(unittest.TestCase):
    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            convert_heic_to_jpeg_bytes("/nonexistent.heic")

    @unittest.skipIf(not (PIL_AVAILABLE and HEIF_AVAILABLE), "Pillow or pillow-heif not available")
    def test_convert_heic_to_jpeg_bytes_with_real_file(self):
        fixtures_dir = Path(__file__).parent / "fixtures"
        heic_files = list(fixtures_dir.glob("*.heic")) + list(fixtures_dir.glob("*.heif"))
        if not heic_files:
            self.skipTest("No HEIC/HEIF fixture files found")
        result = convert_heic_to_jpeg_bytes(heic_files[0])
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)
        self.assertEqual(result[:3], b"\xff\xd8\xff")

    @patch("plugins.formats.heic.converter.HEIF_AVAILABLE", False)
    def test_missing_pillow_heif(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x00ftypheic")
            tmp = f.name
        try:
            with self.assertRaises(RuntimeError) as ctx:
                convert_heic_to_jpeg_bytes(tmp)
            self.assertIn("pillow-heif", str(ctx.exception))
        finally:
            os.unlink(tmp)

    @patch("plugins.formats.heic.converter.PIL_AVAILABLE", False)
    @patch("plugins.formats.heic.converter.HEIF_AVAILABLE", True)
    def test_missing_pillow(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x00ftypheic")
            tmp = f.name
        try:
            with self.assertRaises(RuntimeError) as ctx:
                convert_heic_to_jpeg_bytes(tmp)
            self.assertIn("Pillow", str(ctx.exception))
        finally:
            os.unlink(tmp)


class TestHeicIntegrity(unittest.TestCase):
    def test_valid_heic_signature(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertTrue(validate_heic_integrity(tmp))
        finally:
            os.unlink(tmp)

    def test_valid_heif_mif1_signature(self):
        with tempfile.NamedTemporaryFile(suffix=".heif", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertTrue(validate_heic_integrity(tmp))
        finally:
            os.unlink(tmp)

    def test_too_small_file(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"short")
            tmp = f.name
        try:
            self.assertFalse(validate_heic_integrity(tmp))
        finally:
            os.unlink(tmp)

    def test_missing_ftyp_box(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x18XXXXheic\x00\x00\x00\x00heic\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertFalse(validate_heic_integrity(tmp))
        finally:
            os.unlink(tmp)

    def test_unknown_brand(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypxxxx\x00\x00\x00\x00xxxx\x00\x00\x00\x00")
            tmp = f.name
        try:
            self.assertFalse(validate_heic_integrity(tmp))
        finally:
            os.unlink(tmp)

    def test_nonexistent_file(self):
        self.assertFalse(validate_heic_integrity("/nonexistent/file.heic"))

    def test_not_a_file(self):
        self.assertFalse(validate_heic_integrity("/"))


class TestHeicQualityFromEnv(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_default_quality(self):
        from plugins.formats.heic.converter import _env_quality
        self.assertEqual(_env_quality(), 95)

    @patch.dict(os.environ, {"OPEN_PHOTO_AGENT_HEIC_JPEG_QUALITY": "80"}, clear=True)
    def test_custom_quality(self):
        from plugins.formats.heic.converter import _env_quality
        self.assertEqual(_env_quality(), 80)

    @patch.dict(os.environ, {"OPEN_PHOTO_AGENT_HEIC_JPEG_QUALITY": "not_a_number"}, clear=True)
    def test_invalid_quality_falls_back(self):
        from plugins.formats.heic.converter import _env_quality
        self.assertEqual(_env_quality(), 95)

    @patch.dict(os.environ, {"OPEN_PHOTO_AGENT_HEIC_JPEG_QUALITY": "0"}, clear=True)
    def test_quality_below_1_clamped(self):
        from plugins.formats.heic.converter import _env_quality
        self.assertEqual(_env_quality(), 1)

    @patch.dict(os.environ, {"OPEN_PHOTO_AGENT_HEIC_JPEG_QUALITY": "150"}, clear=True)
    def test_quality_above_100_clamped(self):
        from plugins.formats.heic.converter import _env_quality
        self.assertEqual(_env_quality(), 100)


if __name__ == "__main__":
    unittest.main()
