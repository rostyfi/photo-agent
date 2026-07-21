"""Abstract base class for pluggable embedding generators.

Vector search library is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Union
from pathlib import Path


class BaseEmbeddingGenerator(ABC):
    """Abstract base for pluggable embedding backends.
    
    All embedding generators must implement the methods defined here.
    Currently only Ollama backend is supported.
    
    Vector search library is a HARD REQUIREMENT - vector search will not work without it.
    Ollama v0.1.0+ is required for the /api/embeddings endpoint.
    """

    @abstractmethod
    def generate(self, image_path: Union[str, Path]) -> Optional[List[float]]:
        """Generate embedding vector for an image file.
        
        Args:
            image_path: Path to the image file.
            
        Returns:
            List of floats representing the embedding vector, or None on failure.
        """
        ...

    @abstractmethod
    def generate_b64(self, image_b64: str) -> Optional[List[float]]:
        """Generate embedding vector from a base64-encoded image.
        
        Args:
            image_b64: Base64-encoded image string.
            
        Returns:
            List of floats representing the embedding vector, or None on failure.
        """
        ...

    def generate_from_text(self, text: str, model: Optional[str] = None) -> Optional[List[float]]:
        """Generate embedding vector from text.
        
        Default implementation falls back to generate() for backward compatibility.
        Override this method for text embedding models like nomic-embed-text.
        
        Args:
            text: The text to embed.
            model: Optional model override.
            
        Returns:
            List of floats representing the embedding vector, or None on failure.
        """
        # Default: not supported, return None
        return None

    @abstractmethod
    def dimension(self, model_name: str) -> int:
        """Return the embedding dimension size for a given model.
        
        Args:
            model_name: The embedding model identifier.
            
        Returns:
            The dimension size (number of floats in the embedding vector).
        """
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier for this generator.
        
        Returns:
            The model name string.
        """
        ...

    def health_check(self) -> bool:
        """Check if the embedding backend is reachable and operational.
        
        Default implementation returns True (assumes backend is healthy).
        Override this method for backends that need to verify connectivity.
        
        Returns:
            True if the backend is reachable and operational, False otherwise.
        """
        return True
