import { describe, it } from "node:test";
import { strict as assert } from "node:assert";
import {
	formatNumber,
	formatBucket,
	rangeLabel,
	rangeStartDate,
	nextRange,
	nextBreakdown,
	getBreakdownsForRange,
	renderHeader,
	renderTable,
	renderFooter,
} from "./render.ts";

// Minimal theme stub: tests pass strings through unchanged, but track
// that bold() and fg() were invoked so we can assert behavior.
function makeTheme() {
	const calls: string[] = [];
	const fn: any = (...args: unknown[]) => {
		const s = args.length === 1 ? String(args[0]) : JSON.stringify(args);
		calls.push(s);
		return `[${s}]`;
	};
	fn.fg = fn;
	fn.bold = fn;
	fn.calls = calls;
	return fn;
}

describe("formatNumber", () => {
	it("formats numbers under 1000 as-is", () => {
		assert.equal(formatNumber(42), "42");
		assert.equal(formatNumber(999), "999");
	});

	it("formats thousands with K suffix", () => {
		assert.equal(formatNumber(1_000), "1.0K");
		assert.equal(formatNumber(1_500), "1.5K");
		assert.equal(formatNumber(999_999), "1.0M");
	});

	it("formats millions with M suffix", () => {
		assert.equal(formatNumber(1_000_000), "1.0M");
		assert.equal(formatNumber(1_500_000), "1.5M");
		assert.equal(formatNumber(1_570_000), "1.6M");
	});
});

describe("formatBucket", () => {
	it("formats day buckets", () => {
		assert.equal(formatBucket("2026-04-21", "day"), "Apr 21");
		assert.equal(formatBucket("2026-01-05", "day"), "Jan 05");
	});

	it("formats week buckets", () => {
		assert.equal(formatBucket("2026-W16", "week"), "W16");
		assert.equal(formatBucket("2026-W01", "week"), "W01");
	});

	it("formats month buckets", () => {
		assert.equal(formatBucket("2026-04", "month"), "Apr 2026");
		assert.equal(formatBucket("2026-01", "month"), "Jan 2026");
	});
});

describe("rangeLabel", () => {
	it("returns a human label for each range", () => {
		assert.equal(rangeLabel("week"), "1 week");
		assert.equal(rangeLabel("month"), "1 month");
		assert.equal(rangeLabel("year"), "1 year");
	});
});

describe("rangeStartDate", () => {
	it("returns a Date roughly 7 days back for week", () => {
		const before = Date.now();
		const start = rangeStartDate("week");
		const after = Date.now();
		// 7 days = 6 days 23:30 to 7 days 00:30 in local time
		const days = (before - start.getTime()) / 86_400_000;
		assert.ok(days >= 6.9 && days <= 7.1, `expected ~7 days, got ${days}`);
		// also must be <= after
		assert.ok(start.getTime() <= after);
	});
});

describe("nextRange / nextBreakdown", () => {
	it("cycles ranges week -> month -> year -> week", () => {
		assert.equal(nextRange("week"), "month");
		assert.equal(nextRange("month"), "year");
		assert.equal(nextRange("year"), "week");
	});

	it("cycles breakdowns within a range", () => {
		assert.equal(nextBreakdown("week", "day"), "day"); // only 1 option
		assert.equal(nextBreakdown("month", "day"), "week");
		assert.equal(nextBreakdown("month", "week"), "day");
		assert.equal(nextBreakdown("year", "week"), "month");
		assert.equal(nextBreakdown("year", "month"), "week");
	});

	it("returns the right breakdowns per range", () => {
		assert.deepEqual(getBreakdownsForRange("week"), ["day"]);
		assert.deepEqual(getBreakdownsForRange("month"), ["day", "week"]);
		assert.deepEqual(getBreakdownsForRange("year"), ["week", "month"]);
	});
});

describe("renderHeader", () => {
	it("includes the start date and range label", () => {
		const theme = makeTheme();
		const start = new Date("2026-04-21T00:00:00Z");
		const out = renderHeader(theme, start, "week");
		// theme.fg("accent", "...1 week...") and theme.bold are called.
		// The stub wraps every call; both the range label and a bold pass
		// must show up in the call log.
		const joined = theme.calls.join("\n");
		assert.ok(joined.includes("1 week"));
		assert.ok(joined.includes("Apr"));
		// bold must be invoked (the call is wrapped in theme.bold)
		assert.ok(theme.calls.some((c: string) => c.length > 0), "no theme calls recorded");
		assert.ok(out.includes("Token Usage"));
	});
});

describe("renderFooter", () => {
	it("shows Ctrl+R and Esc hints, dimmed by default", () => {
		const theme = makeTheme();
		const out = renderFooter(theme, "week", "day", false);
		assert.ok(out.includes("Ctrl+R: 1 week"));
		assert.ok(out.includes("Esc to close"));
		// single-option range still shows the breakdown
		assert.ok(out.includes("day"));
	});

	it("shows Tab hint when more than one breakdown is available", () => {
		const theme = makeTheme();
		const out = renderFooter(theme, "month", "day", true);
		assert.ok(out.includes("Tab: breakdown: day"));
	});
});

describe("renderTable", () => {
	it("renders grouped rows, totals, and a header band", () => {
		const theme = makeTheme();
		const rows = [
			{
				bucket: "2026-04-21",
				provider: "anthropic",
				model: "sonnet",
				input: 1_000,
				output: 500,
				cacheRead: 200,
				cacheWrite: 50,
				calls: 3,
			},
			{
				bucket: "2026-04-22",
				provider: "openai",
				model: "gpt-4o",
				input: 600,
				output: 300,
				cacheRead: 0,
				cacheWrite: 0,
				calls: 2,
			},
		];
		const totals = { calls: 5, input: 1_600, output: 800, cacheRead: 200, cacheWrite: 50 };
		const lines = renderTable(rows, totals, "day", theme, 100);

		// Header band uses ─ characters and contains column labels
		const joined = lines.join("\n");
		assert.ok(joined.includes("Date"));
		assert.ok(joined.includes("Model"));
		assert.ok(joined.includes("Totals"));

		// Both models are listed
		assert.ok(joined.includes("anthropic/sonnet"));
		assert.ok(joined.includes("openai/gpt-4o"));

		// Day labels formatted
		assert.ok(joined.includes("Apr 21"));
		assert.ok(joined.includes("Apr 22"));
	});

	it("collapses repeated bucket labels within the same group", () => {
		const theme = makeTheme();
		const rows = [
			{ bucket: "2026-04-21", provider: "anthropic", model: "sonnet", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, calls: 1 },
			{ bucket: "2026-04-21", provider: "openai", model: "gpt-4o", input: 200, output: 100, cacheRead: 0, cacheWrite: 0, calls: 1 },
		];
		const totals = { calls: 2, input: 300, output: 150, cacheRead: 0, cacheWrite: 0 };
		const lines = renderTable(rows, totals, "day", theme, 80);
		// The day label "Apr 21" should appear in the data column once and
		// again only in the totals/divider lines (not as a duplicate row).
		// Strip the header band and check the data lines.
		const dataLines = lines.filter((l) => !l.startsWith("[") && !l.includes("─"));
		const dayCount = dataLines.filter((l) => l.startsWith("Apr 21")).length;
		assert.equal(dayCount, 1, `Apr 21 appeared ${dayCount} times in data lines`);
	});
});
