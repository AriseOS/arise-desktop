/**
 * Execution Data Collector — Extracts tool use and thinking from agent messages.
 *
 * Ported from execution_data_collector.py.
 *
 * Collects execution data from agent conversations after each subtask completes.
 * Compresses tool inputs/outputs and extracts thinking/judgment for the LearnerAgent.
 *
 * Data source: agent.state.messages returns Anthropic-format messages.
 */

import type { Agent } from "@mariozechner/pi-agent-core";
import {
  SubtaskState,
  type AMISubtask,
  type ToolUseRecord,
  type SubtaskExecutionData,
  type TaskExecutionData,
} from "./schemas.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("execution-data-collector");

// Tools to skip — snapshot is too noisy, send_message/replan are meta
const SKIP_TOOLS = new Set([
  "browser_get_page_snapshot",
  "send_message",
  "replan_review_context",
  "replan_split_and_handoff",
]);

// Tool input compression rules per tool type
// Keys must match actual tool names from browser-tools.ts
const INPUT_KEEP_FIELDS: Record<string, string[]> = {
  browser_visit_page: ["url"],
  browser_click: ["ref", "element_description"],
  browser_type: ["ref", "text", "element_description"],
  browser_scroll: ["coordinate", "direction"],
  browser_select: ["coordinate", "value"],
  browser_enter: [],
  browser_back: [],
  browser_forward: [],
  browser_press_key: ["key"],
  browser_switch_tab: ["tab_id"],
  browser_close_tab: ["tab_id"],
  browser_new_tab: ["url"],
  search_google: ["query"],
  take_note: ["content"],
  read_note: [],
};

// ===== ExecutionDataCollector =====

export class ExecutionDataCollector {
  private subtaskData: SubtaskExecutionData[] = [];

  /**
   * Extract and compress execution data from a completed subtask.
   */
  collectSubtaskData(agent: Agent, subtask: AMISubtask): void {
    const messages = agent.state.messages as any[];
    const toolRecords = this.extractToolRecords(messages);

    const resultSummary = subtask.result
      ? subtask.result.slice(0, 500)
      : "";

    const data: SubtaskExecutionData = {
      subtaskId: subtask.id,
      content: subtask.content,
      agentType: subtask.agentType,
      dependsOn: subtask.dependsOn,
      state: subtask.state,
      resultSummary,
      toolRecords,
    };

    this.subtaskData.push(data);

    logger.info(
      {
        subtaskId: subtask.id,
        toolRecordCount: toolRecords.length,
      },
      "Collected execution data",
    );
  }

  /**
   * Build complete TaskExecutionData from collected subtask data.
   */
  buildTaskData(
    taskId: string,
    userRequest: string,
    subtasks: AMISubtask[],
  ): TaskExecutionData {
    const completedCount = subtasks.filter(
      (s) => s.state === SubtaskState.DONE,
    ).length;
    const failedCount = subtasks.filter(
      (s) => s.state === SubtaskState.FAILED,
    ).length;

    return {
      taskId,
      userRequest,
      subtasks: this.subtaskData,
      completedCount,
      failedCount,
      totalCount: subtasks.length,
    };
  }

  /**
   * Serialize TaskExecutionData to snake_case dict for cloud API.
   * Matches Python's TaskExecutionData.to_dict().
   */
  static toDict(data: TaskExecutionData): Record<string, unknown> {
    return {
      task_id: data.taskId,
      user_request: data.userRequest,
      subtasks: data.subtasks.map((s) => ({
        subtask_id: s.subtaskId,
        content: s.content,
        agent_type: s.agentType,
        depends_on: s.dependsOn,
        state: s.state,
        result_summary: s.resultSummary,
        tool_records: s.toolRecords.map((r) => ({
          thinking: r.thinking,
          tool_name: r.toolName,
          input_summary: r.inputSummary,
          success: r.success,
          result_summary: r.resultSummary,
          judgment: r.judgment,
          current_url: r.currentUrl,
          current_page_title: r.currentPageTitle,
        })),
      })),
      completed_count: data.completedCount,
      failed_count: data.failedCount,
      total_count: data.totalCount,
    };
  }

