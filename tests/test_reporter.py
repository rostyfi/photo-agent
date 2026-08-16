import json
import tempfile
import unittest
from pathlib import Path

from src.batch_state import read_batch_state, write_batch_state


class TestBatchState(unittest.TestCase):
    """Test batch state functions directly since we no longer have reporter classes."""

    def test_write_and_read_batch_state(self):
        with tempfile.TemporaryDirectory() as td:
            write_batch_state(td, "running", 10, 5, status_msg="Test running")
            state = read_batch_state(td)
            self.assertIsNotNone(state)
            self.assertEqual(state["status"], "running")
            self.assertEqual(state["total"], 10)
            self.assertEqual(state["completed"], 5)
            self.assertEqual(state["status_msg"], "Test running")

    def test_read_nonexistent_batch_state(self):
        with tempfile.TemporaryDirectory() as td:
            state = read_batch_state(td)
            self.assertIsNone(state)

    def test_write_done_state_with_stats(self):
        with tempfile.TemporaryDirectory() as td:
            write_batch_state(
                td,
                "done",
                10,
                10,
                avg_duration_ms=500.0,
                min_duration_ms=400.0,
                max_duration_ms=600.0,
                total_model_time_s=5.0,
                status_msg="All images processed",
            )
            state = read_batch_state(td)
            self.assertIsNotNone(state)
            self.assertEqual(state["status"], "done")
            self.assertEqual(state["total"], 10)
            self.assertEqual(state["completed"], 10)
            self.assertIn("avg_duration_ms", state)
            self.assertIn("min_duration_ms", state)
            self.assertIn("max_duration_ms", state)


if __name__ == "__main__":
    unittest.main()
