/**
 * Settings Routes — Budget, LLM model, proxy, and credentials configuration.
 *
 * GET  /api/v1/settings              — get all settings
 * POST /api/v1/settings              — update settings
 * GET  /api/v1/settings/budget       — get budget settings (frontend compat)
 * POST /api/v1/settings/budget       — update budget settings (frontend compat)
 * GET  /api/v1/settings/integrations — integration status
 * GET  /api/v1/settings/credentials  — get credentials (API keys masked)
 * POST /api/v1/settings/credentials  — save credentials
 */

import { Router, type Request, type Response } from "express";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { getConfig } from "../utils/config.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("settings-routes");

export const settingsRouter = Router();

// ===== Persisted Settings =====

const AMI_DIR = join(homedir(), ".ami");
const SETTINGS_FILE = join(AMI_DIR, "settings.json");

function loadOverrides(): Record<string, unknown> {
  try {
    if (existsSync(SETTINGS_FILE)) {
      return JSON.parse(readFileSync(SETTINGS_FILE, "utf-8"));
    }
  } catch {
    // corrupted file
  }
  return {};
}

function saveOverrides(data: Record<string, unknown>): void {
  mkdirSync(AMI_DIR, { recursive: true });
  writeFileSync(SETTINGS_FILE, JSON.stringify(data, null, 2), "utf-8");
}

const overrides: Record<string, unknown> = loadOverrides();

// ===== GET / =====

settingsRouter.get("/", (_req: Request, res: Response) => {
  const config = getConfig();

  res.json({
    llm: {
      model: overrides.llm_model ?? config.llm.model,
      use_proxy: overrides.llm_use_proxy ?? config.llm.use_proxy,
      proxy_url: overrides.llm_proxy_url ?? config.llm.proxy_url,
    },
    budget: {
      max_cost_per_task: overrides.budget_max_cost ?? 1.0,
      enabled: overrides.budget_enabled ?? false,
    },
    integrations: {
      gmail: !!process.env.GMAIL_CREDENTIALS_PATH,
      google_calendar: !!(
        process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
      ),
      notion: true, // Always available via MCP
      google_drive: true,
    },
  });
});

// ===== POST / =====

settingsRouter.post("/", (req: Request, res: Response) => {
  const updates = req.body;

  if (updates.llm_model) overrides.llm_model = updates.llm_model;
  if (updates.llm_use_proxy !== undefined)
    overrides.llm_use_proxy = updates.llm_use_proxy;
  if (updates.llm_proxy_url) overrides.llm_proxy_url = updates.llm_proxy_url;
  if (updates.budget_max_cost !== undefined)
    overrides.budget_max_cost = updates.budget_max_cost;
  if (updates.budget_enabled !== undefined)
    overrides.budget_enabled = updates.budget_enabled;

  saveOverrides(overrides);
  logger.info({ updates: Object.keys(updates) }, "Settings updated");

  res.json({ success: true, message: "Settings updated" });
});

// ===== GET /budget =====

settingsRouter.get("/budget", (_req: Request, res: Response) => {
  res.json({
    budget: {
      maxTokens: overrides.budget_max_tokens ?? 200_000,
      maxCostUsd: overrides.budget_max_cost ?? 1.0,
      warningThreshold: overrides.budget_warning_threshold ?? 0.8,
      fallbackModel: overrides.budget_fallback_model ?? null,
      action: overrides.budget_action ?? "warn",
      enabled: overrides.budget_enabled ?? false,
    },
  });
});

// ===== POST /budget =====

settingsRouter.post("/budget", (req: Request, res: Response) => {
  const updates = req.body;

  if (updates.maxTokens !== undefined) overrides.budget_max_tokens = updates.maxTokens;
  if (updates.maxCostUsd !== undefined) overrides.budget_max_cost = updates.maxCostUsd;
  if (updates.warningThreshold !== undefined) overrides.budget_warning_threshold = updates.warningThreshold;
  if (updates.fallbackModel !== undefined) overrides.budget_fallback_model = updates.fallbackModel;
  if (updates.action !== undefined) overrides.budget_action = updates.action;
  if (updates.enabled !== undefined) overrides.budget_enabled = updates.enabled;

  saveOverrides(overrides);
  logger.info({ updates: Object.keys(updates) }, "Budget settings updated");

  res.json({
    success: true,
    message: "Budget settings updated",
    budget: {
      maxTokens: overrides.budget_max_tokens ?? 200_000,
      maxCostUsd: overrides.budget_max_cost ?? 1.0,
      warningThreshold: overrides.budget_warning_threshold ?? 0.8,
      fallbackModel: overrides.budget_fallback_model ?? null,
      action: overrides.budget_action ?? "warn",
      enabled: overrides.budget_enabled ?? false,
    },
  });
});

// ===== GET /integrations =====

settingsRouter.get("/integrations", (_req: Request, res: Response) => {
  res.json({
    gmail: {
      configured: !!process.env.GMAIL_CREDENTIALS_PATH,
      credentials_path: process.env.GMAIL_CREDENTIALS_PATH ?? null,
    },
    google_calendar: {
      configured: !!(
        process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
      ),
    },
    notion: {
      configured: true,
      note: "Notion uses remote MCP, always available",
    },
    google_drive: {
      configured: true,
      note: "Google Drive uses MCP server",
    },
    openai: {
      configured: !!process.env.OPENAI_API_KEY,
      note: "Required for image generation and audio transcription",
    },
  });
});

// ===== GET /credentials =====

function maskApiKey(key: string): string {
  if (key.length <= 10) return "***";
  return key.slice(0, 6) + "***" + key.slice(-4);
}

settingsRouter.get("/credentials", (_req: Request, res: Response) => {
  const creds = (overrides.credentials ?? {}) as Record<string, any>;
  const result: Record<string, any> = {};

  for (const [provider, config] of Object.entries(creds)) {
    if (config && typeof config === "object") {
      result[provider] = {
        ...config,
        api_key: config.api_key ? maskApiKey(config.api_key) : undefined,
      };
    }
  }

  res.json(result);
});

// ===== POST /credentials =====

settingsRouter.post("/credentials", (req: Request, res: Response) => {
  const updates = req.body;

  if (!updates || typeof updates !== "object") {
    res.status(400).json({ error: "Request body must be an object" });
    return;
  }

  const creds = ((overrides.credentials ?? {}) as Record<string, any>);

  for (const [provider, config] of Object.entries(updates)) {
    if (config && typeof config === "object") {
      creds[provider] = { ...(creds[provider] ?? {}), ...config };
    }
  }

  overrides.credentials = creds;
  saveOverrides(overrides);
  logger.info({ providers: Object.keys(updates) }, "Credentials updated");

  res.json({ success: true, message: "Credentials updated" });
});
