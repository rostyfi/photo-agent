# extend-database.md

> **Status:** Draft
> **Created:** 2026-06-06 12:39:31

## Overview

Extend the per-folder SQLite database (`features.db`) from a single JSON-blob table into a normalized, queryable schema with full-text search (FTS5) support. The goal is to let users search photos by extracted content (description, tags, subjects, etc.) directly from the SQL Explorer and from new search UI components, without requiring raw `json_extract()` queries.

## Motivation

Today `features.db` only stores the full `ProcessingResult` dict as JSON in `raw_features.model_output`. While this preserves every detail, it makes structured queries painful:

- Searching for photos tagged "beach" requires `json_extract(model_output, '$.parsed.tags')`.
- There are no indexes on tags, descriptions, or subjects.
- The SQL Explorer UI is under-utilised because users must know SQLite JSON syntax.

By normalising the most common parsed fields and adding an FTS5 index, we unlock fast content-based search, tag aggregation, and better photo discovery from the web UI.

## Requirements

- [ ] **R1 — Backward compatibility:** Existing `raw_features` table and all current read/write behaviour must remain unchanged. Existing databases continue to work.
- [ ] **R2 — Schema migrations:** Introduce a `schema_migrations` table and an ordered migration runner so future schema changes are tracked and idempotent.
- [ ] **R3 — Normalised feature table:** Add `extracted_features` with nullable columns `description`, `subjects`, `objects`, `colors`, `setting`, `mood` (all `TEXT`). One row per `image_path` with `FOREIGN KEY` or `UNIQUE` linkage to `raw_features.image_path`.
- [ ] **R4 — Tag normalisation:** Add `feature_tags` table (`image_path TEXT`, `tag TEXT`) so tags can be queried and counted efficiently.
- [ ] **R5 — Full-text search (FTS5):** Add `extracted_features_fts` virtual table indexing `description`, `subjects`, `objects`, `colors`, `setting`, `mood`, plus a virtual column fed by tags. Provide `search_features(query, limit=50)`.
- [ ] **R6 — Automatic indexing on save:** When `FeaturesDatabase.save_extraction()` is called, parse `result["parsed"]` and upsert into `extracted_features`, `feature_tags`, and the FTS index. If `parsed` is missing or malformed, write NULLs / empty tag set (graceful degradation).
- [ ] **R7 — Query helpers:** Add Python methods:
  - `search_features(query: str, limit: int = 50) -> List[Dict]` — FTS search.
  - `get_features_by_tag(tag: str) -> List[Dict]` — photos matching a tag.
  - `list_all_tags() -> List[str]` — distinct tags across the folder.
  - `get_feature_summary(image_path: str) -> Optional[Dict]` — joined view of raw + normalised data.
- [ ] **R8 — SQL Explorer enhancements:** Update the Dash UI to show preset query buttons (e.g. *List all tags*, *Search descriptions*, *Photos by tag*) and a dedicated search input that uses the new query helpers.
- [ ] **R9 — Graceful fallback:** If the Python build does not support FTS5, log a warning and skip the virtual table creation; all other features still work.
- [ ] **R10 — Tests:** Unit tests for schema migration, normalised upserts, tag population, FTS queries, and fallback behaviour.

## Design / Approach

### High-level flow

```
Image processed
      │
      ▼
save_extraction(image_path, result)
      │
      ├─► Upsert raw_features (existing)
      ├─► Parse result["parsed"] dict
      ├─► Upsert extracted_features (description, subjects, …)
      ├─► DELETE + INSERT feature_tags for this image_path
      └─► INSERT / UPDATE extracted_features_fts row
```

### Schema additions

```sql
-- Migration tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT
);

-- Normalised feature columns (1:1 with image_path)
CREATE TABLE IF NOT EXISTS extracted_features (
    image_path TEXT PRIMARY KEY,
    description TEXT,
    subjects TEXT,
    objects TEXT,
    colors TEXT,
    setting TEXT,
    mood TEXT,
    updated_at TEXT
);

-- Normalised tags (1:N with image_path)
CREATE TABLE IF NOT EXISTS feature_tags (
    image_path TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (image_path, tag)
);
CREATE INDEX idx_feature_tags_tag ON feature_tags(tag);

-- FTS5 virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS extracted_features_fts USING fts5(
    description, subjects, objects, colors, setting, mood,
    tags,
    content='extracted_features',
    content_rowid='rowid'
);
```

> **Note on FTS5:** We use `content='extracted_features'` so the FTS table is an *external content* index. This keeps the normalised table as the source of truth and lets us rebuild the index easily.

> **Note on tags in FTS:** We will concatenate tags into a single space-separated string column in the FTS table (or use an `INSERT INTO extracted_features_fts` trigger approach) so searching `"beach sunset"` matches both tag sets and descriptions.

### Files to modify

