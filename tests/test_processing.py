import threading
import unittest

from src.interfaces import ProcessingResult


class TestProcessingResult(unittest.TestCase):
    def test_defaults(self):
        result = ProcessingResult()
        self.assertFalse(result.success)
        self.assertIsNone(result.image_path)

    def test_as_dict(self):
        result = ProcessingResult(
            image_path="/tmp/test.jpg",
            success=True,
            model="test-model",
            total_duration_ms=100.0,
        )
        data = result.as_dict()
        self.assertEqual(data["image_path"], "/tmp/test.jpg")
        self.assertTrue(data["success"])
        self.assertEqual(data["model"], "test-model")
        self.assertEqual(data["total_duration_ms"], 100.0)
        self.assertNotIn("error", data)

    def test_as_dict_omits_none(self):
        result = ProcessingResult(success=False, error="something")
        data = result.as_dict()
        self.assertIn("error", data)
        self.assertNotIn("image_path", data)


class TestBatchJob(unittest.TestCase):
    """Test BatchJob-like behavior from processing.py (now in state/coordinator)."""

    def test_snapshot_returns_copy(self):
        job = _SimpleBatchJob(total=1)
        job.add({"id": 1})
        results1, _, _ = job.snapshot()
        results1.append({"id": "modified"})
        results2, _, _ = job.snapshot()
        self.assertEqual(len(results2), 1)

    def test_thread_safety_concurrent_adds(self):
        job = _SimpleBatchJob(total=100)
        errors = []

        def add_many(start, count):
            try:
                for i in range(start, start + count):
                    job.add({"id": i})
            except Exception as e:
                errors.append(str(e))

        threads = []
        for t in range(4):
            t = threading.Thread(target=add_many, args=(t * 25, 25))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        results, _, _ = job.snapshot()
        self.assertEqual(len(results), 100)


class _SimpleBatchJob:
    """Simple thread-safe result container for testing."""

    def __init__(self, total):
        self.total = total
        self._results = []
        self._lock = threading.Lock()
        self.done = False
        self._added_count = 0

    def add(self, result):
        with self._lock:
            self._results.append(result)
            self._added_count += 1

    def snapshot(self):
        with self._lock:
            return self._results.copy(), self.done, self.total


if __name__ == "__main__":
    unittest.main()
