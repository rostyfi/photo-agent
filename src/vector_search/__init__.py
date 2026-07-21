"""
Vector Search Utilities for Open Photo Agent.

This package provides vector search availability checking and utilities.

The underlying vector search library (sqlite-vec) is a HARD REQUIREMENT for vector search functionality.
"""

from .availability import is_vector_search_available

__all__ = ["is_vector_search_available"]
