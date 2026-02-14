/**
 * Orchestrator Session — persistent parent agent that manages user sessions.
 *
 * Ported from orchestrator_agent.py OrchestratorSession.
 *
 * Architecture:
 * - Persistent Agent with tools: shell_exec, search_google, ask_human,
 *   attach_file, decompose_task, inject_message, cancel_task, replan_task
 * - decompose_task triggers: TaskPlanner → TaskExecutor in background
 * - inject_message/cancel_task operate on running executors
 * - Main loop: process message → wait for user message or executor completion
 */

import { Agent } from "@mariozechner/pi-agent-core";
import { streamSimple } from "@mariozechner/pi-ai";
import { basename } from "node:path";
import { statSync } from "node:fs";
import { getConfiguredModel, getAnthropicApiKey, getConfig } from "../utils/config.js";
import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import { getOrchestratorSystemPrompt } from "../prompts/orchestrator.js";
import {
  getAgentSystemPrompt,
  getDefaultPromptVars,
  type AgentType,
} from "../prompts/unified-agent.js";
import { AMITaskPlanner } from "./task-planner.js";
import { AMITaskExecutor } from "./task-executor.js";
import {
  type AMISubtask,
  type ExecutorHandle,
  type ExecutionResult,
  SubtaskState,
  createSubtask,
} from "./schemas.js";
import { bridgeAgentToSSE } from "../events/bridge.js";
import { Action, type FileAttachment } from "../events/types.js";
import type { SSEEmitter } from "../events/emitter.js";
import type { TaskState } from "../services/task-state.js";
import { t, detectLanguage } from "../utils/i18n.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("orchestrator");

const SESSION_IDLE_TIMEOUT_MS = 600_000; // 10 minutes

// ===== Orchestrator Tools =====

function createDecomposeTaskTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    task_description: Type.String({
      description:
        "The user's request in their own words. Copy the original wording " +
        "as closely as possible. Do NOT rephrase, translate, or add requirements.",
    }),
    workspace_folder: Type.Optional(
      Type.String({
        description:
          'Short kebab-case folder name for output files (e.g. "stock-analysis").',
      }),
    ),
  });

  return {
    name: "decompose_task",
    label: "Delegate Task",
    description:
      "Delegate a task to specialized agents (Browser, Developer, Document, etc.). " +
      "Call this when the task requires browsing websites, writing code, or creating documents.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      if (ctx.decomposePending) {
        return {
          content: [
            {
              type: "text",
              text:
                "Task already delegated and is being executed. " +
                "Do NOT call decompose_task again. Summarize your plan to the user.",
            },
          ],
          details: undefined,
        };
      }

      ctx.decomposePending = true;
      ctx.decomposeTaskDescription = params.task_description;
      ctx.decomposeWorkspaceFolder = params.workspace_folder ?? "";

      logger.info(
        {
          task: params.task_description?.slice(0, 100),
          folder: ctx.decomposeWorkspaceFolder,
        },
        "decompose_task triggered",
      );

      return {
        content: [
          {
            type: "text",
            text:
              "Task delegated successfully. The team will now execute this task. " +
              "Summarize what you plan to do for the user.",
          },
        ],
        details: undefined,
      };
    },
  };
}

function createAttachFileTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    file_path: Type.String({ description: "Absolute path to the file" }),
  });

  return {
    name: "attach_file",
    label: "Attach File",
    description:
      "Attach a file to your response. The user can click to open/preview it.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      ctx.attachedFiles.push(params.file_path);
      return {
        content: [
          {
            type: "text",
            text: `File attached: ${params.file_path}`,
          },
        ],
        details: undefined,
      };
    },
  };
}

function createInjectMessageTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    executor_id: Type.String({ description: "ID of the running executor" }),
    message: Type.String({ description: "Message to inject" }),
  });

  return {
    name: "inject_message",
    label: "Inject Message",
    description:
      "Send a message to a running executor's agent to modify its behavior.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      const handle = ctx.runningExecutors.get(params.executor_id);
      if (!handle) {
        return {
          content: [
            {
              type: "text",
              text: `No running executor with ID '${params.executor_id}'`,
            },
          ],
          details: undefined,
        };
      }

      const agent = handle.executor?.getCurrentAgent();
      if (agent?.steer) {
        agent.steer({
          role: "user" as const,
          content: params.message,
          timestamp: Date.now(),
        });
        return {
          content: [
            { type: "text", text: `Message injected to executor ${params.executor_id}` },
          ],
          details: undefined,
        };
      }

      return {
        content: [
          {
            type: "text",
            text: `Executor ${params.executor_id} has no active agent to inject into`,
          },
        ],
        details: undefined,
      };
    },
  };
}

function createCancelTaskTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    executor_id: Type.String({ description: "ID of the executor to cancel" }),
  });

  return {
    name: "cancel_task",
    label: "Cancel Task",
    description: "Cancel a specific running executor.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      const handle = ctx.runningExecutors.get(params.executor_id);
      if (!handle) {
        return {
          content: [
            {
              type: "text",
              text: `No running executor with ID '${params.executor_id}'`,
            },
          ],
          details: undefined,
        };
      }

      handle.executor?.stop();
      handle.abortController.abort();

      return {
        content: [
          { type: "text", text: `Executor ${params.executor_id} cancelled` },
        ],
        details: undefined,
      };
    },
  };
}

function createReplanTaskTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    executor_id: Type.String({ description: "ID of the executor to replan" }),
    new_subtasks: Type.String({
      description:
        'JSON array of new subtask objects. Each: { "id": "N", "content": "...", ' +
        '"type": "browser|document|code|multi_modal", "depends_on": "1,2" }',
    }),
    reason: Type.Optional(
      Type.String({ description: "Reason for replanning" }),
    ),
  });

  return {
    name: "replan_task",
    label: "Replan Task",
    description:
      "Replace pending subtasks of a running executor with a new plan. " +
      "DONE and RUNNING subtasks are preserved.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      const handle = ctx.runningExecutors.get(params.executor_id);
      if (!handle?.executor) {
        return {
          content: [
            {
              type: "text",
              text: `No running executor with ID '${params.executor_id}'`,
            },
          ],
          details: undefined,
        };
      }

      try {
        const parsed = JSON.parse(params.new_subtasks);
        if (!Array.isArray(parsed)) {
          return {
            content: [
              { type: "text", text: "Error: new_subtasks must be a JSON array" },
            ],
            details: undefined,
          };
        }

        const newSubtasks = parsed.map((item: any) =>
          createSubtask({
            id: item.id ?? String(Math.random()).slice(2, 8),
            content: item.content ?? "",
            agentType: item.type ?? "browser",
            dependsOn: item.depends_on
              ? String(item.depends_on)
                  .split(",")
                  .map((s: string) => s.trim())
                  .filter(Boolean)
              : [],
          }),
        );

        const result = handle.executor.replanSubtasks(newSubtasks);

        // Emit SSE event
        ctx.emitter?.emitTaskReplanned(
          newSubtasks.map((s) => ({
            id: s.id,
            content: s.content,
            state: s.state,
            agent_type: s.agentType,
          })),
          ctx.taskId,
          params.reason,
        );

        return {
          content: [
            {
              type: "text",
              text:
                `Replanned executor ${params.executor_id}: ` +
                `removed ${result.removedCount} PENDING, added ${result.addedCount} new. ` +
                `Kept: [${result.keptIds.join(", ")}]`,
            },
          ],
          details: undefined,
        };
      } catch (e: any) {
        return {
          content: [
            { type: "text", text: `Replan failed: ${e.message}` },
          ],
          details: undefined,
        };
      }
    },
  };
}

