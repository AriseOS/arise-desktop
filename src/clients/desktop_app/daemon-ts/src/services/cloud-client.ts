/**
 * Cloud Client — HTTP client for AMI cloud backend API.
 *
 * Ported from CloudClient in Python daemon.
 *
 * Endpoints: check_version, memory/plan, memory/query, memory/learn,
 * memory/add, memory/stats, memory/phrases, recordings, intent-builder, etc.
 */

import { createLogger } from "../utils/logging.js";
import { getConfig } from "../utils/config.js";

const logger = createLogger("cloud-client");

// ===== Cloud Client =====

/** Per-request credentials to avoid singleton mutation races */
export interface RequestCredentials {
  apiKey?: string;
  userId?: string;
}

export class CloudClient {
  private baseUrl: string;
  private timeout = 30_000;

  constructor(opts?: { baseUrl?: string }) {
    this.baseUrl = opts?.baseUrl ?? getConfig().cloud.api_url;
    logger.info({ baseUrl: this.baseUrl }, "CloudClient initialized");
  }

  // ===== Generic Request =====

  private async request(
    method: string,
    path: string,
    body?: unknown,
    extraHeaders?: Record<string, string>,
    creds?: RequestCredentials,
    timeoutMs?: number,
  ): Promise<unknown> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...extraHeaders,
    };

    if (creds?.apiKey) {
      headers["X-Ami-API-Key"] = creds.apiKey;
    }
    if (creds?.userId) {
      headers["X-User-Id"] = creds.userId;
    }

    logger.debug({ method, path }, "Cloud API request");

    const resp = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeoutMs ?? this.timeout),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Cloud API error ${resp.status} ${method} ${path}: ${text}`);
    }

    const contentType = resp.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      return resp.json();
    }
    return resp.text();
  }

  private get(path: string, creds?: RequestCredentials, extraHeaders?: Record<string, string>) {
    return this.request("GET", path, undefined, extraHeaders, creds);
  }

  private post(path: string, body?: unknown, creds?: RequestCredentials, extraHeaders?: Record<string, string>) {
    return this.request("POST", path, body, extraHeaders, creds);
  }

  private del(path: string, creds?: RequestCredentials, extraHeaders?: Record<string, string>) {
    return this.request("DELETE", path, undefined, extraHeaders, creds);
  }

  private patch(path: string, body?: unknown, creds?: RequestCredentials, extraHeaders?: Record<string, string>) {
    return this.request("PATCH", path, body, extraHeaders, creds);
  }

  // ===== Version =====

  async checkVersion(clientVersion: string, platform: string, creds?: RequestCredentials): Promise<{
    compatible: boolean;
    minimum_version?: string;
    update_url?: string;
    message?: string;
  }> {
    try {
      const result = (await this.post(
        "/api/v1/app/version-check",
        { version: clientVersion, platform },
        creds,
      )) as any;
      return result;
    } catch (err) {
      logger.warn({ err }, "Version check failed");
      return { compatible: true };
    }
  }

  // ===== Memory API =====

  async memoryQuery(body: Record<string, unknown>, creds?: RequestCredentials): Promise<unknown> {
    return this.post("/api/v1/memory/query", body, creds);
  }

  async memoryPlan(body: Record<string, unknown>, creds?: RequestCredentials): Promise<unknown> {
    // PlannerAgent runs LLM agent loop — needs longer timeout than default 30s
    return this.request("POST", "/api/v1/memory/plan", body, undefined, creds, 120_000);
  }

  async memoryLearn(body: Record<string, unknown>, creds?: RequestCredentials): Promise<unknown> {
    // LearnerAgent runs LLM agent loop with tool calls — typically 20-50s, can exceed 60s for large tasks
    return this.request("POST", "/api/v1/memory/learn", body, undefined, creds, 120_000);
  }

  async memoryAdd(body: Record<string, unknown>, creds?: RequestCredentials): Promise<unknown> {
    return this.post("/api/v1/memory/add", body, creds);
  }

  async memoryStats(creds?: RequestCredentials): Promise<unknown> {
    return this.get("/api/v1/memory/stats", creds);
  }

  async memoryDelete(creds?: RequestCredentials): Promise<unknown> {
    return this.del("/api/v1/memory", creds);
  }

  // ===== CognitivePhrase API =====

  async listPhrases(limit = 50, creds?: RequestCredentials): Promise<unknown> {
    return this.get(`/api/v1/memory/phrases?limit=${limit}`, creds);
  }

  async listPublicPhrases(limit = 50, sort = "popular", creds?: RequestCredentials): Promise<unknown> {
    return this.get(`/api/v1/memory/phrases/public?limit=${limit}&sort=${sort}`, creds);
  }

  async getPhrase(phraseId: string, source?: string, creds?: RequestCredentials): Promise<unknown> {
    const query = source ? `?source=${source}` : "";
    return this.get(`/api/v1/memory/phrases/${phraseId}${query}`, creds);
  }

  async deletePhrase(phraseId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.del(`/api/v1/memory/phrases/${phraseId}`, creds);
  }

  async publishPhrase(phraseId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.post("/api/v1/memory/share", { phrase_id: phraseId }, creds);
  }

  async unpublishPhrase(phraseId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.post("/api/v1/memory/unpublish", { phrase_id: phraseId }, creds);
  }

  async getPublishStatus(creds?: RequestCredentials): Promise<unknown> {
    return this.get("/api/v1/memory/publish-status", creds);
  }

  // ===== Recordings =====

  async getRecording(sessionId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.get(`/api/v1/recordings/${sessionId}`, creds);
  }

  async analyzeRecording(sessionId: string, userId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.post(`/api/v1/recordings/${sessionId}/analyze`, {
      user_id: userId,
    }, creds);
  }

  // ===== Intent Builder =====

  async createIntentBuilderSession(body: Record<string, unknown>, creds?: RequestCredentials): Promise<unknown> {
    return this.post("/api/v1/intent-builder/sessions", body, creds);
  }

  async intentBuilderChat(sessionId: string, message: string, creds?: RequestCredentials): Promise<unknown> {
    return this.post(`/api/v1/intent-builder/sessions/${sessionId}/chat`, {
      message,
    }, creds);
  }

  async getIntentBuilderState(sessionId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.get(`/api/v1/intent-builder/sessions/${sessionId}/state`, creds);
  }

  async deleteIntentBuilderSession(sessionId: string, creds?: RequestCredentials): Promise<unknown> {
    return this.del(`/api/v1/intent-builder/sessions/${sessionId}`, creds);
  }

  /**
   * Stream SSE from intent builder session.
   * Returns raw fetch Response for SSE streaming.
   */
  async intentBuilderStream(sessionId: string, creds?: RequestCredentials): Promise<Response> {
    const url = `${this.baseUrl}/api/v1/intent-builder/sessions/${sessionId}/stream`;
    const headers: Record<string, string> = {};
    if (creds?.apiKey) headers["X-Ami-API-Key"] = creds.apiKey;
    if (creds?.userId) headers["X-User-Id"] = creds.userId;

    // SSE streams are long-lived — use 10 min timeout instead of the default 30s
    return fetch(url, {
      headers,
      signal: AbortSignal.timeout(600_000),
    });
  }
}

// ===== Singleton =====

let _client: CloudClient | null = null;

export function getCloudClient(): CloudClient {
  if (!_client) {
    _client = new CloudClient();
  }
  return _client;
}

export function setCloudClient(client: CloudClient): void {
  _client = client;
}
