"""Tests for the sequential processor module."""

import tempfile
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