function createAskHumanTool(ctx: OrchestratorContext): AgentTool<any> {
  const schema = Type.Object({
    question: Type.String({ description: "Question to ask the user" }),
  });

  return {
    name: "ask_human",
    label: "Ask User",
    description: "Ask the user a question and wait for their response.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      // Emit wait_confirm event
      ctx.emitter?.emitWaitConfirm(
        params.question,
        params.question,
        "clarification",
      );

      // Wait for user response
      const response = await ctx.taskState.waitForHumanResponse(300_000);

      return {
        content: [
          {
            type: "text",
            text: response ?? "(No response from user within timeout)",
          },
        ],
        details: undefined,
      };
    },
  };
}

function createSearchGoogleTool(): AgentTool<any> {
  const schema = Type.Object({
    query: Type.String({ description: "Search query" }),
  });

  return {
    name: "search_google",
    label: "Google Search",
    description:
      "Search Google for information. Use for quick factual lookups. " +
      "For complex research tasks, use decompose_task instead.",
    parameters: schema,
    execute: async (
      _toolCallId: string,
      params: any,
    ): Promise<AgentToolResult<undefined>> => {
      // TODO: Phase 4 — implement real Google Custom Search API call
      return {
        content: [
          {
            type: "text",
            text: `[search_google not yet implemented] Query: ${params.query}`,
          },
        ],
        details: undefined,
      };
    },
  };
}

// ===== Orchestrator Context =====

interface OrchestratorContext {
  taskId: string;
  taskState: TaskState;
  emitter: SSEEmitter;
  runningExecutors: Map<string, ExecutorHandle>;
  decomposePending: boolean;
  decomposeTaskDescription: string;
  decomposeWorkspaceFolder: string;
  attachedFiles: string[];
}

// ===== OrchestratorSession =====

export class OrchestratorSession {
  private taskId: string;
  readonly taskState: TaskState;
  private emitter: SSEEmitter;
  private apiKey?: string;
  private workspaceDir: string;

  // Agent
  private agent: Agent | null = null;
  private ctx: OrchestratorContext;

  // Executor tracking
  private executorCounter = 0;
  private runningExecutors = new Map<string, ExecutorHandle>();
  private lastExecutionResult: ExecutionResult | null = null;

  // Agent tools for child agents (browser, document, code, multi_modal)
  private childAgentToolsFactory?: (
    agentType: AgentType,
    sessionId: string,
  ) => AgentTool<any>[];

  constructor(opts: {
    taskId: string;
    taskState: TaskState;
    emitter: SSEEmitter;
    apiKey?: string;
    workspaceDir?: string;
    childAgentToolsFactory?: (
      agentType: AgentType,
      sessionId: string,
    ) => AgentTool<any>[];
  }) {
    this.taskId = opts.taskId;
    this.taskState = opts.taskState;
    this.emitter = opts.emitter;
    this.apiKey = opts.apiKey;
    this.workspaceDir =
      opts.workspaceDir ?? process.env.HOME + "/.ami/workspace";
    this.childAgentToolsFactory = opts.childAgentToolsFactory;

    this.ctx = {
      taskId: this.taskId,
      taskState: this.taskState,
      emitter: this.emitter,
      runningExecutors: this.runningExecutors,
      decomposePending: false,
      decomposeTaskDescription: "",
      decomposeWorkspaceFolder: "",
      attachedFiles: [],
    };
  }

  // ===== Main Session Loop =====

