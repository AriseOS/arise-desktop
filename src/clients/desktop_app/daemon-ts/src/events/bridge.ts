/**
 * Event Bridge — maps pi-agent-core AgentEvent → SSE ActionData.
 *
 * Subscribes to an Agent's event stream and forwards translated events
 * to an SSEEmitter for streaming to the frontend.
 */

import type { AgentEvent } from "@mariozechner/pi-agent-core";
import { Action, type ActionData } from "./types.js";
import type { SSEEmitter } from "./emitter.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("bridge");

const isDebug = !!(process.env.AMI_DEBUG || process.env.LOG_LEVEL === "debug");

/**
 * Safely JSON.stringify with circular reference protection.
 */
function safeStringify(value: unknown, maxLen = 200): string {
  try {
    const str = JSON.stringify(value);
    return str?.slice(0, maxLen) ?? "";
  } catch {
    return String(value).slice(0, maxLen);
  }
}

/**
 * Extract a concise summary of message content for debug logging.
 * For text/thinking: truncated text. For toolCall: name + args preview.
 */
function summarizeContent(
  content: Array<{ type: string; text?: string; thinking?: string; name?: string; arguments?: unknown }>,
  maxLen = 500,
): string {
  const parts: string[] = [];
  for (const c of content) {
    if (c.type === "text" && c.text) {
      parts.push(`[text] ${c.text.slice(0, maxLen)}`);
    } else if (c.type === "thinking" && c.thinking) {
      parts.push(`[thinking] ${c.thinking.slice(0, maxLen)}`);
    } else if (c.type === "toolCall") {
      parts.push(`[toolCall] ${c.name}(${safeStringify(c.arguments, maxLen)})`);
    }
  }
  return parts.join("\n");
}

/**
 * Extract text from an agent message's content array.
 */
