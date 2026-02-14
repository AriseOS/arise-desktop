/**
 * Task State Persistence — read/write task-state.json for resume support.
 *
 * Each task gets a snapshot at ~/.ami/workspace/{taskId}/task-state.json.
 * The snapshot contains the full subtask plan with states/results so a
 * restarted daemon can resume where it left off.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import {
  getTaskWorkspacePath,
  createTaskWorkspace,
  getWorkspaceBase,
} from "../utils/workspace-manager.js";
import type {
  TaskStateSnapshot,
  SubtaskSnapshot,
  AMISubtask,
} from "../agent/schemas.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("task-state-persistence");

const STATE_FILE = "task-state.json";

// ===== Snapshot builders =====

export function subtaskToSnapshot(st: AMISubtask): SubtaskSnapshot {
  return {
    id: st.id,
    content: st.content,
    agentType: st.agentType,
    dependsOn: st.dependsOn,
    workflowGuide: st.workflowGuide,
    memoryLevel: st.memoryLevel,
    state: st.state,
    result: st.result,
    error: st.error,
  };
}

export function buildSnapshot(
  taskId: string,
  userRequest: string,
  subtasks: AMISubtask[],
  status: TaskStateSnapshot["status"],
  memoryPlan?: Record<string, unknown>,
  createdAt?: string,
): TaskStateSnapshot {
  const now = new Date().toISOString();
  return {
    taskId,
    userRequest,
    status,
    memoryPlan,
    subtasks: subtasks.map(subtaskToSnapshot),
    createdAt: createdAt ?? now,
    updatedAt: now,
  };
}

// ===== Read / Write =====

export function saveTaskState(taskId: string, snapshot: TaskStateSnapshot): void {
  try {
    const dir = createTaskWorkspace(taskId);
    const filePath = join(dir, STATE_FILE);
    writeFileSync(filePath, JSON.stringify(snapshot, null, 2), "utf-8");
    logger.debug({ taskId }, "Task state saved");
  } catch (err) {
    logger.warn({ taskId, err }, "Failed to save task state");
  }
}

export function loadTaskState(taskId: string): TaskStateSnapshot | null {
  try {
    const dir = getTaskWorkspacePath(taskId);
    const filePath = join(dir, STATE_FILE);
    if (!existsSync(filePath)) return null;
    const raw = readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as TaskStateSnapshot;
  } catch (err) {
    logger.warn({ taskId, err }, "Failed to load task state");
    return null;
  }
}

/**
 * Scan all workspace subdirectories and return tasks whose status is NOT "completed",
 * sorted by updatedAt descending (most recent first).
 */
export function listResumableTasks(): TaskStateSnapshot[] {
  const results: TaskStateSnapshot[] = [];
  try {
    const base = getWorkspaceBase();
    const entries = readdirSync(base, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const filePath = join(base, entry.name, STATE_FILE);
      if (!existsSync(filePath)) continue;
      try {
        const raw = readFileSync(filePath, "utf-8");
        const snapshot = JSON.parse(raw) as TaskStateSnapshot;
        if (snapshot.status !== "completed") {
          results.push(snapshot);
        }
      } catch {
        // skip corrupted files
      }
    }
  } catch (err) {
    logger.warn({ err }, "Failed to list resumable tasks");
  }

  // Sort by updatedAt descending
  results.sort((a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""));
  return results;
}

/**
 * Incrementally update a single subtask's state in the persisted snapshot.
 * Reads → patches → writes. Fire-and-forget safe (errors are logged, not thrown).
 */
export function updateSubtaskState(
  taskId: string,
  subtaskId: string,
  state: string,
  result?: string,
  error?: string,
): void {
  try {
    const snapshot = loadTaskState(taskId);
    if (!snapshot) return;

    const st = snapshot.subtasks.find((s) => s.id === subtaskId);
    if (!st) return;

    st.state = state;
    if (result !== undefined) st.result = result;
    if (error !== undefined) st.error = error;
    snapshot.updatedAt = new Date().toISOString();

    saveTaskState(taskId, snapshot);
  } catch (err) {
    logger.warn({ taskId, subtaskId, err }, "Failed to update subtask state");
  }
}

/**
 * Update only the top-level status field of a persisted snapshot.
 */
export function updateTaskStatus(
  taskId: string,
  status: TaskStateSnapshot["status"],
): void {
  try {
    const snapshot = loadTaskState(taskId);
    if (!snapshot) return;

    snapshot.status = status;
    snapshot.updatedAt = new Date().toISOString();

    saveTaskState(taskId, snapshot);
  } catch (err) {
    logger.warn({ taskId, status, err }, "Failed to update task status");
  }
}
