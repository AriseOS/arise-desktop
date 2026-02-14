/**
 * Integrations Routes — OAuth & API key management for third-party services.
 *
 * Ported from integrations.py.
 *
 * GET  /api/v1/integrations/list                 — List installed/available integrations
 * GET  /api/v1/integrations/oauth-status/:id      — Check OAuth flow status
 * POST /api/v1/integrations/oauth-callback/:id    — Handle OAuth callback
 * POST /api/v1/integrations/configure/:id         — Configure API-key integration
 * POST /api/v1/integrations/uninstall/:id         — Remove integration
 * GET  /api/v1/integrations/config/:id            — Get integration config (no secrets)
 */

import { Router, type Request, type Response } from "express";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("integrations");

export const integrationsRouter = Router();

// ===== Storage =====

const AMI_DIR = join(homedir(), ".ami");
const INTEGRATIONS_FILE = join(AMI_DIR, "integrations.json");

const AVAILABLE_INTEGRATIONS = ["gmail", "google_drive", "google_calendar", "notion"];

interface IntegrationData {
  installed: string[];
  configs: Record<string, { api_key?: string; configured_at?: string }>;
}

function loadIntegrations(): IntegrationData {
  try {
    if (existsSync(INTEGRATIONS_FILE)) {
      return JSON.parse(readFileSync(INTEGRATIONS_FILE, "utf-8"));
    }
  } catch {
    // corrupted file
  }
  return { installed: [], configs: {} };
}

function saveIntegrations(data: IntegrationData): void {
  mkdirSync(AMI_DIR, { recursive: true });
  writeFileSync(INTEGRATIONS_FILE, JSON.stringify(data, null, 2), "utf-8");
}

// ===== In-memory OAuth state =====

const oauthStates = new Map<string, { completed: boolean; failed: boolean; error?: string }>();

// ===== GET /list =====

integrationsRouter.get("/list", (_req: Request, res: Response) => {
  const data = loadIntegrations();
  res.json({
    installed: data.installed,
    available: AVAILABLE_INTEGRATIONS,
  });
});

// ===== GET /oauth-status/:integrationId =====

integrationsRouter.get("/oauth-status/:integrationId", (req: Request, res: Response) => {
  const { integrationId } = req.params;
  const state = oauthStates.get(integrationId);

  if (state) {
    res.json(state);
    return;
  }

  // Check if already installed
  const data = loadIntegrations();
  if (data.installed.includes(integrationId)) {
    res.json({ completed: true, failed: false, error: null });
    return;
  }

  res.json({ completed: false, failed: false, error: null });
});

// ===== POST /oauth-callback/:integrationId =====

integrationsRouter.post("/oauth-callback/:integrationId", (req: Request, res: Response) => {
  const { integrationId } = req.params;
  const code = req.query.code as string | undefined;

  const googleServices = ["gmail", "google_drive", "google_calendar"];
  if (!googleServices.includes(integrationId)) {
    res.status(400).json({ error: `Invalid integration: ${integrationId}` });
    return;
  }

  try {
    oauthStates.set(integrationId, { completed: true, failed: false });

    const data = loadIntegrations();
    if (!data.installed.includes(integrationId)) {
      data.installed.push(integrationId);
    }
    saveIntegrations(data);

    logger.info({ integrationId }, "OAuth completed");
    res.json({ success: true, message: "OAuth completed" });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    oauthStates.set(integrationId, { completed: false, failed: true, error: msg });
    res.status(500).json({ error: msg });
  }
});

// ===== POST /configure/:integrationId =====

integrationsRouter.post("/configure/:integrationId", (req: Request, res: Response) => {
  const { integrationId } = req.params;
  const { api_key } = req.body;

  if (integrationId !== "notion") {
    res.status(400).json({ error: `Configuration not supported for: ${integrationId}` });
    return;
  }

  if (!api_key || typeof api_key !== "string" || !api_key.startsWith("secret_")) {
    res.status(400).json({ error: "Invalid API key format (must start with 'secret_')" });
    return;
  }

  try {
    const data = loadIntegrations();
    data.configs[integrationId] = {
      api_key,
      configured_at: new Date().toISOString(),
    };
    if (!data.installed.includes(integrationId)) {
      data.installed.push(integrationId);
    }
    saveIntegrations(data);

    logger.info({ integrationId }, "Integration configured");
    res.json({ success: true, message: `${integrationId} configured successfully` });
  } catch (err) {
    res.status(500).json({ error: `Configuration failed: ${err}` });
  }
});

// ===== POST /uninstall/:integrationId =====

integrationsRouter.post("/uninstall/:integrationId", (req: Request, res: Response) => {
  const { integrationId } = req.params;

  try {
    const data = loadIntegrations();
    data.installed = data.installed.filter((id) => id !== integrationId);
    delete data.configs[integrationId];
    saveIntegrations(data);

    oauthStates.delete(integrationId);

    logger.info({ integrationId }, "Integration uninstalled");
    res.json({ success: true, message: `${integrationId} uninstalled` });
  } catch (err) {
    res.status(500).json({ error: `Uninstall failed: ${err}` });
  }
});

// ===== GET /config/:integrationId =====

integrationsRouter.get("/config/:integrationId", (req: Request, res: Response) => {
  const { integrationId } = req.params;
  const data = loadIntegrations();

  if (!data.installed.includes(integrationId)) {
    res.status(404).json({ error: `Integration not installed: ${integrationId}` });
    return;
  }

  const config = data.configs[integrationId];
  res.json({
    integration_id: integrationId,
    installed: true,
    configured_at: config?.configured_at ?? null,
    has_api_key: !!config?.api_key,
  });
});
