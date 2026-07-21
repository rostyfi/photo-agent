import { describe, it, beforeEach, afterEach } from "node:test";
import { strict as assert } from "node:assert";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { TokenDb } from "./db.ts";

const TEST_DIR = join(process.cwd(), ".test-db");

let db: TokenDb;

beforeEach(() => {
	mkdirSync(TEST_DIR, { recursive: true });
	db = new TokenDb(join(TEST_DIR, "test.db"));
});

afterEach(() => {
	db.close();
	rmSync(TEST_DIR, { recursive: true, force: true });
});

describe("TokenDb", () => {
	it("inserts and queries a row", () => {
		db.insert({
			provider: "anthropic",
			model: "claude-sonnet-4-20250514",
			input: 1000,
			output: 500,
			cacheRead: 200,
			cacheWrite: 50,
			source: "agent",
			cwd: "/home/user/project",
		});

		const rows = db.query(new Date("2020-01-01"), new Date("2030-01-01"));
		assert.equal(rows.length, 1);
		assert.deepEqual(rows[0], {
			ts: rows[0]!.ts,
			provider: "anthropic",
			model: "claude-sonnet-4-20250514",
			input: 1000,
			output: 500,
			cacheRead: 200,
			cacheWrite: 50,
			calls: 1,
			source: "agent",
			cwd: "/home/user/project",
		});
	});

	it("groups by day", () => {
		const day1 = new Date("2026-04-21T10:00:00Z").getTime();
		const day2 = new Date("2026-04-22T10:00:00Z").getTime();

		db.insert({ provider: "anthropic", model: "sonnet", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: day1 });
		db.insert({ provider: "anthropic", model: "sonnet", input: 200, output: 50, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: day1 });
		db.insert({ provider: "anthropic", model: "sonnet", input: 300, output: 150, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: day2 });

		const groups = db.queryGrouped(
			new Date("2026-04-21"), new Date("2026-04-23"), "day",
		);

		// same model on same day merges into 1 row per group
		assert.equal(groups.length, 2);
		assert.equal(groups[0]!.bucket, "2026-04-21");
		assert.equal(groups[0]!.provider, "anthropic");
		assert.equal(groups[0]!.input, 300);
		assert.equal(groups[0]!.output, 100);
		assert.equal(groups[1]!.bucket, "2026-04-22");
		assert.equal(groups[1]!.input, 300);
		assert.equal(groups[1]!.output, 150);
	});

	it("groups by week", () => {
		// Apr 19 (Sun) and Apr 20 (Mon) are in different weeks
		const sun = new Date("2026-04-19T12:00:00Z").getTime();
		const mon = new Date("2026-04-20T12:00:00Z").getTime();

		db.insert({ provider: "anthropic", model: "sonnet", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: sun });
		db.insert({ provider: "anthropic", model: "sonnet", input: 200, output: 100, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: mon });

		const groups = db.queryGrouped(
			new Date("2026-04-19"), new Date("2026-04-21"), "week",
		);

		assert.equal(groups.length, 2); // two different weeks
	});

	it("groups by month", () => {
		const mar = new Date("2026-03-15T12:00:00Z").getTime();
		const apr = new Date("2026-04-15T12:00:00Z").getTime();

		db.insert({ provider: "anthropic", model: "sonnet", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: mar });
		db.insert({ provider: "anthropic", model: "sonnet", input: 200, output: 100, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: null, ts: apr });

		const groups = db.queryGrouped(
			new Date("2026-03-01"), new Date("2026-05-01"), "month",
		);

		assert.equal(groups.length, 2);
		assert.equal(groups[0]!.bucket, "2026-03");
		assert.equal(groups[1]!.bucket, "2026-04");
	});

	it("returns totals for a range", () => {
		const ts = new Date("2026-04-21T10:00:00Z").getTime();
		db.insert({ provider: "anthropic", model: "sonnet", input: 1000, output: 500, cacheRead: 200, cacheWrite: 50, source: "agent", cwd: null, ts });
		db.insert({ provider: "openai", model: "gpt-4o", input: 500, output: 200, cacheRead: 0, cacheWrite: 0, source: "extension", cwd: null, ts });

		const totals = db.totals(new Date("2026-04-01"), new Date("2026-05-01"));
		assert.deepEqual(totals, {
			calls: 2,
			input: 1500,
			output: 700,
			cacheRead: 200,
			cacheWrite: 50,
		});
	});

	it("filters by cwd when provided", () => {
		const ts = new Date("2026-04-21T10:00:00Z").getTime();
		db.insert({ provider: "anthropic", model: "sonnet", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: "/project/a", ts });
		db.insert({ provider: "anthropic", model: "sonnet", input: 200, output: 100, cacheRead: 0, cacheWrite: 0, source: "agent", cwd: "/project/b", ts });

		const rows = db.query(new Date("2020-01-01"), new Date("2030-01-01"), "/project/a");
		assert.equal(rows.length, 1);
		assert.equal(rows[0]!.input, 100);
	});

	it("handles empty query results", () => {
		const from = new Date("2026-01-01");
		const to = new Date("2026-01-02");

		const rows = db.query(from, to);
		assert.deepEqual(rows, []);

		const groups = db.queryGrouped(from, to, "day");
		assert.deepEqual(groups, []);

		const totals = db.totals(from, to);
		assert.deepEqual(totals, {
			calls: 0,
			input: 0,
			output: 0,
			cacheRead: 0,
			cacheWrite: 0,
		});
	});
});
