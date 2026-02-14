/**
 * File Tools — File reading, writing, and management as AgentTool[].
 *
 * Ported from file_toolkit.py.
 *
 * Tools: write_to_file, append_to_file, read_file, file_exists, list_files.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import {
  writeFile,
  readFile,
  appendFile,
  mkdir,
  access,
  readdir,
  stat,
  copyFile,
} from "node:fs/promises";
import { join, resolve, dirname, basename, extname } from "node:path";
import { constants } from "node:fs";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";
import { renderMarkdownToPdf } from "./pdf-renderer.js";
import { renderMarkdownToDocx } from "./docx-renderer.js";

const logger = createLogger("file-tools");

// ===== Schemas =====

const writeFileSchema = Type.Object({
  content: Type.String({ description: "Content to write to the file" }),
  filename: Type.String({
    description:
      "File name with extension (e.g., 'report.md', 'data.csv'). Relative paths resolved against working directory.",
  }),
  create_backup: Type.Optional(
    Type.Boolean({
      description: "Create a backup of existing file before overwriting",
    }),
  ),
});

const appendFileSchema = Type.Object({
  content: Type.String({ description: "Content to append" }),
  filename: Type.String({ description: "File name or path" }),
});

const readFileSchema = Type.Object({
  filename: Type.String({ description: "File name or path to read" }),
  offset: Type.Optional(
    Type.Number({ description: "Line number to start reading from (1-indexed)" }),
  ),
  limit: Type.Optional(
    Type.Number({ description: "Maximum number of lines to read" }),
  ),
});

const fileExistsSchema = Type.Object({
  filename: Type.String({ description: "File name or path to check" }),
});

const listFilesSchema = Type.Object({
  directory: Type.Optional(
    Type.String({
      description: "Directory to list. Defaults to working directory.",
    }),
  ),
  pattern: Type.Optional(
    Type.String({ description: "Glob-like filter pattern (e.g., '*.csv')" }),
  ),
});

// ===== Helpers =====

function resolvePath(filename: string, workingDir: string): string {
  let resolved: string;
  if (filename.startsWith("/") || filename.startsWith("~")) {
    resolved = resolve(filename.replace(/^~/, process.env.HOME ?? "/tmp"));
  } else {
    resolved = resolve(workingDir, filename);
  }

  // Validate the resolved path stays within the working directory to prevent
  // path traversal attacks (e.g., "../../etc/passwd").
  const normalizedWorkingDir = resolve(workingDir);
  if (!resolved.startsWith(normalizedWorkingDir + "/") && resolved !== normalizedWorkingDir) {
    throw new Error(`Path traversal detected: "${filename}" resolves outside working directory`);
  }

  return resolved;
}

async function ensureDir(filepath: string): Promise<void> {
  const dir = dirname(filepath);
  await mkdir(dir, { recursive: true });
}

function matchPattern(filename: string, pattern: string): boolean {
  // Simple glob matching: *.ext or *keyword*
  const regex = new RegExp(
    "^" + pattern.replace(/\*/g, ".*").replace(/\?/g, ".") + "$",
    "i",
  );
  return regex.test(filename);
}

const MAX_READ_BYTES = 50 * 1024; // 50KB
const MAX_READ_LINES = 2000;

// ===== Tool Factory =====

