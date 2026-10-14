"""Tests for the sequential processor module."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.llm import create_extractor
from src.interfaces import ProcessingResult
from src.sequential_processor import SequentialProcessor, process_image, process_paths


@pytest.fixture
def temp_folder():
    """Create a temporary folder for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_extractor():
    """Create a mock extractor for testing."""
    mock = MagicMock()
    mock.extract_b64.return_value = ProcessingResult(
        success=True,
        image_path=None,
        model="test-model",
        response='{"description": "test"}',
        parsed={"description": "test"},
        total_duration_ms=100.0,
        eval_count=10,
    )
    mock.base_url = "http://test:11434"
    mock.model = "test-model"
    return mock


class TestSequentialProcessor:
    """Tests for SequentialProcessor class."""

    def test_init(self, mock_extractor):
        """Test SequentialProcessor initialization."""
        processor = SequentialProcessor(mock_extractor)
        assert processor.extractor == mock_extractor
        assert processor.config is not None

    def test_process_image(self, mock_extractor, temp_folder):
        """Test processing a single image."""
        # Create a test image file
        image_path = Path(temp_folder) / "test.jpg"
        image_path.write_bytes(b"test image data")

        processor = SequentialProcessor(mock_extractor)

        # Mock encode_image_file to return a base64 string
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_image(str(image_path), prompt="test prompt")

        assert result.success is True
        assert result.image_path == str(image_path)
        assert mock_extractor.extract_b64.called

    def test_process_paths(self, mock_extractor, temp_folder):
        """Test processing multiple paths."""
        # Create test image files
        paths = []
        for i in range(3):
            image_path = Path(temp_folder) / f"test_{i}.jpg"
            image_path.write_bytes(b"test image data")
            paths.append(str(image_path))

        processor = SequentialProcessor(mock_extractor)

        # Mock encode_image_file
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="test prompt", resume=False)

        assert result["total_found"] == 3
        assert result["processed"] == 3
        assert result["skipped"] == 0
        assert result["successes"] == 3
        assert result["failures"] == 0
        assert len(result["results"]) == 3

    def test_process_paths_with_resume(self, mock_extractor, temp_folder):
        """Test processing with resume enabled."""
        # Create test image files
        paths = []
        for i in range(3):
            image_path = Path(temp_folder) / f"test_{i}.jpg"
            image_path.write_bytes(b"test image data")
            paths.append(str(image_path))

        processor = SequentialProcessor(mock_extractor)

        # Mock SimpleProcessingTracker to return some processed files
        with patch("src.sequential_processor.SimpleProcessingTracker") as mock_tracker_class:
            mock_tracker = MagicMock()
            # Return the first path as already processed
            mock_tracker.get_processed_files.return_value = {paths[0]}
            mock_tracker_class.return_value = mock_tracker

            with patch("src.sequential_processor.encode_image_file") as mock_encode:
                mock_encode.return_value = "base64_test_data"
                result = processor.process_paths(paths, prompt="test prompt", resume=True)

        assert result["total_found"] == 3
        assert result["processed"] == 2  # Two processed (one skipped)
        assert result["skipped"] == 1


class TestProcessFunctions:
    """Tests for standalone process functions."""

    def test_process_image(self, mock_extractor, temp_folder):
        """Test the standalone process_image function."""
        image_path = Path(temp_folder) / "test.jpg"
        image_path.write_bytes(b"test image data")

        with patch("src.sequential_processor.SequentialProcessor") as mock_processor_class:
            mock_processor = MagicMock()
            mock_result = ProcessingResult(
                success=True,
                image_path=str(image_path),
                model="test-model",
            )
            mock_processor.process_image.return_value = mock_result
            mock_processor_class.return_value = mock_processor

            result = process_image(str(image_path), mock_extractor, prompt="test")

        assert result.success is True
        assert result.image_path == str(image_path)

    def test_process_paths(self, mock_extractor, temp_folder):
        """Test the standalone process_paths function."""
        paths = []
        for i in range(2):
            image_path = Path(temp_folder) / f"test_{i}.jpg"
            image_path.write_bytes(b"test image data")
            paths.append(str(image_path))

        with patch("src.sequential_processor.SequentialProcessor") as mock_processor_class:
            mock_processor = MagicMock()
            mock_result = {
                "total_found": 2,
                "processed": 2,
                "skipped": 0,
                "successes": 2,
                "failures": 0,
                "results": [],
            }
            mock_processor.process_paths.return_value = mock_result
            mock_processor_class.return_value = mock_processor

            result = process_paths(paths, mock_extractor, prompt="test")

        assert result["total_found"] == 2
        assert result["processed"] == 2


