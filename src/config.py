import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from src.constants import DEFAULT_BATCH_CONCURRENCY, DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL
from src.interfaces import DEFAULT_PROMPT

logger = logging.getLogger(__name__)

_MIN_PORT = 1
_MAX_PORT = 65535


def _safe_int(env_name: str, fallback: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return fallback
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.error("Invalid integer value for %s=%r, using fallback %d", env_name, raw, fallback)
        return fallback


def _safe_int_or(env_name1: str, env_name2: str, fallback: int) -> int:
    raw = os.getenv(env_name1)
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            logger.error("Invalid integer value for %s=%r, trying %s", env_name1, raw, env_name2)
    raw = os.getenv(env_name2)
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            logger.error("Invalid integer value for %s=%r, using fallback %d", env_name2, raw, fallback)
    return fallback


def _warn_deprecated(new_name: str, old_base: str):
    for suffix in ("_HOST", "_PORT", "_MODEL", "_TIMEOUT"):
        old_var = f"LOCAL_PHOTO_AGENT_{old_base}{suffix}"
        if os.getenv(old_var) is not None:
            logger.warning(
                "Environment variable %s is deprecated, use %s instead",
                old_var,
                f"LOCAL_PHOTO_AGENT_{new_name}{suffix}",
            )


def _validate_port_range(port_var: str, port: int, label: str):
    if not (_MIN_PORT <= port <= _MAX_PORT):
        raise ValueError(f"Invalid {label}: {port}. Must be between {_MIN_PORT} and {_MAX_PORT} (env var: {port_var})")


def _validate_host(host_var: str, host: str, label: str):
    if not host or not host.strip():
        raise ValueError(f"{label} must not be empty (env var: {host_var})")


def _validate_positive(timeout_var: str, timeout: int, label: str):
    if timeout <= 0:
        raise ValueError(f"{label} must be positive, got {timeout} (env var: {timeout_var})")


def _validate_concurrency(conc_var: str, concurrency: int):
    if concurrency < 1:
        raise ValueError(
            f"Batch concurrency must be >= 1, got {concurrency} (env var: {conc_var})"
        )


@dataclass
class EmbeddingConfig:
    """Embedding/similarity configuration shared by AppConfig and ProcessingConfig.

    Single source of truth for the embedding-related fields (toggle, model,
    backend) and similarity search defaults. ``AppConfig`` and
    ``ProcessingConfig`` inherit from this class so the fields, defaults, and
    validation are declared exactly once and the flat ``config.embedding_*``
    access pattern is preserved.

    Note: callers are responsible for calling ``load_dotenv()`` before
    ``from_env()`` so environment variables are populated.
    """

    embedding_enabled: bool = True
    embedding_model: str = "nomic-embed-text"
    embedding_backend: str = "ollama"
    similarity_limit: int = 10
    similarity_metric: str = "cosine"

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Build embedding configuration from environment variables."""
        return cls(
            embedding_enabled=os.getenv("LOCAL_PHOTO_AGENT_EMBEDDING_ENABLED", "true").lower() in ("1", "true", "yes"),
            embedding_model=os.getenv("LOCAL_PHOTO_AGENT_EMBEDDING_MODEL", "nomic-embed-text"),
            embedding_backend=os.getenv("LOCAL_PHOTO_AGENT_EMBEDDING_BACKEND", "ollama"),
            similarity_limit=_safe_int("LOCAL_PHOTO_AGENT_SIMILARITY_LIMIT", 10),
            similarity_metric=os.getenv("LOCAL_PHOTO_AGENT_SIMILARITY_METRIC", "cosine"),
        )

    def validate(self):
        """Validate embedding model and similarity settings.

        Raises ValueError with a clear message on invalid configuration.
        """
        if self.similarity_limit <= 0:
            raise ValueError(f"Similarity limit must be positive, got {self.similarity_limit}")
        if self.similarity_metric not in ("cosine",):
            raise ValueError(f"Similarity metric must be 'cosine', got {self.similarity_metric}")
        if not self.embedding_model:
            raise ValueError("Embedding model must not be empty")


@dataclass
class ProcessingConfig(EmbeddingConfig):
    """Configuration for an LLM processing run.

    Captures the backend name, connection details, model tag, timeout, and
    default prompt used by the coordinator and image processor. Embedding
    and similarity fields are inherited from :class:`EmbeddingConfig`.

    Requirements:
    - Vector search library (HARD REQUIREMENT) for vector search
    - Ollama v0.1.0+ for embedding generation
    """

    backend: str = "ollama"
    host: str = DEFAULT_LLM_HOST
    port: int = 11434
    model: str = DEFAULT_LLM_MODEL
    timeout: int = 600
    default_prompt: str = DEFAULT_PROMPT
    # Number of images to process in parallel against the LLM backend.
    # 1 = strictly sequential (historical behaviour).
    batch_concurrency: int = DEFAULT_BATCH_CONCURRENCY

    @classmethod
    def from_env(cls) -> "ProcessingConfig":
        """Load configuration from environment variables (with .env support).

        Prefers ``LOCAL_PHOTO_AGENT_LLM_*`` variables, falling back to
        ``LOCAL_PHOTO_AGENT_OLLAMA_*`` for backward compatibility.

        Embedding configuration uses:
        - LOCAL_PHOTO_AGENT_EMBEDDING_ENABLED
        - LOCAL_PHOTO_AGENT_EMBEDDING_MODEL
        - LOCAL_PHOTO_AGENT_EMBEDDING_BACKEND
        - LOCAL_PHOTO_AGENT_SIMILARITY_LIMIT
        - LOCAL_PHOTO_AGENT_SIMILARITY_METRIC
        """
        load_dotenv()
        _warn_deprecated("LLM", "OLLAMA")
        emb = EmbeddingConfig.from_env()
        return cls(
            backend=os.getenv("LOCAL_PHOTO_AGENT_LLM_BACKEND", "ollama"),
            host=os.getenv("LOCAL_PHOTO_AGENT_LLM_HOST")
            or os.getenv("LOCAL_PHOTO_AGENT_OLLAMA_HOST", DEFAULT_LLM_HOST),
            port=_safe_int_or("LOCAL_PHOTO_AGENT_LLM_PORT", "LOCAL_PHOTO_AGENT_OLLAMA_PORT", 11434),
            model=os.getenv("LOCAL_PHOTO_AGENT_LLM_MODEL")
            or os.getenv("LOCAL_PHOTO_AGENT_OLLAMA_MODEL", DEFAULT_LLM_MODEL),
            timeout=_safe_int_or("LOCAL_PHOTO_AGENT_LLM_TIMEOUT", "LOCAL_PHOTO_AGENT_OLLAMA_TIMEOUT", 600),
            default_prompt=os.getenv("LOCAL_PHOTO_AGENT_DEFAULT_PROMPT", DEFAULT_PROMPT),
            batch_concurrency=_safe_int("LOCAL_PHOTO_AGENT_BATCH_CONCURRENCY", DEFAULT_BATCH_CONCURRENCY),
            embedding_enabled=emb.embedding_enabled,
            embedding_model=emb.embedding_model,
            embedding_backend=emb.embedding_backend,
            similarity_limit=emb.similarity_limit,
            similarity_metric=emb.similarity_metric,
        )

    def validate(self):
        """Validate port ranges, non-empty hosts, and positive timeout.

        Raises ValueError with a clear message on invalid configuration.
        """
        _validate_host("LOCAL_PHOTO_AGENT_LLM_HOST", self.host, "LLM host")
        _validate_port_range("LOCAL_PHOTO_AGENT_LLM_PORT", self.port, "LLM port")
        _validate_positive("LOCAL_PHOTO_AGENT_LLM_TIMEOUT", self.timeout, "LLM timeout")
        _validate_concurrency("LOCAL_PHOTO_AGENT_BATCH_CONCURRENCY", self.batch_concurrency)
        super().validate()


@dataclass
class AppConfig(EmbeddingConfig):
    """Master configuration for the entire application (CLI + Dash web UI).

    Holds LLM connection details, Dash server settings, default prompt, and
    processing tracker settings.  All values can be overridden
    via environment variables with the ``LOCAL_PHOTO_AGENT_`` prefix.
    Embedding and similarity fields are inherited from :class:`EmbeddingConfig`.

    Requirements:
    - Vector search library (HARD REQUIREMENT) for vector search
    - Ollama v0.1.0+ for embedding generation
    """

    llm_host: str = DEFAULT_LLM_HOST
    llm_port: int = 11434
    llm_model: str = DEFAULT_LLM_MODEL
    llm_backend: str = "ollama"
    dash_host: str = "127.0.0.1"
    dash_port: int = 8050
    dash_debug: bool = False
    timeout: int = 600
    default_prompt: str = DEFAULT_PROMPT
    # Number of images to process in parallel against the LLM backend.
    # 1 = strictly sequential (historical behaviour).
    batch_concurrency: int = DEFAULT_BATCH_CONCURRENCY
    folder_path: str = "/photos"
    recursive: bool = True
    dry_run: bool = False
    # Optional mapping from server/container paths to host paths for the
    # "Copy Path" feature. Newline- or semicolon-separated list of
    # ``container_prefix=host_prefix`` entries. Empty by default, which returns
    # the server-side path as-is (correct when the app runs on the host).
    reveal_map: str = ""

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load application configuration from environment variables.

        Reads ``.env`` via python-dotenv, then respects both the newer
        ``LOCAL_PHOTO_AGENT_LLM_*`` and legacy ``LOCAL_PHOTO_AGENT_OLLAMA_*``
        variable families.

        Embedding configuration uses:
        - LOCAL_PHOTO_AGENT_EMBEDDING_ENABLED
        - LOCAL_PHOTO_AGENT_EMBEDDING_MODEL
        - LOCAL_PHOTO_AGENT_EMBEDDING_BACKEND
        - LOCAL_PHOTO_AGENT_SIMILARITY_LIMIT
        - LOCAL_PHOTO_AGENT_SIMILARITY_METRIC

        Requirements:
        - Vector search library (HARD REQUIREMENT) for vector search
        - Ollama v0.1.0+ for embedding generation
        """
        load_dotenv()
        _warn_deprecated("LLM", "OLLAMA")
        emb = EmbeddingConfig.from_env()
        return cls(
            llm_host=os.getenv("LOCAL_PHOTO_AGENT_LLM_HOST")
            or os.getenv("LOCAL_PHOTO_AGENT_OLLAMA_HOST", DEFAULT_LLM_HOST),
            llm_port=_safe_int_or("LOCAL_PHOTO_AGENT_LLM_PORT", "LOCAL_PHOTO_AGENT_OLLAMA_PORT", 11434),
            llm_model=os.getenv("LOCAL_PHOTO_AGENT_LLM_MODEL")
            or os.getenv("LOCAL_PHOTO_AGENT_OLLAMA_MODEL", DEFAULT_LLM_MODEL),
            llm_backend=os.getenv("LOCAL_PHOTO_AGENT_LLM_BACKEND", "ollama"),
            dash_host=os.getenv("LOCAL_PHOTO_AGENT_DASH_HOST", "127.0.0.1"),
            dash_port=_safe_int("LOCAL_PHOTO_AGENT_DASH_PORT", 8050),
            dash_debug=os.getenv("LOCAL_PHOTO_AGENT_DASH_DEBUG", "false").lower() in ("1", "true", "yes"),
            timeout=_safe_int_or("LOCAL_PHOTO_AGENT_LLM_TIMEOUT", "LOCAL_PHOTO_AGENT_OLLAMA_TIMEOUT", 600),
            default_prompt=os.getenv("LOCAL_PHOTO_AGENT_DEFAULT_PROMPT", DEFAULT_PROMPT),
            batch_concurrency=_safe_int("LOCAL_PHOTO_AGENT_BATCH_CONCURRENCY", DEFAULT_BATCH_CONCURRENCY),
            folder_path=os.getenv("LOCAL_PHOTO_AGENT_FOLDER", "/photos"),
            recursive=os.getenv("LOCAL_PHOTO_AGENT_RECURSIVE", "true").lower() in ("1", "true", "yes"),
            dry_run=os.getenv("LOCAL_PHOTO_AGENT_DRY_RUN", "false").lower() in ("1", "true", "yes"),
            reveal_map=os.getenv("LOCAL_PHOTO_AGENT_REVEAL_MAP", ""),
            embedding_enabled=emb.embedding_enabled,
            embedding_model=emb.embedding_model,
            embedding_backend=emb.embedding_backend,
            similarity_limit=emb.similarity_limit,
            similarity_metric=emb.similarity_metric,
        )

    def validate(self):
        """Validate all port ranges, non-empty hosts, and positive timeout.

        Raises ValueError with a clear message on invalid configuration.
        """
        _validate_host("LOCAL_PHOTO_AGENT_LLM_HOST", self.llm_host, "LLM host")
        _validate_port_range("LOCAL_PHOTO_AGENT_LLM_PORT", self.llm_port, "LLM port")
        _validate_positive("LOCAL_PHOTO_AGENT_LLM_TIMEOUT", self.timeout, "LLM timeout")
        _validate_host("LOCAL_PHOTO_AGENT_DASH_HOST", self.dash_host, "Dash host")
        _validate_port_range("LOCAL_PHOTO_AGENT_DASH_PORT", self.dash_port, "Dash port")
        _validate_concurrency("LOCAL_PHOTO_AGENT_BATCH_CONCURRENCY", self.batch_concurrency)
        super().validate()

    def to_processing_config(self) -> ProcessingConfig:
        """Derive a ProcessingConfig snapshot from this AppConfig."""
        return ProcessingConfig(
            backend=self.llm_backend,
            host=self.llm_host,
            port=self.llm_port,
            model=self.llm_model,
            timeout=self.timeout,
            default_prompt=self.default_prompt,
            batch_concurrency=self.batch_concurrency,
            embedding_enabled=self.embedding_enabled,
            embedding_model=self.embedding_model,
            embedding_backend=self.embedding_backend,
            similarity_limit=self.similarity_limit,
            similarity_metric=self.similarity_metric,
        )