export function createFileTools(opts: {
  workingDir: string;
  taskId: string;
  emitter?: SSEEmitter;
}): AgentTool<any>[] {
  const { workingDir, taskId, emitter } = opts;

  const write_to_file: AgentTool<typeof writeFileSchema> = {
    name: "write_to_file",
    label: "Write File",
    description:
      "Write content to a file. Supports txt, md, html, json, csv, yaml, xml, pdf, docx and more. For .pdf and .docx the content should be Markdown — it will be rendered automatically. Creates parent directories automatically.",
    parameters: writeFileSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.filename, workingDir);
      const ext = extname(filepath).toLowerCase();
      logger.info({ filepath, ext }, "Writing file");

      await ensureDir(filepath);

      // Backup if requested and file exists
      if (params.create_backup) {
        try {
          await access(filepath, constants.F_OK);
          const backupName = `${filepath}.bak.${Date.now()}`;
          await copyFile(filepath, backupName);
          logger.info({ backupName }, "Backup created");
        } catch {
          // File doesn't exist, no backup needed
        }
      }

      // Route by extension: PDF and DOCX expect Markdown content
      const title = basename(filepath, ext);
      if (ext === ".pdf") {
        await renderMarkdownToPdf(params.content, title, filepath);
      } else if (ext === ".docx") {
        await renderMarkdownToDocx(params.content, title, filepath);
      } else {
        await writeFile(filepath, params.content, "utf-8");
      }

      const fileStat = await stat(filepath);

      // Emit write_file event
      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
        file_size: fileStat.size,
        content_preview: params.content.slice(0, 200),
      });

      return {
        content: [
          {
            type: "text",
            text: `File written successfully: ${filepath} (${fileStat.size} bytes)`,
          },
        ],
        details: undefined,
      };
    },
  };

  const append_to_file: AgentTool<typeof appendFileSchema> = {
    name: "append_to_file",
    label: "Append to File",
    description:
      "Append content to an existing file. Creates the file if it does not exist. Useful for .jsonl, logs, and incremental writes.",
    parameters: appendFileSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.filename, workingDir);
      logger.info({ filepath }, "Appending to file");

      await ensureDir(filepath);
      await appendFile(filepath, params.content, "utf-8");

      return {
        content: [
          {
            type: "text",
            text: `Content appended to: ${filepath}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const read_file: AgentTool<typeof readFileSchema> = {
    name: "read_file",
    label: "Read File",
    description: `Read content from a file. Output is truncated to ${MAX_READ_LINES} lines or ${MAX_READ_BYTES / 1024}KB. Use offset/limit for large files.`,
    parameters: readFileSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.filename, workingDir);
      logger.info({ filepath }, "Reading file");

      const buffer = await readFile(filepath);
      const text = buffer.toString("utf-8");
      const allLines = text.split("\n");
      const totalLines = allLines.length;

      // Apply offset (1-indexed)
      const startLine = params.offset ? Math.max(0, params.offset - 1) : 0;
      if (startLine >= allLines.length) {
        throw new Error(
          `Offset ${params.offset} beyond end of file (${totalLines} lines)`,
        );
      }

      // Apply limit
      const endLine = params.limit
        ? Math.min(startLine + params.limit, allLines.length)
        : allLines.length;
      let selected = allLines.slice(startLine, endLine);

      // Truncate by lines
      let truncated = false;
      if (selected.length > MAX_READ_LINES) {
        selected = selected.slice(0, MAX_READ_LINES);
        truncated = true;
      }

      let output = selected.join("\n");

      // Truncate by bytes
      if (Buffer.byteLength(output, "utf-8") > MAX_READ_BYTES) {
        while (Buffer.byteLength(output, "utf-8") > MAX_READ_BYTES) {
          selected.pop();
          output = selected.join("\n");
        }
        truncated = true;
      }

      if (truncated) {
        const shownEnd = startLine + selected.length;
        const nextOffset = shownEnd + 1;
        output += `\n\n[Showing lines ${startLine + 1}-${shownEnd} of ${totalLines}. Use offset=${nextOffset} to continue.]`;
      }

      return {
        content: [{ type: "text", text: output }],
        details: undefined,
      };
    },
  };

  const file_exists: AgentTool<typeof fileExistsSchema> = {
    name: "file_exists",
    label: "Check File Exists",
    description: "Check if a file or directory exists at the given path.",
    parameters: fileExistsSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.filename, workingDir);
      try {
        const s = await stat(filepath);
        const type = s.isDirectory() ? "directory" : "file";
        return {
          content: [
            {
              type: "text",
              text: `Yes, ${type} exists: ${filepath} (${s.size} bytes)`,
            },
          ],
          details: undefined,
        };
      } catch {
        return {
          content: [
            { type: "text", text: `No, does not exist: ${filepath}` },
          ],
          details: undefined,
        };
      }
    },
  };

  const list_files: AgentTool<typeof listFilesSchema> = {
    name: "list_files",
    label: "List Files",
    description:
      "List files in a directory. Optionally filter by pattern (e.g., '*.csv').",
    parameters: listFilesSchema,
    execute: async (_id, params) => {
      const dir = params.directory
        ? resolvePath(params.directory, workingDir)
        : workingDir;

      const entries = await readdir(dir, { withFileTypes: true });
      let items = entries.map((e) => ({
        name: e.name,
        isDir: e.isDirectory(),
      }));

      // Filter by pattern
      if (params.pattern) {
        items = items.filter((i) => matchPattern(i.name, params.pattern!));
      }

      // Sort: directories first, then alphabetical
      items.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
        return a.name.localeCompare(b.name);
      });

      const lines = items.map(
        (i) => `${i.isDir ? "[DIR] " : "      "}${i.name}`,
      );

      return {
        content: [
          {
            type: "text",
            text:
              lines.length > 0
                ? `${dir}/\n${lines.join("\n")}`
                : `${dir}/ (empty)`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [write_to_file, append_to_file, read_file, file_exists, list_files];
}
