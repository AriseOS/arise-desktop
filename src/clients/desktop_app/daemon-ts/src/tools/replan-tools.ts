/**
 * Replan Tools — agent can dynamically add follow-up subtasks.
 *
 * Ported from replan_toolkit.py.
 *
 * Two tools:
 * - replan_review_context: View all subtasks and workspace files
 * - replan_split_and_handoff: Save progress and add follow-up subtasks
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import { SubtaskState, createSubtask, type AMISubtask } from "../agent/schemas.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("replan-tools");

// ===== Types =====

/** Minimal interface for the executor (avoid circular import) */
interface ExecutorRef {
  readonly subtasks: AMISubtask[];
  addSubtasksAsync(
    newSubtasks: AMISubtask[],
    afterSubtaskId?: string,
  ): Promise<string[]>;
}

interface ReplanContext {
  executor: ExecutorRef;
  currentSubtaskId: string;
  workspaceDir?: string;
  /** Set by split_and_handoff — executor checks this after agent completes */
  handoffResult?: string;
}

// ===== Review Context Tool =====

const reviewContextSchema = Type.Object({});

type ReviewContextParams = Static<typeof reviewContextSchema>;

function createReviewContextTool(
  ctx: ReplanContext,
): AgentTool<typeof reviewContextSchema> {
  return {
    name: "replan_review_context",
    label: "Review Context",
    description:
      "Review the current execution context: what subtasks have been completed, " +
      "what is still pending, and what files are available in the workspace. " +
      "Call this BEFORE splitting work to understand the current state.",
    parameters: reviewContextSchema,
    execute: async (
      _toolCallId: string,
      _params: ReviewContextParams,
    ): Promise<AgentToolResult<undefined>> => {
      const lines: string[] = ["## Execution Context\n"];

      // Subtask states
      lines.push("### Subtask States:");
      for (const subtask of ctx.executor.subtasks) {
        const deps = subtask.dependsOn.length > 0
          ? ` (depends_on: ${subtask.dependsOn.join(", ")})`
          : "";
        const result = subtask.result
          ? ` → ${subtask.result.slice(0, 100)}...`
          : "";
        lines.push(
          `- [${subtask.state}] ${subtask.id} (${subtask.agentType}): ${subtask.content.slice(0, 80)}${deps}${result}`,
        );
      }

      // Workspace files
      if (ctx.workspaceDir) {
        try {
          const { readdirSync, statSync } = await import("node:fs");
          const { join } = await import("node:path");
          const files = readdirSync(ctx.workspaceDir);
          if (files.length > 0) {
            lines.push("\n### Workspace Files:");
            for (const file of files.slice(0, 50)) {
              try {
                const stat = statSync(join(ctx.workspaceDir, file));
                const size = stat.isDirectory()
                  ? "(dir)"
                  : `${(stat.size / 1024).toFixed(1)}KB`;
                lines.push(`- ${file} ${size}`);
              } catch {
                lines.push(`- ${file}`);
              }
            }
          } else {
            lines.push("\n### Workspace Files: (empty)");
          }
        } catch {
          lines.push("\n### Workspace Files: (unable to read)");
        }
      }

      const text = lines.join("\n");
      logger.info(
        { subtaskId: ctx.currentSubtaskId },
        "Review context called",
      );

      return {
        content: [{ type: "text", text }],
        details: undefined,
      };
    },
  };
}

// ===== Split and Handoff Tool =====

const splitAndHandoffSchema = Type.Object({
  summary: Type.String({
    description: "Summary of what you have done so far",
  }),
  tasks: Type.String({
    description:
      "JSON array of follow-up task objects. Each must have: " +
      '{ "content": "task description", "agent_type": "browser|document|code|multi_modal", ' +
      '"depends_on": [] }',
  }),
});

type SplitAndHandoffParams = Static<typeof splitAndHandoffSchema>;

function createSplitAndHandoffTool(
  ctx: ReplanContext,
): AgentTool<typeof splitAndHandoffSchema> {
  return {
    name: "replan_split_and_handoff",
    label: "Split and Handoff",
    description:
      "Split remaining work into follow-up subtasks and hand off. " +
      "You MUST call replan_review_context() first to see the current state. " +
      "After calling this, your current subtask will be marked complete.",
    parameters: splitAndHandoffSchema,
    execute: async (
      _toolCallId: string,
      params: SplitAndHandoffParams,
    ): Promise<AgentToolResult<undefined>> => {
      // Parse tasks JSON
      let taskList: any[];
      try {
        taskList = JSON.parse(params.tasks);
        if (!Array.isArray(taskList)) {
          return {
            content: [
              { type: "text", text: "Error: tasks must be a JSON array" },
            ],
            details: undefined,
          };
        }
      } catch (e: any) {
        return {
          content: [
            {
              type: "text",
              text: `Error: Invalid JSON in tasks: ${e.message}`,
            },
          ],
          details: undefined,
        };
      }

      // Build new subtasks
      const newSubtasks: AMISubtask[] = [];
      for (let i = 0; i < taskList.length; i++) {
        const item = taskList[i];
        if (!item.content) {
          return {
            content: [
              {
                type: "text",
                text: `Error: Task ${i} missing 'content' field`,
              },
            ],
            details: undefined,
          };
        }

        const agentType = item.agent_type ?? "browser";
        if (
          !["browser", "document", "code", "multi_modal"].includes(agentType)
        ) {
          return {
            content: [
              {
                type: "text",
                text: `Error: Task ${i} has invalid agent_type '${agentType}'`,
              },
            ],
            details: undefined,
          };
        }

        const subtaskId = `${ctx.currentSubtaskId}_dyn_${i + 1}`;

        // Inherit parent's dependencies + current subtask as dependency
        // so dynamic subtasks see the same upstream context
        const currentSubtask = ctx.executor.subtasks.find(
          (s) => s.id === ctx.currentSubtaskId,
        );
        const inheritedDeps = [
          ...(currentSubtask?.dependsOn ?? []),
          ctx.currentSubtaskId,
        ];
        const explicitDeps = Array.isArray(item.depends_on)
          ? item.depends_on.map(String)
          : [];
        const dependsOn = [
          ...new Set([...inheritedDeps, ...explicitDeps]),
        ];

        newSubtasks.push(
          createSubtask({
            id: subtaskId,
            content: item.content,
            agentType,
            dependsOn,
          }),
        );
      }

      // Add subtasks to executor
      const newIds = await ctx.executor.addSubtasksAsync(
        newSubtasks,
        ctx.currentSubtaskId,
      );

      // Store handoff result
      ctx.handoffResult = params.summary;

      logger.info(
        {
          subtaskId: ctx.currentSubtaskId,
          newCount: newIds.length,
          newIds,
        },
        "Split and handoff completed",
      );

      return {
        content: [
          {
            type: "text",
            text:
              `Successfully created ${newIds.length} follow-up subtasks: ${newIds.join(", ")}. ` +
              "Your current task will now end. The new subtasks will be executed next.",
          },
        ],
        details: undefined,
      };
    },
  };
}

// ===== Public Factory =====

export function createReplanTools(
  executor: ExecutorRef,
  currentSubtaskId: string,
  workspaceDir?: string,
): {
  tools: AgentTool<any>[];
  getHandoffResult: () => string | undefined;
} {
  const ctx: ReplanContext = {
    executor,
    currentSubtaskId,
    workspaceDir,
  };

  return {
    tools: [
      createReviewContextTool(ctx),
      createSplitAndHandoffTool(ctx),
    ],
    getHandoffResult: () => ctx.handoffResult,
  };
}
