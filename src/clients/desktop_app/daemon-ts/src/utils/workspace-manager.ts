/**
 * Workspace Manager — Per-task workspace directories under ~/.ami/workspace/.
 *
 * Ported from WorkingDirectoryManager in Python daemon.
 */

import { mkdirSync, existsSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { AMI_DIR } from "./config.js";
import { createLogger } from "./logging.js";

const logger = createLogger("workspace");

const WORKSPACE_BASE = join(AMI_DIR, "workspace");

/** Sanitize taskId to prevent path traversal */
function safeTaskDir(taskId: string): string {
  // Strip any path separators and traversal attempts
  const sanitized = taskId.replace(/[/\\]/g, "_").replace(/\.\./g, "_");
  const dir = resolve(WORKSPACE_BASE, sanitized);
  // Double-check the resolved path is under WORKSPACE_BASE
  if (!dir.startsWith(resolve(WORKSPACE_BASE) + "/") && dir !== resolve(WORKSPACE_BASE)) {
    throw new Error(`Invalid taskId: path traversal detected in "${taskId}"`);
  }
  return dir;
}

/**
 * Create an isolated workspace directory for a task.
 * Returns the absolute path.
 */
export function createTaskWorkspace(taskId: string): string {
  const dir = safeTaskDir(taskId);
  mkdirSync(dir, { recursive: true });
  logger.info({ dir }, "Task workspace created");
  return dir;
}

/**
 * Get the workspace path for a task (may not exist yet).
 */
export function getTaskWorkspacePath(taskId: string): string {
  return safeTaskDir(taskId);
}

/**
 * Get the base workspace directory.
 */
export function getWorkspaceBase(): string {
  mkdirSync(WORKSPACE_BASE, { recursive: true });
  return WORKSPACE_BASE;
}

/**
 * Clean up a task workspace.
 */
export function cleanupTaskWorkspace(taskId: string): boolean {
  const dir = safeTaskDir(taskId);
  if (existsSync(dir)) {
    try {
      rmSync(dir, { recursive: true, force: true });
      logger.info({ dir }, "Task workspace cleaned up");
      return true;
    } catch (err) {
      logger.warn({ dir, err }, "Failed to clean up workspace");
      return false;
    }
  }
  return false;
}
