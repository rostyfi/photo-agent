# features-database

> **Status:** Draft  
> **Created:** 2026-05-31 20:10:46

## Overview

A SQLite-backed features database for Open Photo Agent. Initially a minimal schema (`raw_features` with `model_output TEXT`) that creates itself on first access. Future iterations will expand the schema and wire it into extraction pipelines for cross-folder search and aggregation.

## Motivation

Currently, every extraction result is stored as an individual JSON sidecar file. At scale (thousands of images), querying or aggregating across folders requires `os.walk()` + `json.load()` on every file. A SQLite database provides indexed, queryable storage for structured features without sacrificing the existing sidecar-first architecture.

## Requirements

- Provide a module (`src/db.py`) that opens or creates a SQLite database at a given path.
- If the database does not exist, automatically create the `raw_features` table with a single `model_output TEXT` column.
- Parent directories for the DB path must be created automatically if missing.
- The module must use only stdlib (`sqlite3`, `pathlib`, `logging`).
- No new third-party dependencies may be added for this iteration.
- A unit test must verify that `init_db()` creates the file and the table when called on a non-existent path.
- No data insertion, querying, or integration with existing processing pipelines in this iteration.

## Design / Approach

The database is opened on demand via ``FeaturesDatabase(db_path).init_db()``. The caller is responsible for closing the connection via ``.close()`` or a context manager. The table uses ``CREATE TABLE IF NOT EXISTS`` so the call is idempotent — safe to call repeatedly without error.

A classmethod ``FeaturesDatabase.default_db_path(folder)`` returns ``.open-photo-agent/features.db`` inside a given folder, matching the existing per-folder sidecar/WAL convention.

### Files to modify

```
src/sidecar/database/db.py      - New module: FeaturesDatabase class with SQLite init and schema creation
src/sidecar/database/__init__.py - Re-exports FeaturesDatabase
tests/test_db.py                  - New test: verify DB file + table creation via class API
```

### Database changes (if any)

No migrations needed. Schema is created automatically via `CREATE TABLE IF NOT EXISTS`.

Schema for this iteration:

```sql
CREATE TABLE IF NOT EXISTS raw_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_output TEXT
);
```

### API changes (if any)

None. The database is not yet wired into any CLI, web UI, or processing pipeline.

## Implementation Steps

1. Create `src/db.py` with `init_db()` and `default_db_path()`.
2. Create `tests/test_db.py` with a test that asserts the DB file is created and the `raw_features` table exists.
3. Run the test suite to confirm no regressions.

## Testing Plan

- [x] Unit tests added/updated (`tests/test_db.py`)
- [ ] Integration tests pass (N/A — no pipeline integration yet)
- [x] Manual smoke test: run `python -c "from src.sidecar.database import FeaturesDatabase; db = FeaturesDatabase('/tmp/test-features.db'); db.init_db(); db.close()"` and verify file appears

## Edge Cases & Risks

- Calling `init_db()` on a read-only filesystem or without permissions will raise `OSError` — acceptable, callers can catch.
- The `id` column uses `AUTOINCREMENT` which is safe but slightly slower than plain `INTEGER PRIMARY KEY` on very large insert volumes. Acceptable for current scale.
- Future iterations must decide on DB path strategy (per-folder vs global) before wiring into the app.

## References

- SQLite `CREATE TABLE IF NOT EXISTS` semantics: https://www.sqlite.org/lang_createtable.html
- Existing per-folder data convention: `src/sidecar/`, `src/wal.py`, `src/batch_state.py`
