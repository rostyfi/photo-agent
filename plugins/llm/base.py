"""Re-exports shared interfaces from src/interfaces.py for backward compatibility."""

from src.interfaces import BasePhotoExtractor, ErrorCode, DEFAULT_PROMPT, ProcessingResult

__all__ = ["BasePhotoExtractor", "ErrorCode", "DEFAULT_PROMPT", "ProcessingResult"]
