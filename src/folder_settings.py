"""Per-folder processing settings persistence.

``<folder>/.local-photo-agent/settings.json`` stores per-folder processing
options. Settings here are the source of truth read at processing start, so a
user can tune a folder (e.g. batch concurrency) without touching environment
variables or restarting the app.

This is a small, generic key/value JSON store. Per-image lifecycle tracking
lives in ``SimpleProcessingTracker`` (``features.db``); the aggregate batch
status lives in ``batch_state.json``. This file holds durable processing
*options* (currently ``batch_concurrency``).

Writes are atomic (temp file + ``replace``) to survive concurrent readers.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical keys stored in settings.json.
KEY_BATCH_CONCURRENCY = "batch_concurrency"


def _settings_path(folder: str | Path) -> Path:
    """Return the path to the per-folder settings JSON file."""
    return Path(folder) / ".local-photo-agent" / "settings.json"


def read_folder_settings(folder: str | Path) -> dict:
    """Read the per-folder settings dictionary.

    Returns an empty dict if the file does not exist or is unreadable. Never
    raises — settings are best-effort and processing falls back to defaults.
    """
    p = _settings_path(folder)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read folder settings at %s: %s", p, e)
        return {}


def write_folder_setting(folder: str | Path, key: str, value) -> None:
    """Atomically upsert a single setting key in the per-folder settings file.

    Preserves any existing keys. Creates the ``.local-photo-agent`` directory
    if needed. Never raises on read failure (treats a corrupt file as empty
    before writing).
    """
    p = _settings_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)

    settings = read_folder_settings(folder)
    settings[key] = value

    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings), encoding="utf-8")
    tmp.replace(p)
    logger.debug("Folder setting written: %s/%s=%r", folder, key, value)


def get_batch_concurrency(folder: str | Path, default: int) -> int:
    """Return the per-folder batch concurrency, coerced to >= 1.

    Reads ``batch_concurrency`` from the per-folder settings file. If absent or
    invalid, returns ``default`` (also coerced to >= 1).

    Args:
        folder: The folder being processed.
        default: Fallback value when the setting is not stored or invalid.

    Returns:
        The effective concurrency (always >= 1).
    """
    settings = read_folder_settings(folder)
    raw = settings.get(KEY_BATCH_CONCURRENCY)
    if raw is None:
        effective = default
    else:
        try:
            effective = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s=%r in %s; using default %d",
                KEY_BATCH_CONCURRENCY,
                raw,
                _settings_path(folder),
                default,
            )
            effective = default
    if effective < 1:
        effective = 1
    return effective
