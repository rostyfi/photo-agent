from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class AbstractSidecarStore(ABC):
    """Abstract interface for sidecar persistence."""

    @abstractmethod
    def save(self, image_path: str, result: Dict) -> str:
        """Persist an extraction result dict and return the sidecar path."""
        ...

    @abstractmethod
    def load(self, image_path: str) -> Optional[Dict]:
        """Read and parse an extraction result for the given image, or None."""
        ...

    @abstractmethod
    def exists(self, image_path: str) -> bool:
        """Return True if a sidecar exists for the given image."""
        ...

    @classmethod
    @abstractmethod
    def sidecar_path(cls, image_path: str) -> Path:
        """Return the expected storage path for a given image."""
        ...