  async run(initialMessage: string): Promise<ExecutionResult | null> {
    let message: string | null = initialMessage;

    while (message !== null) {
      // 1. Collect completed executor results
      const completedMsgs = this.collectCompleted();
      if (completedMsgs.length > 0) {
        const resultsBlock = completedMsgs.join("\n\n");
        message = message
          ? `${resultsBlock}\n\n[USER MESSAGE]\n${message}`
          : resultsBlock;
      }

      // 2. Build active tasks context
      const activeCtx = this.buildActiveTasksContext();

      // 3. Create/update system prompt
      const systemPrompt = getOrchestratorSystemPrompt({
        userWorkspace: this.workspaceDir,
        activeTasksContext: activeCtx,
      });

      // 4. Reset decompose state
      this.ctx.decomposePending = false;
      this.ctx.decomposeTaskDescription = "";
      this.ctx.decomposeWorkspaceFolder = "";
      this.ctx.attachedFiles = [];

      // 5. Create or update agent
      if (!this.agent) {
        this.agent = this.createOrchestratorAgent(systemPrompt);
      } else {
        // Update system prompt for existing agent
        this.agent.state.systemPrompt = systemPrompt;
      }

      // 6. Validate API key before prompt (prevents hang on missing key)
      const resolvedKey = this.apiKey ?? getAnthropicApiKey();
      if (!resolvedKey) {
        const errorMsg =
          "No API key configured. Set it via Settings or ANTHROPIC_API_KEY env var.";
        logger.error(errorMsg);
        this.emitter.emitError(errorMsg, "NO_API_KEY", false);
        this.emitter.emitWaitConfirm(
          `Error: ${errorMsg}`,
          message,
          "initial",
        );
        message = await this.waitForEvent();
        continue;
      }

      // 7. Run orchestrator
      logger.info(
        { message: message.slice(0, 200) },
        "Calling orchestrator agent",
      );

      const unsubscribe = bridgeAgentToSSE(
        this.agent,
        this.emitter,
        this.taskId,
        "Orchestrator",
      );

      try {
        await this.agent.prompt(message);
      } finally {
        unsubscribe();
      }

      // 7b. Check for agent error (API failure, auth error, etc.)
      // The bridge already emitted SSE error; here we surface it as a reply.
      if (this.agent.state.error) {
        const errorMsg = this.agent.state.error;
        logger.error({ error: errorMsg }, "Orchestrator agent error");

        // Remove the error message from agent history to prevent
        // sending an empty assistant message to the API on next turn
        const msgs = this.agent.state.messages;
        if (msgs.length > 0) {
          const last = msgs[msgs.length - 1] as any;
          if (last.role === "assistant" && last.stopReason === "error") {
            msgs.pop();
          }
        }

        this.emitter.emitWaitConfirm(
          `Error: ${errorMsg}`,
          message,
          "initial",
        );

        // Wait for user to retry or give up
        message = await this.waitForEvent();
        continue;
      }

      // 7. Extract reply
      const reply = this.extractLastAssistantText(this.agent);

      // 8. Handle decompose_task trigger
      if (this.ctx.decomposePending) {
        // Emit orchestrator's reply first
        if (reply) {
          this.emitter.emitWaitConfirm(
            reply,
            this.ctx.decomposeTaskDescription,
            "initial",
            this.buildAttachments(),
          );
        }

        // Emit confirmed event
        this.emitter.emit({
          action: Action.confirmed,
          task_id: this.taskId,
          question: this.ctx.decomposeTaskDescription,
        });

        // Spawn background plan+execute
        await this.supervisedExecute(
          this.ctx.decomposeTaskDescription,
          this.ctx.decomposeWorkspaceFolder,
        );
      } else if (reply) {
        // Normal reply
        this.emitter.emitWaitConfirm(
          reply,
          message,
          "initial",
          this.buildAttachments(),
        );
      }

      // 9. Wait for next event
      message = await this.waitForEvent();
    }

    logger.info("Session ending");
    return this.lastExecutionResult;
  }

  // ===== Agent Creation =====

