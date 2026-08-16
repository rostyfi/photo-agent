"""Ollama-based embedding generator.

Uses Ollama's /api/embeddings endpoint to generate vector embeddings.

Requirements:
- Ollama v0.1.0+ (for /api/embeddings endpoint support)
- Vector search library (HARD REQUIREMENT for vector search)

Known working models:
- nomic-embed-text (768 dimensions, TEXT embedding model - embeds text, not images)
- all-minilm (384 dimensions, TEXT embedding model)
- clip-vit-base-patch32 (512 dimensions, VISION embedding model - embeds images)
- nomic-embed-vision (768 dimensions, VISION embedding model - embeds images)

Note: By default, this generator embeds TEXT descriptions extracted from images.
For vision models that embed images directly, use models like clip-vit-base-patch32
or nomic-embed-vision and ensure they are pulled to your Ollama server.
"""

import base64
import logging
import time
from pathlib import Path

import requests

from src.constants import DEFAULT_LLM_HOST
from src.embeddings.base import BaseEmbeddingGenerator

logger = logging.getLogger(__name__)

# Known model dimensions for validation
KNOWN_MODEL_DIMENSIONS: dict[str, int] = {
    "clip-vit-base-patch32": 512,
    "clip-vit-base-patch16": 512,
    "all-minilm": 384,
    "nomic-embed-text": 768,  # TEXT embedding model
    "nomic-embed-vision": 768,  # VISION embedding model
    "bakllava": 1024,
}

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Minimum Ollama version required for embeddings API
MIN_OLLAMA_VERSION = "0.1.0"


