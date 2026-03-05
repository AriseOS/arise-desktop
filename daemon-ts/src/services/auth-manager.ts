/**
 * Auth Manager — Central JWT token management for the daemon.
 *
 * Single source of truth for auth state. Persists session to ~/.arise/session.json.
 * Auto-refreshes tokens before expiry. Thread-safe via refresh mutex.
 *
 * Exports:
 * - getAuthToken()   — returns valid access_token, auto-refreshes if expiring soon
 * - storeSession()   — persist tokens + user info to file
 * - clearSession()   — delete session file
 * - getSession()     — returns user info (no tokens exposed)
 * - hasSession()     — quick check if session exists
 */

import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { AMI_DIR, getConfig } from "../utils/config.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("auth-manager");

// ===== Session File =====

const SESSION_FILE = join(AMI_DIR, "session.json");

interface StoredSession {
  access_token: string;
  refresh_token: string;
  username: string;
  user_id: string;
  email: string;
  stored_at: string;
}

export interface SessionInfo {
  logged_in: boolean;
  username?: string;
  user_id?: string;
  email?: string;
}

// ===== File I/O =====

function readSessionFile(): StoredSession | null {
  try {
    if (!existsSync(SESSION_FILE)) return null;
    const raw = readFileSync(SESSION_FILE, "utf-8");
    return JSON.parse(raw) as StoredSession;
  } catch {
    logger.warn("Failed to read session file, treating as no session");
    return null;
  }
}

function writeSessionFile(session: StoredSession): void {
  try {
    mkdirSync(dirname(SESSION_FILE), { recursive: true });
    writeFileSync(SESSION_FILE, JSON.stringify(session, null, 2), "utf-8");
  } catch (err) {
    logger.error({ err }, "Failed to write session file");
    throw new Error("Failed to persist session");
  }
}

// ===== JWT Expiry Check =====

/**
 * Decode JWT payload without crypto verification.
 * Returns the exp claim (seconds since epoch) or null.
 */
function getJwtExp(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(
      Buffer.from(parts[1], "base64url").toString("utf-8"),
    );
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

/**
 * Check if token is expiring within the given margin (seconds).
 */
function isTokenExpiringSoon(token: string, marginSeconds = 300): boolean {
  const exp = getJwtExp(token);
  if (exp === null) return true; // can't determine → treat as expired
  const now = Math.floor(Date.now() / 1000);
  return exp - now < marginSeconds;
}

// ===== Refresh Mutex =====

let _refreshPromise: Promise<string | null> | null = null;

/**
 * Refresh the access token using the stored refresh_token.
 * Returns the new access_token, or null on failure.
 * Uses a mutex to prevent concurrent refresh calls.
 */
async function refreshAccessToken(): Promise<string | null> {
  // If a refresh is already in-flight, wait for it
  if (_refreshPromise) {
    return _refreshPromise;
  }

  _refreshPromise = _doRefresh();
  try {
    return await _refreshPromise;
  } finally {
    _refreshPromise = null;
  }
}

async function _doRefresh(): Promise<string | null> {
  const session = readSessionFile();
  if (!session?.refresh_token) {
    logger.warn("No refresh_token available for refresh");
    return null;
  }

  const apiUrl = getConfig().cloud.api_url;
  const url = `${apiUrl}/api/v1/auth/refresh`;

  logger.info({ url }, "Refreshing access token...");

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
      signal: AbortSignal.timeout(15_000),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      logger.error({ status: resp.status, text }, "Token refresh failed");
      return null;
    }

    const data = (await resp.json()) as {
      access_token: string;
      refresh_token?: string;
    };

    // Update stored session with new tokens
    session.access_token = data.access_token;
    if (data.refresh_token) {
      session.refresh_token = data.refresh_token;
    }
    session.stored_at = new Date().toISOString();
    writeSessionFile(session);

    logger.info("Access token refreshed successfully");
    return data.access_token;
  } catch (err) {
    logger.error({ err }, "Token refresh request failed");
    return null;
  }
}

// ===== Public API =====

/**
 * Get a valid access token. Auto-refreshes if expiring within 5 minutes.
 * Returns null if no session or refresh fails.
 */
export async function getAuthToken(): Promise<string | null> {
  const session = readSessionFile();
  if (!session?.access_token) {
    return null;
  }

  // If token is still fresh, return it directly
  if (!isTokenExpiringSoon(session.access_token, 300)) {
    return session.access_token;
  }

  // Token is expiring soon — try to refresh
  logger.info("Token expiring soon, attempting refresh");
  const newToken = await refreshAccessToken();
  return newToken ?? session.access_token; // fallback to old token if refresh fails
}

/**
 * Store a new session (called after login/register).
 */
export function storeSession(data: {
  access_token: string;
  refresh_token: string;
  username: string;
  user_id: string;
  email?: string;
}): void {
  const session: StoredSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    username: data.username,
    user_id: data.user_id,
    email: data.email ?? "",
    stored_at: new Date().toISOString(),
  };
  writeSessionFile(session);
  logger.info({ username: data.username }, "Session stored");
}

/**
 * Update tokens in an existing session (called after token refresh).
 * Only overwrites fields that are provided; preserves everything else.
 */
export function updateSessionTokens(data: {
  access_token: string;
  refresh_token?: string;
}): void {
  const session = readSessionFile();
  if (!session) {
    logger.warn("No existing session to update tokens for");
    return;
  }

  session.access_token = data.access_token;
  if (data.refresh_token) {
    session.refresh_token = data.refresh_token;
  }
  session.stored_at = new Date().toISOString();
  writeSessionFile(session);
  logger.info("Session tokens updated");
}

/**
 * Clear the stored session (logout).
 */
export function clearSession(): void {
  try {
    if (existsSync(SESSION_FILE)) {
      unlinkSync(SESSION_FILE);
      logger.info("Session cleared");
    }
  } catch (err) {
    logger.error({ err }, "Failed to clear session file");
  }
}

/**
 * Get public session info (no tokens exposed).
 */
export function getSession(): SessionInfo {
  const session = readSessionFile();
  if (!session?.access_token) {
    return { logged_in: false };
  }

  return {
    logged_in: true,
    username: session.username,
    user_id: session.user_id,
    email: session.email,
  };
}

/**
 * Quick check if a session exists.
 */
export function hasSession(): boolean {
  const session = readSessionFile();
  return !!session?.access_token;
}
