/**
 * Recording Routes — Start/stop/list/manage recordings.
 *
 * POST   /api/v1/recordings/start
 * POST   /api/v1/recordings/stop
 * GET    /api/v1/recordings/current/operations
 * GET    /api/v1/recordings
 * GET    /api/v1/recordings/:sessionId
 * DELETE /api/v1/recordings/:sessionId
 * PATCH  /api/v1/recordings/:sessionId
 * GET    /api/v1/recordings/:sessionId/replay/preview
 * POST   /api/v1/recordings/:sessionId/replay
 * POST   /api/v1/recordings/:sessionId/analyze
 */

import { Router, type Request, type Response } from "express";
import { getStorageManager } from "../services/storage-manager.js";
import { BehaviorRecorder } from "../browser/behavior-recorder.js";
import { BrowserSession } from "../browser/browser-session.js";
import { getCloudClient } from "../services/cloud-client.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("recordings-routes");

export const recordingsRouter = Router();

// ===== Active Recording State =====

let activeRecorder: BehaviorRecorder | null = null;
let activeSessionId: string | null = null;

// ===== POST /start =====

recordingsRouter.post("/start", async (req: Request, res: Response) => {
  const { url, user_id, title, description } = req.body;

  if (activeRecorder) {
    res.status(409).json({
      error: "Recording already in progress",
      session_id: activeSessionId,
    });
    return;
  }

  const userId = user_id ?? "default";
  const sessionId = `rec_${Date.now()}`;

  try {
    const session = BrowserSession.getInstance("default");
    await session.ensureBrowser();

    // Navigate to URL if provided
    if (url) {
      const page = session.currentPage;
      if (page) {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
      }
    }

    activeRecorder = new BehaviorRecorder();
    await activeRecorder.startRecording(session);
    activeSessionId = sessionId;

    // Save initial metadata
    const storage = getStorageManager();
    storage.saveRecording(userId, sessionId, {
      session_id: sessionId,
      created_at: new Date().toISOString(),
      task_metadata: {
        name: title ?? "New Recording",
        description: description ?? "",
      },
      operations: [],
    });

    logger.info({ sessionId, url }, "Recording started");

    res.json({
      session_id: sessionId,
      status: "recording",
      url: url ?? null,
    });
  } catch (err) {
    activeRecorder = null;
    activeSessionId = null;
    res.status(500).json({ error: String(err) });
  }
});

// ===== POST /stop =====

