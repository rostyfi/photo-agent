from abc import ABC, abstractmethod


class AbstractSidecarStore(ABC):
    """Abstract interface for sidecar persistence."""

    @abstractmethod
    def save(self, image_path: str, result: dict) -> str:
        """Persist an extraction result dict and return the sidecar path."""
        ...

    @abstractmethod
    def load(self, image_path: str) -> dict | None:
        """Read and parse an extraction result for the given image, or None."""
        ...

    @abstractmethod
    def exists(self, image_path: str) -> bool:
        """Return True if a sidecar exists for the given image."""
        ...
