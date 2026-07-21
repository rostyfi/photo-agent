/**
 * /git Extension
 *
 * Commits all changes. Uses Mistral for auto-generated messages, then restores
 * the original model.
 *
 * Usage:
 *   /git                      - Auto-commit: stage all, use Mistral to generate
 *                               commit message and commit, restore model after
 *   /git "message"            - Stage all and commit with given message
 *                               (no model switch)
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MISTRAL_MODEL = {
  provider: "mistral",
  id: "devstral-small-2507",
} as const;

export default function (pi: ExtensionAPI) {
  let originalModel: { provider: string; id: string } | null = null;
  let pendingRestore = false;

  pi.registerCommand("git", {
    description:
      "Stage and commit all changes. Without args: uses Mistral to auto-generate message and commits. With args: commits with given message.",
    handler: async (args, ctx) => {
      const { stdout: status, code: statusCode } = await pi.exec("git", [
        "status",
        "--porcelain",
      ]);

      if (statusCode !== 0) {
        ctx.ui.notify("Not a git repository.", "error");
        return;
      }

      if (status.trim().length === 0) {
        ctx.ui.notify("Nothing to commit — working tree clean.", "info");
        return;
      }

      const message = args?.trim();

      if (message) {
        // Explicit message: commit directly (no model switch)
        const { code: addCode } = await pi.exec("git", ["add", "."]);
        if (addCode !== 0) {
          ctx.ui.notify("Failed to stage files.", "error");
          return;
        }

        const { stdout: commitOut, code: commitCode } = await pi.exec("git", [
          "commit",
          "-m",
          message,
        ]);

        if (commitCode !== 0) {
          ctx.ui.notify(`Commit failed: ${commitOut.trim()}`, "error");
          return;
        }

        ctx.ui.notify("Committed successfully.", "success");

        const { code: codeRefreshCode } = await pi.exec("code", [
          "--reuse-window",
          ctx.cwd,
        ]);
        if (codeRefreshCode === 0) {
          ctx.ui.notify("VS Code workspace refreshed.", "info");
        }
      } else {
        // Auto mode: switch to Mistral, let it generate message and commit
        const current = ctx.model;
        if (
          current &&
          !(
            current.provider === MISTRAL_MODEL.provider &&
            current.id === MISTRAL_MODEL.id
          )
        ) {
          originalModel = {
            provider: current.provider,
            id: current.id,
          };
        }

        const mistralModel = ctx.modelRegistry.find(
          MISTRAL_MODEL.provider,
          MISTRAL_MODEL.id,
        );
        if (!mistralModel) {
          ctx.ui.notify(
            `Model "${MISTRAL_MODEL.id}" not found.`,
            "error",
          );
          originalModel = null;
          return;
        }

        const switched = await pi.setModel(mistralModel);
        if (!switched) {
          ctx.ui.notify("Failed to switch to Mistral.", "error");
          originalModel = null;
          return;
        }

        pendingRestore = true;
        ctx.ui.notify(
          `Switched to ${MISTRAL_MODEL.id} — will restore ${originalModel?.id ?? "unchanged"} after.`,
          "info",
        );

        await ctx.waitForIdle();

        // Stage and get diff for the commit message prompt
        await pi.exec("git", ["add", "."]);
        const { stdout: diff } = await pi.exec("git", [
          "diff",
          "--staged",
          "--stat",
        ]);

        pi.sendUserMessage(
          `Stage all changes (already staged) and commit them with a concise, descriptive commit message. The staged changes summary:\n\n${diff}`,
        );
      }
    },
  });

  // Restore original model after the Mistral auto-commit turn completes
  pi.on("agent_end", async (_event, ctx) => {
    if (!pendingRestore || !originalModel) return;
    pendingRestore = false;

    const restore = ctx.modelRegistry.find(
      originalModel.provider,
      originalModel.id,
    );
    if (restore) {
      await pi.setModel(restore);
      ctx.ui.notify(`Restored model: ${originalModel.id}`, "info");
    }

    originalModel = null;
  });
}
