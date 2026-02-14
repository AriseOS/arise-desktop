/**
 * Express server entry point.
 *
 * - CORS (*)
 * - Port discovery (start at 8765, try up to 10)
 * - Write ~/.ami/daemon.port
 * - Single-instance check via magic health response
 * - Graceful shutdown on SIGTERM/SIGINT
 */

import express from "express";
import cors from "cors";
import { writeFileSync, unlinkSync, existsSync, readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { platform, arch } from "node:process";
import { createServer, type Server } from "node:http";
import { createLogger } from "./utils/logging.js";
import { quickTaskRouter } from "./routes/quick-task.js";
import { browserRouter } from "./routes/browser.js";
import { recordingsRouter } from "./routes/recordings.js";
import { memoryRouter } from "./routes/memory.js";
import { settingsRouter } from "./routes/settings.js";
import { intentBuilderRouter } from "./routes/intent-builder.js";
import { sessionRouter } from "./routes/session.js";
import { integrationsRouter } from "./routes/integrations.js";
import { loadConfig } from "./utils/config.js";
import { getCloudClient } from "./services/cloud-client.js";

const logger = createLogger("server");

// ===== Constants =====

const APP_VERSION = "0.3.0";
const DAEMON_MAGIC = `ami-daemon-${APP_VERSION}`;
const AMI_DIR = join(homedir(), ".ami");
const PORT_FILE = join(AMI_DIR, "daemon.port");
const DEFAULT_PORT = 8765;
const MAX_PORT_TRIES = 10;
const BROWSER_CDP_PORT = process.env.BROWSER_CDP_PORT;

if (BROWSER_CDP_PORT) {
  logger.info({ cdpPort: BROWSER_CDP_PORT }, "Browser CDP port from Electron");
}

// ===== Express App =====

const app = express();

// Middleware
app.use(cors());
app.use(express.json({ limit: "10mb" }));

// ===== Health Check =====

app.get("/api/v1/health", (_req, res) => {
  res.json({
    status: "ok",
    magic: DAEMON_MAGIC,
    version: APP_VERSION,
    browser_ready: !!BROWSER_CDP_PORT,
    platform: `${platform}-${arch}`,
    timestamp: new Date().toISOString(),
  });
});

// ===== Shutdown =====

app.post("/api/v1/app/shutdown", (_req, res) => {
  logger.info("Shutdown requested via API");
  res.json({ status: "shutting_down" });
  // Use SIGTERM to trigger the graceful shutdown handler (which cleans up port file)
  setTimeout(() => process.kill(process.pid, "SIGTERM"), 500);
});

// ===== Version =====

app.get("/api/v1/app/version", async (_req, res) => {
  const platformStr = `${platform}-${arch}`;
  try {
    const client = getCloudClient();
    const result = await client.checkVersion(APP_VERSION, platformStr);
    res.json({
      version: APP_VERSION,
      platform: platformStr,
      compatible: result.compatible,
      update_required: !result.compatible,
      minimum_version: result.minimum_version,
      update_url: result.update_url,
      message: result.message,
      daemon_type: "typescript",
    });
  } catch {
    // Cloud unreachable — assume compatible to avoid blocking the app
    res.json({
      version: APP_VERSION,
      platform: platformStr,
      compatible: true,
      update_required: false,
      daemon_type: "typescript",
    });
  }
});

// ===== Dashboard =====

app.get("/api/v1/dashboard", (req, res) => {
  // Matches Python's dashboard response schema
  res.json({
    has_workflows: false,
    total_workflows: 0,
    total_recordings: 0,
    recent_workflows: [],
  });
});

// ===== Diagnostic =====

app.post("/api/v1/app/diagnostic", (_req, res) => {
  // Collect recent log lines (matching Python's behavior of last 5000 lines)
  let recentLogs = "";
  try {
    const logPath = join(AMI_DIR, "logs", "app.log");
    if (existsSync(logPath)) {
      const logContent = readFileSync(logPath, "utf-8");
      const lines = logContent.split("\n");
      recentLogs = lines.slice(-5000).join("\n");
    }
  } catch {
    recentLogs = "(failed to read logs)";
  }

  res.json({
    system: {
      platform: `${platform}-${arch}`,
      node_version: process.version,
      uptime: process.uptime(),
      memory: process.memoryUsage(),
    },
    browser: {
      cdp_port: BROWSER_CDP_PORT ? parseInt(BROWSER_CDP_PORT) : null,
      connected: !!BROWSER_CDP_PORT,
    },
    daemon_type: "typescript",
    recent_logs: recentLogs,
  });
});

// ===== Mount Routers =====

app.use("/api/v1/quick-task", quickTaskRouter);
app.use("/api/v1/browser", browserRouter);
app.use("/api/v1/recordings", recordingsRouter);
app.use("/api/v1/memory", memoryRouter);
app.use("/api/v1/settings", settingsRouter);
app.use("/api/v1/intent-builder", intentBuilderRouter);
app.use("/api/v1/session", sessionRouter);
app.use("/api/v1/integrations", integrationsRouter);

// ===== Port Discovery =====

function checkExistingDaemon(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = import("node:http").then(({ default: http }) => {
      const request = http.get(`http://127.0.0.1:${port}/api/v1/health`, {
        timeout: 2000,
      }, (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            const json = JSON.parse(data);
            resolve(json.magic?.startsWith("ami-daemon-") ?? false);
          } catch {
            resolve(false);
          }
        });
      });
      request.on("error", () => resolve(false));
      request.on("timeout", () => {
        request.destroy();
        resolve(false);
      });
    });
  });
}

