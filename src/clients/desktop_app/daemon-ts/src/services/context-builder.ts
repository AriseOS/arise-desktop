/**
 * Context Builder — Conversation context formatting for LLM prompts.
 *
 * Ported from context_builder.py.
 *
 * Builds and formats conversation context for LLM prompt injection.
 * Collects files from working directories, checks history limits,
 * and summarizes long histories.
 */

import { existsSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import type { TaskState } from "./task-state.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("context-builder");

// ===== Constants =====

const DEFAULT_MAX_HISTORY_LENGTH = 100_000; // 100KB
const DEFAULT_MAX_CONTEXT_ENTRIES = 20;
const DEFAULT_MAX_FILES_TO_LIST = 50;
const CONTEXT_WARNING_THRESHOLD = 0.80;

const SKIP_DIRECTORIES = new Set([
  "node_modules",
  "__pycache__",
  ".git",
  ".venv",
  "venv",
  ".env",
  "dist",
  "build",
  ".next",
  ".cache",
]);

const SKIP_EXTENSIONS = new Set([
  ".pyc",
  ".pyo",
  ".so",
  ".dll",
  ".dylib",
  ".exe",
  ".o",
  ".obj",
  ".class",
  ".jar",
  ".war",
]);

// ===== Types =====

interface ConversationEntry {
  role: string;
  content: string | Record<string, unknown>;
}

interface TaskResult {
  task?: string;
  summary?: string;
  status?: string;
  files_created?: string[];
  working_directory?: string;
}

// ===== Build Context =====

/**
 * Build conversation context from task state history.
 */
export function buildConversationContext(
  state: TaskState,
  opts?: {
    header?: string;
    skipFiles?: boolean;
    maxEntries?: number;
    includeToolCalls?: boolean;
  },
): string {
  const history = state.conversationHistory;
  if (!history || history.length === 0) return "";

  const header = opts?.header ?? "=== CONVERSATION HISTORY ===";
  const skipFiles = opts?.skipFiles ?? false;
  const maxEntries = opts?.maxEntries;
  const includeToolCalls = opts?.includeToolCalls ?? false;

  const parts: string[] = [header];
  const workingDirectories = new Set<string>();

  const entries = maxEntries != null ? history.slice(-maxEntries) : history;

  for (const entry of entries) {
    if (entry.role === "tool_call" && !includeToolCalls) continue;

    if (entry.role === "task_result") {
      try {
        const result: TaskResult = JSON.parse(entry.content);
        parts.push(formatTaskResult(result, skipFiles));
        if (result.working_directory) {
          workingDirectories.add(result.working_directory);
        }
      } catch {
        parts.push(`Task Result: ${entry.content}`);
      }
    } else if (entry.role === "assistant") {
      const content = truncateContent(entry.content, 2000);
      parts.push(`Assistant: ${content}`);
    } else if (entry.role === "user") {
      const content = truncateContent(entry.content, 1000);
      parts.push(`User: ${content}`);
    } else if (entry.role === "tool_call") {
      try {
        const tc: Record<string, unknown> = JSON.parse(entry.content);
        const toolName = tc.name ?? "unknown";
        const toolResult = truncateContent(String(tc.result ?? ""), 200);
        parts.push(`Tool [${toolName}]: ${toolResult}`);
      } catch {
        parts.push(`Tool: ${truncateContent(entry.content, 200)}`);
      }
    } else if (entry.role === "system") {
      const content = truncateContent(entry.content, 500);
      parts.push(`System: ${content}`);
    }
  }

  // Collect files from working directories
  if (!skipFiles && workingDirectories.size > 0) {
    const filesCtx = collectWorkingDirectoryFiles(workingDirectories);
    if (filesCtx) parts.push(filesCtx);
  }

  return parts.join("\n\n");
}

// ===== Format Task Result =====

function formatTaskResult(result: TaskResult, skipFiles: boolean): string {
  const parts = ["Task Result:"];

  if (result.task) {
    parts.push(`  Task: ${truncateContent(result.task, 200)}`);
  }
  if (result.summary) {
    parts.push(`  Summary: ${truncateContent(result.summary, 500)}`);
  }
  if (result.status) {
    parts.push(`  Status: ${result.status}`);
  }
  if (!skipFiles && result.files_created && result.files_created.length > 0) {
    let files = result.files_created.slice(0, 10).join(", ");
    if (result.files_created.length > 10) {
      files += ` ... (+${result.files_created.length - 10} more)`;
    }
    parts.push(`  Files Created: ${files}`);
  }
  if (result.working_directory) {
    parts.push(`  Working Directory: ${result.working_directory}`);
  }

  return parts.join("\n");
}

// ===== Truncate =====

function truncateContent(content: string, maxLength: number): string {
  if (content.length > maxLength) {
    return content.slice(0, maxLength) + "...";
  }
  return content;
}

// ===== Collect Files =====

function collectWorkingDirectoryFiles(
  directories: Set<string>,
  maxFiles: number = DEFAULT_MAX_FILES_TO_LIST,
): string {
  const allFiles: string[] = [];

  for (const directory of directories) {
    try {
      if (!existsSync(directory)) continue;

      const walk = (dir: string) => {
        if (allFiles.length >= maxFiles * 2) return;

        let entries: string[];
        try {
          entries = readdirSync(dir);
        } catch {
          return;
        }

        for (const name of entries) {
          if (name.startsWith(".")) continue;
          if (SKIP_DIRECTORIES.has(name)) continue;

          const fullPath = join(dir, name);
          try {
            const stat = statSync(fullPath);
            if (stat.isDirectory()) {
              walk(fullPath);
            } else {
              const ext = name.lastIndexOf(".") >= 0
                ? name.slice(name.lastIndexOf(".")).toLowerCase()
                : "";
              if (SKIP_EXTENSIONS.has(ext)) continue;

              try {
                allFiles.push(relative(directory, fullPath));
              } catch {
                allFiles.push(fullPath);
              }
            }
          } catch {
            // Permission or stat error
          }

          if (allFiles.length >= maxFiles * 2) return;
        }
      };

      walk(directory);
    } catch {
      // Directory access error
    }
  }

  if (allFiles.length === 0) return "";

  const unique = [...new Set(allFiles)].sort().slice(0, maxFiles);
  const parts = ["Generated Files:"];
  for (const f of unique) {
    parts.push(`  - ${f}`);
  }
  if (unique.length === maxFiles) {
    parts.push(`  ... (showing first ${maxFiles} files)`);
  }

  return parts.join("\n");
}

// ===== History Length Check =====

/**
 * Check if conversation history exceeds maximum length.
 */
export function checkHistoryLength(
  state: TaskState,
  maxLength: number = DEFAULT_MAX_HISTORY_LENGTH,
): { exceeded: boolean; totalLength: number } {
  let totalLength = 0;
  for (const entry of state.conversationHistory) {
    totalLength += typeof entry.content === "string"
      ? entry.content.length
      : JSON.stringify(entry.content).length;
  }
  return { exceeded: totalLength > maxLength, totalLength };
}

/**
 * Build enhanced prompt with conversation context + current task.
 */
export function buildEnhancedPrompt(
  state: TaskState,
  currentTask: string,
  opts?: {
    includeContext?: boolean;
    maxContextEntries?: number;
  },
): string {
  const parts: string[] = [];

  const includeContext = opts?.includeContext ?? true;
  const maxContextEntries = opts?.maxContextEntries ?? DEFAULT_MAX_CONTEXT_ENTRIES;

  if (includeContext && state.conversationHistory.length > 0) {
    const context = buildConversationContext(state, {
      maxEntries: maxContextEntries,
      skipFiles: false,
    });
    if (context) parts.push(context);
  }

  parts.push("=== CURRENT TASK ===");
  parts.push(currentTask);

  return parts.join("\n\n");
}

// ===== Recording Helpers =====

export function recordTaskCompletion(
  state: TaskState,
  summary: string,
  filesCreated?: string[],
  status: string = "completed",
): void {
  const content: Record<string, unknown> = {
    task: state.task,
    summary,
    status,
  };
  if (filesCreated) content.files_created = filesCreated;
  state.addConversation("task_result", JSON.stringify(content));
}

export function recordUserMessage(state: TaskState, message: string): void {
  state.addConversation("user", message);
}

export function recordAssistantResponse(state: TaskState, response: string): void {
  state.addConversation("assistant", response);
}

export function recordToolCall(
  state: TaskState,
  toolName: string,
  toolInput?: Record<string, unknown>,
  toolResult?: string,
): void {
  state.addConversation(
    "tool_call",
    JSON.stringify({ name: toolName, input: toolInput, result: toolResult }),
  );
}
