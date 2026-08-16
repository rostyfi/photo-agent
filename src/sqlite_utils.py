"""Shared SQLite connection helpers.

Centralises the connection setup (PRAGMA configuration, extension loading,
parent-directory creation) that was previously duplicated across
``FeaturesDatabase``, ``SimpleProcessingTracker``, and ad-hoc callers.

Keeping this in one place ensures every connection in the application
applies the same pragmas (foreign keys, WAL journal mode, recursive
triggers) and handles extension loading consistently.
"""

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

logger = logging.getLogger(__name__)


def open_connection(
    db_path: str | Path,
    *,
    enable_extensions: bool = False,
    ensure_parent: bool = True,
) -> sqlite3.Connection:
    """Open a SQLite connection with the application's standard PRAGMAs.

    Applies: ``foreign_keys = ON``, ``journal_mode = WAL`` (warn on failure),
    and ``recursive_triggers = ON`` (ignored on failure). When
    ``enable_extensions`` is set, ``enable_load_extension(True)`` is called so
    sqlite-vec can be loaded; failures are logged at debug level and do not
    raise, matching the previous per-module behaviour.

    The caller owns the returned connection and is responsible for closing it.
    Prefer :func:`connect` when a context manager is more convenient.

    Args:
        db_path: Path to the SQLite database file.
        enable_extensions: If True, enable extension loading (sqlite-vec).
        ensure_parent: If True, create the parent directory tree if missing.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    path = Path(db_path)
    if ensure_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:
        logger.warning("Could not set WAL journal mode on %s", path)
    if enable_extensions:
        try:
            conn.enable_load_extension(True)
            logger.debug("Extension loading enabled for connection")
        except sqlite3.Error as e:
            logger.debug("Could not enable extension loading: %s", e)
    with suppress(sqlite3.Error):
        conn.execute("PRAGMA recursive_triggers = ON")
    return conn


@contextmanager
def connect(
    db_path: str | Path,
    *,
    enable_extensions: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager wrapping :func:`open_connection` with cleanup.

    Yields an open connection and closes it on exit, including on error.
    """
    conn = open_connection(db_path, enable_extensions=enable_extensions)
    try:
        yield conn
    finally:
        conn.close()