function extractText(message: { content?: Array<{ type: string; text?: string; thinking?: string }> }): string {
  if (!message?.content) return "";
  return message.content
    .map((c) => {
      if (c.type === "text") return c.text ?? "";
      if (c.type === "thinking") return c.thinking ?? "";
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

/**
 * Derive toolkit name from tool name (e.g., "browser_click" → "BrowserToolkit").
 */
function deriveToolkitName(toolName: string): string {
  const prefix = toolName.split("_")[0];
  if (!prefix) return "Toolkit";
  return prefix.charAt(0).toUpperCase() + prefix.slice(1) + "Toolkit";
}

/**
 * Map a single pi-agent-core AgentEvent to an SSE ActionData, or null if no mapping.
 */
export function mapAgentEventToSSE(
  event: AgentEvent,
  taskId: string,
  agentName = "Agent",
): ActionData | null {
  const timestamp = new Date().toISOString();

  switch (event.type) {
    case "agent_start":
      return {
        action: Action.activate_agent,
        agent_name: agentName,
        process_task_id: taskId,
        task_id: taskId,
        timestamp,
      };

    case "agent_end": {
      // Extract final output from agent messages
      const messages = (event as any).messages as any[] | undefined;
      let message = "";
      let errorMessage: string | undefined;
      if (messages && messages.length > 0) {
        const lastMsg = messages[messages.length - 1];
        if (lastMsg?.role === "assistant") {
          message = extractText(lastMsg);
          // Detect error stop reason from the last assistant message
          if (lastMsg.stopReason === "error" && lastMsg.errorMessage) {
            errorMessage = lastMsg.errorMessage;
          }
        }
      }
      return {
        action: Action.deactivate_agent,
        agent_name: agentName,
        process_task_id: taskId,
        message,
        error: errorMessage,
        task_id: taskId,
        timestamp,
      };
    }

    case "message_update": {
      // Accumulate streaming deltas — do NOT emit per-token SSE events.
      // The accumulated text is emitted as a single agent_thinking event
      // at turn boundaries (tool_execution_start / message_end / turn_end).
      // This is handled in bridgeAgentToSSE() below.
      return null;
    }

    case "tool_execution_start":
      return {
        action: Action.activate_toolkit,
        toolkit_name: deriveToolkitName(event.toolName),
        method_name: event.toolName,
        input_preview: safeStringify(event.args),
        process_task_id: event.toolCallId,
        task_id: taskId,
        timestamp,
      };

    case "tool_execution_end":
      return {
        action: Action.deactivate_toolkit,
        toolkit_name: deriveToolkitName(event.toolName),
        method_name: event.toolName,
        success: !event.isError,
        output_preview: typeof event.result === "string"
          ? event.result.slice(0, 200)
          : safeStringify(event.result),
        process_task_id: event.toolCallId,
        task_id: taskId,
        timestamp,
      };

    // Turn lifecycle events — no direct SSE mapping needed
    case "turn_start":
    case "turn_end":
    case "message_start":
    case "message_end":
    case "tool_execution_update":
      return null;

    default:
      return null;
  }
}

/**
 * Bridge: subscribe to an Agent and forward events to an SSEEmitter.
 * Returns an unsubscribe function.
 *
 * Detects agent errors (stopReason === "error") and emits SSE error events
 * so the frontend is notified immediately when an API call fails.
 *
 * Also tracks accumulated text within a turn: when a tool_execution_start
 * fires after text was emitted, an agent_report(report_type="thinking")
 * is sent so the frontend ChatBox shows the agent's reasoning.
 * (Matches Python AMIAgent.astep() lines 558-564)
 */
export function bridgeAgentToSSE(
  agent: { subscribe: (cb: (event: AgentEvent) => void) => () => void },
  emitter: SSEEmitter,
  taskId: string,
  agentName = "Agent",
  subtaskLabel?: string,
): () => void {
  // Accumulate streaming deltas within a turn.
  // Emit as a single agent_thinking + agent_report at boundaries:
  //   - tool_execution_start: thinking before a tool call (+ agent_report)
  //   - agent_end: final response text (no tool call followed)
  //
  // Event order from pi-agent-core for a tool-call turn:
  //   turn_start → message_start → message_update* → message_end → tool_execution_start → ...
  // Event order for a text-only turn (final answer):
  //   turn_start → message_start → message_update* → message_end → turn_end → agent_end
  //
  // We do NOT emit at message_end because we can't tell if a tool_execution_start
  // will follow. Instead we emit at tool_execution_start or agent_end.
  let turnText = "";
  // Whether accumulated text was already emitted (to avoid double-emit)
  let flushed = false;

  return agent.subscribe((event: AgentEvent) => {
    // Reset accumulated text at turn boundaries
    if (event.type === "turn_start") {
      turnText = "";
      flushed = false;
      return;
    }

    // Accumulate streaming deltas (message_update returns null from mapAgentEventToSSE)
    if (event.type === "message_update") {
      const ame = (event as any).assistantMessageEvent;
      if (ame) {
        if (ame.type === "text_delta" || ame.type === "thinking_delta") {
          turnText += ame.delta ?? "";
        }
      }
      return;
    }

    // Debug: log full message content at message boundaries
    if (isDebug && event.type === "message_end") {
      const msg = (event as any).message;
      if (msg?.role === "user") {
        const text = extractText(msg);
        logger.debug(
          { agent: agentName, role: "user", contentLen: text.length },
          ">>> LLM INPUT:\n%s",
          text.slice(0, 2000),
        );
      } else if (msg?.role === "assistant") {
        const summary = msg.content ? summarizeContent(msg.content, 1000) : "";
        const usage = msg.usage;
        logger.debug(
          {
            agent: agentName,
            role: "assistant",
            stopReason: msg.stopReason,
            usage: usage ? {
              input: usage.input,
              output: usage.output,
              cacheRead: usage.cacheRead,
              total: usage.totalTokens,
            } : undefined,
          },
          "<<< LLM OUTPUT:\n%s",
          summary.slice(0, 2000),
        );
      } else if (msg?.role === "toolResult") {
        const text = extractText(msg);
        logger.debug(
          { agent: agentName, role: "toolResult", tool: msg.toolName, isError: msg.isError },
          "--- TOOL RESULT [%s]:\n%s",
          msg.toolName,
          text.slice(0, 1000),
        );
      }
    }

    // Skip message_end — we flush at tool_execution_start or agent_end instead
    if (event.type === "message_end" || event.type === "message_start") {
      return;
    }

    const sseEvent = mapAgentEventToSSE(event, taskId, agentName);
    if (sseEvent) {
      // When tool execution starts and there's accumulated text,
      // emit agent_thinking + agent_report before the tool event
      if (sseEvent.action === Action.activate_toolkit && turnText && !flushed) {
        emitter.emitAgentThinking(turnText.slice(0, 500), agentName);
        emitter.emitAgentReport(turnText.slice(0, 300), "thinking", undefined, undefined, undefined, subtaskLabel);
        logger.info(
          { agent: agentName, thinking: turnText.slice(0, 200) },
          "Agent thinking before tool call",
        );
        flushed = true;
      }

      emitter.emit(sseEvent);

      // Log tool execution events
      if (sseEvent.action === Action.activate_toolkit) {
        logger.info(
          { agent: agentName, tool: (sseEvent as any).method_name },
          "Tool call started",
        );
      }
      if (sseEvent.action === Action.deactivate_toolkit) {
        logger.info(
          {
            agent: agentName,
            tool: (sseEvent as any).method_name,
            success: (sseEvent as any).success,
          },
          "Tool call ended",
        );
      }

      // If agent_end: emit remaining text + handle errors
      if (sseEvent.action === Action.deactivate_agent) {
        if (turnText && !flushed) {
          emitter.emitAgentThinking(turnText.slice(0, 500), agentName);
          logger.info(
            { agent: agentName, thinking: turnText.slice(0, 200) },
            "Agent final response",
          );
        }
        if ("error" in sseEvent && sseEvent.error) {
          logger.error({ agent: agentName, error: sseEvent.error }, "Agent ended with error");
          emitter.emitError(
            sseEvent.error,
            "AGENT_ERROR",
            false,
          );
        }
      }
    }
  });
}
