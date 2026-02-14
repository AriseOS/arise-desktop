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
  browser_click: ["coordinate", "element_description"],
  browser_type: ["coordinate", "text", "element_description"],
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
      { content: string; isError: boolean }
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
      const inputSummary = ExecutionDataCollector.compressToolInput(
        tu.name,
        tu.input,
      );
      const resultInfo = toolResults.get(tu.id);
      const resultContent = resultInfo?.content ?? "";
      const isError = resultInfo?.isError ?? false;
      const currentUrl =
        ExecutionDataCollector.extractCurrentUrl(resultContent);
      const resultSummary = resultContent.slice(0, 300);
      const judgment = (judgments.get(tu.id) ?? "").slice(0, 500);
      const thinking = tu.thinking.slice(0, 500);

      records.push({
        thinking,
        toolName: tu.name,
        inputSummary,
        success: !isError,
        resultSummary,
        judgment,
        currentUrl,
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
}