class TestErrorHandling:
    """Tests for error handling in sequential processor."""

    def test_process_image_failure(self, temp_folder):
        """Test handling of extraction failures."""
        mock_extractor = MagicMock()
        mock_extractor.extract_b64.side_effect = RuntimeError("Test error")

        processor = SequentialProcessor(mock_extractor)

        image_path = Path(temp_folder) / "test.jpg"
        image_path.write_bytes(b"test image data")

        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"

            with pytest.raises(RuntimeError, match="Test error"):
                processor.process_image(str(image_path))

    def test_process_paths_with_failures(self, mock_extractor, temp_folder):
        """Test processing with some failures."""
        # Create test image files
        paths = []
        for i in range(3):
            image_path = Path(temp_folder) / f"test_{i}.jpg"
            image_path.write_bytes(b"test image data")
            paths.append(str(image_path))

        # Make the second image fail
        def extract_side_effect(*args, **kwargs):
            # Check which image is being processed
            # This is a simplified test - in reality we'd need to track the image_path
            raise Exception("Test failure")

        mock_extractor.extract_b64.side_effect = extract_side_effect

        processor = SequentialProcessor(mock_extractor)

        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="test prompt", resume=False)

        # Should have some failures
        assert result["failures"] > 0

    def test_failed_extraction_marks_tracker_failed(self, temp_folder):
        """When extract_b64 returns success=False (not raises), tracker marks as failed."""
        mock_extractor = MagicMock()
        mock_extractor.extract_b64.return_value = ProcessingResult(
            success=False,
            error="Model returned empty response",
            error_code="invalid_response",
            model="test-model",
        )

        processor = SequentialProcessor(mock_extractor)
        image_path = Path(temp_folder) / "test.jpg"
        image_path.write_bytes(b"test image data")

        with patch("src.sequential_processor.encode_image_file", return_value="base64_test_data"):
            result = processor.process_paths([str(image_path)], resume=False)

        assert result["successes"] == 0
        assert result["failures"] == 1

        # Tracker should mark as failed, not completed
        from src.simple_processing_tracker import SimpleProcessingTracker

        tracker = SimpleProcessingTracker(temp_folder)
        assert str(image_path) not in tracker.get_processed_files() or tracker.is_processed(str(image_path))
        failed = tracker.get_failed_files()
        assert len(failed) == 1
        assert failed[0]["image_path"] == str(image_path)
        stats = tracker.get_stats()
        assert stats["failed"] == 1
        assert stats["completed"] == 0

    def test_failed_extraction_retried_on_resume(self, temp_folder):
        """A failed extraction should be retried on the next resume run."""
        mock_extractor = MagicMock()
        # First call: fail. Second call: succeed.
        mock_extractor.extract_b64.side_effect = [
            ProcessingResult(
                success=False,
                error="Model returned empty response",
                error_code="invalid_response",
                model="test-model",
            ),
            ProcessingResult(
                success=True,
                model="test-model",
                response='{"description": "retried"}',
                parsed={"description": "retried"},
            ),
        ]

        processor = SequentialProcessor(mock_extractor)
        image_path = Path(temp_folder) / "test.jpg"
        image_path.write_bytes(b"test image data")

        with patch("src.sequential_processor.encode_image_file", return_value="base64_test_data"):
            # First run: fails
            result1 = processor.process_paths([str(image_path)], resume=False)
            assert result1["failures"] == 1

            # Second run with resume=True: should NOT skip the failed image
            result2 = processor.process_paths([str(image_path)], resume=True)
            assert result2["skipped"] == 0
            assert result2["successes"] == 1

    def test_concurrent_failed_extraction_marks_failed(self, temp_folder):
        """Concurrent path: success=False result should mark tracker as failed."""
        mock_extractor = MagicMock()
        mock_extractor.extract_b64.return_value = ProcessingResult(
            success=False,
            error="timeout",
            error_code="timeout",
            model="test-model",
        )

        processor = SequentialProcessor(mock_extractor)
        paths = []
        for i in range(2):
            p = Path(temp_folder) / f"img_{i}.jpg"
            p.write_bytes(b"data")
            paths.append(str(p))

        with patch("src.sequential_processor.encode_image_file", return_value="base64_test_data"):
            result = processor.process_paths(paths, resume=False, concurrency=2)

        assert result["successes"] == 0
        assert result["failures"] == 2

        from src.simple_processing_tracker import SimpleProcessingTracker

        tracker = SimpleProcessingTracker(temp_folder)
        stats = tracker.get_stats()
        assert stats["failed"] == 2
        assert stats["completed"] == 0


