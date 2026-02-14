/**
 * Agent Factory — creates child agents using pi-agent-core.
 *
 * `createChildAgentTools` assembles the correct tool set per AgentType:
 * - browser: BrowserTools, FileTools, TerminalTools, SearchTools, HumanTools, MarkItDownTools, MemoryTools
 * - code: TerminalTools, FileTools, HumanTools, SearchTools
 * - document: FileTools, ExcelTools, PptxTools, MarkItDownTools, TerminalTools, HumanTools
 * - multi_modal: ImageTools, AudioTools, VideoTools, FileTools, TerminalTools, HumanTools
 */

import { Agent } from "@mariozechner/pi-agent-core";
import { getConfiguredModel, getAnthropicApiKey } from "../utils/config.js";
import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import type { TextContent, ImageContent } from "@mariozechner/pi-ai";
import { bridgeAgentToSSE } from "../events/bridge.js";
import { Action } from "../events/types.js";
import type { SSEEmitter } from "../events/emitter.js";
import type { TaskState } from "../services/task-state.js";
import type { AgentType } from "../prompts/unified-agent.js";
import {
  createBrowserTools,
  createFileTools,
  createTerminalTools,
  createSearchTools,
  createHumanTools,
  createExcelTools,
  createPptxTools,
  createImageTools,
  createAudioTools,
  createVideoTools,
  createMarkItDownTools,
  createMemoryTools,
} from "../tools/index.js";
import { getConfig } from "../utils/config.js";
import { agentPrompt, requireApiKey, debugStreamSimple } from "../utils/agent-helpers.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("agent-factory");

// ===== Echo Tool (Phase 1 smoke test) =====

const echoSchema = Type.Object({
  message: Type.String({ description: "The message to echo back" }),
});

type EchoParams = Static<typeof echoSchema>;

const echoTool: AgentTool<typeof echoSchema> = {
  name: "echo",
  label: "Echo",
  description: "Echo a message back to the user. Use this for testing.",
  parameters: echoSchema,
  execute: async (
    _toolCallId: string,
    params: EchoParams,
  ): Promise<AgentToolResult<undefined>> => {
    return {
      content: [{ type: "text", text: `Echo: ${params.message}` }],
      details: undefined,
    };
  },
};

// ===== Shell exec tool (basic) =====

const shellExecSchema = Type.Object({
  command: Type.String({ description: "Shell command to execute" }),
});

type ShellExecParams = Static<typeof shellExecSchema>;

const shellExecTool: AgentTool<typeof shellExecSchema> = {
  name: "shell_exec",
  label: "Terminal",
  description: "Execute a shell command and return its output.",
  parameters: shellExecSchema,
  execute: async (
    _toolCallId: string,
    params: ShellExecParams,
    signal?: AbortSignal,
  ): Promise<AgentToolResult<undefined>> => {
    const { exec } = await import("node:child_process");
    const { promisify } = await import("node:util");
    const execAsync = promisify(exec);

    try {
      const { stdout, stderr } = await execAsync(params.command, {
        timeout: 30_000,
        maxBuffer: 50 * 1024,
        signal,
      });
      const output = (stdout + (stderr ? `\nSTDERR: ${stderr}` : "")).trim();
      return {
        content: [{ type: "text", text: output || "(no output)" }],
        details: undefined,
      };
    } catch (err: any) {
      return {
        content: [{ type: "text", text: `Error: ${err.message}` }],
        details: undefined,
      };
    }
  },
};

// ===== Create child agent tools per AgentType =====

/**
 * Assemble the correct tool set for a given agent type.
 * Mirrors Python agent_factories.py tool assembly.
 */
