/**
 * pi-token-tracker
 *
 * A pi extension that tracks model token usage across the main agent loop
 * and extension out-of-band calls, stored in SQLite, displayed via a
 * `/token-usage` command with configurable time ranges and breakdowns.
 *
 * Listens to `message_end` for main-loop assistant usage and the shared
 * `pi.events` bus for `model:usage` events from other extensions.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { matchesKey, Key } from "@earendil-works/pi-tui";
import { join } from "node:path";
import { TokenDb } from "./db.ts";
import {
	type RangeOption,
	type BreakdownOption,
	getBreakdownsForRange,
	nextRange,
	nextBreakdown,
	rangeStartDate,
	rangeLabel,
	renderHeader,
	renderTable,
	renderFooter,
} from "./render.ts";
import type { Breakdown } from "./db.ts";

// Resolve DB path: honor $PI_TOKEN_DB for tests / power users, otherwise
// place the SQLite file in the standard pi agent data dir.
function defaultDbPath(): string {
	const envHome = process.env.HOME ?? process.env.USERPROFILE ?? "~";
	return join(envHome, ".pi", "agent", "data", "token-usage.db");
}

const DB_PATH = process.env.PI_TOKEN_DB ?? defaultDbPath();

/** Payload other extensions emit onto `pi.events` to report OOB usage. */
export interface ModelUsageEvent {
	provider: string;
	model: string;
	input: number;
	output: number;
	cacheRead?: number;
	cacheWrite?: number;
}

export default function (pi: ExtensionAPI) {
	const db = new TokenDb(DB_PATH);

	// --- Main agent loop: track assistant messages ---
	pi.on("message_end", async (event, ctx) => {
		const msg = event.message;
		if (msg.role !== "assistant") return;

		const usage = msg.usage;
		db.insert({
			provider: msg.provider,
			model: msg.model,
			input: usage.input ?? 0,
			output: usage.output ?? 0,
			cacheRead: usage.cacheRead ?? 0,
			cacheWrite: usage.cacheWrite ?? 0,
			source: "agent",
			cwd: ctx.cwd,
		});
	});

	// --- Extension out-of-band calls ---
	// The EventBus channel is untyped (`data: unknown`), so we narrow it
	// defensively before inserting.
	pi.events.on("model:usage", ((raw: unknown) => {
		const data = raw as Partial<ModelUsageEvent> | null | undefined;
		if (!data || typeof data !== "object") return;
		const provider = typeof data.provider === "string" ? data.provider : "unknown";
		const model = typeof data.model === "string" ? data.model : "unknown";
		const input = Number.isFinite(data.input) ? (data.input as number) : 0;
		const output = Number.isFinite(data.output) ? (data.output as number) : 0;
		const cacheRead = Number.isFinite(data.cacheRead) ? (data.cacheRead as number) : 0;
		const cacheWrite = Number.isFinite(data.cacheWrite) ? (data.cacheWrite as number) : 0;
		db.insert({
			provider,
			model,
			input,
			output,
			cacheRead,
			cacheWrite,
			source: "extension",
			cwd: process.cwd(),
		});
	}) as (data: unknown) => void);

	// --- Cleanup on session shutdown ---
	pi.on("session_shutdown", () => {
		db.close();
	});

	// --- /token-usage command ---
	pi.registerCommand("token-usage", {
		description:
			"Show token usage breakdown by model with configurable time ranges",
		handler: async (_args, ctx) => {
			if (!ctx.hasUI) {
				ctx.ui.notify("Token usage requires interactive mode", "warning");
				return;
			}

			let range: RangeOption = "week";
			let breakdown: BreakdownOption = getBreakdownsForRange(range)[0]!;

			await ctx.ui.custom<void>((tui, theme, _kb, done) => {
				const renderView = (): string[] => {
					const lines: string[] = [];

					const startDate = rangeStartDate(range);
					const now = new Date();
					const rows = db.queryGrouped(
						startDate,
						now,
						breakdown as Breakdown,
						undefined,
					);
					const totals = db.totals(startDate, now);

					lines.push(renderHeader(theme, startDate, range));
					lines.push(
						...renderTable(
							rows.map((r) => ({ ...r })),
							totals,
							breakdown as Breakdown,
							theme,
							process.stdout.columns ?? 80,
						),
					);
					lines.push("");
					lines.push(
						renderFooter(
							theme,
							range,
							breakdown,
							getBreakdownsForRange(range).length > 1,
						),
					);

					return lines;
				};

				let cachedLines: string[] = renderView();

				return {
					render(_width: number): string[] {
						return cachedLines;
					},
					invalidate(): void {
						cachedLines = renderView();
					},
					handleInput(data: string): void {
						if (matchesKey(data, "escape") || data === "q") {
							done();
						} else if (matchesKey(data, Key.ctrl("r"))) {
							range = nextRange(range);
							breakdown = getBreakdownsForRange(range)[0]!;
							cachedLines = renderView();
							tui.requestRender();
						} else if (matchesKey(data, Key.tab)) {
							breakdown = nextBreakdown(range, breakdown);
							cachedLines = renderView();
							tui.requestRender();
						}
					},
				};
			});
		},
	});
}