class TestBatchConcurrency:
    """Tests for concurrent (batch) processing in process_paths."""

    def _make_paths(self, temp_folder, count):
        paths = []
        for i in range(count):
            image_path = Path(temp_folder) / f"img_{i}.jpg"
            image_path.write_bytes(b"test image data")
            paths.append(str(image_path))
        return paths

    def test_concurrency_processes_all_images(self, mock_extractor, temp_folder):
        """Concurrent processing processes every image and reports correct stats."""
        paths = self._make_paths(temp_folder, 5)

        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="p", resume=False, concurrency=3)

        assert result["total_found"] == 5
        assert result["processed"] == 5
        assert result["successes"] == 5
        assert result["failures"] == 0
        assert len(result["results"]) == 5
        # Every image was extracted exactly once
        assert mock_extractor.extract_b64.call_count == 5

    def test_concurrency_runs_in_parallel(self, mock_extractor, temp_folder):
        """With concurrency > 1, multiple LLM calls overlap in time."""
        paths = self._make_paths(temp_folder, 4)

        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def slow_extract(*args, **kwargs):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.1)
            with active_lock:
                active -= 1
            return ProcessingResult(
                success=True,
                model="test-model",
                response='{"description": "test"}',
                parsed={"description": "test"},
                total_duration_ms=100.0,
            )

        mock_extractor.extract_b64.side_effect = slow_extract

        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="p", resume=False, concurrency=4)

        assert result["successes"] == 4
        # If calls were sequential, max_active would stay 1. With concurrency=4
        # and 100ms work each, at least two must overlap.
        assert max_active >= 2, f"expected parallel execution, max_active={max_active}"

    def test_concurrency_one_is_sequential(self, mock_extractor, temp_folder):
        """concurrency=1 must not overlap calls (sequential behaviour)."""
        paths = self._make_paths(temp_folder, 3)

        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def slow_extract(*args, **kwargs):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with active_lock:
                active -= 1
            return ProcessingResult(success=True, model="m", response="{}", parsed={})

        mock_extractor.extract_b64.side_effect = slow_extract

        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            processor.process_paths(paths, prompt="p", resume=False, concurrency=1)

        assert max_active == 1

    def test_concurrency_none_is_sequential(self, mock_extractor, temp_folder):
        """concurrency=None must behave sequentially."""
        paths = self._make_paths(temp_folder, 3)
        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="p", resume=False, concurrency=None)

        assert result["successes"] == 3
        assert mock_extractor.extract_b64.call_count == 3

    def test_concurrency_with_failures(self, temp_folder):
        """Failures in concurrent mode are counted and recorded, not raised."""
        paths = self._make_paths(temp_folder, 4)

        mock_extractor = MagicMock()
        # Alternate success/failure
        results = [
            ProcessingResult(success=True, model="m", response="{}", parsed={}),
            RuntimeError("boom"),
            ProcessingResult(success=True, model="m", response="{}", parsed={}),
            RuntimeError("boom"),
        ]
        call_iter = iter(results)
        mock_extractor.extract_b64.side_effect = lambda *a, **k: next(call_iter)
        mock_extractor.base_url = "http://test:11434"
        mock_extractor.model = "test-model"

        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            result = processor.process_paths(paths, prompt="p", resume=False, concurrency=2)

        assert result["successes"] == 2
        assert result["failures"] == 2
        assert result["processed"] == 4

    def test_concurrency_progress_callback(self, mock_extractor, temp_folder):
        """Progress callback is invoked once per completed image in concurrent mode."""
        paths = self._make_paths(temp_folder, 4)

        progress_calls = []

        def capture(processed, total):
            progress_calls.append((processed, total))

        processor = SequentialProcessor(mock_extractor)
        with patch("src.sequential_processor.encode_image_file") as mock_encode:
            mock_encode.return_value = "base64_test_data"
            processor.process_paths(paths, prompt="p", resume=False, concurrency=2, progress_callback=capture)

        # One progress call per completed image
        assert len(progress_calls) == 4
        # Total reported is the folder size
        assert all(total == 4 for _, total in progress_calls)
        # Processed counts are 1..4 in some order
        assert sorted(processed for processed, _ in progress_calls) == [1, 2, 3, 4]
