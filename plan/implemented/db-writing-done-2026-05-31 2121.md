# db-writing

> **Status:** Approved  
> **Created:** 2026-05-31 20:47:35  
> **Confirmed:** 2026-05-31

## Overview

Replace per-image JSON sidecars with writes to the existing SQLite database managed by `FeaturesDatabase`. Each processed folder already gets a `features.db` inside its `.open-photo-agent/` directory (created by `FeaturesDatabase.default_db_path`). The existing write-ahead log (`src/wal.py`) and batch state JSON remain unchanged; only the final result persistence layer switches from individual `.json` files to rows in the existing `raw_features` table.

## Motivation

- JSON sidecars are hard to query at scale (e.g., "show me all images tagged 'beach' in this folder").
- Atomic writes and concurrent reads are simpler with SQLite.
- The `FeaturesDatabase` class and `features.db` already exist but are under-utilised; we will extend the existing `raw_features` table to store extraction results instead of creating a parallel persistence mechanism.
- Prepares the ground for the Dash UI to search, filter, and browse extraction results without loading thousands of small files.

## Requirements

1. **Use the existing `FeaturesDatabase` class.** Database lives at `<folder>/.open-photo-agent/features.db` — the same path already produced by `FeaturesDatabase.default_db_path()`.
2. **No new database tables.** All writes go into the existing `raw_features` table created by `FeaturesDatabase.init_db()`. The table schema may be extended with new columns (e.g., `image_path`) to support lookups, but no additional tables are created.
3. **Schema mirrors sidecar JSON.** The `model_output` column stores the full extraction result as a JSON string. Additional columns (e.g., `image_path`, `success`, `model`) are added to `raw_features` to support efficient querying and deduplication.
4. **Replace, don't duplicate.** `save_sidecar_json()` and its callers switch to DB writes. JSON sidecars are no longer created for new extractions.
5. **WAL unchanged.** `src/wal.py` continues to track `pending → in_progress → completed`. The WAL compaction/prune logic is unaffected.
6. **Thread-safe writes.** Background `BatchJob` threads in the web UI must be able to write completions safely. Use SQLite WAL journal mode and `check_same_thread=False`.
7. **Backward compatibility for reads.** `PhotoList.exclude_processed_from` (and any future read path) should consider the DB as the source of truth, falling back to legacy JSON sidecars if the DB row is missing.
8. **Atomic init.** The DB and table are created lazily on the first write to a folder; callers don't need to pre-initialize.

## Design / Approach

### Reused module: `src/sidecar/database/db.py`
- `FeaturesDatabase` is already instantiated in `src/discovery.py` and `src/callbacks.py`.
- Extend `init_db()` to add any missing columns to `raw_features` via `ALTER TABLE ... ADD COLUMN` (SQLite supports this and it is safe to repeat).
- Add methods to `FeaturesDatabase`:
  - `save_extraction(image_path, result: Dict) -> None`
    - Upsert (`INSERT ... ON CONFLICT(image_path) DO UPDATE`) into `raw_features`.
    - Serialize the full `result` dict into the existing `model_output` column as JSON text.
  - `get_extraction(image_path) -> Optional[Dict]`
    - Read a single row by `image_path`; deserialize `model_output` back to a dict.
  - `is_processed(image_path) -> bool`
    - Lightweight existence check for `PhotoList` filtering.
  - `list_extractions() -> List[Dict]`
    - Return all rows for the folder.

### Modified files

```
src/sidecar/database/db.py    - Extend raw_features schema; add save/get/list/is_processed methods
src/sidecar.py               - Replace JSON write with DB write via FeaturesDatabase; keep public function names for minimal caller churn
src/discovery.py             - Update PhotoList.exclude_processed_from to query DB + legacy JSON fallback
src/processing.py            - Ensure DB connection lifecycle is safe inside background threads
main.py                      - No direct DB code, but verify batch/resume flows still work
```

### Database schema (extended `raw_features`)

```sql
-- Already created by FeaturesDatabase.init_db()
CREATE TABLE IF NOT EXISTS raw_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_output TEXT,
    image_path TEXT UNIQUE,      -- ADD COLUMN
    success INTEGER,             -- ADD COLUMN
    model TEXT,                  -- ADD COLUMN
    created_at TEXT            -- ADD COLUMN
);
CREATE INDEX IF NOT EXISTS idx_raw_features_image_path ON raw_features(image_path);
```

*Note:* `model_output` continues to store the full JSON payload (including `parsed`, `response`, `eval_count`, etc.). Additional top-level columns are added only for fields that need indexing or fast filtering (`image_path`, `success`, `model`).

### Data flow

```
CLI / Web UI → Ollama extract → WAL append (in_progress) → result returned
                                    ↓
                            WAL append (completed)
                                    ↓
                           save_extraction() → SQLite upsert into raw_features
```

## Implementation Steps

1. **Extend `src/sidecar/database/db.py`**
   - Update `init_db()` to add missing columns to `raw_features` via `ALTER TABLE ... ADD COLUMN` guards.
   - Implement `save_extraction()`, `get_extraction()`, `list_extractions()`, `is_processed()`.
2. **Refactor `src/sidecar.py`**
   - Delegate to `FeaturesDatabase.save_extraction()` and `FeaturesDatabase.is_processed()`.
   - Keep the same public signatures so callers (`main.py`, `processing.py`) don't change.
3. **Update `src/discovery.py`**
   - Change `exclude_processed_from` logic to query the DB first, then fall back to checking for legacy `.json` sidecars.
4. **Add tests**
   - Extend `tests/test_db.py` for upsert, get, list, thread safety, and backward-compatibility reads.
5. **Run smoke tests**
   - CLI single image → verify `features.db` updated, no JSON sidecar.
   - CLI recursive folder → correct row counts in each folder's `features.db`.
   - Web UI batch → background threads complete without SQLite thread errors.
   - Resume with WAL → existing WAL entries replay into DB on reprocessing.

## Testing Plan

- [ ] Unit tests in `tests/test_db.py` for schema extension, upsert, get, list, thread safety.
- [ ] Unit tests for `PhotoList` exclusion logic using temporary DBs.
- [ ] Integration: run `python main.py <folder>` and assert `features.db` has rows, no JSON sidecars created.
- [ ] Manual smoke test: web UI folder scan + batch run → check DB rows via `sqlite3` CLI and verify existing callback query UI still works.

## Edge Cases & Risks

- **Concurrent writes from multiple processes:** SQLite handles multiple readers + one writer fine, but two CLI processes hitting the same folder DB could see `DATABASE_LOCKED`. Acceptable for now; document that parallel CLI runs against the same folder are not supported.
- **Large `model_output` blobs:** If LLM returns huge JSON, SQLite TEXT can handle it (2GB limit), but we should store raw.
- **Migration:** Existing JSON sidecars will remain; they serve as a fallback for `is_processed` but won't be imported into the DB automatically. A future migration script can backfill if needed.
- **Rollback / WAL abandonment:** If a WAL entry is abandoned and retried, the DB upsert is idempotent, so reprocessing is safe.
- **Schema drift:** Older `features.db` files may lack the new columns. `init_db()` must use `ALTER TABLE ... ADD COLUMN` guards so existing databases are upgraded in place.

## References

- `src/sidecar/database/db.py` — existing `FeaturesDatabase` class
- `src/sidecar.py` — current JSON persistence
- `src/wal.py` — unchanged crash-recovery log
- `src/discovery.py` — `PhotoList` processed-image exclusion
- `AGENTS.md` — architecture overview
