/**
 * Implement Plan Extension
 *
 * /implement command that:
 * 1. Lists available plan files from plan/ directory (excluding plan/implemented/)
 * 2. Loads the selected plan and sends it to the agent for implementation
 * 3. After implementation, moves the plan to plan/implemented/ with timestamp
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFile, mkdir, rename } from "node:fs/promises";
import { join, basename, dirname, extname } from "node:path";
import { readdirSync, existsSync } from "node:fs";

const PLAN_DIR = "plan";
const IMPLEMENTED_DIR = "plan/implemented";

function timestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function listPlans(cwd: string): string[] {
  const planDir = join(cwd, PLAN_DIR);
  if (!existsSync(planDir)) return [];

  try {
    return readdirSync(planDir).filter(
      (f) => f.endsWith(".md"),
    );
  } catch {
    return [];
  }
}

export default function implementPlanExtension(pi: ExtensionAPI) {
  let currentPlanPath: string | null = null;
  let currentPlanName: string | null = null;

  function persistState(): void {
    pi.appendEntry("implement-plan", {
      planPath: currentPlanPath,
      planName: currentPlanName,
    });
  }

  async function moveToImplemented(
    planPath: string,
    cwd: string,
  ): Promise<string | null> {
    const implementedDir = join(cwd, IMPLEMENTED_DIR);
    await mkdir(implementedDir, { recursive: true });

    const name = basename(planPath, extname(planPath));
    const ts = timestamp().replace(/:/g, "");
    const newName = `${name}-done-${ts}.md`;
    const newPath = join(implementedDir, newName);

    await rename(planPath, newPath);
    return newPath;
  }

  // /implement - pick a plan and start implementing
  pi.registerCommand("implement", {
    description: "Select a plan and start implementing it. Pass a name to match in plan/ (e.g. removing-control-tab) or a relative path (e.g. plan/show-funds.md).",
    handler: async (_args, ctx) => {
      const requested = _args?.trim();
      let planPath: string;
      let selectedPlan: string;

      if (requested) {
        // If the argument looks like a path (contains / or .md), resolve it relative to cwd
        if (requested.includes("/") || requested.endsWith(".md")) {
          const resolved = join(ctx.cwd, requested);
          if (!existsSync(resolved)) {
            ctx.ui.notify(
              `Plan file not found: ${requested}`,
              "warning",
            );
            return;
          }
          planPath = resolved;
          selectedPlan = basename(resolved);
        } else {
          // Otherwise, match against plans in the plan/ directory
          const plans = listPlans(ctx.cwd);

          if (plans.length === 0) {
            ctx.ui.notify(
              'No plans found in plan/. Use /plan to create one first.',
              "warning",
            );
            return;
          }

          const match = plans.find(
            (p) =>
              p.toLowerCase().includes(requested.toLowerCase()) ||
              p.replace(/\.md$/, "").toLowerCase() ===
                requested.toLowerCase().replace(/\.md$/, ""),
          );
          if (!match) {
            ctx.ui.notify(
              `No plan matching "${requested}". Use /implement without args to pick.`,
              "warning",
            );
            return;
          }
          planPath = join(ctx.cwd, PLAN_DIR, match);
          selectedPlan = match;
        }
      } else {
        // Show selection dialog
        const plans = listPlans(ctx.cwd);

        if (plans.length === 0) {
          ctx.ui.notify(
            'No plans found in plan/. Use /plan to create one first.',
            "warning",
          );
          return;
        }

        const choice = await ctx.ui.select(
          "Pick a plan to implement:",
          plans,
        );
        if (!choice) {
          ctx.ui.notify("No plan selected.", "info");
          return;
        }
        selectedPlan = choice;
        planPath = join(ctx.cwd, PLAN_DIR, selectedPlan);
      }

      try {
        const content = await readFile(planPath, "utf-8");

        // Store current plan
        currentPlanPath = planPath;
        currentPlanName = selectedPlan;
        persistState();

        ctx.ui.notify(
          `Implementing: ${selectedPlan}`,
          "info",
        );

        // Send the plan to the agent for implementation
        pi.sendUserMessage(
          `Implement the following plan. After completing all steps, check whether AGENTS.md and README.md need updates to reflect the changes, and update them if necessary. Then let me know so I can mark it as done.\n\n${content}`,
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        ctx.ui.notify(`Failed to read plan: ${message}`, "error");
      }
    },
  });

  // /implemented - mark current plan as done and move to plan/implemented/
  pi.registerCommand("implemented", {
    description:
      "Mark the current plan as implemented (moves to plan/implemented/)",
    handler: async (_args, ctx) => {
      if (!currentPlanPath) {
        ctx.ui.notify(
          "No plan is currently being implemented. Use /implement first.",
          "warning",
        );
        return;
      }

      if (!existsSync(currentPlanPath)) {
        ctx.ui.notify(
          `Plan file no longer exists: ${currentPlanPath}`,
          "error",
        );
        currentPlanPath = null;
        currentPlanName = null;
        persistState();
        return;
      }

      const movedPath = await moveToImplemented(currentPlanPath, ctx.cwd);

      if (movedPath) {
        ctx.ui.notify(
          `Plan implemented and archived: implemented/${basename(movedPath)}`,
          "success",
        );
      }

      currentPlanPath = null;
      currentPlanName = null;
      persistState();
    },
  });

  // Prompt to mark as done after agent finishes
  pi.on("agent_end", async (event, ctx) => {
    if (!currentPlanPath || !ctx.hasUI) return;

    // Check if the plan file still exists (it might have been moved already)
    if (!existsSync(currentPlanPath)) {
      currentPlanPath = null;
      currentPlanName = null;
      persistState();
      return;
    }

    const done = await ctx.ui.confirm(
      "Plan Implemented?",
      `Is "${currentPlanName}" fully implemented? This will move it to plan/implemented/.`,
    );

    if (done) {
      const movedPath = await moveToImplemented(currentPlanPath, ctx.cwd);

      if (movedPath) {
        ctx.ui.notify(
          `Plan archived: implemented/${basename(movedPath)}`,
          "success",
        );
      }

      currentPlanPath = null;
      currentPlanName = null;
      persistState();
    } else {
      ctx.ui.notify(
        `Plan "${currentPlanName}" still in progress. Use /implemented when done.`,
        "info",
      );
    }
  });

  // Restore state on session resume
  pi.on("session_start", async (_event, ctx) => {
    const entries = ctx.sessionManager.getEntries();

    const implEntry = entries
      .filter(
        (e: { type: string; customType?: string }) =>
          e.type === "custom" && e.customType === "implement-plan",
      )
      .pop() as
      | { data?: { planPath?: string | null; planName?: string | null } }
      | undefined;

    if (implEntry?.data) {
      currentPlanPath = implEntry.data.planPath ?? null;
      currentPlanName = implEntry.data.planName ?? null;
    }

    if (currentPlanPath) {
      ctx.ui.notify(
        `Resumed implementation of: ${currentPlanName}`,
        "info",
      );
    }
  });
}
