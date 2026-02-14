/**
 * Structured logging — writes to ~/.ami/logs/app.log
 */

import { pino } from "pino";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const logDir = join(homedir(), ".ami", "logs");
mkdirSync(logDir, { recursive: true });

const logFile = join(logDir, "app.log");

const isDebug = !!(process.env.AMI_DEBUG || process.env.LOG_LEVEL === "debug");
const consoleLevel = isDebug ? "debug" : "info";

export const logger = pino({
  level: isDebug ? "debug" : (process.env.LOG_LEVEL ?? "info"),
  transport: {
    targets: [
      {
        target: "pino-pretty",
        options: { colorize: true },
        level: consoleLevel,
      },
      {
        target: "pino/file",
        options: { destination: logFile, mkdir: true },
        level: "debug",
      },
    ],
  },
});

export { isDebug };

export function createLogger(name: string) {
  return logger.child({ module: name });
}