  private createOrchestratorAgent(systemPrompt: string): Agent {
    // Import shell_exec tool from agent-factory (basic version)
    const shellExecSchema = Type.Object({
      command: Type.String({ description: "Shell command to execute" }),
    });

    const shellExecTool: AgentTool<typeof shellExecSchema> = {
      name: "shell_exec",
      label: "Terminal",
      description: "Execute a shell command and return its output.",
      parameters: shellExecSchema,
      execute: async (
        _toolCallId: string,
        params: any,
        signal?: AbortSignal,
      ): Promise<AgentToolResult<undefined>> => {
        const { exec } = await import("node:child_process");
        const { promisify } = await import("node:util");
        const execAsync = promisify(exec);

        // Emit terminal event
        this.emitter.emitTerminal(params.command);

        try {
          const { stdout, stderr } = await execAsync(params.command, {
            timeout: 30_000,
            maxBuffer: 50 * 1024,
            cwd: this.workspaceDir,
            signal,
          });
          const output = (stdout + (stderr ? `\nSTDERR: ${stderr}` : "")).trim();

          this.emitter.emitTerminal(
            params.command,
            output.slice(0, 2000),
            0,
            this.workspaceDir,
          );

          return {
            content: [{ type: "text", text: output || "(no output)" }],
            details: undefined,
          };
        } catch (err: any) {
          this.emitter.emitTerminal(
            params.command,
            err.message,
            err.code ?? 1,
            this.workspaceDir,
          );
          return {
            content: [{ type: "text", text: `Error: ${err.message}` }],
            details: undefined,
          };
        }
      },
    };

    const tools: AgentTool<any>[] = [
      shellExecTool,
      createSearchGoogleTool(),
      createAskHumanTool(this.ctx),
      createAttachFileTool(this.ctx),
      createDecomposeTaskTool(this.ctx),
      createInjectMessageTool(this.ctx),
      createCancelTaskTool(this.ctx),
      createReplanTaskTool(this.ctx),
    ];

    const model = getConfiguredModel();

    const agent = new Agent({
      initialState: {
        systemPrompt,
        model,
        tools,
        messages: [],
        thinkingLevel: "off",
      },
      getApiKey: async (provider: string) => {
        if (provider === "anthropic") {
          return this.apiKey ?? getAnthropicApiKey();
        }
        return undefined;
      },
      streamFn: streamSimple,
    });

    return agent;
  }

  // ===== Supervised Execute =====

  private async supervisedExecute(
    taskDescription: string,
    workspaceFolder: string,
  ): Promise<void> {
    this.executorCounter++;
    const executorId = `exec_${this.executorCounter}`;
    const taskLabel = taskDescription.slice(0, 20).trim();

    const abortController = new AbortController();

    const promise = trackPromise(
      this.planAndExecute(
        taskDescription,
        workspaceFolder,
        executorId,
        taskLabel,
      ),
    );

    const handle: ExecutorHandle = {
      executorId,
      taskLabel,
      executor: null,
      promise,
      abortController,
      subtasks: [],
      startedAt: new Date(),
      workspaceFolder,
    };

    this.runningExecutors.set(executorId, handle);
    logger.info(
      { executorId },
      "Spawned background plan+execute",
    );
  }

