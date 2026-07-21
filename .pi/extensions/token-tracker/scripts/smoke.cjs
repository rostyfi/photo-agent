// Smoke test: load the extension via jiti (the same loader pi uses) and
// ensure the default export factory can be invoked without errors.
const path = require("node:path");
const { createJiti } = require("jiti");

async function main() {
	const jiti = createJiti(__filename, { interopDefault: true, esmResolve: true });
	const srcDir = path.resolve(__dirname, "..", "src");
	const mod = jiti(path.join(srcDir, "index.ts"));

	// Minimal pi stub. We only need to record the registered handlers and
	// verify the factory wires them up.
	const handlers = {};
	const eventBusHandlers = {};

	const pi = {
		on(event, handler) {
			(handlers[event] ??= []).push(handler);
		},
		registerCommand(name, _opts) {
			if (name !== "token-usage") {
				throw new Error(`Unexpected command name: ${name}`);
			}
		},
		events: {
			on(channel, handler) {
				(eventBusHandlers[channel] ??= []).push(handler);
				return () => {};
			},
		},
	};

	mod.default(pi);

	const expected = ["message_end", "session_shutdown"];
	for (const e of expected) {
		if (!handlers[e] || handlers[e].length !== 1) {
			throw new Error(`${e} handler not registered`);
		}
	}

	if (!eventBusHandlers["model:usage"] || eventBusHandlers["model:usage"].length !== 1) {
		throw new Error("model:usage event handler not registered");
	}

	// Test that message_end can be invoked without throwing.
	const fakeMsg = {
		role: "assistant",
		provider: "anthropic",
		model: "smoke",
		usage: { input: 5, output: 3, cacheRead: 1, cacheWrite: 0, totalTokens: 9, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
		timestamp: Date.now(),
		content: [],
		api: "anthropic-messages",
		stopReason: "stop",
	};

	const ctx = { cwd: "/tmp" };
	await handlers.message_end[0]({ message: fakeMsg }, ctx);

	// Verify the row landed. Open a fresh DB handle to read.
	const TokenDb = jiti(path.join(srcDir, "db.ts")).TokenDb;
	const dbPath = process.env.PI_TOKEN_DB || path.join(process.env.HOME || "/tmp", ".pi/agent/data/token-usage.db");
	const db = new TokenDb(dbPath);
	const rows = db.query(new Date(Date.now() - 60_000), new Date(Date.now() + 60_000));
	const smoke = rows.find((r) => r.model === "smoke" && r.input === 5);
	if (!smoke) {
		db.close();
		throw new Error("smoke row not persisted");
	}

	// Test model:usage event handler
	eventBusHandlers["model:usage"][0]({
		provider: "openai",
		model: "smoke-oob",
		input: 7,
		output: 11,
	});

	const rows2 = db.query(new Date(Date.now() - 60_000), new Date(Date.now() + 60_000));
	const oob = rows2.find((r) => r.model === "smoke-oob" && r.source === "extension");
	if (!oob) {
		db.close();
		throw new Error("OOB row not persisted");
	}

	// Trigger session_shutdown to close the DB cleanly
	await handlers.session_shutdown[0]({}, {});

	console.log("smoke: extension factory wired all required handlers and persisted rows");
}

main().catch((err) => {
	console.error("smoke FAILED:", err);
	process.exit(1);
});