function tryListen(server: Server, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    server.once("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "EADDRINUSE") {
        resolve(false);
      } else {
        throw err;
      }
    });
    server.listen(port, "0.0.0.0", () => {
      resolve(true);
    });
  });
}

// ===== Port File Management =====

function writePortFile(port: number): void {
  mkdirSync(AMI_DIR, { recursive: true });
  writeFileSync(PORT_FILE, String(port), "utf-8");
  logger.info({ port, file: PORT_FILE }, "Port file written");
}

function deletePortFile(): void {
  try {
    if (existsSync(PORT_FILE)) {
      unlinkSync(PORT_FILE);
      logger.info("Port file deleted");
    }
  } catch {
    // Best effort
  }
}

// ===== Startup =====

async function start(): Promise<void> {
  // Load configuration
  loadConfig();

  logger.info("=".repeat(60));
  logger.info(`Starting Ami Daemon v${APP_VERSION} (TypeScript)...`);
  logger.info("=".repeat(60));

  // Check for existing daemon via port file
  if (existsSync(PORT_FILE)) {
    const existingPort = parseInt(readFileSync(PORT_FILE, "utf-8").trim());
    if (!isNaN(existingPort)) {
      const isRunning = await checkExistingDaemon(existingPort);
      if (isRunning) {
        logger.warn(
          { port: existingPort },
          "Another daemon is already running. Exiting.",
        );
        process.exit(1);
      }
      logger.info(
        { port: existingPort },
        "Stale port file found, will overwrite",
      );
    }
  }

  const server = createServer(app);

  // Try ports
  let port = DEFAULT_PORT;
  let bound = false;

  for (let attempt = 0; attempt < MAX_PORT_TRIES; attempt++) {
    const candidatePort = DEFAULT_PORT + attempt;
    bound = await tryListen(server, candidatePort);
    if (bound) {
      port = candidatePort;
      break;
    }
    logger.info({ port: candidatePort }, "Port in use, trying next");
  }

  if (!bound) {
    logger.error("Failed to find available port");
    process.exit(1);
  }

  writePortFile(port);

  logger.info("=".repeat(60));
  logger.info(`Ami Daemon v${APP_VERSION} running on port ${port}`);
  logger.info(`Health: http://127.0.0.1:${port}/api/v1/health`);
  if (BROWSER_CDP_PORT) {
    logger.info(`Browser CDP: ${BROWSER_CDP_PORT}`);
  }
  logger.info("=".repeat(60));

  // Graceful shutdown with re-entrancy guard
  let shutdownCalled = false;
  let exitCode = 0;
  const shutdown = (code = 0) => {
    if (shutdownCalled) return;
    shutdownCalled = true;
    exitCode = code;
    logger.info("Shutting down...");
    deletePortFile();
    server.close(() => {
      logger.info("Server closed");
      process.exit(exitCode);
    });
    // Force exit after 5 seconds
    setTimeout(() => {
      logger.warn("Forced exit after timeout");
      process.exit(exitCode || 1);
    }, 5000);
  };

  process.on("SIGTERM", () => shutdown(0));
  process.on("SIGINT", () => shutdown(0));
  process.on("uncaughtException", (err) => {
    logger.error({ err }, "Uncaught exception");
    // Playwright TimeoutErrors can leak as uncaught exceptions from waitForEvent
    // timers. These are non-fatal — the tool call already handles the error.
    const msg = err?.message ?? "";
    if (msg.includes("Timeout") && msg.includes("waitForEvent")) {
      logger.warn("Suppressed Playwright timeout — not shutting down");
      return;
    }
    shutdown(1);
  });
  process.on("unhandledRejection", (reason) => {
    logger.error({ reason }, "Unhandled rejection");
    // Don't crash on Playwright-related rejections (timeouts, closed pages, etc.)
    const msg = reason instanceof Error ? reason.message : String(reason ?? "");
    if (
      msg.includes("Timeout") ||
      msg.includes("Target closed") ||
      msg.includes("Target page, context or browser has been closed") ||
      msg.includes("Navigation failed") ||
      msg.includes("Frame was detached")
    ) {
      logger.warn("Suppressed Playwright rejection — not shutting down");
      return;
    }
    shutdown(1);
  });
}

start().catch((err) => {
  logger.error({ err }, "Failed to start daemon");
  process.exit(1);
});
