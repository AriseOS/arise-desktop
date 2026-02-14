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
      // Use the streaming delta from assistantMessageEvent for incremental updates
      const ame = (event as any).assistantMessageEvent;
      let content = "";
      if (ame) {
        if (ame.type === "text_delta") {
          content = ame.delta ?? "";
        } else if (ame.type === "thinking_delta") {
          content = ame.delta ?? "";
        }
      }
      // Fallback: extract from accumulated message
      if (!content) {
        content = extractText((event as any).message);
      }
      if (!content) return null;
      return {
        action: Action.agent_thinking,
        agent_name: agentName,
        thinking: content,
        task_id: taskId,
        timestamp,
      };
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
): () => void {
  // Track accumulated text within a turn for agent_report emission
  let turnText = "";

  return agent.subscribe((event: AgentEvent) => {
    // Reset accumulated text at turn boundaries
    if (event.type === "turn_start") {
      turnText = "";
      return;
    }

    const sseEvent = mapAgentEventToSSE(event, taskId, agentName);
    if (sseEvent) {
      emitter.emit(sseEvent);

      // Track text from message_update → agent_thinking
      if (sseEvent.action === Action.agent_thinking && "thinking" in sseEvent) {
        const delta = (sseEvent as any).thinking;
        turnText += delta;
      }

      // When tool execution starts and there's accumulated text,
      // emit agent_report so it shows in ChatBox as a thinking bubble
      if (sseEvent.action === Action.activate_toolkit && turnText) {
        logger.info(
          { agent: agentName, thinking: turnText.slice(0, 200) },
          "Agent thinking before tool call",
        );
        emitter.emitAgentReport(turnText.slice(0, 300), "thinking");
        turnText = "";
      }

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

      // If agent_end carried an error, emit a dedicated SSE error event
      if (sseEvent.action === Action.deactivate_agent) {
        if ("error" in sseEvent && sseEvent.error) {
          logger.error({ agent: agentName, error: sseEvent.error }, "Agent ended with error");
          emitter.emitError(
            sseEvent.error,
            "AGENT_ERROR",
            false,
          );
        }
        // Log remaining thinking text that wasn't followed by a tool call
        if (turnText) {
          logger.info(
            { agent: agentName, thinking: turnText.slice(0, 200) },
            "Agent final response",
          );
        }
      }
    }
  });
}