class OllamaEmbeddingGenerator(BaseEmbeddingGenerator):
    """Embedding generator using Ollama's /api/embeddings endpoint.

    Requires Ollama v0.1.0+ for the embeddings API.
    Vector search library is a HARD REQUIREMENT for vector search operations.

    Args:
        host: Ollama server hostname or IP.
        port: Ollama server port.
        model: Embedding model name (default: nomic-embed-text).
        timeout: Request timeout in seconds (default: 120).
        max_retries: Maximum retry attempts on failure (default: 3).
        backoff_factor: Multiplier for exponential backoff (default: 1.0).
    """

    def __init__(
        self,
        host: str = DEFAULT_LLM_HOST,
        port: int = 11434,
        model: str = DEFAULT_EMBEDDING_MODEL,
        timeout: int = 120,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.base_url = f"http://{self.host}:{self.port}"
        # Reuse a single session for connection pooling across bulk requests
        self._session = requests.Session()

        # Verify Ollama version requirement
        version_str = self._check_ollama_version()
        if version_str is None:
            logger.warning(
                "Could not verify Ollama version. Embedding generation requires Ollama v%s+", MIN_OLLAMA_VERSION
            )
            self._ollama_version = None
        else:
            self._ollama_version = version_str
            version_tuple = self._parse_version(version_str)
            min_version_tuple = self._parse_version(MIN_OLLAMA_VERSION)
            if version_tuple < min_version_tuple:
                raise RuntimeError(
                    f"Ollama v{MIN_OLLAMA_VERSION}+ is required for embedding generation. "
                    f"Detected version: {version_str}"
                )

    @staticmethod
    def _parse_version(version_str: str) -> tuple[int, ...]:
        """Parse a version string into a tuple of integers."""
        try:
            return tuple(int(x) for x in version_str.split("."))
        except (ValueError, AttributeError):
            return (0,)

    def _check_ollama_version(self) -> str | None:
        """Check the Ollama server version via /api/version endpoint."""
        try:
            url = f"{self.base_url}/api/version"
            response = self._session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                version = data.get("version", "")
                if version:
                    return version
        except requests.exceptions.RequestException as e:
            logger.debug("Could not check Ollama version: %s", e)
        return None

    def _get_known_dimension(self, model_name: str) -> int | None:
        """Get the known dimension for a model name."""
        return KNOWN_MODEL_DIMENSIONS.get(model_name.lower())

    def _get_model_dimension(self, model_name: str) -> int:
        """Get the embedding dimension for a model, either from known models or by querying."""
        # First try known models
        dim = self._get_known_dimension(model_name)
        if dim is not None:
            return dim

        # Try to get dimension from Ollama (not all models support this)
        # For now, use a sensible default or raise an error
        logger.warning(
            "Unknown embedding model '%s'. Using default dimension 512. Consider adding it to KNOWN_MODEL_DIMENSIONS.",
            model_name,
        )
        return 512

    def dimension(self, model_name: str) -> int:
        """Return the embedding dimension size for a given model.

        Args:
            model_name: The embedding model identifier.

        Returns:
            The dimension size (number of floats in the embedding vector).
        """
        return self._get_model_dimension(model_name)

    def model_name(self) -> str:
        """Return the model identifier for this generator.

        Returns:
            The model name string.
        """
        return self.model

    def _encode_image(self, image_path: str | Path) -> str:
        """Read an image file and encode it as base64."""
        path = Path(image_path)
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
            return base64.b64encode(image_bytes).decode("utf-8")
        except OSError as e:
            logger.error("Failed to read image file %s: %s", image_path, e)
            raise

    def _encode_image_b64(self, image_b64: str) -> str:
        """Ensure the image is properly base64 encoded (handles both raw and already encoded)."""
        # Check if already base64 encoded
        try:
            # Try to decode and re-encode to ensure proper format
            decoded = base64.b64decode(image_b64)
            return base64.b64encode(decoded).decode("utf-8")
        except Exception:
            # If decoding fails, assume it's already in the right format
            return image_b64

    def _generate_embedding_request(
        self, image_b64: str, model: str | None = None, prompt: str | None = None
    ) -> list[float]:
        """Send a request to Ollama's /api/embeddings endpoint.

        Args:
            image_b64: Base64-encoded image string.
            model: Optional model override.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            RuntimeError: If embedding generation fails after all retries.
        """
        url = f"{self.base_url}/api/embeddings"
        use_model = model or self.model

        payload = {
            "model": use_model,
        }
        # nomic-embed-text is a text embedding model, not vision
        # If prompt is provided, use it for text embedding
        if prompt is not None:
            payload["prompt"] = prompt
        else:
            payload["images"] = [image_b64]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Handle both singular and plural forms
                    # nomic-embed-text returns {"embedding": [floats]} (a list of floats)
                    # Multi-image requests return {"embeddings": [[floats], [floats], ...]}
                    embeddings_list = data.get("embeddings")
                    embedding_single = data.get("embedding")

                    if embeddings_list is not None:
                        # This is the multi-image format: {"embeddings": [[...], [...]]}
                        if len(embeddings_list) > 0 and len(embeddings_list[0]) > 0:
                            return embeddings_list[0]
                        # Empty list of embeddings
                        last_error = RuntimeError(
                            f"Empty embeddings list in response from Ollama for model '{use_model}'. "
                            f"Response: {data}. "
                            f"Vector search library is a HARD REQUIREMENT for vector search. "
                            f"Check that the model '{use_model}' supports embedding generation."
                        )
                        logger.error(
                            "Empty embeddings list in response from Ollama for model '%s': %s", use_model, data
                        )
                    elif embedding_single is not None:
                        # This is the single embedding format: {"embedding": [floats]}
                        if isinstance(embedding_single, list) and len(embedding_single) > 0:
                            return embedding_single
                        last_error = RuntimeError(
                            f"Empty embeddings in response from Ollama for model '{use_model}'. "
                            f"Response: {data}. "
                            f"Vector search library is a HARD REQUIREMENT for vector search. "
                            f"Check that the model '{use_model}' supports embedding generation. "
                            f"Note: nomic-embed-text is a TEXT embedding model. "
                            f"For image embeddings, use a vision model like 'clip-vit-base-patch32' or 'nomic-embed-vision'. "
                            f"Or embed the extracted text description instead."
                        )
                        logger.error("Empty embeddings in response from Ollama for model '%s': %s", use_model, data)
                    else:
                        last_error = RuntimeError(
                            f"No embeddings in response from Ollama for model '{use_model}'. "
                            f"Response: {data}. "
                            f"Vector search library is a HARD REQUIREMENT for vector search. "
                            f"Check that the model '{use_model}' supports embedding generation."
                        )
                        logger.error("No embeddings in response from Ollama for model '%s': %s", use_model, data)

                elif response.status_code == 404:
                    # Endpoint not found - Ollama version too old
                    last_error = RuntimeError(
                        f"Ollama /api/embeddings endpoint not found at {url}. "
                        f"Requires Ollama v{MIN_OLLAMA_VERSION}+ for embedding generation. "
                        f"Vector search library is a HARD REQUIREMENT for vector search. "
                        f"Current Ollama version: {self._ollama_version or 'unknown'}"
                    )
                    logger.error("Ollama /api/embeddings endpoint not found. Requires Ollama v%s+", MIN_OLLAMA_VERSION)

                else:
                    last_error = RuntimeError(
                        f"Ollama embeddings request failed with status {response.status_code}. "
                        f"URL: {url}, Model: {use_model}. "
                        f"Response: {response.text[:500]}. "
                        f"Vector search library is a HARD REQUIREMENT for vector search."
                    )
                    logger.error(
                        "Ollama embeddings request failed with status %d: %s", response.status_code, response.text[:200]
                    )

            except requests.exceptions.Timeout as e:
                last_error = RuntimeError(
                    f"Timeout on embedding request after {self.max_retries + 1} attempts. "
                    f"URL: {url}, Model: {use_model}, Timeout: {self.timeout}s. "
                    f"Last error: {e}. "
                    f"Vector search library is a HARD REQUIREMENT for vector search."
                )
                logger.warning("Timeout on embedding request (attempt %d/%d)", attempt + 1, self.max_retries + 1)

            except requests.exceptions.RequestException as e:
                last_error = RuntimeError(
                    f"Network error on embedding request after {self.max_retries + 1} attempts. "
                    f"URL: {url}, Model: {use_model}. "
                    f"Last error: {e}. "
                    f"Vector search library is a HARD REQUIREMENT for vector search."
                )
                logger.error(
                    "Network error on embedding request (attempt %d/%d): %s", attempt + 1, self.max_retries + 1, e
                )

            # Sleep before retrying. This single backoff point covers every
            # non-success branch above, preventing a busy retry loop that
            # hammers the server when embeddings are empty or the endpoint
            # returns a non-200 status.
            if attempt < self.max_retries:
                time.sleep(self.backoff_factor * (2**attempt))
                continue

        raise last_error or RuntimeError(
            f"Failed to generate embedding for model '{use_model}' at {url}. "
            f"Vector search library is a HARD REQUIREMENT for vector search."
        )

    def generate(self, image_path: str | Path) -> list[float]:
        """Generate embedding vector for an image file.

        Args:
            image_path: Path to the image file.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            RuntimeError: If embedding generation fails.
            IOError: If the image file cannot be read.
        """
        try:
            image_b64 = self._encode_image(image_path)
            return self._generate_embedding_request(image_b64)
        except RuntimeError:
            # Re-raise embedding generation errors
            raise
        except Exception as e:
            logger.error("Failed to generate embedding for %s: %s", image_path, e)
            raise RuntimeError(
                f"Failed to generate embedding for {image_path}. "
                f"Error: {e}. "
                f"Vector search library is a HARD REQUIREMENT for vector search."
            ) from e

    def generate_from_text(self, text: str, model: str | None = None) -> list[float]:
        """Generate embedding vector from text.

        Args:
            text: The text to embed.
            model: Optional model override.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            RuntimeError: If embedding generation fails.
        """
        try:
            return self._generate_embedding_request("", model=model, prompt=text)
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Failed to generate embedding from text: %s", e)
            raise RuntimeError(
                f"Failed to generate embedding from text. "
                f"Error: {e}. "
                f"Vector search library is a HARD REQUIREMENT for vector search."
            ) from e

    def generate_b64(self, image_b64: str) -> list[float]:
        """Generate embedding vector from a base64-encoded image.

        Args:
            image_b64: Base64-encoded image string.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            RuntimeError: If embedding generation fails.
        """
        try:
            encoded = self._encode_image_b64(image_b64)
            return self._generate_embedding_request(encoded)
        except RuntimeError:
            # Re-raise embedding generation errors
            raise
        except Exception as e:
            logger.error("Failed to generate embedding from base64: %s", e)
            raise RuntimeError(
                f"Failed to generate embedding from base64 image. "
                f"Error: {e}. "
                f"Vector search library is a HARD REQUIREMENT for vector search."
            ) from e

    def health_check(self) -> bool:
        """Check if the Ollama server is reachable and supports embeddings.

        Returns:
            True if the server is reachable and supports embeddings, False otherwise.
        """
        try:
            # First check if server is running
            url = f"{self.base_url}/api/tags"
            response = self._session.get(url, timeout=10)
            if response.status_code != 200:
                return False

            # Check if embeddings endpoint exists
            url = f"{self.base_url}/api/embeddings"

            # Determine if this is a text or vision model
            # Text embedding models (like nomic-embed-text) require "prompt" parameter
            # Vision embedding models (like clip-vit-base-patch32) require "images" parameter
            is_text_model = self.model.lower() in ["nomic-embed-text", "all-minilm"]

            try:
                if is_text_model:
                    # For text models, use a test prompt
                    response = self._session.post(
                        url,
                        json={"model": self.model, "prompt": "test"},
                        timeout=10,
                    )
                else:
                    # For vision models, use a test image (empty base64 or placeholder)
                    response = self._session.post(
                        url,
                        json={"model": self.model, "images": [""]},
                        timeout=10,
                    )

                # 400 is OK - it means the endpoint exists but the request was bad
                # 404 means the endpoint doesn't exist (old Ollama version)
                if response.status_code == 404:
                    logger.warning(
                        "Ollama server is running but /api/embeddings endpoint not found. Requires Ollama v%s+",
                        MIN_OLLAMA_VERSION,
                    )
                    return False
                return True
            except requests.exceptions.RequestException:
                return False

        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> list[str]:
        """List available embedding models from the Ollama server.

        Returns:
            List of model names that support embedding generation.
        """
        try:
            url = f"{self.base_url}/api/tags"
            response = self._session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                # Filter for models that are likely to support embeddings
                # For now, return all models and let the user try
                return [m.get("name", "") for m in models if m.get("name")]
        except requests.exceptions.RequestException as e:
            logger.error("Failed to list Ollama models: %s", e)
        return []
