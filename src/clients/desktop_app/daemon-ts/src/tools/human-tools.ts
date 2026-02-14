/**
 * Human Tools — Human-in-the-loop interaction for agents.
 *
 * Ported from human_toolkit.py.
 *
 * Tools: ask_human, send_message.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import type { SSEEmitter } from "../events/emitter.js";
import type { TaskState } from "../services/task-state.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("human-tools");

// ===== Schemas =====

const askHumanSchema = Type.Object({
  question: Type.String({
    description:
      "The question to ask the human. Be specific and provide context.",
  }),
  context: Type.Optional(
    Type.String({
      description:
        "Additional context to help the human understand the question.",
    }),
  ),
});

const sendMessageSchema = Type.Object({
  title: Type.String({ description: "Short title for the notification" }),
  description: Type.String({
    description: "Detailed message content",
  }),
});

// ===== Constants =====

const DEFAULT_TIMEOUT_MS = 300_000; // 5 minutes

// ===== Tool Factory =====

export function createHumanTools(opts: {
  taskId: string;
  taskState: TaskState;
  emitter?: SSEEmitter;
  timeoutMs?: number;
  executorId?: string;
  taskLabel?: string;
}): AgentTool<any>[] {
  const {
    taskId,
    taskState,
    emitter,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    executorId,
    taskLabel,
  } = opts;

  const ask_human: AgentTool<typeof askHumanSchema> = {
    name: "ask_human",
    label: "Ask Human",
    description:
      "Ask the human user a question and wait for their response. Use when you need login credentials, CAPTCHA solving, clarification, or confirmation. The human will see a dialog in the app.",
    parameters: askHumanSchema,
    execute: async (_id, params) => {
      const { question, context } = params;

      logger.info(
        { question: question.slice(0, 100) },
        "Asking human",
      );

      // Emit wait_confirm event (frontend shows dialog)
      emitter?.emit({
        action: Action.wait_confirm,
        task_id: taskId,
        content: question,
        question,
        context: context ?? "",
        executor_id: executorId,
        task_label: taskLabel,
      });

      // Wait for human response
      const response = await taskState.waitForHumanResponse(timeoutMs);

      if (response === null) {
        // Emit confirmed with timeout
        emitter?.emit({
          action: Action.confirmed,
          task_id: taskId,
          question,
        });

        return {
          content: [
            {
              type: "text",
              text: `Human did not respond within ${timeoutMs / 1000} seconds. The question was: "${question}". Proceed with your best judgment or try a different approach.`,
            },
          ],
          details: undefined,
        };
      }

      // Emit confirmed event
      emitter?.emit({
        action: Action.confirmed,
        task_id: taskId,
        question,
      });

      logger.info(
        { responseLen: response.length },
        "Human responded",
      );

      return {
        content: [
          { type: "text", text: `Human response: ${response}` },
        ],
        details: undefined,
      };
    },
  };

  const send_message: AgentTool<typeof sendMessageSchema> = {
    name: "send_message",
    label: "Send Message",
    description:
      "Send a one-way notification message to the human user. No response expected. Use for progress updates or important notices.",
    parameters: sendMessageSchema,
    execute: async (_id, params) => {
      const { title, description } = params;

      logger.info({ title }, "Sending notice to human");

      emitter?.emit({
        action: Action.notice,
        task_id: taskId,
        level: "info",
        title,
        message: description,
      });

      return {
        content: [
          {
            type: "text",
            text: `Message sent to user: "${title}"`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [ask_human, send_message];
}
