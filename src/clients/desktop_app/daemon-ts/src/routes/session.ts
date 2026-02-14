/**
 * Session Routes — Conversation persistence API.
 *
 * GET  /api/v1/session              — Get current session with messages
 * GET  /api/v1/session/history      — Get historical messages (cursor-based)
 * POST /api/v1/session/message      — Append a message
 * POST /api/v1/session/new          — Force create new session
 * POST /api/v1/session/touch        — Keep session alive
 */

import { Router, type Request, type Response } from "express";
import { getSessionManager } from "../services/session-manager.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("session-routes");

export const sessionRouter = Router();

// ===== GET / — Get current session =====

sessionRouter.get("/", (req: Request, res: Response) => {
  const limit = parseInt(req.query.limit as string) || 50;
  const manager = getSessionManager();

  const currentId = manager.getCurrentSessionId();
  const isExpired = manager.isSessionExpired();

  // Get active session (may create new one if expired)
  const sessionId = manager.getActiveSession();
  const isNewSession = currentId !== sessionId || currentId === null;

  const info = manager.getSessionInfo(sessionId);
  const messages = manager.getMessages(sessionId, limit);

  res.json({
    session_id: sessionId,
    created_at: info?.created_at ?? "",
    updated_at: info?.updated_at ?? "",
    message_count: info?.message_count ?? 0,
    messages: messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
      attachments: m.attachments ?? null,
      metadata: m.metadata ?? null,
      is_context: m.is_context ?? null,
      from_session: m.from_session ?? null,
    })),
    is_new_session: isNewSession,
  });
});

// ===== GET /history — Cross-session history =====

sessionRouter.get("/history", (req: Request, res: Response) => {
  const beforeTimestamp = req.query.before_timestamp as string;
  const limit = parseInt(req.query.limit as string) || 30;

  if (!beforeTimestamp) {
    res.status(400).json({ error: "before_timestamp query parameter required" });
    return;
  }

  const manager = getSessionManager();
  const result = manager.getHistoryMessages(beforeTimestamp, limit);

  res.json({
    messages: result.messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
      attachments: m.attachments ?? null,
      metadata: m.metadata ?? null,
      is_context: m.is_context ?? null,
      from_session: m.from_session ?? null,
    })),
    has_more: result.has_more,
    oldest_timestamp: result.oldest_timestamp,
  });
});

// ===== POST /message — Append message =====

sessionRouter.post("/message", (req: Request, res: Response) => {
  const { role, content, message_id, attachments, metadata } = req.body;

  if (!role || !content) {
    res.status(400).json({ error: "role and content are required" });
    return;
  }

  const manager = getSessionManager();
  const sessionId = manager.getActiveSession();

  const messageId = manager.appendMessage(
    role,
    content,
    message_id,
    attachments,
    metadata,
  );

  const info = manager.getSessionInfo(sessionId);

  res.json({
    message_id: messageId,
    session_id: sessionId,
    timestamp: info?.updated_at ?? "",
  });
});

// ===== POST /new — Force new session =====

sessionRouter.post("/new", (_req: Request, res: Response) => {
  const manager = getSessionManager();
  const sessionId = manager.forceNewSession();

  const info = manager.getSessionInfo(sessionId);
  const messages = manager.getMessages(sessionId, 50);

  res.json({
    session_id: sessionId,
    created_at: info?.created_at ?? "",
    updated_at: info?.updated_at ?? "",
    message_count: info?.message_count ?? 0,
    messages: messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
      attachments: m.attachments ?? null,
      metadata: m.metadata ?? null,
      is_context: m.is_context ?? null,
      from_session: m.from_session ?? null,
    })),
    is_new_session: true,
  });
});

// ===== POST /touch — Keep alive =====

sessionRouter.post("/touch", (_req: Request, res: Response) => {
  const manager = getSessionManager();
  manager.touchSession();
  res.json({ ok: true });
});