recordingsRouter.post("/stop", async (req: Request, res: Response) => {
  const { user_id } = req.body;
  const userId = user_id ?? "default";

  if (!activeRecorder || !activeSessionId) {
    res.status(404).json({ error: "No active recording" });
    return;
  }

  try {
    const operations = activeRecorder.getOperations();
    await activeRecorder.stopRecording();

    const storage = getStorageManager();
    const existing = storage.getRecording(userId, activeSessionId) ?? {};

    storage.saveRecording(userId, activeSessionId, {
      ...existing,
      ended_at: new Date().toISOString(),
      operations,
    });

    const sessionId = activeSessionId;
    activeRecorder = null;
    activeSessionId = null;

    logger.info({ sessionId, operationsCount: operations.length }, "Recording stopped");

    res.json({
      session_id: sessionId,
      operations_count: operations.length,
      status: "stopped",
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /current/operations =====

recordingsRouter.get("/current/operations", (_req: Request, res: Response) => {
  if (!activeRecorder || !activeSessionId) {
    res.json({
      is_recording: false,
      operations_count: 0,
      operations: [],
    });
    return;
  }

  const operations = activeRecorder.getOperations();

  res.json({
    is_recording: true,
    session_id: activeSessionId,
    operations_count: operations.length,
    operations,
  });
});

// ===== GET / (list) =====

recordingsRouter.get("/", (req: Request, res: Response) => {
  const userId = (req.query.user_id as string) ?? "default";
  const storage = getStorageManager();
  const recordings = storage.listRecordings(userId);

  res.json({
    recordings,
    count: recordings.length,
  });
});

// ===== GET /:sessionId =====

recordingsRouter.get("/:sessionId", (req: Request, res: Response) => {
  const { sessionId } = req.params;
  const userId = (req.query.user_id as string) ?? "default";
  const storage = getStorageManager();

  const detail = storage.getRecordingDetail(userId, sessionId);
  if (!detail) {
    res.status(404).json({ error: `Recording ${sessionId} not found` });
    return;
  }

  res.json(detail);
});

// ===== DELETE /:sessionId =====

recordingsRouter.delete("/:sessionId", (req: Request, res: Response) => {
  const { sessionId } = req.params;
  const userId = (req.query.user_id as string) ?? "default";
  const storage = getStorageManager();

  const deleted = storage.deleteRecording(userId, sessionId);
  if (deleted) {
    res.json({ status: "deleted", message: `Recording ${sessionId} deleted` });
  } else {
    res.status(404).json({ error: `Recording ${sessionId} not found` });
  }
});

// ===== PATCH /:sessionId =====

recordingsRouter.patch("/:sessionId", (req: Request, res: Response) => {
  const { sessionId } = req.params;
  const { user_id, task_description, user_query, name } = req.body;
  const userId = user_id ?? "default";
  const storage = getStorageManager();

  const updated = storage.updateRecordingMetadata(userId, sessionId, {
    name,
    task_description,
    user_query,
  });

  if (updated) {
    res.json({ success: true, message: "Metadata updated" });
  } else {
    res.status(404).json({ error: `Recording ${sessionId} not found` });
  }
});

// ===== GET /:sessionId/replay/preview =====

recordingsRouter.get(
  "/:sessionId/replay/preview",
  (req: Request, res: Response) => {
    const { sessionId } = req.params;
    const userId = (req.query.user_id as string) ?? "default";
    const storage = getStorageManager();

    const detail = storage.getRecordingDetail(userId, sessionId);
    if (!detail) {
      res.status(404).json({ error: `Recording ${sessionId} not found` });
      return;
    }

    const operations = (detail.operations as Record<string, unknown>[]) ?? [];
    const summary = operations
      .slice(0, 10)
      .map((op: any) => `${op.type}: ${op.text ?? op.url ?? ""}`)
      .join(", ");

    res.json({
      session_id: sessionId,
      created_at: detail.created_at,
      operations_count: operations.length,
      operation_summary: summary,
      task_metadata: detail.task_metadata,
      operations,
    });
  },
);

// ===== POST /:sessionId/replay =====

recordingsRouter.post(
  "/:sessionId/replay",
  async (req: Request, res: Response) => {
    const { sessionId } = req.params;
    const {
      user_id,
      wait_between_operations = 0.5,
      stop_on_error = false,
      start_from_index = 0,
      end_at_index,
    } = req.body;
    const userId = user_id ?? "default";

    const storage = getStorageManager();
    const detail = storage.getRecordingDetail(userId, sessionId);
    if (!detail) {
      res.status(404).json({ error: `Recording ${sessionId} not found` });
      return;
    }

    const operations = (detail.operations as Record<string, unknown>[]) ?? [];
    if (operations.length === 0) {
      res.status(400).json({ error: "Recording has no operations to replay" });
      return;
    }

    const replayId = `replay_${sessionId}_${Date.now()}`;
    const startedAt = new Date().toISOString();

    try {
      const session = BrowserSession.getInstance("default");
      await session.ensureBrowser();
      const page = await session.getPage();

      const opsToReplay = operations.slice(
        start_from_index,
        end_at_index ?? undefined,
      );

      const executionLog: Array<{
        index: number;
        type: string;
        status: string;
        error?: string;
      }> = [];

      for (let i = 0; i < opsToReplay.length; i++) {
        const op = opsToReplay[i];
        const actualIndex = start_from_index + i;
        const opType = (op.type as string) ?? "unknown";

        try {
          await _executeReplayOperation(page, op);
          executionLog.push({ index: actualIndex, type: opType, status: "success" });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          executionLog.push({ index: actualIndex, type: opType, status: "failed", error: errorMsg });

          if (stop_on_error) {
            logger.warn({ index: actualIndex, error: errorMsg }, "Replay stopped on error");
            break;
          }
        }

        // Wait between operations
        if (wait_between_operations > 0 && i < opsToReplay.length - 1) {
          await new Promise((resolve) =>
            setTimeout(resolve, wait_between_operations * 1000),
          );
        }
      }

      const endedAt = new Date().toISOString();
      const successful = executionLog.filter((r) => r.status === "success").length;
      const failed = executionLog.filter((r) => r.status === "failed").length;

      logger.info(
        { replayId, total: executionLog.length, successful, failed },
        "Replay completed",
      );

      res.json({
        replay_id: replayId,
        status: "completed",
        recording_session_id: sessionId,
        execution_summary: {
          total_operations: executionLog.length,
          successful,
          failed,
          skipped: 0,
          success_rate: executionLog.length > 0 ? successful / executionLog.length : 0,
        },
        timing: {
          started_at: startedAt,
          ended_at: endedAt,
          duration_seconds:
            (new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 1000,
        },
        operation_results: executionLog,
      });
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);

// ===== Replay Operation Executor =====

async function _executeReplayOperation(
  page: import("playwright").Page,
  operation: Record<string, unknown>,
): Promise<void> {
  const opType = operation.type as string;

  switch (opType) {
    case "navigate": {
      const url = operation.url as string;
      if (url) {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
        await page.waitForLoadState("networkidle").catch(() => {});
      }
      break;
    }

    case "click": {
      const element = await _locateElement(page, operation);
      if (element) {
        await element.click({ timeout: 5_000 });
      } else {
        // Fallback to coordinate-based click
        const x = operation.x as number | undefined;
        const y = operation.y as number | undefined;
        if (x !== undefined && y !== undefined) {
          await page.mouse.click(x, y);
        } else {
          throw new Error("Click target not found and no coordinates available");
        }
      }
      break;
    }

    case "input": {
      const element = await _locateElement(page, operation);
      const value = (operation.value as string) ?? (operation.text as string) ?? "";
      if (element) {
        await element.fill("");
        await element.type(value, { delay: 50 });
      } else {
        throw new Error("Input target element not found");
      }
      break;
    }

    case "select": {
      const element = await _locateElement(page, operation);
      if (element) {
        await element.click({ clickCount: 3 });
      }
      break;
    }

    case "scroll": {
      const distance = (operation.distance as number) ?? (operation.deltaY as number) ?? 300;
      await page.evaluate((d) => window.scrollBy(0, d), distance);
      break;
    }

    case "copy_action": {
      const modifier = process.platform === "darwin" ? "Meta" : "Control";
      await page.keyboard.press(`${modifier}+KeyC`);
      break;
    }

    case "paste_action": {
      const modifier = process.platform === "darwin" ? "Meta" : "Control";
      await page.keyboard.press(`${modifier}+KeyV`);
      break;
    }

    case "dataload": {
      await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => {});
      break;
    }

    case "test":
      // Skip binding verification tests
      break;

    default:
      logger.warn({ opType }, "Unknown replay operation type, skipping");
  }
}

// ===== Element Location (4-tier fallback) =====

async function _locateElement(
  page: import("playwright").Page,
  operation: Record<string, unknown>,
): Promise<import("playwright").ElementHandle | null> {
  const element = (operation.element ?? operation) as Record<string, unknown>;

  // Strategy 1: XPath
  const xpath = element.xpath as string | undefined;
  if (xpath) {
    try {
      const el = await page.waitForSelector(`xpath=${xpath}`, {
        timeout: 5_000,
        state: "attached",
      });
      if (el) return el;
    } catch {
      // fall through
    }
  }

  // Strategy 2: ID attribute
  const elementId = element.id as string | undefined;
  if (elementId) {
    try {
      const el = await page.waitForSelector(`#${elementId}`, {
        timeout: 2_000,
        state: "attached",
      });
      if (el) return el;
    } catch {
      // fall through
    }
  }

  // Strategy 3: Name attribute (forms)
  const name = element.name as string | undefined;
  const tagName = ((element.tagName as string) ?? "").toUpperCase();
  if (name && ["INPUT", "SELECT", "TEXTAREA"].includes(tagName)) {
    try {
      const el = await page.waitForSelector(
        `${tagName.toLowerCase()}[name='${name}']`,
        { timeout: 2_000 },
      );
      if (el) return el;
    } catch {
      // fall through
    }
  }

  // Strategy 4: Text content (buttons, links)
  const textContent = element.textContent as string | undefined;
  if (textContent && ["BUTTON", "A", "SPAN"].includes(tagName)) {
    try {
      const el = await page.waitForSelector(`text=${textContent}`, {
        timeout: 2_000,
      });
      if (el) return el;
    } catch {
      // fall through
    }
  }

  return null;
}

// ===== POST /:sessionId/analyze =====

recordingsRouter.post(
  "/:sessionId/analyze",
  async (req: Request, res: Response) => {
    const { sessionId } = req.params;
    const apiKey = req.headers["x-ami-api-key"] as string | undefined;
    const { user_id } = req.body;
    const userId = user_id ?? "default";

    if (!apiKey) {
      res.status(401).json({ error: "X-Ami-API-Key header required" });
      return;
    }

    try {
      const client = getCloudClient();
      const result = await client.analyzeRecording(sessionId, userId, { apiKey });
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);
