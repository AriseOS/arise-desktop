/**
 * MCP Tools — Gmail, Google Drive, and Notion via MCP (Model Context Protocol).
 *
 * Ported from gmail_mcp_toolkit.py, notion_mcp_toolkit.py, gdrive_mcp_toolkit.py.
 *
 * MCP servers communicate over stdin/stdout (JSON-RPC 2.0).
 * Each server provides dynamically-discovered tools.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { spawn, type ChildProcess } from "node:child_process";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("mcp-tools");

// ===== JSON-RPC Types =====

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: unknown;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

interface MCPToolDefinition {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

// ===== MCP Client =====

export class MCPClient {
  private process?: ChildProcess;
  private nextId = 1;
  private pendingRequests = new Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (reason: Error) => void;
    }
  >();
  private buffer = "";
  private connected = false;

  constructor(
    private command: string,
    private args: string[],
    private env?: Record<string, string>,
  ) {}

  async connect(): Promise<void> {
    if (this.connected) return;

    logger.info(
      { command: this.command, args: this.args },
      "Starting MCP server",
    );

    this.process = spawn(this.command, this.args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, ...this.env },
    });

    this.process.stdout!.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      try {
        this.processBuffer();
      } catch (e) {
        logger.warn({ err: e }, "Error processing MCP buffer");
      }
    });

    this.process.stderr!.on("data", (data: Buffer) => {
      logger.debug({ stderr: data.toString().trim() }, "MCP stderr");
    });

    this.process.on("close", (code) => {
      logger.info({ code }, "MCP server closed");
      this.connected = false;
      // Reject all pending requests
      for (const [id, req] of this.pendingRequests) {
        req.reject(new Error(`MCP server exited with code ${code}`));
      }
      this.pendingRequests.clear();
    });

    // Send initialize
    await this.sendRequest("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "ami-daemon", version: "1.0.0" },
    });

    // Send initialized notification
    this.sendNotification("notifications/initialized");

    this.connected = true;
    logger.info("MCP server connected");
  }

  async disconnect(): Promise<void> {
    if (this.process) {
      this.process.kill("SIGTERM");
      this.process = undefined;
      this.connected = false;
    }
  }

  async listTools(): Promise<MCPToolDefinition[]> {
    const result = (await this.sendRequest("tools/list", {})) as {
      tools: MCPToolDefinition[];
    };
    return result.tools ?? [];
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<string> {
    const result = (await this.sendRequest("tools/call", {
      name,
      arguments: args,
    })) as { content?: { type: string; text?: string }[] };

    if (result.content) {
      return result.content
        .filter((c) => c.type === "text" && c.text)
        .map((c) => c.text!)
        .join("\n");
    }

    return JSON.stringify(result);
  }

  private sendRequest(
    method: string,
    params?: unknown,
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.process?.stdin) {
        reject(new Error(`MCP server not running, cannot send: ${method}`));
        return;
      }

      const id = this.nextId++;
      const request: JsonRpcRequest = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

      this.pendingRequests.set(id, { resolve, reject });

      const data = JSON.stringify(request) + "\n";
      this.process.stdin.write(data);

      // Timeout — clear on resolution to avoid timer leak
      const timer = setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`MCP request timeout: ${method}`));
        }
      }, 30_000);

      // Wrap resolve/reject to clear timeout
      const origResolve = this.pendingRequests.get(id)!.resolve;
      const origReject = this.pendingRequests.get(id)!.reject;
      this.pendingRequests.set(id, {
        resolve: (v) => { clearTimeout(timer); origResolve(v); },
        reject: (e) => { clearTimeout(timer); origReject(e); },
      });
    });
  }

  private sendNotification(method: string, params?: unknown): void {
    if (!this.process?.stdin) {
      logger.warn({ method }, "MCP server not running, cannot send notification");
      return;
    }
    const notification = {
      jsonrpc: "2.0",
      method,
      params,
    };
    this.process.stdin.write(JSON.stringify(notification) + "\n");
  }

  private processBuffer(): void {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop()!; // Keep incomplete line

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line) as JsonRpcResponse;
        if (msg.id !== undefined && this.pendingRequests.has(msg.id)) {
          const req = this.pendingRequests.get(msg.id)!;
          this.pendingRequests.delete(msg.id);

          if (msg.error) {
            req.reject(
              new Error(`MCP error: ${msg.error.message} (${msg.error.code})`),
            );
          } else {
            req.resolve(msg.result);
          }
        }
      } catch {
        // Ignore non-JSON lines
      }
    }
  }
}

// ===== Convert MCP tools to AgentTool[] =====

function mcpToolToAgentTool(
  client: MCPClient,
  def: MCPToolDefinition,
): AgentTool {
  // Build a generic params schema, respecting required fields
  const requiredFields = new Set<string>(
    (def.inputSchema as any)?.required ?? [],
  );

  const paramsSchema = Type.Object(
    Object.fromEntries(
      Object.entries(
        (def.inputSchema as any)?.properties ?? {},
      ).map(([key, val]: [string, any]) => {
        const isRequired = requiredFields.has(key);
        const baseType =
          val.type === "string"
            ? Type.String({ description: val.description })
            : val.type === "number" || val.type === "integer"
              ? Type.Number({ description: val.description })
              : val.type === "boolean"
                ? Type.Boolean({ description: val.description })
                : Type.Unknown({ description: val.description });
        return [key, isRequired ? baseType : Type.Optional(baseType)];
      }),
    ),
  );

  return {
    name: def.name,
    label: def.name,
    description: def.description ?? `MCP tool: ${def.name}`,
    parameters: paramsSchema,
    execute: async (_id, params) => {
      const result = await client.callTool(def.name, params as Record<string, unknown>);
      return {
        content: [{ type: "text", text: result }],
        details: undefined,
      };
    },
  };
}

// ===== Gmail MCP =====

export async function createGmailTools(
  credentialsPath?: string,
): Promise<{ client: MCPClient; tools: AgentTool[] }> {
  const creds =
    credentialsPath ?? process.env.GMAIL_CREDENTIALS_PATH;
  if (!creds) {
    throw new Error(
      "GMAIL_CREDENTIALS_PATH not set. Cannot create Gmail tools.",
    );
  }

  const client = new MCPClient("npx", [
    "-y",
    "@gongrzhe/server-gmail-autoauth-mcp",
  ], {
    GMAIL_CREDENTIALS_PATH: creds,
  });

  await client.connect();
  const defs = await client.listTools();

  logger.info({ toolCount: defs.length }, "Gmail MCP tools loaded");

  return {
    client,
    tools: defs.map((d) => mcpToolToAgentTool(client, d)),
  };
}

// ===== Google Drive MCP =====

export async function createGDriveTools(): Promise<{
  client: MCPClient;
  tools: AgentTool<any>[];
}> {
  const client = new MCPClient("npx", [
    "-y",
    "@modelcontextprotocol/server-gdrive",
  ]);

  await client.connect();
  const defs = await client.listTools();

  logger.info({ toolCount: defs.length }, "GDrive MCP tools loaded");

  return {
    client,
    tools: defs.map((d) => mcpToolToAgentTool(client, d)),
  };
}

// ===== Notion MCP =====

export async function createNotionTools(): Promise<{
  client: MCPClient;
  tools: AgentTool<any>[];
}> {
  const configDir =
    process.env.MCP_REMOTE_CONFIG_DIR ?? `${process.env.HOME}/.mcp-auth`;

  const client = new MCPClient(
    "npx",
    ["-y", "mcp-remote", "https://mcp.notion.com/mcp"],
    { MCP_REMOTE_CONFIG_DIR: configDir },
  );

  // Retry connection (Notion remote MCP can be slow)
  let lastError: Error | undefined;
  let connected = false;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await client.connect();
      connected = true;
      break;
    } catch (err) {
      lastError = err as Error;
      logger.warn(
        { attempt, err: String(err) },
        "Notion MCP connection retry",
      );
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  if (!connected) {
    throw lastError ?? new Error("Failed to connect to Notion MCP after 3 attempts");
  }

  const defs = await client.listTools();
  if (defs.length === 0 && lastError) {
    throw lastError;
  }

  logger.info({ toolCount: defs.length }, "Notion MCP tools loaded");

  return {
    client,
    tools: defs.map((d) => mcpToolToAgentTool(client, d)),
  };
}
