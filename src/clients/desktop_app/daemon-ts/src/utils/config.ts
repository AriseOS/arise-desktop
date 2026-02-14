/**
 * Config — Load application configuration from ~/.ami/config/app-backend.yaml.
 *
 * Ported from config_loader pattern in Python daemon.
 */

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { getModel } from "@mariozechner/pi-ai";
import type { Model } from "@mariozechner/pi-ai";
import { createLogger } from "./logging.js";

const logger = createLogger("config");

// ===== Paths =====

export const AMI_DIR = join(homedir(), ".ami");
export const CONFIG_DIR = join(AMI_DIR, "config");
// Config file: daemon-ts/config/app-backend.yaml (relative to dist/)
export const CONFIG_FILE = join(import.meta.dirname, "..", "..", "config", "app-backend.yaml");
export const LOG_DIR = join(AMI_DIR, "logs");
export const PORT_FILE = join(AMI_DIR, "daemon.port");

// ===== Config Interface =====

export interface AppConfig {
  daemon: {
    port: number;
    host: string;
  };
  cloud: {
    api_url: string;
  };
  llm: {
    model: string;
    use_proxy: boolean;
    proxy_url?: string;
  };
  storage: {
    base_path: string;
  };
  browser: {
    auto_start: boolean;
    headless: boolean;
  };
}

// ===== Default Config =====

const DEFAULT_CONFIG: AppConfig = {
  daemon: {
    port: 8765,
    host: "0.0.0.0",
  },
  cloud: {
    api_url: "https://i.ariseos.com",
  },
  llm: {
    model: "claude-sonnet-4-5-20250929",
    use_proxy: false,
  },
  storage: {
    base_path: AMI_DIR,
  },
  browser: {
    auto_start: true,
    headless: false,
  },
};

// ===== Loader =====

let _config: AppConfig | null = null;

export function loadConfig(): AppConfig {
  if (_config) return _config;

  if (existsSync(CONFIG_FILE)) {
    try {
      const raw = readFileSync(CONFIG_FILE, "utf-8");
      // Simple YAML-like parser for flat key-value config
      // For full YAML, install js-yaml
      const parsed = parseSimpleYaml(raw);
      const merged = deepMerge(DEFAULT_CONFIG, parsed) as AppConfig;

      // Handle "auto" for storage.base_path (Python parity)
      if (merged.storage?.base_path === "auto") {
        merged.storage.base_path = AMI_DIR;
      }

      // Expand ${key.path} variable references (Python parity)
      expandVars(merged, merged);

      // Environment variable overrides
      applyEnvOverrides(merged);

      _config = merged;
      logger.info({ file: CONFIG_FILE }, "Config loaded");
    } catch (err) {
      logger.warn({ err, file: CONFIG_FILE }, "Failed to load config, using defaults");
      _config = DEFAULT_CONFIG;
    }
  } else {
    logger.info("No config file found, using defaults");
    _config = { ...DEFAULT_CONFIG };
    applyEnvOverrides(_config);
  }

  return _config;
}

export function getConfig(): AppConfig {
  return _config ?? loadConfig();
}

// ===== Simple YAML Parser (no dependency) =====

function parseSimpleYaml(text: string): Record<string, any> {
  const result: Record<string, any> = {};
  const lines = text.split("\n");
  const stack: { indent: number; obj: Record<string, any> }[] = [
    { indent: -1, obj: result },
  ];

  for (const line of lines) {
    const trimmed = line.trimEnd();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const indent = line.length - line.trimStart().length;
    const match = trimmed.match(/^(\s*)(\w[\w.]*)\s*:\s*(.*)/);
    if (!match) continue;

    const key = match[2];
    // Strip inline comments: "value  # comment" → "value"
    // But not inside quoted strings: "'val # ue'" stays intact
    let rawValue = match[3].trim();
    if (!rawValue.startsWith('"') && !rawValue.startsWith("'")) {
      const commentIdx = rawValue.indexOf("  #");
      if (commentIdx >= 0) {
        rawValue = rawValue.slice(0, commentIdx).trimEnd();
      }
    }

    // Pop stack to correct nesting level
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].obj;

    if (rawValue === "" || rawValue === "|" || rawValue === ">") {
      // Nested object
      const child: Record<string, any> = {};
      parent[key] = child;
      stack.push({ indent, obj: child });
    } else {
      // Scalar value
      parent[key] = parseScalar(rawValue);
    }
  }

  return result;
}

function parseScalar(value: string): string | number | boolean {
  if (value === "true") return true;
  if (value === "false") return false;
  if (value === "null" || value === "~") return "";
  // Remove quotes
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  const num = Number(value);
  if (!isNaN(num) && value !== "") return num;
  return value;
}

