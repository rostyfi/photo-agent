import json
import os
import tempfile
import unittest
from pathlib import Path

from src.batch_state import read_batch_state, write_batch_state


class TestWriteBatchState(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.folder = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_writes_file_at_expected_path(self):
        write_batch_state(self.folder, "running", 10, 0)
        p = Path(self.folder) / ".local-photo-agent" / "batch_state.json"
        self.assertTrue(p.exists())

    def test_file_contains_core_fields(self):
        write_batch_state(self.folder, "running", 10, 5)
        p = Path(self.folder) / ".local-photo-agent" / "batch_state.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["total"], 10)
        self.assertEqual(data["completed"], 5)
        self.assertEqual(data["folder"], self.folder)

    def test_extra_kwargs_are_included(self):
        write_batch_state(self.folder, "running_all", 100, 0, status_msg="Process All started")
        p = Path(self.folder) / ".local-photo-agent" / "batch_state.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["status_msg"], "Process All started")

    def test_extra_timing_stats_are_included(self):
        write_batch_state(
            self.folder,
            "done",
            50,
            50,
            min_duration_ms=100.0,
            max_duration_ms=500.0,
            avg_duration_ms=250.0,
        )
        p = Path(self.folder) / ".local-photo-agent" / "batch_state.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["min_duration_ms"], 100.0)
        self.assertEqual(data["max_duration_ms"], 500.0)
        self.assertEqual(data["avg_duration_ms"], 250.0)

    def test_atomic_write_prevents_partial_reads(self):
        write_batch_state(self.folder, "running", 10, 0)

        write_batch_state(self.folder, "done", 10, 10, avg_duration_ms=123.0)

        p = Path(self.folder) / ".local-photo-agent" / "batch_state.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["avg_duration_ms"], 123.0)

    def test_writes_override_previous(self):
        write_batch_state(self.folder, "running", 10, 0)
        write_batch_state(self.folder, "running", 10, 3)
        data = read_batch_state(self.folder)
        self.assertEqual(data["completed"], 3)


class TestReadBatchState(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.folder = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_returns_none_when_no_file(self):
        result = read_batch_state(self.folder)
        self.assertIsNone(result)

    def test_returns_data_when_file_exists(self):
        write_batch_state(self.folder, "done", 5, 5)
        data = read_batch_state(self.folder)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "done")

    def test_returns_none_for_invalid_json(self):
        p = Path(self.folder) / ".local-photo-agent"
        p.mkdir(parents=True, exist_ok=True)
        (p / "batch_state.json").write_text("not valid json", encoding="utf-8")
        result = read_batch_state(self.folder)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
