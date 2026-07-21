/**
 * /diff Extension
 *
 * Opens each file changed since the last commit in the VS Code diff viewer.
 * Uses `code --diff` to compare the HEAD version against the working tree.
 *
 * Usage: /diff [file-filter]
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";

interface ChangedFile {
  status: string;
  file: string;
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("diff", {
    description: "Open changed files in VS Code diff viewer",
    handler: async (args, ctx) => {
      // 1. Collect changed files
      const { stdout: diffOutput } = await pi.exec("git", [
        "diff",
        "--name-status",
        "HEAD",
      ]);
      const { stdout: untrackedOutput } = await pi.exec("git", [
        "ls-files",
        "--others",
        "--exclude-standard",
      ]);

      const changedFiles: ChangedFile[] = [];

      // Parse git diff --name-status output
      const diffLines = diffOutput.trim().split("\n").filter(Boolean);
      for (const line of diffLines) {
        const parts = line.split("\t");
        if (parts.length >= 2) {
          changedFiles.push({ status: parts[0], file: parts[1] });
        }
      }

      // Add untracked files
      const untrackedLines = untrackedOutput.trim().split("\n").filter(Boolean);
      for (const file of untrackedLines) {
        changedFiles.push({ status: "?", file });
      }

      if (changedFiles.length === 0) {
        ctx.ui.notify("No changes since last commit", "info");
        return;
      }

      // Filter by args if provided
      let filesToShow = changedFiles;
      if (args.trim()) {
        const filter = args.trim().toLowerCase();
        filesToShow = changedFiles.filter((f) =>
          f.file.toLowerCase().includes(filter),
        );
        if (filesToShow.length === 0) {
          ctx.ui.notify(
            `No changed files matching "${args.trim()}"`,
            "warning",
          );
          return;
        }
      }

      // Show selection dialog if too many files
      if (filesToShow.length > 15 && ctx.hasUI) {
        const items = filesToShow.map(
          (f) => `[${f.status}] ${f.file}`,
        );
        const selected = await ctx.ui.select(
          `${filesToShow.length} changed files — select one to diff (or Esc to diff all)`,
          items,
        );
        if (selected) {
          const idx = items.indexOf(selected);
          filesToShow = [filesToShow[idx]];
        }
      }

      // 2. Prepare diff files
      const diffDir = path.join(os.tmpdir(), "pi-diff-files");
      // Clean up old diff files from previous runs
      try {
        if (fs.existsSync(diffDir)) {
          fs.rmSync(diffDir, { recursive: true, force: true });
        }
      } catch {
        // Ignore cleanup errors
      }
      fs.mkdirSync(diffDir, { recursive: true });

      const labelMap: Record<string, string> = {
        M: "modified",
        A: "added",
        D: "deleted",
        R: "renamed",
        "?": "untracked",
      };

      let openedCount = 0;
      const errors: string[] = [];

      for (const { status, file } of filesToShow) {
        try {
          if (status.startsWith("R")) {
            // Renamed files: git diff --name-status shows "R100\told\tnew"
            // We handle by diffing HEAD old vs working tree new
            const parts = file.split("\t");
            const oldFile = parts[0];
            const newFile = parts[1] || parts[0];
            const headPath = path.join(
              diffDir,
              `${randomUUID()}-${path.basename(oldFile)}`,
            );
            const { stdout } = await pi.exec("git", [
              "show",
              `HEAD:${oldFile}`,
            ]);
            fs.writeFileSync(headPath, stdout || "");
            await pi.exec("code", ["--diff", headPath, newFile]);
          } else if (status === "D") {
            // Deleted: diff HEAD version vs /dev/null
            const headPath = path.join(
              diffDir,
              `${randomUUID()}-${path.basename(file)}`,
            );
            const { stdout } = await pi.exec("git", [
              "show",
              `HEAD:${file}`,
            ]);
            fs.writeFileSync(headPath, stdout || "");
            await pi.exec("code", [
              "--diff",
              headPath,
              "/dev/null",
            ]);
          } else if (status === "A" || status === "?") {
            // Added or untracked: open the file directly
            await pi.exec("code", ["--goto", file]);
          } else {
            // Modified: diff HEAD version vs working tree
            const headPath = path.join(
              diffDir,
              `${randomUUID()}-${path.basename(file)}`,
            );
            const { stdout } = await pi.exec("git", [
              "show",
              `HEAD:${file}`,
            ]);
            fs.writeFileSync(headPath, stdout || "");
            await pi.exec("code", ["--diff", headPath, file]);
          }
          openedCount++;
        } catch (err) {
          errors.push(`${file}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }

      // Report results
      const label =
        openedCount === filesToShow.length
          ? `Opened ${openedCount} file(s) in VS Code diff viewer`
          : `Opened ${openedCount}/${filesToShow.length} file(s) — ${errors.length} error(s)`;
      ctx.ui.notify(label, errors.length > 0 ? "warning" : "info");

      if (errors.length > 0) {
        const shown = errors.slice(0, 3);
        if (errors.length > 3) {
          shown.push(`... and ${errors.length - 3} more`);
        }
        ctx.ui.setWidget("diff-errors", shown);
      }
    },
  });
}
