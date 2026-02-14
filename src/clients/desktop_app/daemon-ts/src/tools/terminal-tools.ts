/**
 * Terminal Tools — Shell command execution with safety controls.
 *
 * Ported from terminal_toolkit.py.
 *
 * Leverages the same spawn pattern as pi-coding-agent's bash tool
 * but adds AMI-specific safety features (dangerous command blocking,
 * output size limits, SSE terminal events).
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("terminal-tools");

// ===== Safety =====

const DANGEROUS_COMMANDS = [
  "rm -rf /",
  "rm -rf /*",
  "dd if=/dev/",
  "mkfs.",
  ":(){:|:&};:",
  "chmod -R 777 /",
  "chown -R",
  "> /dev/sda",
  "mv / ",
  "wget -O- | sh",
  "curl | sh",
  "curl | bash",
];

const CAUTION_COMMANDS = [
  "sudo",
  "rm -rf",
  "shutdown",
  "reboot",
  "kill -9",
  "killall",
  "pkill",
  "systemctl stop",
  "service stop",
  "iptables",
  "ufw",
  "passwd",
  "useradd",
  "userdel",
  "groupdel",
  "chroot",
  "mount",
  "umount",
  "fdisk",
  "parted",
  "docker rm",
  "docker rmi",
  "npm publish",
  "pip install --force",
];

const DANGEROUS_PATTERNS = [
  /\bbase64\s+-d\b/i,
  /\$\(.*\)/,
  /`.*`/,
  /\beval\b/,
  /\|\s*(sh|bash|zsh|dash)\b/,
  />\s*\/etc\//,
  />\s*\/usr\//,
  />\s*\/bin\//,
];

function validateCommand(
  command: string,
  safeMode: boolean,
): { safe: boolean; warning?: string } {
  const lower = command.toLowerCase().trim();

  // Always block truly dangerous commands
  for (const dc of DANGEROUS_COMMANDS) {
    if (lower.includes(dc)) {
      return { safe: false, warning: `Blocked dangerous command: ${dc}` };
    }
  }

  // Check dangerous patterns
  for (const pattern of DANGEROUS_PATTERNS) {
    if (pattern.test(command)) {
      return {
        safe: false,
        warning: `Blocked command matching dangerous pattern: ${pattern}`,
      };
    }
  }

  if (safeMode) {
    for (const cc of CAUTION_COMMANDS) {
      if (lower.includes(cc)) {
        return {
          safe: true,
          warning: `Caution: command contains '${cc}'`,
        };
      }
    }
  }

  return { safe: true };
}

// ===== Schema =====

const shellExecSchema = Type.Object({
  command: Type.String({ description: "Shell command to execute" }),
  timeout: Type.Optional(
    Type.Number({
      description:
        "Timeout in seconds. Default: 120. Max: 600.",
    }),
  ),
});

// ===== Constants =====

const DEFAULT_TIMEOUT = 120;
const MAX_TIMEOUT = 600;
const MAX_OUTPUT_SIZE = 50_000; // 50KB chars

// ===== Tool Factory =====

export function createTerminalTools(opts: {
  workingDir: string;
  taskId: string;
  emitter?: SSEEmitter;
  safeMode?: boolean;
}): AgentTool<any>[] {
  const { workingDir, taskId, emitter, safeMode = true } = opts;

  const shell_exec: AgentTool<typeof shellExecSchema> = {
    name: "shell_exec",
    label: "Execute Shell Command",
    description:
      "Execute a shell command in the task workspace. Returns stdout+stderr. Output is truncated to 50KB. Use timeout parameter for long-running commands.",
    parameters: shellExecSchema,
    execute: async (_id, params, signal?) => {
      const { command } = params;
      const timeout = Math.min(params.timeout ?? DEFAULT_TIMEOUT, MAX_TIMEOUT);

      // Safety check
      const validation = validateCommand(command, safeMode);
      if (!validation.safe) {
        throw new Error(validation.warning!);
      }
      if (validation.warning) {
        logger.warn({ command: command.slice(0, 100) }, validation.warning);
      }

      const cwd = workingDir;
      if (!existsSync(cwd)) {
        throw new Error(`Working directory does not exist: ${cwd}`);
      }

      logger.info(
        { command: command.slice(0, 200), cwd, timeout },
        "Executing shell command",
      );

      const startTime = Date.now();

      return new Promise((resolve, reject) => {
        const shell = process.env.SHELL ?? "/bin/bash";
        const child = spawn(shell, ["-c", command], {
          cwd,
          detached: true,
          env: { ...process.env },
          stdio: ["ignore", "pipe", "pipe"],
        });

        let output = "";
        let timedOut = false;

        const timeoutHandle = setTimeout(() => {
          timedOut = true;
          if (child.pid) {
            try {
              process.kill(-child.pid, "SIGTERM");
            } catch {
              try {
                child.kill("SIGTERM");
              } catch {
                // already dead
              }
            }
          }
        }, timeout * 1000);

        const appendOutput = (data: Buffer) => {
          const chunk = data.toString("utf-8");
          if (output.length < MAX_OUTPUT_SIZE) {
            output += chunk;
          }
        };

        child.stdout?.on("data", appendOutput);
        child.stderr?.on("data", appendOutput);

        // Abort signal
        const onAbort = () => {
          if (child.pid) {
            try {
              process.kill(-child.pid, "SIGTERM");
            } catch {
              try {
                child.kill("SIGTERM");
              } catch {
                // already dead
              }
            }
          }
        };

        if (signal) {
          if (signal.aborted) {
            onAbort();
          } else {
            signal.addEventListener("abort", onAbort, { once: true });
          }
        }

        child.on("error", (err) => {
          clearTimeout(timeoutHandle);
          signal?.removeEventListener("abort", onAbort);
          reject(err);
        });

        child.on("close", (code) => {
          clearTimeout(timeoutHandle);
          signal?.removeEventListener("abort", onAbort);

          const durationMs = Date.now() - startTime;

          // Truncate if needed
          let truncated = false;
          if (output.length > MAX_OUTPUT_SIZE) {
            output = output.slice(0, MAX_OUTPUT_SIZE);
            output += `\n\n[Output truncated at ${MAX_OUTPUT_SIZE} chars]`;
            truncated = true;
          }

          // Emit terminal SSE event
          emitter?.emit({
            action: Action.terminal,
            task_id: taskId,
            command,
            output: output.slice(0, 2000),
            exit_code: code ?? undefined,
            working_directory: cwd,
            duration_ms: durationMs,
          });

          let resultText: string;

          if (signal?.aborted) {
            resultText = output
              ? `${output}\n\nCommand aborted`
              : "Command aborted";
          } else if (timedOut) {
            resultText = output
              ? `${output}\n\nCommand timed out after ${timeout}s`
              : `Command timed out after ${timeout}s`;
          } else {
            const exitInfo =
              code !== 0 && code !== null
                ? `\n\nExit code: ${code}`
                : "";
            resultText = (output || "(no output)") + exitInfo;
          }

          resolve({
            content: [{ type: "text", text: resultText }],
            details: undefined,
          });
        });
      });
    },
  };

  return [shell_exec];
}
