"""Re-exports shared interfaces from src/interfaces.py for backward compatibility."""

from src.interfaces import DEFAULT_PROMPT, BasePhotoExtractor, ErrorCode, ProcessingResult

__all__ = ["DEFAULT_PROMPT", "BasePhotoExtractor", "ErrorCode", "ProcessingResult"]
