/**
 * TaskRegistry — manages all active and completed tasks.
 */

import { TaskState, TaskStatus } from "./task-state.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("task-registry");

export class TaskRegistry {
  private _tasks = new Map<string, TaskState>();

  create(taskId: string, task: string): TaskState {
    const state = new TaskState(taskId, task);
    this._tasks.set(taskId, state);
    logger.info({ taskId }, "Task created");
    return state;
  }

  get(taskId: string): TaskState | undefined {
    return this._tasks.get(taskId);
  }

  getOrThrow(taskId: string): TaskState {
    const state = this._tasks.get(taskId);
    if (!state) {
      throw new Error(`Task ${taskId} not found`);
    }
    return state;
  }

  list(): TaskState[] {
    return Array.from(this._tasks.values());
  }

  delete(taskId: string): boolean {
    return this._tasks.delete(taskId);
  }

  get size(): number {
    return this._tasks.size;
  }

  /** Clean up old completed/failed tasks older than maxAgeMs. */
  cleanup(maxAgeMs = 3600_000): number {
    const now = Date.now();
    let removed = 0;

    for (const [taskId, state] of this._tasks) {
      if (
        [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED].includes(state.status)
      ) {
        const age = now - state.updatedAt.getTime();
        if (age > maxAgeMs) {
          state.emitter.close();
          this._tasks.delete(taskId);
          removed++;
        }
      }
    }

    if (removed > 0) {
      logger.info({ removed }, "Cleaned up old tasks");
    }
    return removed;
  }

  /** Get summary stats. */
  stats(): { total: number; running: number; completed: number; failed: number } {
    let running = 0;
    let completed = 0;
    let failed = 0;

    for (const state of this._tasks.values()) {
      switch (state.status) {
        case TaskStatus.RUNNING:
        case TaskStatus.WAITING:
          running++;
          break;
        case TaskStatus.COMPLETED:
          completed++;
          break;
        case TaskStatus.FAILED:
          failed++;
          break;
      }
    }

    return { total: this._tasks.size, running, completed, failed };
  }
}

/** Global singleton registry. */
export const taskRegistry = new TaskRegistry();

// Periodic cleanup every 10 minutes to prevent memory leaks from stale tasks
setInterval(() => {
  try { taskRegistry.cleanup(); } catch (e) { /* ignore cleanup errors */ }
}, 600_000).unref();
