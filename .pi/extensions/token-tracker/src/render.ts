import { truncateToWidth } from "@earendil-works/pi-tui";

import type { GroupedRow, Totals, Breakdown } from "./db.ts";
export type RenderRow = GroupedRow;
export type RenderTotals = Totals;
export type BreakdownOption = Breakdown;

export type RangeOption = "week" | "month" | "year";

const RANGES: RangeOption[] = ["week", "month", "year"];
const BREAKDOWN_BY_RANGE: Record<RangeOption, BreakdownOption[]> = {
	week: ["day"],
	month: ["day", "week"],
	year: ["week", "month"],
};

export function getBreakdownsForRange(range: RangeOption): BreakdownOption[] {
	return BREAKDOWN_BY_RANGE[range];
}

export function nextRange(current: RangeOption): RangeOption {
	const idx = RANGES.indexOf(current);
	return RANGES[(idx + 1) % RANGES.length];
}

export function nextBreakdown(range: RangeOption, current: BreakdownOption): BreakdownOption {
	const options = BREAKDOWN_BY_RANGE[range];
	const idx = options.indexOf(current);
	return options[(idx + 1) % options.length];
}

export function formatNumber(n: number): string {
	if (n < 1_000) return String(n);
	if (n < 999_500) return (n / 1_000).toFixed(1) + "K";
	return (n / 1_000_000).toFixed(1) + "M";
}

const MONTHS = [
	"Jan", "Feb", "Mar", "Apr", "May", "Jun",
	"Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatBucket(bucket: string, breakdown: BreakdownOption): string {
	if (breakdown === "day") {
		const [y, m, d] = bucket.split("-");
		return `${MONTHS[parseInt(m!, 10) - 1]} ${d}`;
	}
	if (breakdown === "week") {
		const idx = bucket.indexOf("-W");
		return idx >= 0 ? bucket.slice(idx + 1) : bucket;
	}
	const [y, m] = bucket.split("-");
	return `${MONTHS[parseInt(m!, 10) - 1]} ${y}`;
}

export function rangeLabel(range: RangeOption): string {
	switch (range) {
		case "week":
			return "1 week";
		case "month":
			return "1 month";
		case "year":
			return "1 year";
	}
}

export function rangeStartDate(range: RangeOption): Date {
	const now = new Date();
	const d = new Date(now);
	if (range === "week") d.setDate(d.getDate() - 7);
	else if (range === "month") d.setMonth(d.getMonth() - 1);
	else d.setFullYear(d.getFullYear() - 1);
	return d;
}

export function renderHeader(theme: any, startDate: Date, range: RangeOption): string {
	const dateStr = startDate.toLocaleDateString("en-US", {
		month: "short",
		day: "numeric",
		year: "numeric",
	});
	return theme.bold(theme.fg("accent", `Token Usage — since ${dateStr} (${rangeLabel(range)})`));
}

export function renderTable(
	rows: RenderRow[],
	totals: RenderTotals,
	breakdown: BreakdownOption,
	theme: any,
	width: number,
): string[] {
	const lines: string[] = [];

	const colDate = 10;
	const colModel = 28;
	const colNum = 8;
	const sep = "  ";

	const headerCols = [
		"Date".padEnd(colDate),
		"Model".padEnd(colModel),
		"Calls".padStart(colNum),
		"Input".padStart(colNum),
		"Output".padStart(colNum),
		"CacheR".padStart(colNum),
		"CacheW".padStart(colNum),
		"Total".padStart(colNum),
	];
	const headerLine = headerCols.join(sep);
	lines.push(theme.fg("dim", "─".repeat(width)));
	lines.push(theme.fg("dim", truncateToWidth(headerLine, width)));
	lines.push(theme.fg("dim", "─".repeat(width)));

	let lastBucket = "";
	for (let i = 0; i < rows.length; i++) {
		const row = rows[i]!;
		const dateLabel = row.bucket === lastBucket ? "" : formatBucket(row.bucket, breakdown);
		lastBucket = row.bucket;

		const modelLabel = `${row.provider}/${row.model}`;
		const total = row.input + row.output + row.cacheRead + row.cacheWrite;
		const line = [
			dateLabel.padEnd(colDate),
			truncateToWidth(modelLabel, colModel).padEnd(colModel),
			String(row.calls).padStart(colNum),
			formatNumber(row.input).padStart(colNum),
			formatNumber(row.output).padStart(colNum),
			formatNumber(row.cacheRead).padStart(colNum),
			formatNumber(row.cacheWrite).padStart(colNum),
			formatNumber(total).padStart(colNum),
		].join(sep);

		lines.push(truncateToWidth(line, width));
		if (i < rows.length - 1 && rows[i + 1]?.bucket !== row.bucket) {
			lines.push(theme.fg("dim", "·".repeat(Math.min(width, 60))));
		}
	}

	lines.push(theme.fg("dim", "─".repeat(width)));
	const grandTotal = totals.input + totals.output + totals.cacheRead + totals.cacheWrite;
	const totalLine = [
		"Totals".padEnd(colDate),
		"".padEnd(colModel),
		String(totals.calls).padStart(colNum),
		formatNumber(totals.input).padStart(colNum),
		formatNumber(totals.output).padStart(colNum),
		formatNumber(totals.cacheRead).padStart(colNum),
		formatNumber(totals.cacheWrite).padStart(colNum),
		formatNumber(grandTotal).padStart(colNum),
	].join(sep);
	lines.push(theme.bold(truncateToWidth(totalLine, width)));

	return lines;
}

export function renderFooter(
	theme: any,
	range: RangeOption,
	breakdown: BreakdownOption,
	canTab: boolean,
): string {
	const rangePart = `Ctrl+R: ${rangeLabel(range)}`;
	const tabPart = canTab
		? `Tab: breakdown: ${breakdown}`
		: theme.fg("dim", `breakdown: ${breakdown}`);
	const escPart = "Esc to close";
	return theme.fg("dim", `${rangePart}    ${tabPart}    ${escPart}`);
}
