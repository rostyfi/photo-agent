/**
 * Plan Feature Extension
 *
 * /plan command that:
 * 1. Prompts for a feature name
 * 2. Creates a plan/<feature-name>.md file with a plan template
 * 3. Opens the plan file in VS Code
 * 4. Opens the plan content in the pi editor
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { existsSync } from "node:fs";

const PLAN_DIR = "plan";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function generatePlanTemplate(featureName: string, timestamp: string): string {
  return `# ${featureName}

> **Status:** Draft  
> **Created:** ${timestamp}

## Overview

<!-- Briefly describe what this feature does and why it's needed -->

## Motivation

<!-- Why are we building this? What problem does it solve? -->

## Requirements

<!-- Concrete requirements. What must this feature do? -->

- 
- 

## Design / Approach

<!-- High-level design decisions, data flow, architecture choices -->

### Files to modify

<!-- Use \`tree\` or list files that will be changed -->

<!--
\`\`\`
path/to/file1.py - Description of change
path/to/file2.py - Description of change
\`\`\`
-->

### Database changes (if any)

<!-- Migration scripts, new tables, schema changes -->

### API changes (if any)

<!-- New endpoints, modified responses, request/response shapes -->

## Implementation Steps

1. 
2. 
3. 

## Testing Plan

<!-- How will this be tested? Unit tests, integration tests, manual steps -->

- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual smoke test

## Edge Cases & Risks

<!-- Things that could go wrong, edge cases to handle -->

- 

## References

<!-- Links to docs, issues, related PRs -->

`;
}

export default function planFeatureExtension(pi: ExtensionAPI) {
  pi.registerCommand("plan", {
    description: "Create a new feature plan",
    handler: async (_args, ctx) => {
      // Step 1: Ask for the feature name
      const featureName = await ctx.ui.input(
        "Feature name:",
        "e.g. Add user authentication",
      );

      if (!featureName?.trim()) {
        ctx.ui.notify("Plan creation cancelled.", "warning");
        return;
      }

      const trimmedName = featureName.trim();
      const slug = slugify(trimmedName);
      const planDir = join(ctx.cwd, PLAN_DIR);
      const planPath = join(planDir, `${slug}.md`);

      // Step 2: Check if plan already exists
      if (existsSync(planPath)) {
        const overwrite = await ctx.ui.confirm(
          "Plan exists",
          `"${slug}.md" already exists. Open it instead?`,
        );

        if (overwrite) {
          // Open existing plan
          await pi.exec("code", [planPath]);
          ctx.ui.setEditorText(planPath);
          ctx.ui.notify(`Opening existing plan: plan/${slug}.md`, "info");
          return;
        }

        ctx.ui.notify("Plan creation cancelled.", "warning");
        return;
      }

      // Step 3: Create plan directory and file
      try {
        await mkdir(planDir, { recursive: true });

        const timestamp = new Date().toISOString().replace("T", " ").slice(0, 19);
        const content = generatePlanTemplate(trimmedName, timestamp);

        await writeFile(planPath, content, "utf-8");

        // Step 4: Open in VS Code
        const result = await pi.exec("code", [planPath]);

        if (result.code === 0 || existsSync("/snap/bin/code")) {
          ctx.ui.notify(
            `Plan created and opened in VS Code: plan/${slug}.md`,
            "success",
          );
        } else {
          ctx.ui.notify(
            `Plan created: plan/${slug}.md (VS Code not available)`,
            "info",
          );
        }

        // Step 5: Load the plan content into pi's editor for context
        // Step 6: Send a message to kick off planning discussion
        pi.sendUserMessage(
          `I've created a plan for "${trimmedName}" at plan/${slug}.md. Let's review and flesh out the requirements together.\n\n${content}`,
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        ctx.ui.notify(`Failed to create plan: ${message}`, "error");
      }
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.notify(
      'Use /plan to create a feature plan. Plans are saved to "plan/" and opened in VS Code.',
      "info",
    );
  });
}