export function createChildAgentTools(
  agentType: AgentType,
  sessionId: string,
  opts: {
    workingDir: string;
    taskId: string;
    taskState: TaskState;
    apiKey?: string;
    emitter?: SSEEmitter;
  },
): AgentTool<any>[] {
  const { workingDir, taskId, taskState, apiKey, emitter } = opts;

  // Common tools shared by all agent types
  const fileTools = createFileTools({ workingDir, taskId, emitter });
  const terminalTools = createTerminalTools({ workingDir, taskId, emitter });
  const humanTools = createHumanTools({ taskId, taskState, emitter });

  switch (agentType) {
    case "browser": {
      const browserTools = createBrowserTools(sessionId, emitter);
      const searchTools = createSearchTools();
      const markItDownTools = createMarkItDownTools({ workingDir });
      const { tools: memoryTools } = createMemoryTools({
        memoryApiBaseUrl: getConfig().cloud.api_url,
        apiKey,
        userId: taskState.userId,
        taskId,
        emitter,
      });
      return [
        ...browserTools,
        ...fileTools,
        ...terminalTools,
        ...searchTools,
        ...humanTools,
        ...markItDownTools,
        ...memoryTools,
      ];
    }

    case "code": {
      const searchTools = createSearchTools();
      return [
        ...terminalTools,
        ...fileTools,
        ...humanTools,
        ...searchTools,
      ];
    }

    case "document": {
      const excelTools = createExcelTools({ workingDir, taskId, emitter });
      const pptxTools = createPptxTools({ workingDir, taskId, emitter });
      const markItDownTools = createMarkItDownTools({ workingDir });
      return [
        ...fileTools,
        ...excelTools,
        ...pptxTools,
        ...markItDownTools,
        ...terminalTools,
        ...humanTools,
      ];
    }

    case "multi_modal": {
      const imageTools = createImageTools({ workingDir, taskId, apiKey, emitter });
      const audioTools = createAudioTools({ workingDir, apiKey });
      const videoTools = createVideoTools({ workingDir });
      return [
        ...imageTools,
        ...audioTools,
        ...videoTools,
        ...fileTools,
        ...terminalTools,
        ...humanTools,
      ];
    }


    default: {
      logger.warn({ agentType }, "Unknown agent type, returning minimal tools");
      return [...fileTools, ...terminalTools, ...humanTools];
    }
  }
}

// ===== Create child agent =====

export function createChildAgent(
  apiKey: string | undefined,
  tools: AgentTool<any>[],
  systemPrompt: string,
): Agent {
  // Validate API key before creating agent (prevents hang on missing key)
  const resolvedApiKey = requireApiKey(apiKey ?? getAnthropicApiKey());

  const model = getConfiguredModel();

  const agent = new Agent({
    initialState: {
      systemPrompt,
      model,
      tools,
      messages: [],
      thinkingLevel: "off",
    },
    getApiKey: async () => resolvedApiKey,
    streamFn: debugStreamSimple,
  });

  return agent;
}

// ===== Execute a task (Phase 1: simple single-agent execution) =====

export async function executeTask(
  state: TaskState,
  apiKey?: string,
): Promise<void> {
  const { taskId, task, emitter } = state;

  state.markRunning();
  state.addConversation("user", task);

  const startTime = Date.now();

  try {
    const systemPrompt = `You are Ami, a capable AI assistant. Help the user with their task.
Respond in the user's language. Be concise and helpful.
Current time: ${new Date().toISOString()}`;

    // Phase 1: minimal tools
    const tools: AgentTool<any>[] = [echoTool, shellExecTool];

    const agent = createChildAgent(apiKey, tools, systemPrompt);

    // Bridge agent events to SSE
    const unsubscribe = bridgeAgentToSSE(agent, emitter, taskId, "Agent");

    // Wire abort signal
    const abortHandler = () => agent.abort();
    state.abortController.signal.addEventListener("abort", abortHandler);

    // Run the agent
    try {
      await agentPrompt(agent, task);

      // Extract text from result messages
      const messages = agent.state.messages;
      const lastAssistant = [...messages]
        .reverse()
        .find((m: any) => m.role === "assistant");

      let resultText = "";
      if (lastAssistant && "content" in lastAssistant) {
        resultText = (lastAssistant.content as any[])
          .filter((c: any) => c.type === "text")
          .map((c: any) => c.text)
          .join("\n");
      }

      state.addConversation("assistant", resultText);
      state.markCompleted(resultText);

      const durationSeconds = (Date.now() - startTime) / 1000;

      emitter.emitWaitConfirm(
        resultText,
        task,
        "initial",
        undefined,
        undefined,
        undefined,
      );

      emitter.emitEnd("completed", "Task completed", resultText);
    } finally {
      unsubscribe();
      state.abortController.signal.removeEventListener("abort", abortHandler);
    }
  } catch (err: any) {
    const errorMsg = err.message ?? String(err);
    logger.error({ taskId, err: errorMsg }, "Task execution error");

    state.markFailed(errorMsg);
    emitter.emitError(errorMsg, err.constructor?.name);
    emitter.emitEnd("failed", errorMsg);
  } finally {
    emitter.close();
  }
}
