"""Tests for the embedding module.

sqlite-vec is a HARD REQUIREMENT for vector search functionality.
Ollama v0.1.0+ is required for embedding generation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from src.embeddings import (
    BaseEmbeddingGenerator,
    OllamaEmbeddingGenerator,
    create_generator,
    list_embedding_backends,
    DEFAULT_EMBEDDING_MODEL,
)
from src.embeddings.registry import (
    register_embedding_backend,
    get_embedding_backend,
    unregister_embedding_backend,
)


class TestOllamaEmbeddingGenerator:
    """Tests for OllamaEmbeddingGenerator."""

    def test_init_defaults(self):
        """Test default initialization."""
        generator = OllamaEmbeddingGenerator()
        assert generator.host == "192.168.0.150"
        assert generator.port == 11434
        assert generator.model == DEFAULT_EMBEDDING_MODEL
        assert generator.timeout == 120
        assert generator.max_retries == 3
        assert generator.backoff_factor == 1.0

    def test_init_custom(self):
        """Test custom initialization."""
        generator = OllamaEmbeddingGenerator(
            host="localhost",
            port=8080,
            model="all-minilm",
            timeout=60,
            max_retries=5,
            backoff_factor=2.0,
        )
        assert generator.host == "localhost"
        assert generator.port == 8080
        assert generator.model == "all-minilm"
        assert generator.timeout == 60
        assert generator.max_retries == 5
        assert generator.backoff_factor == 2.0

    def test_model_name(self):
        """Test model_name method."""
        generator = OllamaEmbeddingGenerator(model="test-model")
        assert generator.model_name() == "test-model"

    def test_dimension_known_models(self):
        """Test dimension method with known models."""
        generator = OllamaEmbeddingGenerator()
        assert generator.dimension("clip-vit-base-patch32") == 512
        assert generator.dimension("all-minilm") == 384
        assert generator.dimension("nomic-embed-text") == 768

    def test_dimension_unknown_model(self):
        """Test dimension method with unknown model (should return default)."""
        generator = OllamaEmbeddingGenerator()
        # Should return default 512 for unknown models
        assert generator.dimension("unknown-model") == 512

    @patch("src.embeddings.ollama.requests.Session")
    def test_check_ollama_version_success(self, mock_session_cls):
        """Test successful Ollama version check."""
        mock_session = mock_session_cls.return_value
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "0.1.0"}
        mock_session.get.return_value = mock_response
        
        generator = OllamaEmbeddingGenerator()
        version = generator._check_ollama_version()
        assert version == "0.1.0"

    @patch("src.embeddings.ollama.requests.Session")
    def test_check_ollama_version_failure(self, mock_session_cls):
        """Test failed Ollama version check."""
        import requests
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = requests.exceptions.RequestException("Connection error")
        
        generator = OllamaEmbeddingGenerator()
        version = generator._check_ollama_version()
        assert version is None

    @patch("src.embeddings.ollama.requests.Session")
    def test_health_check_success(self, mock_session_cls):
        """Test successful health check."""
        mock_session = mock_session_cls.return_value
        # Mock version check endpoint (called during __init__)
        version_response = Mock()
        version_response.status_code = 200
        version_response.json.return_value = {"version": "0.1.0"}
        
        # Mock tags endpoint
        tags_response = Mock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": []}
        
        # Mock embeddings endpoint (to check if it exists)
        embeddings_response = Mock()
        embeddings_response.status_code = 400  # Bad request means endpoint exists
        
        mock_session.get.side_effect = [version_response, tags_response]
        mock_session.post.return_value = embeddings_response
        
        generator = OllamaEmbeddingGenerator()
        result = generator.health_check()
        assert result is True

    @patch("src.embeddings.ollama.requests.Session")
    def test_health_check_endpoint_not_found(self, mock_session_cls):
        """Test health check when embeddings endpoint doesn't exist."""
        mock_session = mock_session_cls.return_value
        # Mock version check endpoint (called during __init__)
        version_response = Mock()
        version_response.status_code = 200
        version_response.json.return_value = {"version": "0.1.0"}
        
        # Mock tags endpoint
        tags_response = Mock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": []}
        
        # Mock embeddings endpoint (404 means endpoint doesn't exist)
        embeddings_response = Mock()
        embeddings_response.status_code = 404
        
        mock_session.get.side_effect = [version_response, tags_response]
        mock_session.post.return_value = embeddings_response
        
        generator = OllamaEmbeddingGenerator()
        result = generator.health_check()
        assert result is False

    @patch("src.embeddings.ollama.requests.Session")
    def test_list_models_success(self, mock_session_cls):
        """Test successful model listing."""
        mock_session = mock_session_cls.return_value
        # Mock version check endpoint (called during __init__)
        version_response = Mock()
        version_response.status_code = 200
        version_response.json.return_value = {"version": "0.1.0"}
        
        # Mock tags endpoint
        tags_response = Mock()
        tags_response.status_code = 200
        tags_response.json.return_value = {
            "models": [
                {"name": "nomic-embed-text"},
                {"name": "all-minilm"},
            ]
        }
        mock_session.get.side_effect = [version_response, tags_response]
        
        generator = OllamaEmbeddingGenerator()
        models = generator.list_models()
        assert "nomic-embed-text" in models
        assert "all-minilm" in models

    @patch("src.embeddings.ollama.requests.Session")
    def test_list_models_failure(self, mock_session_cls):
        """Test failed model listing."""
        import requests
        mock_session = mock_session_cls.return_value
        # Mock version check endpoint (called during __init__)
        version_response = Mock()
        version_response.status_code = 200
        version_response.json.return_value = {"version": "0.1.0"}
        
        # Mock tags endpoint - raise exception
        mock_session.get.side_effect = [version_response, requests.exceptions.RequestException("Connection error")]
        
        generator = OllamaEmbeddingGenerator()
        models = generator.list_models()
        assert models == []


