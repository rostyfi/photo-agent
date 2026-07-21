# exploration

> **Status:** Draft  
> **Created:** 2026-05-31 20:30:12  
> **Updated:** 2026-05-31 21:05:00

## Overview

Add a **SQL Explorer** card to the Dash web UI. Users type arbitrary `SELECT` queries against the existing SQLite `features.db` for the currently selected folder, click **Run**, and see results rendered in a table below.

No schema changes, no new tables, no write path, no sync logic in this step.

## Motivation

- Every scanned folder already initialises a `features.db` (`.open-photo-agent/features.db`) via `FeaturesDatabase`.
- The database may contain tables created by other workflows or future features.
- A lightweight query UI lets users inspect whatever data is already there without leaving the browser.

## Requirements

### Functional

1. **UI: SQL input** — A `dbc.Textarea` (id: `sql-input`, ~5 rows) pre-filled with a sensible default query against `raw_features`.
2. **UI: Run button** — A `dbc.Button` (id: `btn-run-sql`, color `primary`) that executes the typed SQL.
3. **UI: Results table** — A `dash.dash_table.DataTable` (id: `sql-results`) rendered below the button, showing headers and rows. Empty result sets show a friendly message.
4. **Folder context** — The explorer targets `FeaturesDatabase.default_db_path(folder)` where `folder` comes from `input-folder`.
5. **Error handling** — Invalid SQL, missing DB file, or connection errors surface as an inline `dbc.Alert`.
6. **No mutations** — The UI only reads. There is no sync, no upsert, no backfill, and no new DDL in this step.

### Non-functional

- Backward-compatible: must not modify `FeaturesDatabase` schema or behaviour.
- Read-only by convention; security trade-off is acceptable for a local dev tool.

## Design / Approach

### Data flow

```
User types SQL + clicks Run
        │
        ▼
Callback receives (folder, sql_text)
        │
        ▼
Open FeaturesDatabase(folder/.open-photo-agent/features.db)
        │
        ▼
conn.execute(sql_text)  →  fetchall()
        │
        ▼
Render DataTable(columns=description, data=rows)
```

### Files to modify

```
src/sidecar/database/db.py        - Add execute_query() helper only (no schema changes)
src/layout.py                     - Add SQL Explorer card (textarea, button, DataTable div)
src/callbacks.py                  - Add register_sql_explorer_callback()
app.py                            - No changes expected (layout/callbacks already wired there)
tests/test_db.py                  - Add execute_query tests only
tests/test_layout.py              - Assert new IDs exist in layout
```

### Database changes

**None.** The existing `raw_features` table remains the only table managed by the app. The explorer simply queries whatever tables already exist.

A single read-only helper is added to `FeaturesDatabase`:

- `execute_query(sql: str) -> Tuple[List[str], List[Tuple]]` — returns `(column_names, rows)`.

### API changes

No external or internal API changes. The coordinator, saver, and sidecar layers are untouched.

## Implementation Steps

1. **DB read helper**
   - Add `execute_query()` to `FeaturesDatabase` in `src/sidecar/database/db.py`.
   - Update `tests/test_db.py` with read-only coverage.

2. **Layout**
   - Add new `dbc.Card` in `src/layout.py` titled "SQL Explorer".
   - Components:
     - `dbc.Textarea(id="sql-input", rows=5, value="SELECT * FROM raw_features LIMIT 10")`
     - `dbc.Button(id="btn-run-sql", children="Run Query", color="primary", className="mt-2")`
     - `html.Div(id="sql-results", className="mt-3")`  (DataTable injected here)

3. **Callback**
   - `register_sql_explorer_callback(app)` in `src/callbacks.py`:
     - Input: `btn-run-sql.n_clicks`
     - State: `input-folder.value`, `sql-input.value`
     - Output: `sql-results.children`
     - Resolve DB path, call `execute_query()`, build `DataTable`, handle errors with `dbc.Alert`.

4. **Tests**
   - `test_db.py`: test `execute_query` returns correct columns and rows.
   - `test_layout.py`: assert `sql-input`, `btn-run-sql`, `sql-results` IDs exist.

## Testing Plan

- [ ] `python -m pytest tests/test_db.py` passes.
- [ ] `python -m pytest tests/test_layout.py` passes.
- [ ] Manual smoke test:
  1. Run `python app.py`.
  2. Enter a folder that has been scanned (so `features.db` exists).
  3. Type `SELECT * FROM raw_features` and click **Run Query**.
  4. Verify DataTable renders with `id` and `model_output` columns.
  5. Type invalid SQL (`SELECT * FROM missing_table`) and verify red Alert.

## Edge Cases & Risks

- **Empty DB / no folder set**: Show `dbc.Alert("Enter a folder path above before running queries.", color="warning")`.
- **Missing `features.db`**: Show `dbc.Alert("No features.db found for this folder. Scan the folder first.", color="warning")`.
- **Invalid SQL**: Catch `sqlite3.Error`, render `dbc.Alert(str(e), color="danger")`.
- **Large result sets**: DataTable handles pagination; return whatever SQLite gives us and let the browser paginate.
- **Write statements (INSERT/UPDATE/DELETE)**: The UI will execute whatever the user types. This is acceptable for a local SQLite file, but we document the caveat.

## References

- `src/sidecar/database/db.py` — existing minimal SQLite wrapper
- Dash DataTable docs: https://dash.plotly.com/datatable
