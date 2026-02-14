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

import type { Agent } from "@mariozechner/pi-agent-core";

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
