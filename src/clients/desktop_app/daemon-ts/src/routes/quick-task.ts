/**
 * Quick Task Routes — SSE streaming task execution.
 *
 * POST /api/v1/quick-task/execute     — submit task
 * GET  /api/v1/quick-task/stream/:id  — SSE stream
 * POST /api/v1/quick-task/message/:id — send message to running task
 * POST /api/v1/quick-task/cancel/:id  — cancel task
 * POST /api/v1/quick-task/pause/:id   — pause task
 * POST /api/v1/quick-task/resume/:id  — resume task
 * GET  /api/v1/quick-task/tasks       — list tasks
 * GET  /api/v1/quick-task/status/:id  — task status
 * GET  /api/v1/quick-task/result/:id  — task result
 * GET  /api/v1/quick-task/:id/detail  — task detail
 */

import { Router, type Request, type Response } from "express";
import { v4 as uuid } from "uuid";
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, relative, resolve as resolvePath } from "node:path";
import { taskRegistry } from "../services/task-registry.js";
import { TaskStatus } from "../services/task-state.js";
import { sseAction, sseHeartbeat } from "../events/emitter.js";
import { Action, TERMINAL_ACTIONS } from "../events/types.js";
import { createLogger } from "../utils/logging.js";
import { executeTaskPipeline, cancelTask, pauseTask, resumeTask } from "../services/quick-task-service.js";
import { getTaskWorkspacePath, cleanupTaskWorkspace } from "../utils/workspace-manager.js";

const logger = createLogger("quick-task");

export const quickTaskRouter = Router();

// ===== POST /execute =====

quickTaskRouter.post("/execute", (req: Request, res: Response) => {
  const { task } = req.body;
  if (!task || typeof task !== "string") {
    res.status(400).json({ error: "task field is required" });
    return;
  }

  const taskId = uuid().slice(0, 8);
  const apiKey = req.headers["x-ami-api-key"] as string | undefined;
  const userId = req.headers["x-user-id"] as string | undefined;

  const state = taskRegistry.create(taskId, task);
  state.userId = userId;

  logger.info({ taskId, task: task.slice(0, 100) }, "Task submitted");

  // Start execution in background
  executeTaskPipeline(state, apiKey).catch((err) => {
    logger.error({ taskId, err }, "Task execution failed");
  });

  res.json({
    task_id: taskId,
    status: "started",
    message: `Task ${taskId} started`,
  });
});

// ===== GET /stream/:taskId =====

quickTaskRouter.get("/stream/:taskId", async (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  // Set SSE headers
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  });

  const HEARTBEAT_INTERVAL_MS = 30_000;
  const IDLE_TIMEOUT_MS = 600_000;
  let lastActivity = Date.now();
  let closed = false;

  const cleanup = () => {
    closed = true;
  };

  req.on("close", cleanup);
  req.on("error", cleanup);

  // Heartbeat timer
  const heartbeatTimer = setInterval(() => {
    if (closed) return;
    try {
      res.write(sseHeartbeat());
    } catch {
      cleanup();
    }
  }, HEARTBEAT_INTERVAL_MS);

  try {
    while (!closed) {
      // Check idle timeout
      if (Date.now() - lastActivity > IDLE_TIMEOUT_MS) {
        logger.info({ taskId }, "SSE stream idle timeout");
        res.write(
          sseAction({
            action: Action.end,
            status: "failed",
            message: "Stream idle timeout — no events for 10 minutes",
            task_id: taskId,
            timestamp: new Date().toISOString(),
          }),
        );
        break;
      }

      // Get next event with timeout for heartbeat
      const event = await state.emitter.getEvent(HEARTBEAT_INTERVAL_MS);

      if (event === null) {
        // Timeout — heartbeat is handled by the interval timer
        continue;
      }

      lastActivity = Date.now();

      try {
        res.write(sseAction(event));
      } catch {
        break;
      }

      // Check for terminal events
      if (TERMINAL_ACTIONS.has(event.action)) {
        break;
      }
    }
  } finally {
    clearInterval(heartbeatTimer);
    res.end();
  }
});

// ===== POST /message/:taskId =====

quickTaskRouter.post("/message/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  const { type, response, message } = req.body;

  if (type === "human_response" && response) {
    // Response to ask_human
    const delivered = state.provideHumanResponse(response);
    res.json({
      success: delivered,
      type: "human_response",
      message: delivered ? "Response delivered" : "No pending question",
    });
  } else if (type === "user_message" && message) {
    // Multi-turn user message
    state.addConversation("user", message);
    state.putUserMessage(message);
    res.json({
      success: true,
      type: "queued",
      message: "Message queued",
    });
  } else {
    res.status(400).json({
      error: "type must be 'human_response' or 'user_message'",
    });
  }
});

// ===== POST /cancel/:taskId =====

quickTaskRouter.post("/cancel/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  // Mark cancelled + abort signal, then stop the active session
  // (which stops executors and aborts running agents).
  // The executeTaskPipeline catch/finally handles SSE end event and cleanup.
  state.markCancelled("User cancelled");
  cancelTask(taskId);

  logger.info({ taskId }, "Task cancelled");
  res.json({ task_id: taskId, status: "cancelled" });
});

// ===== POST /pause/:taskId =====

quickTaskRouter.post("/pause/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  if (state.status !== TaskStatus.RUNNING) {
    res.status(400).json({ error: `Task is ${state.status}, cannot pause` });
    return;
  }

  // Pause the actual executor (not just the TaskState)
  state.status = TaskStatus.WAITING;
  state.updatedAt = new Date();
  pauseTask(taskId);
  res.json({ task_id: taskId, status: "paused" });
});

