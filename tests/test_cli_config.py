"""Tests for CLI flag propagation into the processing/embedding configuration.

The embedding-related CLI flags (--no-embeddings, --embedding-model,
--embedding-backend, --host, --port, --timeout) must reach the
SequentialProcessor used by ``process_paths`` — previously they only
configured the LLM extractor, not the embedding generator.
"""

import sys
from unittest.mock import patch

import pytest

import main


@pytest.fixture
def photo_folder(tmp_path):
    """A folder with one fake image."""
    folder = tmp_path / "photos"
    folder.mkdir()
    (folder / "photo1.jpg").write_bytes(b"fake jpeg data")
    return folder


def _run_main(argv):
    with patch.object(sys, "argv", argv):
        main.main()


def _fake_process_paths(captured):
    def fake(paths, extractor, **kwargs):
        captured.update(kwargs)
        return {
            "total_found": len(paths),
            "processed": 0,
            "skipped": 0,
            "successes": 0,
            "failures": 0,
            "results": [],
        }

    return fake


class TestCliConfigPropagation:
    def test_embedding_flags_reach_process_paths(self, photo_folder):
        """All embedding/connection CLI flags are applied to the ProcessingConfig."""
        captured = {}
        with patch("main.process_paths", side_effect=_fake_process_paths(captured)):
            _run_main(
                [
                    "main.py",
                    str(photo_folder),
                    "--dry-run",
                    "--no-embeddings",
                    "--embedding-model",
                    "my-custom-model",
                    "--embedding-backend",
                    "ollama",
                    "--host",
                    "10.1.2.3",
                    "--port",
                    "9999",
                    "--timeout",
                    "42",
                ]
            )

        config = captured["config"]
        assert config.embedding_enabled is False
        assert config.embedding_model == "my-custom-model"
        assert config.embedding_backend == "ollama"
        assert config.host == "10.1.2.3"
        assert config.port == 9999
        assert config.timeout == 42

    def test_embeddings_enabled_by_default(self, photo_folder):
        """Without --no-embeddings, embedding generation stays enabled."""
        captured = {}
        with patch("main.process_paths", side_effect=_fake_process_paths(captured)):
            _run_main(["main.py", str(photo_folder), "--dry-run"])

        assert captured["config"].embedding_enabled is True
