"""Tests for src/folder_settings.py — per-folder processing settings."""

import json
from pathlib import Path

import pytest

from src.folder_settings import (
    KEY_BATCH_CONCURRENCY,
    get_batch_concurrency,
    read_folder_settings,
    write_folder_setting,
)


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
