import { DatabaseSync } from "node:sqlite";
import { mkdirSync, renameSync, unlinkSync } from "node:fs";
import { dirname } from "node:path";

export interface UsageInsert {
	provider: string;
	model: string;
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	source: "agent" | "extension";
	cwd: string | null;
	ts?: number; // defaults to Date.now()
}

export interface UsageRow {
	ts: number;
	provider: string;
	model: string;
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	calls: number;
	source: string;
	cwd: string | null;
}

export interface GroupedRow {
	bucket: string;
	provider: string;
	model: string;
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	calls: number;
}

export interface Totals {
	calls: number;
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
}

export type Breakdown = "day" | "week" | "month";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS usage (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  provider    TEXT NOT NULL,
  model       TEXT NOT NULL,
  input       INTEGER NOT NULL,
  output      INTEGER NOT NULL,
  cache_read  INTEGER NOT NULL DEFAULT 0,
  cache_write INTEGER NOT NULL DEFAULT 0,
  calls       INTEGER NOT NULL DEFAULT 1,
  source      TEXT NOT NULL DEFAULT 'agent',
  cwd         TEXT
);
CREATE INDEX IF NOT EXISTS idx_ts ON usage(ts);
CREATE INDEX IF NOT EXISTS idx_provider_model ON usage(provider, model);
`;

function bucketExpr(breakdown: Breakdown): string {
	switch (breakdown) {
		case "day":
			// strftime on unixepoch seconds in UTC. Buckets in UTC so the
			// grouping is deterministic across timezone changes.
			return `strftime('%Y-%m-%d', ts / 1000, 'unixepoch')`;
		case "week":
			return `strftime('%Y-W%W', ts / 1000, 'unixepoch')`;
		case "month":
			return `strftime('%Y-%m', ts / 1000, 'unixepoch')`;
	}
}

function rowsFrom<T>(result: unknown): T[] {
	// node:sqlite returns an array of objects with a null prototype.
	// Clone them so they compare as plain objects via deep-equal helpers.
	if (!Array.isArray(result)) return [];
	return result.map((row) => ({ ...(row as object) })) as T[];
}

function rowFrom<T>(result: unknown): T {
	if (!result || typeof result !== "object") {
		throw new Error("Expected single row from query");
	}
	return { ...(result as object) } as T;
}

export class TokenDb {
	private db: DatabaseSync;

	constructor(dbPath: string) {
		mkdirSync(dirname(dbPath), { recursive: true });
		this.db = this.openOrRecreate(dbPath);
		// WAL is supported on node:sqlite via the journal_mode pragma.
		this.db.exec("PRAGMA journal_mode = WAL");
		this.db.exec("PRAGMA synchronous = FULL");
		this.db.exec(SCHEMA);
	}

	private openOrRecreate(dbPath: string): DatabaseSync {
		try {
			return new DatabaseSync(dbPath);
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			if (msg.includes("malformed")) {
				const corruptedPath = `${dbPath}.corrupted-${Date.now()}`;
				renameSync(dbPath, corruptedPath);
				// Clean up leftover WAL files so SQLite starts fresh
				try { unlinkSync(`${dbPath}-wal`); } catch {}
				try { unlinkSync(`${dbPath}-shm`); } catch {}
				return new DatabaseSync(dbPath);
			}
			throw err;
		}
	}

	insert(row: UsageInsert): void {
		const ts = row.ts ?? Date.now();
		this.db
			.prepare(
				`INSERT INTO usage (ts, provider, model, input, output, cache_read, cache_write, source, cwd)
				 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			)
			.run(
				ts,
				row.provider,
				row.model,
				row.input,
				row.output,
				row.cacheRead,
				row.cacheWrite,
				row.source,
				row.cwd,
			);
	}

	query(from: Date, to: Date, cwd?: string): UsageRow[] {
		const sql = cwd
			? `SELECT ts, provider, model, input, output, cache_read AS cacheRead, cache_write AS cacheWrite, calls, source, cwd
			   FROM usage
			   WHERE ts >= ? AND ts < ? AND cwd = ?
			   ORDER BY ts`
			: `SELECT ts, provider, model, input, output, cache_read AS cacheRead, cache_write AS cacheWrite, calls, source, cwd
			   FROM usage
			   WHERE ts >= ? AND ts < ?
			   ORDER BY ts`;
		const params = cwd ? [from.getTime(), to.getTime(), cwd] : [from.getTime(), to.getTime()];
		return rowsFrom<UsageRow>(this.db.prepare(sql).all(...params));
	}

	queryGrouped(from: Date, to: Date, breakdown: Breakdown, cwd?: string): GroupedRow[] {
		const bucket = bucketExpr(breakdown);
		const cwdClause = cwd ? " AND cwd = ?" : "";
		const params: (number | string)[] = cwd
			? [from.getTime(), to.getTime(), cwd]
			: [from.getTime(), to.getTime()];

		const sql = `
			SELECT
				${bucket} AS bucket,
				provider,
				model,
				SUM(input) AS input,
				SUM(output) AS output,
				SUM(cache_read) AS cacheRead,
				SUM(cache_write) AS cacheWrite,
				SUM(calls) AS calls
			FROM usage
			WHERE ts >= ? AND ts < ?${cwdClause}
			GROUP BY bucket, provider, model
			ORDER BY bucket ASC, provider ASC, model ASC
		`;
		return rowsFrom<GroupedRow>(this.db.prepare(sql).all(...params));
	}

	totals(from: Date, to: Date, cwd?: string): Totals {
		const cwdClause = cwd ? " AND cwd = ?" : "";
		const params: (number | string)[] = cwd
			? [from.getTime(), to.getTime(), cwd]
			: [from.getTime(), to.getTime()];

		const sql = `
			SELECT
				COALESCE(SUM(calls), 0) AS calls,
				COALESCE(SUM(input), 0) AS input,
				COALESCE(SUM(output), 0) AS output,
				COALESCE(SUM(cache_read), 0) AS cacheRead,
				COALESCE(SUM(cache_write), 0) AS cacheWrite
			FROM usage
			WHERE ts >= ? AND ts < ?${cwdClause}
		`;
		const result = this.db.prepare(sql).get(...params);
		return rowFrom<Totals>(result);
	}

	close(): void {
		try {
			this.db.exec("PRAGMA wal_checkpoint(TRUNCATE)");
		} catch {}
		this.db.close();
	}
}
