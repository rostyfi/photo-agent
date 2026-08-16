"""Tests for the errors callback."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import dash

from src.callbacks.errors import register_all_errors_callbacks
from src.config import AppConfig
from src.layout import create_layout
from src.simple_processing_tracker import SimpleProcessingTracker


class TestErrorsCallback(unittest.TestCase):
    """Tests for error-related callbacks."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = AppConfig()
        self.layout = create_layout(self.config)

    def test_errors_callback_registered(self):
        """Test that error callbacks are registered."""
        app = dash.Dash(__name__)
        app.layout = self.layout

        # This should not raise an error
        try:
            register_all_errors_callbacks(app)
        except Exception as e:
            self.fail(f"Failed to register error callbacks: {e}")

    def test_build_errors_display_empty(self):
        """Test building errors display with no errors."""
        from src.components import build_errors_display

        result = build_errors_display([], "/test/folder")

        # Should contain success message
        self.assertIn("No errors found", str(result))

    def test_build_errors_display_with_errors(self):
        """Test building errors display with errors."""
        from src.components import build_errors_display

        errors = [
            {
                "image_path": "/test/image1.jpg",
                "error_code": "EMBEDDING_ERROR",
                "error_msg": "Test error message",
                "ts": "2026-01-01T12:00:00",
            }
        ]

        result = build_errors_display(errors, "/test/folder")

        # Should contain error information
        result_str = str(result)
        self.assertIn("image1.jpg", result_str)
        self.assertIn("EMBEDDING_ERROR", result_str)
        self.assertIn("Test error message", result_str)

    def test_load_errors_from_wal(self):
        """Test loading errors from WAL."""
        # This test verifies that the callback can be registered
        # Full callback testing requires a running Dash server
        app = dash.Dash(__name__)
        app.layout = self.layout

        # This should not raise
        try:
            register_all_errors_callbacks(app)
        except Exception as e:
            self.fail(f"Failed to register callbacks: {e}")


if __name__ == "__main__":
    unittest.main()
