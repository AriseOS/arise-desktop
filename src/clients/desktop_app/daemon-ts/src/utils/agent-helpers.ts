/**
 * Agent Helpers — utilities for working with pi-agent-core Agent.
 *
 * pi-agent-core's Agent.prompt() does NOT throw on API errors.
 * Instead, it sets agent.state.error and emits an agent_end event with
 * stopReason "error". This is by design: the agent is stateful and
 * recoverable, so a single API failure shouldn't destroy the session.
 *
 * For one-shot agents (planner, executor subtasks), we DO want errors
 * to propagate as exceptions so the caller's retry/fail-fast logic works.
 * agentPrompt() provides this behavior.
 *
 * IMPORTANT: pi-ai's streamSimpleAnthropic throws synchronously when
 * apiKey is undefined. This throw is NOT caught by agent-loop's IIFE,
 * causing prompt() to hang forever. We must validate the API key
 * BEFORE calling prompt().
 */

import type { Agent, StreamFn } from "@mariozechner/pi-agent-core";
import { streamSimple } from "@mariozechner/pi-ai";
import { createLogger, isDebug } from "./logging.js";

const logger = createLogger("llm-debug");

/**
 * Call agent.prompt() and throw if the agent encountered an error.
 *
 * Use this for one-shot agents (task planner, task executor subtasks)
 * where an API error should propagate to the caller's try-catch.
 *
 * Do NOT use this for the persistent orchestrator agent — it should
 * handle errors via the event bridge (SSE) and remain alive for the
 * user to retry.
 */
export async function agentPrompt(agent: Agent, message: string): Promise<void> {
  await agent.prompt(message);
  if (agent.state.error) {
    throw new Error(agent.state.error);
  }
}

/**
 * Validate that an API key is available before creating an Agent.
 * Throws immediately if no key can be resolved, preventing the
 * agent-loop hang bug (pi-ai throws synchronously inside an IIFE).
 */
export function requireApiKey(apiKey: string | undefined, provider = "anthropic"): string {
  if (!apiKey) {
    throw new Error(
      `No API key for provider: ${provider}. ` +
      `Set it via POST /api/v1/settings/credentials or ANTHROPIC_API_KEY env var.`,
    );
  }
  return apiKey;
}

// ===== Debug Stream Wrapper =====

function summarizeMessageContent(msg: any): string {
  if (typeof msg.content === "string") return msg.content.slice(0, 500);
  if (!Array.isArray(msg.content)) return String(msg.content).slice(0, 200);
  return msg.content
    .map((c: any) => {
      if (c.type === "text") return c.text?.slice(0, 500) ?? "";
      if (c.type === "thinking") return `[thinking] ${(c.thinking ?? "").slice(0, 300)}`;
      if (c.type === "toolCall") return `[toolCall] ${c.name}(${JSON.stringify(c.arguments).slice(0, 300)})`;
      if (c.type === "image") return "[image]";
      return `[${c.type}]`;
    })
    .join("\n");
}

/**
 * streamSimple wrapper that logs the full LLM request context in debug mode.
 * Logs: system prompt (truncated), message count by role, tool names, and each message preview.
 *
 * Use this instead of importing streamSimple directly.
 */
export const debugStreamSimple: StreamFn = (model, context, options) => {
  if (isDebug) {
    const msgs = context.messages ?? [];
    const roleCounts: Record<string, number> = {};
    for (const m of msgs) {
      roleCounts[m.role] = (roleCounts[m.role] ?? 0) + 1;
    }
    const toolNames = (context.tools ?? []).map((t) => t.name);

    logger.debug(
      {
        model: model.id,
        provider: model.provider,
        messageCount: msgs.length,
        roleCounts,
        toolCount: toolNames.length,
      },
      "=== LLM REQUEST ===",
    );

    // System prompt
    if (context.systemPrompt) {
      logger.debug(
        "  [system] (%d chars): %s",
        context.systemPrompt.length,
        context.systemPrompt.slice(0, 500),
      );
    }

    // Tools
    if (toolNames.length > 0) {
      logger.debug("  [tools]: %s", toolNames.join(", "));
    }

    // Messages (last 10 to avoid flooding)
    const displayMsgs = msgs.length > 10 ? msgs.slice(-10) : msgs;
    if (msgs.length > 10) {
      logger.debug("  ... (%d earlier messages omitted)", msgs.length - 10);
    }
    for (const msg of displayMsgs) {
      const summary = summarizeMessageContent(msg);
      logger.debug("  [%s]: %s", msg.role, summary.slice(0, 300));
    }
  }

  return streamSimple(model, context, options);
};
