"""Per-folder processing settings persistence.

``<folder>/.local-photo-agent/settings.json`` stores per-folder processing
options. Settings here are the source of truth read at processing start, so a
user can tune a folder (e.g. batch concurrency) without touching environment
variables or restarting the app.

This is a small, generic key/value JSON store. Per-image lifecycle tracking
lives in ``SimpleProcessingTracker`` (``features.db``); the aggregate batch
status lives in ``batch_state.json``. This file holds durable processing
*options* and connection settings (LLM host/port/model/backend, timeout,
batch concurrency, embedding options, scan/dry-run flags).

At app start (and at ``/process`` time) ``apply_folder_settings`` overlays
stored values onto an ``AppConfig``/``ProcessingConfig``, so the per-folder
file overrides environment defaults. The Settings modal writes back through
``write_folder_settings``/``write_folder_setting``.

Writes are atomic (temp file + ``replace``) to survive concurrent readers.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical keys stored in settings.json.
KEY_BATCH_CONCURRENCY = "batch_concurrency"
KEY_LLM_HOST = "llm_host"
KEY_LLM_PORT = "llm_port"
KEY_LLM_MODEL = "llm_model"
KEY_LLM_BACKEND = "llm_backend"
KEY_TIMEOUT = "timeout"
KEY_RECURSIVE = "recursive"
KEY_DRY_RUN = "dry_run"
KEY_EMBEDDING_ENABLED = "embedding_enabled"
KEY_EMBEDDING_MODEL = "embedding_model"
KEY_EMBEDDING_BACKEND = "embedding_backend"

# Maps a settings key to the config attribute(s) that may hold it. AppConfig
# uses the ``llm_*`` prefix; ProcessingConfig uses bare ``host``/``port``/...
# The first attribute that exists on the config object is the one set.
_ATTR_BY_KEY: dict[str, tuple[str, ...]] = {
    KEY_LLM_HOST: ("llm_host", "host"),
    KEY_LLM_PORT: ("llm_port", "port"),
    KEY_LLM_MODEL: ("llm_model", "model"),
    KEY_LLM_BACKEND: ("llm_backend", "backend"),
    KEY_TIMEOUT: ("timeout",),
    KEY_RECURSIVE: ("recursive",),
    KEY_DRY_RUN: ("dry_run",),
    KEY_EMBEDDING_ENABLED: ("embedding_enabled",),
    KEY_EMBEDDING_MODEL: ("embedding_model",),
    KEY_EMBEDDING_BACKEND: ("embedding_backend",),
    KEY_BATCH_CONCURRENCY: ("batch_concurrency",),
}

# Sentinel for "value could not be coerced; skip it".
_UNSET = object()
_INT_KEYS = (KEY_LLM_PORT, KEY_TIMEOUT, KEY_BATCH_CONCURRENCY)
_BOOL_KEYS = (KEY_RECURSIVE, KEY_DRY_RUN, KEY_EMBEDDING_ENABLED)


def _coerce_value(key: str, raw):
    """Coerce a raw stored value to the right Python type for ``key``.

    Returns ``_UNSET`` when the value is missing or uncoercible so the caller
    can skip it (preserving any existing config value).
    """
    if raw is None:
        return _UNSET
    if key in _INT_KEYS:
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid %s=%r in folder settings; skipping", key, raw)
            return _UNSET
    if key in _BOOL_KEYS:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes")
        return bool(raw)
    # String-valued keys: skip empty strings so we never clobber with "".
    text = str(raw)
    if not text.strip():
        return _UNSET
    return text


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
    write_folder_settings(folder, {key: value})


def write_folder_settings(folder: str | Path, updates: dict) -> None:
    """Atomically upsert multiple setting keys in the per-folder settings file.

    Preserves any existing keys and writes all ``updates`` in a single
    read-modify-replace cycle (one atomic replace). Creates the
    ``.local-photo-agent`` directory if needed. Never raises on read failure
    (treats a corrupt file as empty before writing).
    """
    p = _settings_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)

    settings = read_folder_settings(folder)
    settings.update(updates)

    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings), encoding="utf-8")
    tmp.replace(p)
    logger.debug("Folder settings written for %s: %r", folder, list(updates))


def _apply_settings_dict(config, settings: dict) -> None:
    """Override config attributes in place from a settings dict.

    Only keys present in ``settings`` are applied; absent keys leave the
    config untouched. The first attribute name in ``_ATTR_BY_KEY`` that exists
    on ``config`` is set, so this works for both ``AppConfig`` (``llm_*``) and
    ``ProcessingConfig`` (``host``/``port``/...). Uncoercible values are skipped.
    """
    for key, attrs in _ATTR_BY_KEY.items():
        if key not in settings:
            continue
        value = _coerce_value(key, settings[key])
        if value is _UNSET:
            continue
        for attr in attrs:
            if hasattr(config, attr):
                setattr(config, attr, value)
                break


def apply_folder_settings(config, folder: str | Path):
    """Overlay per-folder settings onto ``config`` in place.

    Reads ``<folder>/.local-photo-agent/settings.json`` and overrides the
    matching fields (LLM host/port/model/backend, timeout, batch concurrency,
    embedding options, recursive/dry-run flags). Missing or uncoercible
    values are skipped, so environment/CLI defaults survive. Never raises.

    Returns the passed-in ``config`` for convenience.
    """
    settings = read_folder_settings(folder)
    if settings:
        _apply_settings_dict(config, settings)
    return config


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
