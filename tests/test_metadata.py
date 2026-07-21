"""Tests for image metadata extraction and storage functionality."""

import json
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from src.metadata import (
    ImageMetadata,
    extract_metadata,
    extract_metadata_dict,
    format_metadata_for_display,
)
from src.sidecar.database import FeaturesDatabase
from src.sequential_processor import SequentialProcessor
from plugins.llm import create_extractor


class TestImageMetadata:
    """Tests for the ImageMetadata dataclass."""

    def test_default_values(self):
        """Test that ImageMetadata has sensible default values."""
        metadata = ImageMetadata()
        assert metadata.file_path == ""
        assert metadata.file_name == ""
        assert metadata.width is None
        assert metadata.height is None
        assert metadata.make is None
        assert metadata.model is None

    def test_to_dict_excludes_none(self):
        """Test that to_dict excludes None values."""
        metadata = ImageMetadata(file_path="/test.jpg", width=800, height=600)
        result = metadata.to_dict()
        assert "file_path" in result
        assert "width" in result
        assert "height" in result
        assert "make" not in result  # None value should be excluded
        assert "model" not in result  # None value should be excluded

    def test_get_camera_info(self):
        """Test camera info formatting."""
        metadata = ImageMetadata()
        
        # Test with make and model
        metadata.make = "Canon"
        metadata.model = "EOS 5D"
        assert metadata.get_camera_info() == "Canon EOS 5D"
        
        # Test with lens model
        metadata.lens_model = "EF 24-70mm"
        assert metadata.get_camera_info() == "Canon EOS 5D (EF 24-70mm)"
        
        # Test with no info
        metadata.make = None
        metadata.model = None
        metadata.lens_model = None
        assert metadata.get_camera_info() == "Unknown"

    def test_get_exposure_info(self):
        """Test exposure info formatting."""
        metadata = ImageMetadata()
        
        # Test with all values
        metadata.f_number = "5.6"
        metadata.exposure_time = "1/250"  # Without s suffix
        metadata.iso_speed = 100
        metadata.focal_length = "50"  # Without mm suffix for this test
        result = metadata.get_exposure_info()
        # The focal_length gets "mm" added by get_exposure_info
        assert "f/5.6" in result
        assert "ISO 100" in result
        assert "50mm" in result
        
        # Test with partial values
        metadata.f_number = None
        metadata.exposure_time = None
        assert metadata.get_exposure_info() == "ISO 100, 50mm"
        
        # Test with no values
        metadata.iso_speed = None
        metadata.focal_length = None
        assert metadata.get_exposure_info() == "Not available"

    def test_get_dimensions_info(self):
        """Test dimensions info formatting."""
        metadata = ImageMetadata()
        
        # Test with width and height
        metadata.width = 1920
        metadata.height = 1080
        metadata.aspect_ratio = 16/9
        assert metadata.get_dimensions_info() == "1920 × 1080 (1.78 aspect ratio)"
        
        # Test without aspect ratio
        metadata.aspect_ratio = None
        assert metadata.get_dimensions_info() == "1920 × 1080"
        
        # Test with no dimensions
        metadata.width = None
        metadata.height = None
        assert metadata.get_dimensions_info() == "Not available"


class TestMetadataExtraction:
    """Tests for metadata extraction from image files."""

    def test_extract_metadata_from_image(self, tmp_path):
        """Test extracting metadata from a real image file."""
        # Create a test image
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (800, 600), color=(128, 128, 128))
        img.save(str(test_image), "JPEG", quality=95)
        
        # Extract metadata
        metadata = extract_metadata(str(test_image))
        
        # Verify basic metadata
        assert metadata.file_path == str(test_image)
        assert metadata.file_name == "test.jpg"
        assert metadata.file_extension == ".jpg"
        assert metadata.file_size_bytes > 0
        assert metadata.width == 800
        assert metadata.height == 600
        assert metadata.aspect_ratio == pytest.approx(800/600, rel=1e-3)
        assert metadata.color_space == "RGB"

    def test_extract_metadata_dict(self, tmp_path):
        """Test extracting metadata as a dictionary."""
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (400, 300), color=(255, 0, 0))
        img.save(str(test_image), "JPEG", quality=95)
        
        metadata_dict = extract_metadata_dict(str(test_image))
        
        # Verify it's a dict with expected keys
        assert isinstance(metadata_dict, dict)
        assert "file_path" in metadata_dict
        assert "file_name" in metadata_dict
        assert "width" in metadata_dict
        assert "height" in metadata_dict
        assert "file_size_bytes" in metadata_dict
        # None values should be excluded
        assert "make" not in metadata_dict or metadata_dict["make"] is not None

    def test_format_metadata_for_display(self, tmp_path):
        """Test formatting metadata for display."""
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (1024, 768), color=(0, 0, 255))
        img.save(str(test_image), "JPEG", quality=95)
        
        metadata = extract_metadata(str(test_image))
        display_metadata = format_metadata_for_display(metadata)
        
        # Verify it's a dict with formatted values
        assert isinstance(display_metadata, dict)
        assert "File Size" in display_metadata
        assert "Dimensions" in display_metadata
        assert "Color Space" in display_metadata
        assert "1024 × 768" in display_metadata["Dimensions"]