```
src/sidecar/database/db.py      — Major changes: migrations, new tables, query helpers, FTS logic
src/callbacks.py                — New callbacks: search input, preset query buttons
src/layout.py                   — Add Search card below SQL Explorer
src/components.py             — Build search result table / tag cloud component
tests/test_db.py                — Expand tests for migrations, FTS, tags, fallback
```

### Database changes

| Change | Details |
|--------|---------|
| `schema_migrations` | New tracking table |
| `extracted_features` | New normalised feature table |
| `feature_tags` | New tag association table + index |
| `extracted_features_fts` | New FTS5 virtual table (external content) |
| Migration runner | Idempotent, ordered, runs inside `init_db()` |

### API changes

- `FeaturesDatabase` gains new public methods (R7). No breaking changes to existing methods.
- `DatabaseSidecarStore.save()` behaviour is unchanged; it already calls `FeaturesDatabase.save_extraction()`, so the normalisation happens transparently.
- Dash UI gets a new **Search** card with:
  - Text input + "Search" button
  - "List all tags" button
  - Results rendered as a sortable `dash_table.DataTable` (image path, description preview, matched tags)

## Implementation Steps

1. **Add migration runner to `FeaturesDatabase`**
   - Create `_run_migrations(conn)` that checks `schema_migrations`, applies pending SQL scripts in order, and records versions.
   - Move existing `ALTER TABLE … ADD COLUMN` logic into migration `001_initial_schema.sql` equivalent (Python-based migration functions).

2. **Implement migrations 002–004**
   - `002`: Create `extracted_features` table.
   - `003`: Create `feature_tags` table + index.
   - `004`: Create `extracted_features_fts` virtual table (with `try/except` for unsupported builds).

3. **Update `save_extraction`**
   - After the existing raw upsert, parse `result.get("parsed", {})`.
   - Upsert `extracted_features`.
   - Clear and re-insert `feature_tags`.
   - Update FTS index via `INSERT INTO extracted_features_fts(rowid, …) VALUES(…)` or use triggers.

4. **Add query helpers**
   - `search_features`, `get_features_by_tag`, `list_all_tags`, `get_feature_summary`.

5. **Build Dash search UI**
   - Add search card to `src/layout.py`.
   - Add `build_search_results()` to `src/components.py`.
   - Register search callback in `src/callbacks.py`.

6. **Testing**
   - Verify migration idempotency on old DBs.
   - Verify tag extraction from `parsed`.
   - Verify FTS round-trip (insert → search → match).
   - Verify graceful behaviour when `parsed` is missing / not a dict.
   - Verify fallback when FTS5 is unavailable (mock or test on build without it).

## Testing Plan

- [ ] Unit tests added/updated in `tests/test_db.py`:
  - `test_migration_001_002_003_004_applies_idempotently`
  - `test_save_extraction_populates_extracted_features`
  - `test_save_extraction_populates_tags`
  - `test_save_extraction_handles_missing_parsed`
  - `test_search_features_returns_matches`
  - `test_list_all_tags_distinct_sorted`
  - `test_get_features_by_tag`
  - `test_fts_rebuild_method`
- [ ] Integration tests pass: run `python -m pytest tests/` — existing tests must not break.
- [ ] Manual smoke test:
  1. Process a folder via web UI.
  2. Open Search card, type a tag from the processed images.
  3. Confirm results appear in table.
  4. Click "List all tags" and confirm tag list renders.
  5. Open SQL Explorer, run `SELECT * FROM extracted_features LIMIT 10` — should return rows.

## Edge Cases & Risks

| Edge Case | Mitigation |
|-----------|------------|
| **Custom prompts** that return different JSON keys | Only extract known keys (`description`, `subjects`, etc.). Missing keys → `NULL`. Custom keys stay in `raw_features.model_output`. |
| **FTS5 unavailable** (rare older builds) | Catch `sqlite3.OperationalError` on virtual table creation, log warning, skip FTS methods. All other tables still work. |
| **Concurrent writes** to FTS5 | SQLite WAL mode is already enabled; FTS5 external content tables are safe for concurrent reads, but writes should be serialised (same as today — one connection per `save_extraction` call). |
| **Large tag lists** | Tags are stored one-per-row; no arbitrary limit. SQLite handles millions of rows fine. |
| **Rebuild after migration** | Existing DBs will have empty `extracted_features` / `feature_tags` until images are re-processed or a backfill script is run. For MVP we accept this; a future backfill migration can populate from `raw_features.model_output`. |
| **Breaking existing SQL Explorer queries** | `raw_features` is untouched; existing user queries continue to work. |

## References

- Current database implementation: `src/sidecar/database/db.py`
- SQL Explorer callback: `src/callbacks.py::register_sql_explorer_callback`
- SQLite FTS5 docs: https://sqlite.org/fts5.html
- Project `README.md` § Sidecar JSON / Database
