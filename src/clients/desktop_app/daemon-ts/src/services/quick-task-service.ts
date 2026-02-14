/**
 * Quick Task Service — Main execution orchestration.
 *
 * Ported from quick_task_service.py.
 *
 * Connects the orchestrator agent pipeline to the HTTP routes.
 * Handles: task submission, multi-turn conversation, cancellation,
 * file attachments, result aggregation.
 */

import { OrchestratorSession } from "../agent/orchestrator.js";
import type { TaskState } from "./task-state.js";
import { TaskStatus } from "./task-state.js";
import { Action } from "../events/types.js";
import { createTaskWorkspace } from "../utils/workspace-manager.js";
import { getCloudClient } from "./cloud-client.js";
import { createChildAgentTools } from "../agent/agent-factory.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("quick-task-service");

// ===== Active Sessions =====

const activeSessions = new Map<string, OrchestratorSession>();

// ===== Execute Task =====

/**
 * Main entry point: start task execution using the orchestrator pipeline.
 * Called from quick-task route's POST /execute handler.
 */
export async function executeTaskPipeline(
  state: TaskState,
  apiKey?: string,
): Promise<void> {
  const { taskId, task, emitter } = state;

  // Create workspace
  const workingDir = createTaskWorkspace(taskId);

  logger.info(
    { taskId, task: task.slice(0, 100), workingDir },
    "Starting task pipeline",
  );

  state.markRunning();

  // Emit task started
  emitter.emit({
    action: Action.task_state,
    task_id: taskId,
    status: "running",
    task,
    progress: 0,
    working_directory: workingDir,
    user_id: state.userId,
  });

  // Create orchestrator session with real tool factory
  const session = new OrchestratorSession({
    taskId,
    apiKey,
    emitter,
    taskState: state,
    workspaceDir: workingDir,
    childAgentToolsFactory: (agentType, sessionId, workingDirOverride) =>
      createChildAgentTools(agentType, sessionId, {
        workingDir: workingDirOverride ?? workingDir,
        taskId,
        taskState: state,
        apiKey,
        emitter,
      }),
  });

  activeSessions.set(taskId, session);

  try {
    // Run the orchestrator loop
    const execResult = await session.run(task);

    // Check if task actually succeeded (all subtasks may have failed)
    if (execResult && execResult.failed > 0 && execResult.completed === 0) {
      // All subtasks failed
      const errorMsg = `All ${execResult.failed} subtasks failed`;
      state.markFailed(errorMsg);

      try {
        emitter.emit({
          action: Action.task_failed,
          task_id: taskId,
          error: errorMsg,
          tools_called: state.toolsCalled,
        });
      } catch (emitErr) {
        logger.warn({ taskId, err: emitErr }, "Failed to emit task_failed");
      }

      logger.error({ taskId, execResult }, "Task failed: all subtasks failed");
    } else {
      // Task completed (with or without partial failures)
      state.markCompleted({ summary: "Task completed" });

      try {
        emitter.emit({
          action: Action.task_completed,
          task_id: taskId,
          output: state.result,
          tools_called: state.toolsCalled,
          loop_iterations: state.loopIteration,
          duration_seconds: state.durationSeconds,
        });
      } catch (emitErr) {
        logger.warn({ taskId, err: emitErr }, "Failed to emit task_completed");
      }

      logger.info(
        { taskId, duration: state.durationSeconds },
        "Task completed",
      );
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);

    if (state.status === TaskStatus.CANCELLED) {
      logger.info({ taskId }, "Task was cancelled");
    } else {
      state.markFailed(errorMsg);

      try {
        emitter.emit({
          action: Action.task_failed,
          task_id: taskId,
          error: errorMsg,
          tools_called: state.toolsCalled,
        });
      } catch (emitErr) {
        logger.warn({ taskId, err: emitErr }, "Failed to emit task_failed in catch");
      }

      logger.error({ taskId, err: errorMsg }, "Task failed");
    }
  } finally {
    // Always emit end event before closing, regardless of what happened above
    try {
      const finalStatus = state.status === TaskStatus.CANCELLED
        ? "cancelled"
        : state.status === TaskStatus.FAILED
          ? "failed"
          : "completed";
      const finalMsg = state.status === TaskStatus.CANCELLED
        ? "Task cancelled"
        : state.status === TaskStatus.FAILED
          ? (state.error ?? "Task failed")
          : "Task completed successfully";
      emitter.emitEnd(finalStatus, finalMsg);
    } catch (endErr) {
      logger.warn({ taskId, err: endErr }, "Failed to emit end event");
    }

    // Cleanup browser session (return pool pages) before removing references
    const activeSession = activeSessions.get(taskId);
    if (activeSession) {
      try {
        await activeSession.cleanup();
      } catch {
        // best effort
      }
    }
    activeSessions.delete(taskId);
    emitter.close();
  }
}

// ===== Cancel Task =====

export function cancelTask(taskId: string): boolean {
  const session = activeSessions.get(taskId);
  if (session) {
    // Fire-and-forget: cleanup is async (returns browser pages to pool).
    // The executeTaskPipeline catch/finally will also attempt cleanup,
    // but we start it here so pool pages are freed as early as possible.
    session.cleanup().catch((err) => {
      logger.warn({ taskId, err }, "Session cleanup during cancel failed");
    });
    return true;
  }
  return false;
}

// ===== Inject Message =====

export function injectMessage(
  taskId: string,
  message: string,
): boolean {
  const session = activeSessions.get(taskId);
  if (session) {
    session.taskState.putUserMessage(message);
    return true;
  }
  return false;
}

// ===== Pause/Resume Task =====

export function pauseTask(taskId: string): boolean {
  const session = activeSessions.get(taskId);
  if (session) {
    session.pauseExecutors();
    return true;
  }
  return false;
}

export function resumeTask(taskId: string): boolean {
  const session = activeSessions.get(taskId);
  if (session) {
    session.resumeExecutors();
    return true;
  }
  return false;
}

// ===== Get Active Session =====

export function getActiveSession(
  taskId: string,
): OrchestratorSession | undefined {
  return activeSessions.get(taskId);
}