  private async planAndExecute(
    taskDescription: string,
    workspaceFolder: string,
    executorId: string,
    taskLabel: string,
  ): Promise<ExecutionResult> {
    // Phase 1: Planning
    const planner = new AMITaskPlanner({
      taskId: this.taskId,
      emitter: this.emitter,
      apiKey: this.apiKey,
      userId: this.taskState.userId,
      memoryApiBaseUrl: getConfig().cloud.api_url,
    });

    logger.info({ executorId }, "Decomposing task...");
    const subtasks = await planner.decomposeAndQueryMemory(taskDescription);

    if (subtasks.length === 0) {
      this.emitter.emitNotice(
        "Decomposition Failed",
        "Could not decompose task into subtasks.",
        "warning",
      );
      throw new Error("Decomposition returned no subtasks");
    }

    // Store on handle
    const handle = this.runningExecutors.get(executorId);
    if (handle) {
      handle.subtasks = subtasks;
    }

    // Emit TaskDecomposed
    const subtasksData = subtasks.map((st) => ({
      id: st.id,
      content: st.content,
      state: st.state,
      status: st.state,
      agent_type: st.agentType,
      memory_level: st.memoryLevel,
      executor_id: executorId,
    }));

    this.emitter.emitTaskDecomposed(subtasksData, taskDescription, this.taskId);

    // Emit human-readable subtask list (matches Python daemon behavior)
    const lang = detectLanguage(taskDescription);
    const typeLabels: Record<string, string> = {
      browser: t("service.type.browser", lang),
      document: t("service.type.document", lang),
      code: t("service.type.code", lang),
      multi_modal: t("service.type.multi_modal", lang),
    };
    const liItems = subtasks.map((st) => {
      const label = typeLabels[st.agentType] ?? st.agentType;
      const preview = st.content.length > 60
        ? st.content.slice(0, 60) + "..."
        : st.content;
      const escaped = preview.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const labelEscaped = label.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return `<li>[${labelEscaped}] ${escaped}</li>`;
    });
    this.emitter.emitAgentReport(
      `${t("service.task_decomposed", lang, { count: subtasks.length })}\n\n` +
        `<details><summary>${t("service.view_subtasks", lang)}</summary>` +
        `<ol>${liItems.join("")}</ol></details>`,
      "info",
      "orchestrator",
      executorId,
      taskLabel,
    );

    // Phase 2: Build agent tools per type
    const agentTypes = new Set(subtasks.map((s) => s.agentType));
    const agentTools = new Map<string, AgentTool<any>[]>();
    const systemPrompts = new Map<string, string>();

    const promptVars = getDefaultPromptVars(this.workspaceDir);

    for (const agentType of agentTypes) {
      if (this.childAgentToolsFactory) {
        agentTools.set(
          agentType,
          this.childAgentToolsFactory(
            agentType as AgentType,
            this.taskId,
          ),
        );
      } else {
        // Fallback: empty tools (will be populated in Phase 4)
        agentTools.set(agentType, []);
      }

      try {
        systemPrompts.set(
          agentType,
          getAgentSystemPrompt(agentType as AgentType, promptVars),
        );
      } catch {
        systemPrompts.set(agentType, "You are a helpful assistant.");
      }
    }

    // Phase 3: Execute
    const executor = new AMITaskExecutor({
      taskId: this.taskId,
      emitter: this.emitter,
      apiKey: this.apiKey,
      agentTools,
      systemPrompts,
      userRequest: taskDescription,
      executorId,
      taskLabel,
      userId: this.taskState.userId,
    });

    executor.setSubtasks(subtasks);

    if (handle) {
      handle.executor = executor;
    }

    // Emit workforce started
    this.emitter.emit({
      action: Action.workforce_started,
      task_id: this.taskId,
      total_tasks: subtasks.length,
      workers_count: agentTypes.size,
      description: `Starting execution: ${taskLabel}`,
      executor_id: executorId,
      task_label: taskLabel,
    });

    return await executor.execute();
  }

  // ===== Wait for Event =====

  private async waitForEvent(): Promise<string | null> {
    // Check if any executors are running
    const hasActive = [...this.runningExecutors.values()].some(
      (h) => !isPromiseSettled(h),
    );

    // When executors are running, wait indefinitely (let executor completion wake us).
    // When idle, timeout after SESSION_IDLE_TIMEOUT_MS to end session.
    const timeout = hasActive ? undefined : SESSION_IDLE_TIMEOUT_MS;

    // Race: user message vs executor completion
    const userMsgPromise = this.taskState.getUserMessage(timeout);

    const executorPromises = [...this.runningExecutors.entries()]
      .filter(([, h]) => !isPromiseSettled(h))
      .map(([id, h]) =>
        h.promise.then(
          () => ({ type: "executor" as const, id }),
          () => ({ type: "executor" as const, id }),
        ),
      );

    if (executorPromises.length === 0) {
      // Only waiting for user message
      const msg: string | null = await userMsgPromise;
      return msg ?? null;
    }

    // Race all
    const result = await Promise.race([
      userMsgPromise.then((msg: string | null) => ({
        type: "user" as const,
        message: msg,
      })),
      ...executorPromises,
    ]);

    if (result.type === "user") {
      return result.message ?? null;
    }

    // Executor completed — clean up the stale getUserMessage() deferred so it
    // doesn't consume the next user message from putUserMessage().
    this.taskState.cancelLastGetUserMessage();

    // Return empty string to trigger collection
    return "";
  }

