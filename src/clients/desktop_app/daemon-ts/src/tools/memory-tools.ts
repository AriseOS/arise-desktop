/**
 * Memory Tools — Query AMI's Workflow Memory (V2).
 *
 * Ported from memory_toolkit.py.
 *
 * LLM-exposed tool: query_page_operations
 * Framework methods: queryTask, queryNavigation, queryActions, planTask
 * HTTP calls to cloud backend: /api/v1/memory/*
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("memory-tools");

// ===== Data Models =====

export interface Intent {
  id: string;
  description: string;
  action_type: string;
  selector?: string;
  value?: string;
}

export interface IntentSequence {
  id: string;
  intents: Intent[];
  description: string;
}

export interface MemoryState {
  id: string;
  url: string;
  title: string;
  description: string;
}

export interface MemoryAction {
  id: string;
  source_id: string;
  target_id: string;
  action_type: string;
  description?: string;
  trigger?: Record<string, unknown>;
  trigger_sequence_id?: string;
}

export interface ExecutionStep {
  index: number;
  state_id: string;
  in_page_sequence_ids: string[];
  navigation_action_id?: string;
  navigation_sequence_id?: string;
}

export interface CognitivePhrase {
  id: string;
  description: string;
  states: MemoryState[];
  actions: MemoryAction[];
  execution_plan: ExecutionStep[];
}

export interface QueryResult {
  success: boolean;
  level?: string; // "L1" | "L2" | "L3"
  cognitive_phrases?: CognitivePhrase[];
  states?: MemoryState[];
  actions?: MemoryAction[];
  intent_sequences?: IntentSequence[];
  error?: string;
}

export interface PlanStepData {
  index: number;
  content: string;
  source: string;
  phrase_id?: string;
  state_ids: string[];
  workflow_guide: string;
}

export interface MemoryPlanData {
  task: string;
  coverage: string;
  preferences: string[];
  uncovered_steps: string[];
  steps: PlanStepData[];
}

export interface MemoryPlanResult {
  memory_plan: MemoryPlanData;
  debug_trace?: Record<string, unknown>;
}

// ===== Schema =====

const queryPageOpsSchema = Type.Object({
  url: Type.String({ description: "The URL of the current page to query operations for" }),
});

// ===== Cloud Client Helpers =====

async function memoryPost(
  baseUrl: string,
  path: string,
  body: Record<string, unknown>,
  apiKey?: string,
): Promise<unknown> {
  const url = `${baseUrl}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (apiKey) {
    headers["X-Ami-API-Key"] = apiKey;
  }

  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Memory API error ${resp.status}: ${text}`);
  }

  return resp.json();
}

// ===== Format Helpers =====

export function formatCognitivePhrase(phrase: CognitivePhrase): string {
  const lines: string[] = [];
  lines.push(`## Workflow: ${phrase.description}`);
  lines.push("");

  // Format states
  if (phrase.states?.length) {
    lines.push("### Pages:");
    for (const state of phrase.states) {
      lines.push(`- [${state.id}] ${state.title} (${state.url})`);
    }
    lines.push("");
  }

  // Format execution plan
  for (const step of phrase.execution_plan) {
    const state = phrase.states?.find((s) => s.id === step.state_id);
    const title = state ? state.title : step.state_id;
    lines.push(`### Step ${step.index}: ${title}`);
    if (state?.url) lines.push(`URL: ${state.url}`);

    if (step.in_page_sequence_ids?.length) {
      lines.push(`  Page operations: ${step.in_page_sequence_ids.join(", ")}`);
    }
    if (step.navigation_action_id) {
      const action = phrase.actions?.find((a) => a.id === step.navigation_action_id);
      lines.push(`  Navigate: ${action?.description ?? step.navigation_action_id}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

export function formatTaskResult(result: QueryResult): string {
  if (!result.success || !result.cognitive_phrases?.length) {
    return "No memory found for this task.";
  }

  const lines: string[] = [];
  lines.push(`Memory Level: ${result.level ?? "unknown"}`);
  lines.push("");

  for (const phrase of result.cognitive_phrases) {
    lines.push(formatCognitivePhrase(phrase));
  }

  return lines.join("\n");
}

export function formatPageOperations(result: QueryResult): string {
  const lines: string[] = [];

  if (result.intent_sequences?.length) {
    lines.push("## Available Page Operations:");
    for (const seq of result.intent_sequences) {
      lines.push(`- ${seq.description}`);
      for (const intent of seq.intents) {
        lines.push(`  ${intent.action_type}: ${intent.description}`);
      }
    }
  }

  if (result.actions?.length) {
    lines.push("\n## Navigation Actions:");
    for (const action of result.actions) {
      lines.push(`- ${action.description}`);
    }
  }

  return lines.length > 0 ? lines.join("\n") : "No operations found for this page.";
}

// ===== Memory Level Helpers =====

export function isTaskMemoryHit(result: QueryResult): boolean {
  return result.success && (result.level === "L1" || result.level === "L2");
}

export function getTaskMemoryLevel(
  result: QueryResult,
): "L1" | "L2" | "L3" {
  if (!result.success) return "L3";
  return (result.level as "L1" | "L2" | "L3") ?? "L3";
}

// ===== MemoryToolkit Class =====

export class MemoryToolkit {
  private baseUrl: string;
  private apiKey?: string;
  private userId?: string;
  private taskId: string;
  private emitter?: SSEEmitter;

  constructor(opts: {
    memoryApiBaseUrl: string;
    apiKey?: string;
    userId?: string;
    taskId: string;
    emitter?: SSEEmitter;
  }) {
    this.baseUrl = opts.memoryApiBaseUrl;
    this.apiKey = opts.apiKey;
    this.userId = opts.userId;
    this.taskId = opts.taskId;
    this.emitter = opts.emitter;
  }

  // ===== Framework Methods (not LLM-exposed) =====

  async queryTask(task: string): Promise<QueryResult> {
    logger.info({ task: task.slice(0, 100) }, "Querying task memory");

    this.emitter?.emit({
      action: Action.memory_query,
      task_id: this.taskId,
      query: task,
      top_k: 5,
    });

    try {
      const data = (await memoryPost(
        this.baseUrl,
        "/api/v1/memory/query",
        { query: task, query_type: "task", top_k: 5 },
        this.apiKey,
      )) as QueryResult;

      this.emitter?.emit({
        action: Action.memory_result,
        task_id: this.taskId,
        paths_count: data.cognitive_phrases?.length ?? 0,
        paths: (data.cognitive_phrases ?? []) as unknown as Record<string, unknown>[],
        has_workflow: !!data.cognitive_phrases?.length,
        method: "task_query",
      });

      return data;
    } catch (err) {
      logger.error({ err }, "Task memory query failed");
      return { success: false, error: String(err) };
    }
  }

  async queryNavigation(
    startState: string,
    endState: string,
  ): Promise<QueryResult> {
    logger.info({ startState, endState }, "Querying navigation memory");

    try {
      return (await memoryPost(
        this.baseUrl,
        "/api/v1/memory/query",
        {
          query: `${startState} -> ${endState}`,
          query_type: "navigation",
          start_state: startState,
          end_state: endState,
        },
        this.apiKey,
      )) as QueryResult;
    } catch (err) {
      logger.error({ err }, "Navigation memory query failed");
      return { success: false, error: String(err) };
    }
  }

  async queryActions(
    currentState: string,
    target?: string,
  ): Promise<QueryResult> {
    logger.info({ currentState, target }, "Querying action memory");

    try {
      return (await memoryPost(
        this.baseUrl,
        "/api/v1/memory/query",
        {
          query: currentState,
          query_type: "actions",
          target,
        },
        this.apiKey,
      )) as QueryResult;
    } catch (err) {
      logger.error({ err }, "Action memory query failed");
      return { success: false, error: String(err) };
    }
  }

  async planTask(task: string): Promise<MemoryPlanResult> {
    logger.info({ task: task.slice(0, 100) }, "Planning task with memory");

    try {
      return (await memoryPost(
        this.baseUrl,
        "/api/v1/memory/plan",
        { task, user_id: this.userId },
        this.apiKey,
      )) as MemoryPlanResult;
    } catch (err) {
      logger.error({ err }, "Memory plan request failed");
      const isTimeout =
        (err instanceof DOMException && err.name === "TimeoutError") ||
        (err instanceof Error && err.message.includes("timeout"));
      if (isTimeout) {
        throw new Error("Memory plan query timed out");
      }
      return {
        memory_plan: {
          task,
          coverage: "none",
          preferences: [],
          uncovered_steps: [task],
          steps: [],
        },
      };
    }
  }

  // ===== LLM-Exposed Tools =====

  getTools(): AgentTool<any>[] {
    const query_page_operations: AgentTool<typeof queryPageOpsSchema> = {
      name: "query_page_operations",
      label: "Query Page Operations",
      description:
        "Query available operations for the current page from AMI's memory. Returns known actions, navigation paths, and behavioral patterns for the given URL.",
      parameters: queryPageOpsSchema,
      execute: async (_id, params) => {
        const { url } = params;
        logger.info({ url }, "Querying page operations");

        const result = await this.queryActions(url);
        const text = formatPageOperations(result);

        this.emitter?.emit({
          action: Action.memory_event,
          task_id: this.taskId,
          event_type: "page_operations_queried",
          data: { url, found: result.success },
          memory_level: result.level,
        });

        return {
          content: [{ type: "text", text }],
          details: undefined,
        };
      },
    };

    return [query_page_operations];
  }
}

// ===== Convenience Factory =====

export function createMemoryTools(opts: {
  memoryApiBaseUrl: string;
  apiKey?: string;
  userId?: string;
  taskId: string;
  emitter?: SSEEmitter;
}): { toolkit: MemoryToolkit; tools: AgentTool<any>[] } {
  const toolkit = new MemoryToolkit(opts);
  return { toolkit, tools: toolkit.getTools() };
}
