"""
Simplified Coordinator for Local Photo Agent.

This module provides simple sequential processing without batch-specific infrastructure.
"""

from src.sequential_processor import SequentialProcessor, process_image, process_paths

# Re-export for backward compatibility
__all__ = [
    "SequentialProcessor",
    "process_image",
    "process_paths",
]