  // ===== Collect Completed =====

  private collectCompleted(): string[] {
    const messages: string[] = [];
    const completedIds: string[] = [];

    for (const [eid, handle] of this.runningExecutors) {
      if (isPromiseSettled(handle)) {
        completedIds.push(eid);

        try {
          const completedCount =
            handle.subtasks.filter((s) => s.state === SubtaskState.DONE)
              .length;
          const failedCount =
            handle.subtasks.filter((s) => s.state === SubtaskState.FAILED)
              .length;

          // Track last execution result
          this.lastExecutionResult = {
            completed: completedCount,
            failed: failedCount,
            stopped: false,
            total: handle.subtasks.length,
          };

          // Build result summary
          const resultParts: string[] = [
            `[EXECUTION COMPLETE: ${handle.taskLabel}]`,
            `Executor ${eid}: ${completedCount} completed, ${failedCount} failed`,
          ];

          for (const st of handle.subtasks) {
            try {
              if (st.state === SubtaskState.DONE && st.result) {
                resultParts.push(
                  `\n--- Subtask ${st.id} (${st.agentType}) ---\n${st.result.slice(0, 1000)}`,
                );
              }
            } catch (subtaskErr) {
              logger.warn({ subtaskId: st.id, err: subtaskErr }, "Failed to collect subtask result");
            }
          }

          messages.push(resultParts.join("\n"));

          // Emit SSE
          this.emitter.emit({
            action: Action.workforce_completed,
            task_id: this.taskId,
            completed_count: completedCount,
            failed_count: failedCount,
            total_count: handle.subtasks.length,
            executor_id: eid,
            task_label: handle.taskLabel,
          });
        } catch (collectErr) {
          logger.error({ executorId: eid, err: collectErr }, "Failed to collect executor results");
          messages.push(`[EXECUTION COMPLETE: ${handle.taskLabel}] (result collection error)`);
        }
      }
    }

    // Remove completed executors
    for (const eid of completedIds) {
      this.runningExecutors.delete(eid);
    }

    return messages;
  }

  // ===== Build Active Tasks Context =====

  private buildActiveTasksContext(): string {
    if (this.runningExecutors.size === 0) return "";

    const lines: string[] = [
      "## Currently Running Tasks",
      "",
    ];

    for (const [eid, handle] of this.runningExecutors) {
      const elapsed = Math.round(
        (Date.now() - handle.startedAt.getTime()) / 1000,
      );
      lines.push(
        `### Executor ${eid}: "${handle.taskLabel}" (${elapsed}s)`,
      );

      for (const st of handle.subtasks) {
        const deps = st.dependsOn.length > 0
          ? ` depends_on=[${st.dependsOn.join(",")}]`
          : "";
        lines.push(
          `- [${st.state}] ${st.id} (${st.agentType}): ${st.content.slice(0, 60)}${deps}`,
        );
      }
      lines.push("");
    }

    return lines.join("\n");
  }

  // ===== Helpers =====

  private extractLastAssistantText(agent: Agent): string {
    const messages = agent.state.messages;
    const lastAssistant = [...messages]
      .reverse()
      .find((m: any) => m.role === "assistant");

    if (!lastAssistant || !("content" in lastAssistant)) return "";

    const content = lastAssistant.content;
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) return "";

