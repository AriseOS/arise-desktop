/**
 * Session Manager — JSONL-based conversation persistence.
 *
 * Ported from session_manager.py.
 *
 * - Each session is a JSONL file in ~/.ami/sessions/
 * - Sessions timeout after 30 minutes of inactivity
 * - New sessions carry context (last 5 messages) from previous session
 * - Cursor-based cross-session history traversal
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  appendFileSync,
  unlinkSync,
  readdirSync,
} from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { randomUUID } from "node:crypto";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("session-manager");

// ===== Constants =====

const SESSION_TIMEOUT_MINUTES = 30;
const CONTEXT_MESSAGES_COUNT = 5;
const SESSIONS_DIR = join(homedir(), ".ami", "sessions");

// ===== Helpers =====

function generateSessionId(): string {
  return `sess_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

function generateMessageId(): string {
  return `msg_${randomUUID().replace(/-/g, "").slice(0, 8)}`;
}

function utcNowISO(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function sanitizeSessionId(id: string): string {
  return id.replace(/[/\\]/g, "_").replace(/\.\./g, "_");
}

// ===== Types =====

export interface SessionMessage {
  type: "message";
  id: string;
  role: string;
  content: string;
  timestamp: string;
  attachments?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
  is_context?: boolean;
  from_session?: string;
}

interface SessionHeader {
  type: "header";
  session_id: string;
  created_at: string;
  previous_session_id: string | null;
}

interface SessionInfo {
  created_at: string;
  updated_at: string;
  message_count: number;
  previous_session_id: string | null;
}

interface SessionIndex {
  current_session_id: string | null;
  last_activity: string | null;
  sessions: Record<string, SessionInfo>;
}

// ===== SessionManager =====

export class SessionManager {
  readonly basePath: string;
  private indexPath: string;
  private indexCache: SessionIndex | null = null;

  constructor(basePath?: string) {
    this.basePath = basePath ?? SESSIONS_DIR;
    mkdirSync(this.basePath, { recursive: true });
    this.indexPath = join(this.basePath, "index.json");
  }

  // ===== Index Management =====

  private loadIndex(): SessionIndex {
    if (this.indexCache) return this.indexCache;

    if (!existsSync(this.indexPath)) {
      this.indexCache = {
        current_session_id: null,
        last_activity: null,
        sessions: {},
      };
      return this.indexCache;
    }

    try {
      const raw = readFileSync(this.indexPath, "utf-8");
      this.indexCache = JSON.parse(raw) as SessionIndex;
      return this.indexCache;
    } catch {
      this.indexCache = {
        current_session_id: null,
        last_activity: null,
        sessions: {},
      };
      return this.indexCache;
    }
  }

  private saveIndex(): void {
    if (!this.indexCache) return;
    try {
      writeFileSync(
        this.indexPath,
        JSON.stringify(this.indexCache, null, 2),
        "utf-8",
      );
    } catch (err) {
      logger.error({ err }, "Failed to save session index");
    }
  }

  // ===== Session Lifecycle =====

  isSessionExpired(): boolean {
    const index = this.loadIndex();
    const lastActivity = index.last_activity;
    if (!lastActivity) return true;

    try {
      const lastMs = new Date(lastActivity).getTime();
      const nowMs = Date.now();
      return nowMs - lastMs > SESSION_TIMEOUT_MINUTES * 60_000;
    } catch {
      return true;
    }
  }

  private createNewSession(carryContext: boolean = true): string {
    const index = this.loadIndex();
    const previousSessionId = index.current_session_id;

    const newSessionId = generateSessionId();
    const now = utcNowISO();

    // Create session JSONL file with header (sessionId is already safe — generated internally)
    const sessionFile = join(this.basePath, `${sanitizeSessionId(newSessionId)}.jsonl`);
    const header: SessionHeader = {
      type: "header",
      session_id: newSessionId,
      created_at: now,
      previous_session_id: previousSessionId,
    };
    writeFileSync(sessionFile, JSON.stringify(header) + "\n", "utf-8");

    // Update index
    index.current_session_id = newSessionId;
    index.last_activity = now;
    index.sessions[newSessionId] = {
      created_at: now,
      updated_at: now,
      message_count: 0,
      previous_session_id: previousSessionId,
    };
    this.saveIndex();

    logger.info({ sessionId: newSessionId }, "Created new session");

    // Carry context from previous session
    if (carryContext && previousSessionId) {
      this.carryContextFromPrevious(previousSessionId, newSessionId);
    }

    return newSessionId;
  }

  private carryContextFromPrevious(
    previousId: string,
    newId: string,
  ): void {
    const previousFile = join(this.basePath, `${sanitizeSessionId(previousId)}.jsonl`);
    if (!existsSync(previousFile)) return;

    const messages = this.readSessionMessages(previousId);
    const contextMessages = messages.slice(-CONTEXT_MESSAGES_COUNT);
    if (contextMessages.length === 0) return;

    const newFile = join(this.basePath, `${sanitizeSessionId(newId)}.jsonl`);
    for (const msg of contextMessages) {
      msg.is_context = true;
      msg.from_session = previousId;
      appendFileSync(newFile, JSON.stringify(msg) + "\n", "utf-8");
    }

    logger.debug(
      { count: contextMessages.length, from: previousId, to: newId },
      "Carried context messages",
    );
  }

  getActiveSession(): string {
    const index = this.loadIndex();
    if (!index.current_session_id || this.isSessionExpired()) {
      return this.createNewSession(true);
    }
    return index.current_session_id;
  }

  forceNewSession(): string {
    return this.createNewSession(true);
  }

  getCurrentSessionId(): string | null {
    const index = this.loadIndex();
    return index.current_session_id;
  }

  // ===== Message Operations =====

  appendMessage(
    role: string,
    content: string,
    messageId?: string,
    attachments?: Record<string, unknown>[],
    metadata?: Record<string, unknown>,
  ): string {
    const sessionId = this.getActiveSession();
    const sessionFile = join(this.basePath, `${sanitizeSessionId(sessionId)}.jsonl`);

    const id = messageId ?? generateMessageId();
    const now = utcNowISO();

    const message: SessionMessage = {
      type: "message",
      id,
      role,
      content,
      timestamp: now,
    };

    if (attachments) message.attachments = attachments;
    if (metadata) message.metadata = metadata;

    appendFileSync(sessionFile, JSON.stringify(message) + "\n", "utf-8");

    // Update index
    const index = this.loadIndex();
    index.last_activity = now;
    const info = index.sessions[sessionId];
    if (info) {
      info.updated_at = now;
      info.message_count = (info.message_count || 0) + 1;
    }
    this.saveIndex();

    return id;
  }

  getMessages(sessionId?: string, limit: number = 100): SessionMessage[] {
    if (!sessionId) {
      const index = this.loadIndex();
      sessionId = index.current_session_id ?? undefined;
      if (!sessionId) return [];
    }

    const messages = this.readSessionMessages(sessionId);
    if (messages.length > limit) {
      return messages.slice(-limit);
    }
    return messages;
  }

  // ===== Session Info =====

  getSessionInfo(
    sessionId?: string,
  ): SessionInfo | null {
    if (!sessionId) {
      sessionId = this.getCurrentSessionId() ?? undefined;
    }
    if (!sessionId) return null;

    const index = this.loadIndex();
    return index.sessions[sessionId] ?? null;
  }

  listSessions(limit: number = 20): Array<SessionInfo & { session_id: string }> {
    const index = this.loadIndex();
    const sessions: Array<SessionInfo & { session_id: string }> = [];

    for (const [id, info] of Object.entries(index.sessions)) {
      sessions.push({ session_id: id, ...info });
    }

    sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return sessions.slice(0, limit);
  }

  touchSession(): void {
    const index = this.loadIndex();
    if (index.current_session_id) {
      const now = utcNowISO();
      index.last_activity = now;
      this.saveIndex();
    }
  }

  // ===== History Traversal =====

  getHistoryMessages(
    beforeTimestamp: string,
    limit: number = 30,
  ): { messages: SessionMessage[]; has_more: boolean; oldest_timestamp: string | null } {
    const index = this.loadIndex();
    const currentSessionId = index.current_session_id;
    if (!currentSessionId) {
      return { messages: [], has_more: false, oldest_timestamp: null };
    }

    let cursorMs: number;
    try {
      cursorMs = new Date(beforeTimestamp).getTime();
      if (isNaN(cursorMs)) {
        return { messages: [], has_more: false, oldest_timestamp: null };
      }
    } catch {
      return { messages: [], has_more: false, oldest_timestamp: null };
    }

    const collected: SessionMessage[] = [];
    let sessionId: string | null = currentSessionId;
    const visited = new Set<string>();
    let hasMoreSessions = false;

    while (sessionId) {
      if (visited.has(sessionId)) break;
      visited.add(sessionId);

      const messages = this.readSessionMessages(sessionId);

      for (const msg of messages) {
        // Skip context messages (duplicates from carry-over)
        if (msg.is_context) continue;
        if (!msg.timestamp) continue;

        const msgMs = new Date(msg.timestamp).getTime();
        if (isNaN(msgMs)) continue;

        if (msgMs < cursorMs) {
          collected.push(msg);
        }
      }

      // Move to previous session
      sessionId = this.getPreviousSessionId(sessionId);

      if (collected.length > limit && sessionId) {
        hasMoreSessions = true;
        break;
      }
    }

    // Sort by timestamp ascending, take most recent `limit`
    collected.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

    const hasMore = collected.length > limit || hasMoreSessions;
    const resultMessages =
      collected.length > limit ? collected.slice(-limit) : collected;

    const oldestTimestamp =
      resultMessages.length > 0 ? resultMessages[0].timestamp : null;

    return { messages: resultMessages, has_more: hasMore, oldest_timestamp: oldestTimestamp };
  }

  // ===== Internal Helpers =====

  private readSessionMessages(sessionId: string): SessionMessage[] {
    const sessionFile = join(this.basePath, `${sanitizeSessionId(sessionId)}.jsonl`);
    if (!existsSync(sessionFile)) return [];

    const messages: SessionMessage[] = [];
    try {
      const content = readFileSync(sessionFile, "utf-8");
      for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const record = JSON.parse(trimmed);
          if (record.type === "message") {
            messages.push(record as SessionMessage);
          }
        } catch {
          // Skip invalid lines
        }
      }
    } catch {
      // File read error
    }
    return messages;
  }

  private getPreviousSessionId(sessionId: string): string | null {
    const index = this.loadIndex();
    const info = index.sessions[sessionId];
    if (info?.previous_session_id) {
      return info.previous_session_id;
    }

    // Fallback: read from session file header
    const sessionFile = join(this.basePath, `${sanitizeSessionId(sessionId)}.jsonl`);
    if (!existsSync(sessionFile)) return null;

    try {
      const content = readFileSync(sessionFile, "utf-8");
      const firstLine = content.split("\n")[0]?.trim();
      if (firstLine) {
        const header = JSON.parse(firstLine);
        if (header.type === "header") {
          return header.previous_session_id ?? null;
        }
      }
    } catch {
      // Parse error
    }
    return null;
  }
}

// ===== Singleton =====

let _manager: SessionManager | null = null;

export function getSessionManager(): SessionManager {
  if (!_manager) {
    _manager = new SessionManager();
    logger.info({ basePath: _manager.basePath }, "SessionManager initialized");
  }
  return _manager;
}