class TestDatabaseMetadata:
    """Tests for metadata storage in the database."""

    def test_save_and_retrieve_metadata(self, tmp_path):
        """Test saving and retrieving metadata from the database."""
        # Create test image
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (640, 480), color=(0, 255, 0))
        img.save(str(test_image), "JPEG", quality=95)
        
        # Create database
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        # Extract and save metadata
        metadata = extract_metadata_dict(str(test_image))
        db.save_metadata(str(test_image), metadata)
        
        # Retrieve metadata
        retrieved = db.get_metadata(str(test_image))
        
        assert retrieved is not None
        assert retrieved["file_name"] == "test.jpg"
        assert retrieved["width"] == 640
        assert retrieved["height"] == 480
        
        db.close()

    def test_get_metadata_for_display(self, tmp_path):
        """Test getting formatted metadata from database."""
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (300, 200), color=(255, 255, 255))
        img.save(str(test_image), "JPEG", quality=95)
        
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        metadata = extract_metadata_dict(str(test_image))
        db.save_metadata(str(test_image), metadata)
        
        display_metadata = db.get_metadata_for_display(str(test_image))
        
        assert isinstance(display_metadata, dict)
        assert "File Size" in display_metadata
        assert "Dimensions" in display_metadata
        assert "300 × 200" in display_metadata["Dimensions"]
        
        db.close()

    def test_feature_summary_includes_metadata(self, tmp_path):
        """Test that feature summary includes metadata."""
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (200, 200), color=(128, 128, 128))
        img.save(str(test_image), "JPEG", quality=95)
        
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        # Save metadata
        metadata = extract_metadata_dict(str(test_image))
        db.save_metadata(str(test_image), metadata)
        
        # Save extraction result
        result = {
            "success": True,
            "image_path": str(test_image),
            "model": "test-model",
            "response": '{"description": "Test image"}',
            "parsed": {"description": "Test image"}
        }
        db.save_extraction(str(test_image), result)
        
        # Get feature summary
        summary = db.get_feature_summary(str(test_image))
        
        assert summary is not None
        assert "metadata" in summary
        assert summary["metadata"]["file_name"] == "test.jpg"
        assert summary["metadata"]["width"] == 200
        
        db.close()


class TestSequentialProcessorMetadata:
    """Tests for metadata extraction in SequentialProcessor."""

    def test_processor_extracts_metadata(self, tmp_path):
        """Test that SequentialProcessor extracts and saves metadata."""
        # Create test image
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (400, 300), color=(200, 200, 200))
        img.save(str(test_image), "JPEG", quality=95)
        
        # Create processor with dry-run extractor
        extractor = create_extractor(backend="dry_run")
        processor = SequentialProcessor(
            extractor=extractor,
            folder=str(tmp_path),
            embedding_enabled=False
        )
        
        # Process image
        result = processor.process_image(str(test_image))
        
        assert result.success is True
        
        # Check that metadata was saved
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        
        metadata = db.get_metadata(str(test_image))
        assert metadata is not None
        assert metadata["file_name"] == "test.jpg"
        assert metadata["width"] == 400
        assert metadata["height"] == 300
        
        # Check that extraction result was saved
        raw_features = db.get_extraction(str(test_image))
        assert raw_features is not None
        assert raw_features["success"] is True
        
        # Check that feature summary includes metadata
        summary = db.get_feature_summary(str(test_image))
        assert summary is not None
        assert "metadata" in summary
        
        db.close()

    def test_processor_with_embeddings_disabled(self, tmp_path):
        """Test that metadata is extracted even when embeddings are disabled."""
        test_image = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color=(100, 100, 100))
        img.save(str(test_image), "JPEG", quality=95)
        
        extractor = create_extractor(backend="dry_run")
        processor = SequentialProcessor(
            extractor=extractor,
            folder=str(tmp_path),
            embedding_enabled=False
        )
        
        result = processor.process_image(str(test_image))
        
        # Check metadata was saved
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        metadata = db.get_metadata(str(test_image))
        
        assert metadata is not None
        assert metadata["width"] == 100
        
        db.close()


class TestMetadataTableSchema:
    """Tests for the image_metadata table schema."""

    def test_image_metadata_table_created(self, tmp_path):
        """Test that the image_metadata table is created."""
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        # Check that the table exists
        with db.get_connection() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='image_metadata'"
            ).fetchone()
            assert result is not None
            assert result[0] == "image_metadata"
        
        db.close()

    def test_image_metadata_index_created(self, tmp_path):
        """Test that the image_metadata index is created."""
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        # Check that the index exists
        with db.get_connection() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_image_metadata_path'"
            ).fetchone()
            assert result is not None
            assert result[0] == "idx_image_metadata_path"
        
        db.close()

    def test_image_metadata_table_columns(self, tmp_path):
        """Test that the image_metadata table has all expected columns."""
        db_path = FeaturesDatabase.default_db_path(str(tmp_path))
        db = FeaturesDatabase(str(db_path))
        db.init_db()
        
        expected_columns = [
            "image_path", "file_name", "file_size_bytes", "file_extension",
            "width", "height", "aspect_ratio", "make", "model", "camera_serial",
            "lens_make", "lens_model", "exposure_time", "f_number", "iso_speed",
            "focal_length", "focal_length_35mm", "aperture_value", "date_taken",
            "date_created", "date_modified", "latitude", "longitude", "altitude",
            "gps_precision", "location_name", "color_space", "bits_per_sample",
            "orientation", "software", "copyright", "artist", "image_description",
            "title", "updated_at"
        ]
        
        with db.get_connection() as conn:
            result = conn.execute("PRAGMA table_info(image_metadata)").fetchall()
            actual_columns = [row[1] for row in result]  # column names are in index 1
            
            for col in expected_columns:
                assert col in actual_columns, f"Missing column: {col}"
        
        db.close()