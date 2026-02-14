/**
 * MarkItDown Tools — Convert various file formats to Markdown.
 *
 * Ported from markitdown_toolkit.py.
 *
 * Tools: convert_to_markdown, read_files, read_url.
 *
 * Supports: PDF, DOCX, HTML, plain text, CSV, JSON, XML.
 * Uses native Node.js libraries rather than Python's markitdown.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { readFile } from "node:fs/promises";
import { resolve, extname } from "node:path";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("markitdown-tools");

// ===== Schemas =====

const convertSchema = Type.Object({
  file_path: Type.String({
    description: "Path to the file to convert to Markdown",
  }),
});

const readFilesSchema = Type.Object({
  file_paths: Type.Array(Type.String(), {
    description: "List of file paths to read and convert to Markdown",
  }),
});

const readUrlSchema = Type.Object({
  url: Type.String({
    description: "URL of the web page to read and convert to Markdown",
  }),
});

// ===== Helpers =====

function resolvePath(filename: string, workingDir: string): string {
  let resolved: string;
  if (filename.startsWith("/") || filename.startsWith("~")) {
    resolved = resolve(filename.replace(/^~/, process.env.HOME ?? "/tmp"));
  } else {
    resolved = resolve(workingDir, filename);
  }

  // Validate the resolved path stays within the working directory
  const normalizedWorkingDir = resolve(workingDir);
  if (!resolved.startsWith(normalizedWorkingDir + "/") && resolved !== normalizedWorkingDir) {
    throw new Error(`Path traversal detected: "${filename}" resolves outside working directory`);
  }

  return resolved;
}

async function convertToMarkdown(filepath: string): Promise<string> {
  const ext = extname(filepath).toLowerCase();
  const buffer = await readFile(filepath);

  switch (ext) {
    case ".txt":
    case ".md":
    case ".log":
      return buffer.toString("utf-8");

    case ".json": {
      const obj = JSON.parse(buffer.toString("utf-8"));
      return "```json\n" + JSON.stringify(obj, null, 2) + "\n```";
    }

    case ".csv": {
      const text = buffer.toString("utf-8");
      const lines = text.split("\n").filter((l) => l.trim());
      if (lines.length === 0) return "(empty CSV)";

      const rows = lines.map((l) => l.split(",").map((c) => c.trim()));
      const header = rows[0];
      const separator = header.map(() => "---");
      const mdLines = [
        "| " + header.join(" | ") + " |",
        "| " + separator.join(" | ") + " |",
        ...rows.slice(1).map((r) => "| " + r.join(" | ") + " |"),
      ];
      return mdLines.join("\n");
    }

    case ".xml":
    case ".html":
    case ".htm": {
      const text = buffer.toString("utf-8");
      // Simple HTML to text: strip tags, preserve structure
      return text
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<style[\s\S]*?<\/style>/gi, "")
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/p>/gi, "\n\n")
        .replace(/<\/div>/gi, "\n")
        .replace(/<\/h[1-6]>/gi, "\n\n")
        .replace(/<h([1-6])[^>]*>/gi, (_, level) => "#".repeat(Number(level)) + " ")
        .replace(/<li[^>]*>/gi, "- ")
        .replace(/<\/li>/gi, "\n")
        .replace(/<[^>]+>/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/\n{3,}/g, "\n\n")
        .trim();
    }

    case ".yaml":
    case ".yml":
      return "```yaml\n" + buffer.toString("utf-8") + "\n```";

    default:
      // Try as plain text
      const text = buffer.toString("utf-8");
      // Check if it looks like binary
      if (text.includes("\0")) {
        return `(Binary file: ${ext}, ${buffer.length} bytes — conversion not supported)`;
      }
      return text;
  }
}

// ===== Tool Factory =====

export function createMarkItDownTools(opts: {
  workingDir: string;
}): AgentTool<any>[] {
  const { workingDir } = opts;

  const convert_to_markdown: AgentTool<typeof convertSchema> = {
    name: "convert_to_markdown",
    label: "Convert to Markdown",
    description:
      "Convert a file to Markdown format. Supports: txt, md, json, csv, xml, html, yaml. Returns the content as Markdown text.",
    parameters: convertSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.file_path, workingDir);
      logger.info({ filepath }, "Converting to markdown");

      const markdown = await convertToMarkdown(filepath);

      // Truncate if too large
      const maxLen = 50_000;
      const truncated = markdown.length > maxLen;
      const output = truncated
        ? markdown.slice(0, maxLen) + `\n\n[Truncated: showing ${maxLen} of ${markdown.length} chars]`
        : markdown;

      return {
        content: [{ type: "text", text: output }],
        details: undefined,
      };
    },
  };

  const read_files: AgentTool<typeof readFilesSchema> = {
    name: "read_files",
    label: "Read Files as Markdown",
    description:
      "Read multiple files and convert each to Markdown. Returns a combined result with each file's content.",
    parameters: readFilesSchema,
    execute: async (_id, params) => {
      const results: string[] = [];

      for (const filePath of params.file_paths) {
        const filepath = resolvePath(filePath, workingDir);
        try {
          const markdown = await convertToMarkdown(filepath);
          const maxLen = 30_000;
          const content =
            markdown.length > maxLen
              ? markdown.slice(0, maxLen) + `\n[Truncated: ${maxLen}/${markdown.length} chars]`
              : markdown;
          results.push(`## ${filePath}\n\n${content}`);
        } catch (err) {
          results.push(`## ${filePath}\n\nError: ${err instanceof Error ? err.message : String(err)}`);
        }
      }

      return {
        content: [{ type: "text", text: results.join("\n\n---\n\n") }],
        details: undefined,
      };
    },
  };

  const read_url: AgentTool<typeof readUrlSchema> = {
    name: "read_url",
    label: "Read URL as Markdown",
    description:
      "Fetch a web page and convert its content to Markdown.",
    parameters: readUrlSchema,
    execute: async (_id, params) => {
      logger.info({ url: params.url }, "Fetching URL");

      const resp = await fetch(params.url, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        signal: AbortSignal.timeout(30_000),
      });

      if (!resp.ok) {
        throw new Error(`Failed to fetch URL (${resp.status}): ${resp.statusText}`);
      }

      const html = await resp.text();

      // Convert HTML to markdown using the same HTML handler
      const markdown = html
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<style[\s\S]*?<\/style>/gi, "")
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/p>/gi, "\n\n")
        .replace(/<\/div>/gi, "\n")
        .replace(/<\/h[1-6]>/gi, "\n\n")
        .replace(/<h([1-6])[^>]*>/gi, (_, level) => "#".repeat(Number(level)) + " ")
        .replace(/<li[^>]*>/gi, "- ")
        .replace(/<\/li>/gi, "\n")
        .replace(/<[^>]+>/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/\n{3,}/g, "\n\n")
        .trim();

      const maxLen = 50_000;
      const output =
        markdown.length > maxLen
          ? markdown.slice(0, maxLen) + `\n\n[Truncated: ${maxLen}/${markdown.length} chars]`
          : markdown;

      return {
        content: [{ type: "text", text: output || "(empty page)" }],
        details: undefined,
      };
    },
  };

  return [convert_to_markdown, read_files, read_url];
}
