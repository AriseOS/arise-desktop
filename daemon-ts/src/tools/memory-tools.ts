/**
 * Memory Tools — Query Arise's Workflow Memory (V2).
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
import { getCloudClient } from "../services/cloud-client.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("memory-tools");

// ===== Data Models =====

export interface Intent {
  id: string;
  type: string;
  description?: string;
  text?: string;
  value?: string;
}

export interface IntentSequence {
  id: string;
  intents: Intent[];
  description: string;
}

export interface MemoryState {
  id: string;
  page_url: string;
  page_title?: string;
  description: string;
}

export interface MemoryAction {
  id: string;
  source: string;
  target: string;
  type: string;
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

/**
 * Raw response from POST /api/v1/memory/query.
 *
 * Backend returns:
 *   - query_type: "task" | "navigation" | "action"
 *   - metadata.memory_level: "L1" | "L2" | "L3"
 *   - cognitive_phrase (singular, optional object — NOT an array)
 *   - outgoing_actions (for action queries, NOT "actions")
 */
export interface QueryResult {
  success: boolean;
  query_type?: string;
  metadata?: Record<string, unknown>;
  // Task query fields
  cognitive_phrase?: CognitivePhrase;
  execution_plan?: ExecutionStep[];
  // Common fields
  states?: MemoryState[];
  actions?: MemoryAction[];
  outgoing_actions?: MemoryAction[];
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
  steps: PlanStepData[];
  preferences: string[];
  context_hints: string[];
}

export interface MemoryPlanResult {
  memory_plan: MemoryPlanData;
  debug_trace?: Record<string, unknown>;
}

// ===== Schema =====

const queryPageOpsSchema = Type.Object({
  url: Type.String({ description: "The URL of the current page to query operations for" }),
});

// ===== Format Helpers =====

export function formatCognitivePhrase(phrase: CognitivePhrase): string {
  const lines: string[] = [];
  lines.push(`## Workflow: ${phrase.description}`);
  lines.push("");

  // Format states
  if (phrase.states?.length) {
    lines.push("### Pages:");
    for (const state of phrase.states) {
      lines.push(`- [${state.id}] ${state.page_title ?? ""} (${state.page_url})`);
    }
    lines.push("");
  }

  // Format execution plan
  for (const step of phrase.execution_plan) {
    const state = phrase.states?.find((s) => s.id === step.state_id);
    const title = state ? (state.page_title ?? state.page_url) : step.state_id;
    lines.push(`### Step ${step.index}: ${title}`);
    if (state?.page_url) lines.push(`URL: ${state.page_url}`);

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
  const level = getTaskMemoryLevel(result);
  const phrase = result.cognitive_phrase;

  if (!result.success || (!phrase && !result.states?.length)) {
    return "No memory found for this task.";
  }

  const lines: string[] = [];
  lines.push(`Memory Level: ${level}`);
  lines.push("");

  if (phrase) {
    // Backend returns states/actions at top level, not nested in phrase.
    // Enrich phrase with top-level data so formatCognitivePhrase can render them.
    const enriched: CognitivePhrase = {
      ...phrase,
      states: phrase.states ?? result.states ?? [],
      actions: phrase.actions ?? result.actions ?? [],
      execution_plan: phrase.execution_plan ?? result.execution_plan ?? [],
    };
    lines.push(formatCognitivePhrase(enriched));
  } else if (result.states?.length) {
    // L2 path-based result — no phrase, but has states/actions
    lines.push("## Navigation Path:");
    for (const state of result.states) {
      lines.push(`- [${state.id}] ${state.page_title ?? ""} (${state.page_url})`);
    }
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
        lines.push(`  ${intent.type}: ${intent.description ?? intent.text ?? ""}`);
      }
    }
  }

  // Backend returns "outgoing_actions" for action queries, "actions" for others
  const navActions = result.outgoing_actions ?? result.actions;
  if (navActions?.length) {
    lines.push("\n## Navigation Actions:");
    for (const action of navActions) {
      lines.push(`- ${action.description}`);
    }
  }

  return lines.length > 0 ? lines.join("\n") : "No operations found for this page.";
}

// ===== Memory Level Helpers =====

export function isTaskMemoryHit(result: QueryResult): boolean {
  const level = getTaskMemoryLevel(result);
  return result.success && (level === "L1" || level === "L2");
}

export function getTaskMemoryLevel(
  result: QueryResult,
): "L1" | "L2" | "L3" {
  if (!result.success) return "L3";
  const level = result.metadata?.memory_level as string | undefined;
  if (level === "L1" || level === "L2" || level === "L3") return level;
  return "L3";
}

// ===== MemoryToolkit Class =====

export class MemoryToolkit {
  private taskId: string;
  private emitter?: SSEEmitter;

  constructor(opts: {
    memoryApiBaseUrl?: string; // deprecated — CloudClient reads from config
    taskId: string;
    emitter?: SSEEmitter;
  }) {
    this.taskId = opts.taskId;
    this.emitter = opts.emitter;
  }

  // ===== Framework Methods (not LLM-exposed) =====

  // queryTask is deprecated — use planTask instead (query(task) returns 410)

  async queryNavigation(
    startState: string,
    endState: string,
  ): Promise<QueryResult> {
    logger.info({ startState, endState }, "Querying navigation memory");

    try {
      return (await getCloudClient().memoryQuery({
        target: `${startState} -> ${endState}`,
        as_type: "navigation",
        start_state: startState,
        end_state: endState,
      })) as QueryResult;
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
      return (await getCloudClient().memoryQuery({
        target: target ?? currentState,
        as_type: "actions",
        current_state: currentState,
      })) as QueryResult;
    } catch (err) {
      logger.error({ err }, "Action memory query failed");
      return { success: false, error: String(err) };
    }
  }

  async planTask(task: string): Promise<MemoryPlanResult> {
    logger.info({ task: task.slice(0, 100) }, "Planning task with memory");

    try {
      return (await getCloudClient().memoryPlan({ task })) as MemoryPlanResult;
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
          steps: [],
          preferences: [],
          context_hints: [],
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
        "Query available operations for the current page from Arise's memory. Returns known actions, navigation paths, and behavioral patterns for the given URL.",
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
          memory_level: getTaskMemoryLevel(result),
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
  memoryApiBaseUrl?: string; // deprecated — CloudClient reads from config
  taskId: string;
  emitter?: SSEEmitter;
}): { toolkit: MemoryToolkit; tools: AgentTool<any>[] } {
  const toolkit = new MemoryToolkit(opts);
  return { toolkit, tools: toolkit.getTools() };
}
