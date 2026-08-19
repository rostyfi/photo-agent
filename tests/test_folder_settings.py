"""Tests for src/folder_settings.py — per-folder processing settings."""

import json
from pathlib import Path

import pytest

from src.folder_settings import (
    KEY_BATCH_CONCURRENCY,
    KEY_DRY_RUN,
    KEY_EMBEDDING_BACKEND,
    KEY_EMBEDDING_ENABLED,
    KEY_EMBEDDING_MODEL,
    KEY_LLM_BACKEND,
    KEY_LLM_HOST,
    KEY_LLM_MODEL,
    KEY_LLM_PORT,
    KEY_RECURSIVE,
    KEY_TIMEOUT,
    apply_folder_settings,
    get_batch_concurrency,
    read_folder_settings,
    write_folder_setting,
    write_folder_settings,
)
from src.config import AppConfig, ProcessingConfig


def test_read_returns_empty_when_missing(tmp_path):
    assert read_folder_settings(tmp_path) == {}


def test_write_then_read_roundtrip(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 4)
    assert read_folder_settings(tmp_path) == {"batch_concurrency": 4}


def test_write_preserves_other_keys(tmp_path):
    write_folder_setting(tmp_path, "other", "x")
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 2)
    settings = read_folder_settings(tmp_path)
    assert settings == {"other": "x", "batch_concurrency": 2}


def test_write_creates_local_photo_agent_dir(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 3)
    assert (tmp_path / ".local-photo-agent" / "settings.json").exists()


def test_get_batch_concurrency_returns_stored(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 6)
    assert get_batch_concurrency(tmp_path, 1) == 6


def test_get_batch_concurrency_falls_back_to_default_when_absent(tmp_path):
    assert get_batch_concurrency(tmp_path, 2) == 2


def test_get_batch_concurrency_coerces_invalid_to_default(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, "not-a-number")
    assert get_batch_concurrency(tmp_path, 3) == 3


def test_get_batch_concurrency_coerces_below_one_to_one(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 0)
    assert get_batch_concurrency(tmp_path, 2) == 1
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, -5)
    assert get_batch_concurrency(tmp_path, 2) == 1


def test_get_batch_concurrency_coerces_default_below_one(tmp_path):
    assert get_batch_concurrency(tmp_path, 0) == 1
    assert get_batch_concurrency(tmp_path, -3) == 1


def test_read_handles_corrupt_file(tmp_path):
    p = tmp_path / ".local-photo-agent" / "settings.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not valid json", encoding="utf-8")
    assert read_folder_settings(tmp_path) == {}


def test_write_overwrites_existing_value(tmp_path):
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 2)
    write_folder_setting(tmp_path, KEY_BATCH_CONCURRENCY, 8)
    assert json.loads((tmp_path / ".local-photo-agent" / "settings.json").read_text()) == {
        "batch_concurrency": 8
    }


def test_write_folder_settings_upserts_multiple_keys_atomically(tmp_path):
    write_folder_setting(tmp_path, "other", "x")
    write_folder_settings(
        tmp_path,
        {KEY_LLM_HOST: "10.0.0.5", KEY_LLM_PORT: 12345, KEY_BATCH_CONCURRENCY: 3},
    )
    settings = read_folder_settings(tmp_path)
    assert settings == {
        "other": "x",
        "llm_host": "10.0.0.5",
        "llm_port": 12345,
        "batch_concurrency": 3,
    }


def test_apply_folder_settings_overrides_app_config(tmp_path):
    write_folder_settings(
        tmp_path,
        {
            KEY_LLM_HOST: "10.0.0.9",
            KEY_LLM_PORT: 12345,
            KEY_LLM_MODEL: "custom-model",
            KEY_LLM_BACKEND: "dry_run",
            KEY_TIMEOUT: 90,
            KEY_RECURSIVE: False,
            KEY_DRY_RUN: True,
            KEY_EMBEDDING_ENABLED: False,
            KEY_EMBEDDING_MODEL: "all-minilm",
            KEY_EMBEDDING_BACKEND: "ollama",
            KEY_BATCH_CONCURRENCY: 4,
        },
    )
    config = AppConfig.from_env()
    apply_folder_settings(config, tmp_path)
    assert config.llm_host == "10.0.0.9"
    assert config.llm_port == 12345
    assert config.llm_model == "custom-model"
    assert config.llm_backend == "dry_run"
    assert config.timeout == 90
    assert config.recursive is False
    assert config.dry_run is True
    assert config.embedding_enabled is False
    assert config.embedding_model == "all-minilm"
    assert config.embedding_backend == "ollama"
    assert config.batch_concurrency == 4


def test_apply_folder_settings_overrides_processing_config(tmp_path):
    write_folder_settings(
        tmp_path,
        {KEY_LLM_HOST: "10.0.0.9", KEY_LLM_PORT: 12345, KEY_LLM_MODEL: "custom-model", KEY_BATCH_CONCURRENCY: 7},
    )
    config = ProcessingConfig.from_env()
    apply_folder_settings(config, tmp_path)
    # ProcessingConfig uses bare host/port/model attribute names
    assert config.host == "10.0.0.9"
    assert config.port == 12345
    assert config.model == "custom-model"
    assert config.batch_concurrency == 7


def test_apply_folder_settings_skips_absent_keys(tmp_path):
    write_folder_setting(tmp_path, KEY_LLM_HOST, "10.0.0.9")
    config = AppConfig.from_env()
    original_port = config.llm_port
    apply_folder_settings(config, tmp_path)
    assert config.llm_host == "10.0.0.9"
    # port was not stored, so the env default is preserved
    assert config.llm_port == original_port


def test_apply_folder_settings_no_file_leaves_config_untouched(tmp_path):
    config = AppConfig.from_env()
    original_host = config.llm_host
    apply_folder_settings(config, tmp_path)
    assert config.llm_host == original_host


def test_apply_folder_settings_skips_invalid_values(tmp_path):
    write_folder_settings(
        tmp_path,
        {KEY_LLM_PORT: "not-a-port", KEY_LLM_HOST: "10.0.0.9"},
    )
    config = AppConfig.from_env()
    original_port = config.llm_port
    apply_folder_settings(config, tmp_path)
    assert config.llm_host == "10.0.0.9"
    # invalid port is skipped, env default preserved
    assert config.llm_port == original_port


def test_apply_folder_settings_coerces_bool_strings(tmp_path):
    write_folder_settings(
        tmp_path,
        {KEY_RECURSIVE: "false", KEY_DRY_RUN: "true", KEY_EMBEDDING_ENABLED: "yes"},
    )
    config = AppConfig.from_env()
    apply_folder_settings(config, tmp_path)
    assert config.recursive is False
    assert config.dry_run is True
    assert config.embedding_enabled is True


def test_apply_folder_settings_skips_empty_string_host(tmp_path):
    write_folder_setting(tmp_path, KEY_LLM_HOST, "   ")
    config = AppConfig.from_env()
    original_host = config.llm_host
    apply_folder_settings(config, tmp_path)
    # empty/whitespace host does not clobber the existing value
    assert config.llm_host == original_host
