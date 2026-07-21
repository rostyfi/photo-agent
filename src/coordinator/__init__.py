"""
Simplified Coordinator for Open Photo Agent.

This module provides simple sequential processing without batch-specific infrastructure.
"""

from src.sequential_processor import SequentialProcessor, process_paths, process_image

# Re-export for backward compatibility
__all__ = [
    "SequentialProcessor",
    "process_paths",
    "process_image",
]
