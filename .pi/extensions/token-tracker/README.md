# pi-token-tracker

A [pi](https://github.com/mariozechner/pi-coding-agent) extension that tracks model
token usage across the main agent loop and extension out-of-band calls, stored
in SQLite, displayed via a `/token-usage` command with configurable time ranges
and breakdowns.

Ported from [`AshesToAgents/pi-token-tracker`](https://github.com/AshesToAgents/pi-token-tracker)
to the `@earendil-works/pi-*` package set and adapted to Node 22's built-in
`node:sqlite` so the extension has zero npm runtime dependencies.

## Install

The extension is auto-discovered when placed in `.pi/extensions/`:

```
.pi/extensions/token-tracker/
├── package.json     # declares entry via `pi.extensions`
├── tsconfig.json
├── src/
│   ├── index.ts     # extension factory (default export)
│   ├── db.ts        # SQLite layer (uses node:sqlite)
│   ├── render.ts    # TUI rendering
│   ├── db.test.ts
│   └── render.test.ts
└── scripts/
    └── smoke.cjs    # jiti-based smoke test
```

No `npm install` is required at runtime — jiti loads TypeScript directly and
`node:sqlite` ships with Node 22.5+. Dev-only `npm install` is only needed to
run `npm run typecheck` / `npm test`.

To install the dev tools:

```bash
cd .pi/extensions/token-tracker
npm install --no-save typescript@5.9 @types/node@22
```

## What's Included

| Type | Name | Description |
|------|------|-------------|
| Extension | — | Listens to `message_end` and the shared `pi.events` bus to record token usage |
| Command | `/token-usage` | Interactive display with time range and breakdown controls |

## Usage

### `/token-usage`

Run `/token-usage` in the pi TUI. Use:

- **Ctrl+R** — cycle time range (week → month → year)
- **Tab** — cycle breakdown granularity (day/week/month depending on range)
- **Esc** / **q** — close the overlay

### Data sources

- **Main agent loop** — every assistant message that has usage data is
  recorded automatically via the `message_end` event.
- **Extension out-of-band calls** — other extensions can report usage
  via the shared event bus:

```typescript
pi.events.emit("model:usage", {
  provider: "anthropic",
  model: "claude-sonnet-4-20250514",
  input: 1234,
  output: 567,
  cacheRead: 800,    // optional, defaults to 0
  cacheWrite: 0,     // optional, defaults to 0
});
```

## Storage

By default the SQLite database is created at:

```
$HOME/.pi/agent/data/token-usage.db
```

Set the `PI_TOKEN_DB` environment variable to override the path (used by the
test suite to keep test data out of the live DB).

Schema:

```sql
CREATE TABLE usage (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,      -- unix ms
  provider    TEXT    NOT NULL,
  model       TEXT    NOT NULL,
  input       INTEGER NOT NULL,
  output      INTEGER NOT NULL,
  cache_read  INTEGER NOT NULL DEFAULT 0,
  cache_write INTEGER NOT NULL DEFAULT 0,
  calls       INTEGER NOT NULL DEFAULT 1,
  source      TEXT    NOT NULL DEFAULT 'agent',  -- 'agent' | 'extension'
  cwd         TEXT
);
```

The schema is created on first open with `CREATE TABLE IF NOT EXISTS`, so the
extension is safe to enable and disable without manual setup.

## Development

```bash
cd .pi/extensions/token-tracker

# Type-check the extension against the installed pi types
npm run typecheck

# Run the unit tests (db + render layers)
npm test

# End-to-end smoke: load the extension via jiti, exercise all
# registered handlers, and verify rows land in the DB
npm run smoke
```

The unit tests use Node's built-in `node:test` runner and the strip-types
loader, so no test framework needs to be installed.

## Differences from the upstream reference

| | Upstream (AshesToAgents) | This port |
|---|---|---|
| Package names | `@mariozechner/pi-*` | `@earendil-works/pi-*` |
| SQLite driver | `better-sqlite3` (native) | `node:sqlite` (built-in) |
| Test runner | `vitest` | `node:test` (built-in) |
| TS imports | `.js` | `.ts` (Node 22 strip-types) |

Functionality, schema, command keys, and the `model:usage` event contract are
preserved.

## License

MIT
