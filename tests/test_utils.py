import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils import encode_image_file, compute_duration_stats


class TestEncodeImageFile(unittest.TestCase):
    @patch("src.utils.read_image_bytes")
    def test_encodes_image_to_base64_string(self, mock_read):
        mock_read.return_value = b"fake-image-bytes"
        result = encode_image_file("/some/fake/path.jpg")
        expected = base64.b64encode(b"fake-image-bytes").decode("utf-8")
        self.assertEqual(result, expected)
        mock_read.assert_called_once_with("/some/fake/path.jpg")


class TestComputeDurationStats(unittest.TestCase):
    def test_empty_list(self):
        stats = compute_duration_stats([])
        self.assertEqual(stats["min_ms"], 0.0)
        self.assertEqual(stats["max_ms"], 0.0)
        self.assertEqual(stats["avg_ms"], 0.0)
        self.assertEqual(stats["total_s"], 0.0)

    def test_single_value(self):
        stats = compute_duration_stats([100.0])
        self.assertEqual(stats["min_ms"], 100.0)
        self.assertEqual(stats["max_ms"], 100.0)
        self.assertEqual(stats["avg_ms"], 100.0)
        self.assertEqual(stats["total_s"], 0.1)

    def test_multiple_values(self):
        stats = compute_duration_stats([100.0, 200.0, 300.0])
        self.assertEqual(stats["min_ms"], 100.0)
        self.assertEqual(stats["max_ms"], 300.0)
        self.assertEqual(stats["avg_ms"], 200.0)
        self.assertEqual(stats["total_s"], 0.6)

    def test_handles_large_values(self):
        stats = compute_duration_stats([100000.0, 200000.0])
        self.assertEqual(stats["min_ms"], 100000.0)
        self.assertEqual(stats["max_ms"], 200000.0)
        self.assertEqual(stats["avg_ms"], 150000.0)
        self.assertEqual(stats["total_s"], 300.0)

    def test_all_keys_present(self):
        stats = compute_duration_stats([50.0])
        self.assertIn("min_ms", stats)
        self.assertIn("max_ms", stats)
        self.assertIn("avg_ms", stats)
        self.assertIn("total_s", stats)


if __name__ == "__main__":
    unittest.main()