class TestCreateGenerator:
    """Tests for create_generator factory function."""

    def test_creates_ollama_generator(self):
        """Test that create_generator creates an Ollama generator."""
        generator = create_generator(
            backend="ollama",
            host="localhost",
            port=11434,
            model="nomic-embed-text",
        )
        assert isinstance(generator, OllamaEmbeddingGenerator)
        assert generator.host == "localhost"
        assert generator.port == 11434
        assert generator.model == "nomic-embed-text"

    def test_unknown_backend(self):
        """Test that create_generator raises for unknown backend."""
        with pytest.raises(ValueError) as exc_info:
            create_generator(backend="unknown_backend")
        assert "Unknown embedding backend" in str(exc_info.value)

    def test_default_backend(self):
        """Test that create_generator defaults to ollama backend."""
        generator = create_generator()
        assert isinstance(generator, OllamaEmbeddingGenerator)


class TestRegistry:
    """Tests for embedding backend registry."""

    def test_register_and_get_backend(self):
        """Test registering and getting a backend."""
        # Clear any existing registrations
        unregister_embedding_backend("test_backend")
        
        def test_factory():
            return Mock()
        
        register_embedding_backend("test_backend", test_factory)
        factory = get_embedding_backend("test_backend")
        assert factory is test_factory
        
        # Clean up
        unregister_embedding_backend("test_backend")

    def test_list_backends(self):
        """Test listing all registered backends."""
        backends = list_embedding_backends()
        assert "ollama" in backends

    def test_unregister_backend(self):
        """Test unregistering a backend."""
        def test_factory():
            return Mock()
        
        register_embedding_backend("test_unregister", test_factory)
        assert get_embedding_backend("test_unregister") is not None
        
        result = unregister_embedding_backend("test_unregister")
        assert result is True
        assert get_embedding_backend("test_unregister") is None


class TestBaseEmbeddingGenerator:
    """Tests for BaseEmbeddingGenerator abstract class."""

    def test_abstract_methods(self):
        """Test that BaseEmbeddingGenerator has all required abstract methods."""
        from src.embeddings.base import BaseEmbeddingGenerator
        
        # Check that all methods are abstract
        assert hasattr(BaseEmbeddingGenerator, "generate")
        assert hasattr(BaseEmbeddingGenerator, "generate_b64")
        assert hasattr(BaseEmbeddingGenerator, "dimension")
        assert hasattr(BaseEmbeddingGenerator, "model_name")

    def test_cannot_instantiate(self):
        """Test that BaseEmbeddingGenerator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseEmbeddingGenerator()