    return content
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text ?? "")
      .join("\n");
  }

  private buildAttachments(): FileAttachment[] | undefined {
    if (this.ctx.attachedFiles.length === 0) return undefined;

    return this.ctx.attachedFiles.map((filePath) => {
      const fileName = basename(filePath);
      const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
      let fileSize: number | undefined;
      try {
        fileSize = statSync(filePath).size;
      } catch {
        // file may not exist yet or be inaccessible
      }

      return {
        file_name: fileName,
        file_path: filePath,
        file_type: inferFileType(ext),
        mime_type: inferMimeType(ext),
        file_size: fileSize,
      };
    });
  }

  // ===== Pause/Resume =====

  pauseExecutors(): void {
    for (const [, handle] of this.runningExecutors) {
      handle.executor?.pause();
    }
  }

  resumeExecutors(): void {
    for (const [, handle] of this.runningExecutors) {
      handle.executor?.resume();
    }
  }

  // ===== Cleanup =====

  private _cleanupDone = false;

  async cleanup(): Promise<void> {
    // Guard against double cleanup (cancelTask + executeTaskPipeline finally)
    if (this._cleanupDone) return;
    this._cleanupDone = true;

    // Stop all running executors
    for (const [, handle] of this.runningExecutors) {
      handle.executor?.stop();
      handle.abortController.abort();
    }
    this.runningExecutors.clear();

    // Return browser pages to pool so next task can use them
    try {
      const { BrowserSession } = await import("../browser/browser-session.js");
      const session = BrowserSession.getExistingInstance(this.taskId);
      if (session) {
        await session.closeTabGroup(this.taskId);
        await session.close();
      }
    } catch {
      // best effort — browser may not be connected
    }

    // NOTE: Do NOT close the emitter here. The emitter is owned by
    // executeTaskPipeline() which needs it to emit final events (task_failed,
    // end) in its catch/finally block after session.cleanup() returns.
  }
}

// ===== File Type Helpers =====

function inferFileType(ext: string): string {
  // Values must match FileAttachmentCard's FILE_TYPE_ICONS keys and
  // hasPreview list: image, html, csv, excel, code, pdf, office, folder, other
  const map: Record<string, string> = {
    xlsx: "excel", xls: "excel", csv: "csv",
    doc: "office", docx: "office",
    pdf: "pdf",
    pptx: "office", ppt: "office",
    html: "html", htm: "html",
    png: "image", jpg: "image", jpeg: "image", gif: "image", svg: "image",
    mp3: "other", wav: "other", mp4: "other",
    json: "code", xml: "code", txt: "other", md: "other",
    py: "code", js: "code", ts: "code", jsx: "code", tsx: "code",
    css: "code", sql: "code", sh: "code", bash: "code",
    yaml: "code", yml: "code",
  };
  return map[ext] ?? "other";
}

function inferMimeType(ext: string): string {
  const map: Record<string, string> = {
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    xls: "application/vnd.ms-excel",
    csv: "text/csv",
    doc: "application/msword",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    pdf: "application/pdf",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ppt: "application/vnd.ms-powerpoint",
    html: "text/html", htm: "text/html",
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
    gif: "image/gif", svg: "image/svg+xml",
    mp3: "audio/mpeg", wav: "audio/wav", mp4: "video/mp4",
    json: "application/json", xml: "application/xml",
    txt: "text/plain", md: "text/markdown",
    py: "text/x-python", js: "text/javascript", ts: "text/typescript",
  };
  return map[ext] ?? "application/octet-stream";
}

// ===== Utility =====

/**
 * Track whether a promise has settled. Since JS doesn't expose this directly,
 * we attach a settled flag via `.then()` on creation.
 */
const settledMap = new WeakMap<Promise<any>, boolean>();

function trackPromise<T>(promise: Promise<T>): Promise<T> {
  settledMap.set(promise, false);
  promise.then(
    () => settledMap.set(promise, true),
    () => settledMap.set(promise, true),
  );
  return promise;
}

function isPromiseSettled(handle: ExecutorHandle): boolean {
  return settledMap.get(handle.promise) ?? false;
}