// ===== POST /resume/:taskId =====

quickTaskRouter.post("/resume/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  if (state.status !== TaskStatus.WAITING) {
    res.status(400).json({
      error: `Task is ${state.status}, cannot resume`,
      task_id: taskId,
      status: state.status,
    });
    return;
  }

  state.status = TaskStatus.RUNNING;
  state.updatedAt = new Date();
  resumeTask(taskId);
  res.json({ task_id: taskId, status: "running" });
});

// ===== GET /tasks =====

quickTaskRouter.get("/tasks", (_req: Request, res: Response) => {
  const states = taskRegistry.list();
  const stats = taskRegistry.stats();

  const tasks = states
    .map((s) => s.toJSON())
    .sort((a, b) => {
      const ta = a.created_at as string;
      const tb = b.created_at as string;
      return tb.localeCompare(ta); // newest first
    });

  res.json({
    tasks,
    total: stats.total,
    running: stats.running,
    completed: stats.completed,
    failed: stats.failed,
  });
});

// ===== GET /status/:taskId =====

quickTaskRouter.get("/status/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  res.json({
    task_id: state.taskId,
    status: state.status,
    progress: state.progress,
    error: state.error,
  });
});

// ===== GET /result/:taskId =====

quickTaskRouter.get("/result/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  res.json({
    task_id: state.taskId,
    success: state.status === TaskStatus.COMPLETED,
    output: state.result,
    duration_seconds: state.durationSeconds,
    error: state.error,
    loop_iterations: state.loopIteration,
    tools_called: state.toolsCalled,
  });
});

// ===== GET /:taskId/detail =====

quickTaskRouter.get("/:taskId/detail", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const state = taskRegistry.get(taskId);

  if (!state) {
    res.status(404).json({ error: `Task ${taskId} not found` });
    return;
  }

  // Frontend expects `messages`, `toolkit_events`, `thinking_logs` arrays.
  // Map conversation_history → messages for compatibility.
  const messages = state.conversationHistory.map((entry, i) => ({
    id: `msg_${i}`,
    role: entry.role,
    content: entry.content,
    timestamp: entry.timestamp,
  }));

  res.json({
    ...state.toJSON(),
    conversation_history: state.conversationHistory,
    messages,
    toolkit_events: [],  // Collected by SSE bridge, not stored per-task yet
    thinking_logs: [],   // Collected by SSE bridge, not stored per-task yet
    duration_seconds: state.durationSeconds,
  });
});

// ===== GET /workspace/:taskId/files =====

quickTaskRouter.get("/workspace/:taskId/files", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const workspaceDir = getTaskWorkspacePath(taskId);

  try {
    if (!existsSync(workspaceDir)) {
      res.status(404).json({ error: `Workspace not found for task ${taskId}` });
      return;
    }

    const files: string[] = [];
    let totalSize = 0;

    function scanDir(dir: string): void {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name.startsWith(".")) continue;
        const fullPath = join(dir, entry.name);
        if (entry.isDirectory()) {
          scanDir(fullPath);
        } else {
          files.push(relative(workspaceDir, fullPath));
          try {
            totalSize += statSync(fullPath).size;
          } catch {
            // skip
          }
        }
      }
    }

    scanDir(workspaceDir);

    res.json({
      task_id: taskId,
      workspace: workspaceDir,
      files,
      total_size_bytes: totalSize,
    });
  } catch (err) {
    res.status(500).json({ error: `Failed to list workspace: ${err}` });
  }
});

// ===== GET /workspace/:taskId/file/* =====

quickTaskRouter.get("/workspace/:taskId/file/*", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const filePath = (req.params as any)[0] as string; // Express splat param
  const workspaceDir = getTaskWorkspacePath(taskId);

  try {
    const fullPath = resolvePath(workspaceDir, filePath);

    // Security: prevent directory traversal
    if (!fullPath.startsWith(resolvePath(workspaceDir) + "/") && fullPath !== resolvePath(workspaceDir)) {
      res.status(403).json({ error: "Access denied: path outside workspace" });
      return;
    }

    if (!existsSync(fullPath)) {
      res.status(404).json({ error: `File not found: ${filePath}` });
      return;
    }

    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      res.status(400).json({ error: "Path is a directory, not a file" });
      return;
    }

    // Try UTF-8 first, fallback to base64
    let content: string;
    let encoding: string;
    try {
      content = readFileSync(fullPath, "utf-8");
      encoding = "utf-8";
    } catch {
      content = readFileSync(fullPath).toString("base64");
      encoding = "base64";
    }

    res.json({
      task_id: taskId,
      file_path: filePath,
      content,
      encoding,
      size_bytes: stat.size,
    });
  } catch (err) {
    res.status(500).json({ error: `Failed to read file: ${err}` });
  }
});

// ===== DELETE /workspace/:taskId =====

quickTaskRouter.delete("/workspace/:taskId", (req: Request, res: Response) => {
  const { taskId } = req.params;
  const force = req.query.force === "true";
  const state = taskRegistry.get(taskId);

  if (state && !force) {
    if (state.status === TaskStatus.PENDING || state.status === TaskStatus.RUNNING) {
      res.status(400).json({
        error: "Cannot cleanup workspace while task is running. Use force=true to override.",
      });
      return;
    }
  }

  const cleaned = cleanupTaskWorkspace(taskId);

  res.json({
    task_id: taskId,
    cleaned,
    message: cleaned ? "Workspace cleaned up" : "No workspace found to clean up",
  });
});
