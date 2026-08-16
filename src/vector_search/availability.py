"""
Vector Search Availability Check.

This module provides a simple function to check if sqlite-vec is available,
without requiring a database connection or instance.
"""

import logging

logger = logging.getLogger(__name__)


def is_vector_search_available() -> bool:
    """Check if sqlite-vec library is installed and can be imported.

    Returns:
        True if sqlite-vec is available, False otherwise.
    """
    try:
        import sqlite_vec  # noqa: F401

        return True
    except ImportError:
        return False
