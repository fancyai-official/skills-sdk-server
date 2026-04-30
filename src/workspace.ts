/**
 * Per-user workspace isolation — prevents Claude Code project-level context
 * from leaking between different users who share the same app `cwd`.
 *
 * Creates `<root>/<userId>/<app>/` with symlinks pointing back to the shared
 * app directory (CLAUDE.md, .claude/skills, scripts, etc.).  Because each user
 * gets a unique filesystem path, Claude Code hashes it into a distinct project
 * ID, keeping session files and project memory separated.
 */

import { mkdirSync, symlinkSync, existsSync, readdirSync, lstatSync, unlinkSync } from "node:fs";
import { basename, join } from "node:path";

export const USER_WORKSPACES_ROOT =
  process.env.USER_WORKSPACES_ROOT || `${process.env.HOME || process.cwd()}/.claude/user-workspaces`;

export function ensureIsolatedWorkspace(originalCwd: string, userId: string): string {
  const safeUserId = userId.replace(/[^a-zA-Z0-9_\-@.]/g, "_").slice(0, 128);
  const appName = basename(originalCwd);
  const workspaceDir = join(USER_WORKSPACES_ROOT, safeUserId, appName);

  try {
    mkdirSync(workspaceDir, { recursive: true });

    const sourceEntries = new Set(readdirSync(originalCwd));
    for (const name of sourceEntries) {
      const dest = join(workspaceDir, name);
      if (!existsSync(dest)) {
        symlinkSync(join(originalCwd, name), dest);
      }
    }

    for (const name of readdirSync(workspaceDir)) {
      if (!sourceEntries.has(name)) {
        try {
          const dest = join(workspaceDir, name);
          if (lstatSync(dest).isSymbolicLink()) {
            unlinkSync(dest);
          }
        } catch { /* ignore */ }
      }
    }
  } catch (err) {
    console.warn("[UserWorkspace] Setup failed, falling back to shared cwd:", err);
    return originalCwd;
  }
  return workspaceDir;
}