// ===== Variable Expansion =====

/**
 * Recursively expand ${key.path} references in config values.
 * Supports config references (dot-notation) and env var fallback.
 * Matches Python ConfigService._expand_vars behavior.
 */
function expandVars(data: any, root: any): void {
  if (typeof data !== "object" || data === null) return;
  for (const key of Object.keys(data)) {
    const value = data[key];
    if (typeof value === "string" && value.includes("${")) {
      data[key] = value.replace(/\$\{([^}]+)\}/g, (_match, ref: string) => {
        // Try dot-notation lookup in config root
        const parts = ref.split(".");
        let cur: any = root;
        for (const p of parts) {
          if (cur && typeof cur === "object" && p in cur) {
            cur = cur[p];
          } else {
            cur = undefined;
            break;
          }
        }
        if (cur !== undefined && typeof cur !== "object") return String(cur);
        // Fallback: environment variable
        return process.env[ref] ?? _match;
      });
    } else if (typeof value === "object") {
      expandVars(value, root);
    }
  }
}

/**
 * Override config values from environment variables.
 * APP_BACKEND_CLOUD_API_URL → cloud.api_url (used by --local flag in run scripts)
 */
function applyEnvOverrides(config: AppConfig): void {
  if (process.env.APP_BACKEND_CLOUD_API_URL) {
    config.cloud.api_url = process.env.APP_BACKEND_CLOUD_API_URL;
    logger.info({ url: config.cloud.api_url }, "Cloud API URL overridden by APP_BACKEND_CLOUD_API_URL");
  }
}

// ===== Settings Overrides =====

const SETTINGS_FILE = join(AMI_DIR, "settings.json");

/**
 * Load user settings overrides from ~/.ami/settings.json.
 * These are saved by the settings route and take priority over yaml config.
 */
function loadSettingsOverrides(): Record<string, unknown> {
  try {
    if (existsSync(SETTINGS_FILE)) {
      return JSON.parse(readFileSync(SETTINGS_FILE, "utf-8"));
    }
  } catch {
    // corrupted file — ignore
  }
  return {};
}

// ===== Configured Model =====

/**
 * Build a Model object from config.
 *
 * Priority: settings.json overrides > app-backend.yaml > defaults.
 * - If llm.use_proxy=true, uses a custom Model with config model ID + proxy baseUrl
 * - Otherwise, uses pi-ai's built-in getModel() with Anthropic defaults
 */
export function getConfiguredModel(): Model<"anthropic-messages"> {
  const config = getConfig();
  const overrides = loadSettingsOverrides();

  // Settings overrides take priority over yaml config
  const model = (overrides.llm_model as string) ?? config.llm.model;
  const use_proxy = (overrides.llm_use_proxy as boolean) ?? config.llm.use_proxy;
  const proxy_url = (overrides.llm_proxy_url as string) ?? config.llm.proxy_url;

  if (use_proxy && proxy_url) {
    // CRS proxy mode: construct Model manually
    return {
      id: model,
      name: model,
      api: "anthropic-messages",
      provider: "anthropic",
      baseUrl: proxy_url,
      reasoning: false,
      input: ["text", "image"],
      cost: { input: 3, output: 15, cacheRead: 0.3, cacheWrite: 3.75 },
      contextWindow: 200000,
      maxTokens: 64000,
    };
  }

  // Direct mode: use pi-ai's built-in model registry
  const piModel = getModel("anthropic", model as any);
  if (!piModel) {
    throw new Error(`Unknown model "${model}" — check llm.model in config`);
  }
  return piModel as Model<"anthropic-messages">;
}

// ===== Credential Resolution =====

/**
 * Resolve Anthropic API key.
 * Priority: settings.json credentials → ANTHROPIC_API_KEY env var.
 */
export function getAnthropicApiKey(): string | undefined {
  const overrides = loadSettingsOverrides();
  const creds = overrides.credentials as Record<string, any> | undefined;
  return creds?.anthropic?.api_key ?? process.env.ANTHROPIC_API_KEY;
}

/**
 * Resolve Anthropic base URL.
 * Priority: settings.json credentials → ANTHROPIC_BASE_URL env var.
 */
export function getAnthropicBaseUrl(): string | undefined {
  const overrides = loadSettingsOverrides();
  const creds = overrides.credentials as Record<string, any> | undefined;
  return creds?.anthropic?.base_url ?? process.env.ANTHROPIC_BASE_URL;
}

// ===== Utilities =====

function deepMerge(target: any, source: any): any {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === "object" &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === "object"
    ) {
      result[key] = deepMerge(target[key], source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}