  // ===== Internal: Extract Tool Records =====

  private extractToolRecords(messages: any[]): ToolUseRecord[] {
    const records: ToolUseRecord[] = [];

    // First pass: collect tool_use blocks with their thinking
    const toolUses: Array<{
      id: string;
      name: string;
      input: any;
      thinking: string;
    }> = [];

    // pi-ai/pi-agent-core message format:
    // - AssistantMessage: role="assistant", content: (TextContent | ThinkingContent | ToolCall)[]
    //   ToolCall: { type: "toolCall", id, name, arguments }
    // - ToolResultMessage: role="toolResult", toolCallId, toolName, content, isError

    for (const msg of messages) {
      if (msg.role !== "assistant") continue;
      const content = msg.content;
      if (!Array.isArray(content)) continue;

      let currentText = "";
      for (const block of content) {
        if (typeof block !== "object" || block === null) continue;
        if (block.type === "text") {
          currentText = block.text ?? "";
        } else if (block.type === "toolCall") {
          const toolName = block.name ?? "";
          if (SKIP_TOOLS.has(toolName)) continue;
          toolUses.push({
            id: block.id ?? "",
            name: toolName,
            input: block.arguments ?? {},
            thinking: currentText,
          });
          currentText = "";
        }
      }
    }

    // Second pass: collect toolResult messages (separate messages in pi-agent-core)
    const toolResults = new Map<
      string,
      { content: string; isError: boolean; details?: any }
    >();

    for (const msg of messages) {
      if (msg.role !== "toolResult") continue;
      const toolCallId = msg.toolCallId ?? "";
      const isError = msg.isError ?? false;
      let resultContent = "";
      if (Array.isArray(msg.content)) {
        resultContent = msg.content
          .filter(
            (rb: any) =>
              typeof rb === "object" && rb?.type === "text",
          )
          .map((rb: any) => rb.text ?? "")
          .join("\n");
      } else if (typeof msg.content === "string") {
        resultContent = msg.content;
      }
      toolResults.set(toolCallId, {
        content: String(resultContent),
        isError,
        details: msg.details,
      });
    }

    // Third pass: collect judgment (assistant text after toolResult)
    const judgments = new Map<string, string>();
    const resultLocations: Array<{ msgIdx: number; toolCallId: string }> =
      [];

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role !== "toolResult") continue;
      resultLocations.push({
        msgIdx: i,
        toolCallId: msg.toolCallId ?? "",
      });
    }

    for (const { msgIdx, toolCallId } of resultLocations) {
      for (let j = msgIdx + 1; j < messages.length; j++) {
        if (messages[j].role === "assistant") {
          const content = messages[j].content;
          if (Array.isArray(content)) {
            for (const block of content) {
              if (
                typeof block === "object" &&
                block !== null &&
                block.type === "text"
              ) {
                judgments.set(toolCallId, block.text ?? "");
                break;
              }
            }
          }
          break;
        }
      }
    }

    // Build ToolUseRecords
    for (const tu of toolUses) {
      const resultInfo = toolResults.get(tu.id);
      const resultContent = resultInfo?.content ?? "";
      const isError = resultInfo?.isError ?? false;
      const currentUrl =
        ExecutionDataCollector.extractCurrentUrl(resultContent);
      const currentPageTitle =
        ExecutionDataCollector.extractPageTitle(resultContent);
      const resultSummary = resultContent.slice(0, 300);
      const judgment = (judgments.get(tu.id) ?? "").slice(0, 500);
      const thinking = tu.thinking.slice(0, 500);

      // Enrich click/type/select inputs with element name from structured details
      let enrichedInput = tu.input;
      const details = resultInfo?.details;
      if (details?.element_name && typeof tu.input === "object" && tu.input !== null) {
        enrichedInput = { ...tu.input, element_description: details.element_name };
      }

      const inputSummary = ExecutionDataCollector.compressToolInput(
        tu.name,
        enrichedInput,
      );

      records.push({
        thinking,
        toolName: tu.name,
        inputSummary,
        success: !isError,
        resultSummary,
        judgment,
        currentUrl,
        currentPageTitle,
      });
    }

    return records;
  }

  // ===== Static Helpers =====

  static compressToolInput(toolName: string, inputDict: any): string {
    if (typeof inputDict !== "object" || inputDict === null) {
      return String(inputDict).slice(0, 200);
    }

    const keepFields = INPUT_KEEP_FIELDS[toolName];
    if (keepFields !== undefined) {
      if (keepFields.length === 0) return "";
      const filtered: Record<string, any> = {};
      for (const k of keepFields) {
        if (k in inputDict) filtered[k] = inputDict[k];
      }
      return JSON.stringify(filtered).slice(0, 300);
    }

    // Default: keep all fields but truncate values
    const compressed: Record<string, string> = {};
    for (const [k, v] of Object.entries(inputDict)) {
      const sv = String(v);
      compressed[k] = sv.length > 100 ? sv.slice(0, 100) : sv;
    }
    return JSON.stringify(compressed).slice(0, 300);
  }

  static extractCurrentUrl(toolResultText: string): string {
    if (!toolResultText) return "";
    const match = toolResultText.match(/URL:\*?\*?\s*(https?:\/\/\S+)/);
    return match ? match[1] : "";
  }

  static extractPageTitle(toolResultText: string): string {
    if (!toolResultText) return "";
    const match = toolResultText.match(/\*\*Current Page:\*\*\s*(.+)/);
    return match ? match[1].trim() : "";
  }

  // ===== Conversation Trace Generation =====

  /**
   * Extract user/assistant text turns from pi-agent-core messages.
   *
   * Filters out tool_use/toolResult details — only keeps human-readable
   * text content from user and assistant messages.
   *
   * pi-agent-core message format:
   * - UserMessage: role="user", content: string | ContentBlock[]
   * - AssistantMessage: role="assistant", content: (TextContent | ThinkingContent | ToolCall)[]
   * - ToolResultMessage: role="toolResult" (skipped)
   *
   * @param messages - agent.state.messages from pi-agent-core Agent
   * @param activeUrls - Optional list of active browser URLs for session_context
   * @param activeBrowserTask - Optional description of active browser task
   */
  static buildConversationTrace(
    messages: any[],
    activeUrls?: string[],
    activeBrowserTask?: string,
  ): ConversationTrace | null {
    const turns: ConversationTurn[] = [];

    // Backend schema enforces max_length=10000 on ConversationTurn.text
    const MAX_TURN_TEXT = 10000;

    for (const msg of messages) {
      if (msg.role === "user") {
        // User messages: extract text content
        const text = ExecutionDataCollector.extractMessageText(msg);
        if (!text) continue;

        // Filter out orchestrator-injected synthetic messages
        if (
          text.startsWith("[EXECUTION COMPLETE:") ||
          text.startsWith("[USER MESSAGE]") ||
          text.startsWith("[SYSTEM]") ||
          text.startsWith("[TASK")
        ) {
          // Extract the real user message from "[USER MESSAGE]\n<actual text>" if present
          const userMsgMatch = text.match(/\[USER MESSAGE\]\n([\s\S]+)/);
          if (userMsgMatch) {
            turns.push({ role: "user", text: userMsgMatch[1].trim().slice(0, MAX_TURN_TEXT) });
          }
          continue;
        }

        turns.push({ role: "user", text: text.slice(0, MAX_TURN_TEXT) });
      } else if (msg.role === "assistant") {
        // Assistant messages: extract only text blocks (skip toolCall, thinking)
        const text = ExecutionDataCollector.extractAssistantText(msg);
        if (text) {
          turns.push({ role: "assistant", text: text.slice(0, MAX_TURN_TEXT) });
        }
      }
      // Skip toolResult messages — they are internal tool call results
    }

    if (turns.length === 0) return null;

    const trace: ConversationTrace = { turns };

    // Attach session_context if any URLs or browser task are active
    if ((activeUrls && activeUrls.length > 0) || activeBrowserTask) {
      trace.session_context = {};
      if (activeBrowserTask) {
        trace.session_context.active_browser_task = activeBrowserTask;
      }
      if (activeUrls && activeUrls.length > 0) {
        trace.session_context.active_urls = activeUrls;
      }
    }

    return trace;
  }

  /**
   * Extract text from a user message (string or content blocks).
   */
  private static extractMessageText(msg: any): string {
    if (typeof msg.content === "string") {
      return msg.content.trim();
    }
    if (Array.isArray(msg.content)) {
      return msg.content
        .filter((b: any) => typeof b === "object" && b !== null && b.type === "text")
        .map((b: any) => b.text ?? "")
        .join("\n")
        .trim();
    }
    return "";
  }

  /**
   * Extract only text content from an assistant message (skip toolCall/thinking blocks).
   */
  private static extractAssistantText(msg: any): string {
    const content = msg.content;
    if (!Array.isArray(content)) return "";

    return content
      .filter((b: any) => typeof b === "object" && b !== null && b.type === "text")
      .map((b: any) => b.text ?? "")
      .join("\n")
      .trim();
  }

  // ===== Browser Trace Generation =====

  /**
   * Build a simplified trace from TaskExecutionData for the learn-from-trace endpoint.
   *
   * Extracts browser tool records and maps them back to trace actions.
   * Inserts synthetic `navigate` steps when URL changes between records.
   */
  static buildTrace(data: TaskExecutionData): TraceData {
    const toolToAction: Record<string, string> = {
      browser_visit_page: "navigate",
      browser_click: "click",
      browser_type: "type",
      browser_scroll: "scroll",
      browser_select: "select",
      browser_enter: "submit",
      search_google: "navigate",
    };

    const steps: TraceStep[] = [];
    let lastUrl = "";

    for (const subtask of data.subtasks) {
      if (subtask.agentType !== "browser") continue;

      for (const record of subtask.toolRecords) {
        const action = toolToAction[record.toolName];
        if (!action) continue;

        const url = record.currentUrl || "";

        const pageTitle = record.currentPageTitle || "";

        // Insert navigate step when URL changes (but not for navigate actions themselves)
        if (url && url !== lastUrl && action !== "navigate") {
          const navStep: TraceStep = { url, action: "navigate" };
          if (pageTitle) navStep.page_title = pageTitle;
          steps.push(navStep);
        }

        const step: TraceStep = { url, action };

        // Extract target and value from inputSummary JSON
        if (record.inputSummary) {
          try {
            const input = JSON.parse(record.inputSummary);
            if (input.element_description) {
              step.target = input.element_description;
            }
            if (input.text) {
              step.value = input.text;
            }
            if (input.url && action === "navigate") {
              step.url = input.url;
            }
            if (input.query && record.toolName === "search_google") {
              step.value = input.query;
            }
            if (input.direction && action === "scroll") {
              step.target = input.direction;
            }
            if (input.value && action === "select") {
              step.value = input.value;
            }
          } catch {
            // inputSummary is not valid JSON — skip extraction
          }
        }

        // Include rich execution fields from ToolUseRecord
        if (pageTitle) step.page_title = pageTitle;
        if (record.thinking) step.thinking = record.thinking;
        if (!record.success) step.success = false;
        if (record.resultSummary) step.result_summary = record.resultSummary;
        if (record.judgment) step.judgment = record.judgment;

        steps.push(step);
        lastUrl = step.url || url;
      }
    }

    // Append done marker
    if (steps.length > 0) {
      steps.push({ url: lastUrl, action: "done" });
    }

    const success = data.completedCount > 0 && data.failedCount === 0;

    return {
      type: "browser_workflow",
      task: data.userRequest,
      success,
      steps,
      source: "arise-desktop",
    };
  }
}

// ===== Trace Types =====

export interface TraceStep {
  url: string;
  action: string;
  target?: string;
  value?: string;
  page_title?: string;
  // Rich execution fields (optional, for LearnerAgent task outcome judgment)
  thinking?: string;
  success?: boolean;
  result_summary?: string;
  judgment?: string;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  text: string;
}

export interface ConversationTrace {
  turns: ConversationTurn[];
  session_context?: {
    active_browser_task?: string;
    active_urls?: string[];
  };
}

export interface TraceData {
  type: string;
  task: string;
  success: boolean;
  steps: TraceStep[];
  source: string;
  conversation?: ConversationTrace;
}
