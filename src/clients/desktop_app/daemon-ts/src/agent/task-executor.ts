/**
 * AMI Task Executor — Sequential execution with dependency resolution.
 *
 * Ported from ami_task_executor.py.
 *
 * Key features:
 * - workflow_guide injected as explicit instruction in prompt
 * - Sequential execution with dependency resolution
 * - SSE events for real-time UI updates
 * - Pause/resume support
 * - Fail-fast: if a subtask fails, skip all dependents
 * - Replan tool injection per subtask
 */

import { Agent } from "@mariozechner/pi-agent-core";
import { streamSimple } from "@mariozechner/pi-ai";
import { getConfiguredModel, getAnthropicApiKey } from "../utils/config.js";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import {
  type AMISubtask,
  SubtaskState,
  type ExecutionResult,
  type ReplanResult,
  type TaskExecutorLike,
  type AgentLike,
} from "./schemas.js";
import { bridgeAgentToSSE } from "../events/bridge.js";
import { Action } from "../events/types.js";
import type { SSEEmitter } from "../events/emitter.js";
import { REPLAN_INSTRUCTION } from "../prompts/task-decomposition.js";
import { createReplanTools } from "../tools/replan-tools.js";
import { ExecutionDataCollector } from "./execution-data-collector.js";
import { getCloudClient, type RequestCredentials } from "../services/cloud-client.js";
import { agentPrompt, requireApiKey } from "../utils/agent-helpers.js";
import { createLogger } from "../utils/logging.js";
import { BehaviorRecorder } from "../browser/behavior-recorder.js";
import { BrowserSession } from "../browser/browser-session.js";
import {
  updateSubtaskState as persistSubtaskState,
  updateTaskStatus as persistTaskStatus,
  buildSnapshot,
  saveTaskState,
} from "../services/task-state-persistence.js";

const logger = createLogger("task-executor");

// ===== AMITaskExecutor =====

export class AMITaskExecutor implements TaskExecutorLike {
  readonly taskId: string;
  readonly executorId: string;
  readonly taskLabel: string;
  private emitter?: SSEEmitter;
  private apiKey?: string;
  private userRequest: string;
  private maxRetries: number;
  private maxTurnsPerSubtask: number;
  private userId?: string;

  // Agent management: agentType -> tools for that agent type
  private agentTools: Map<string, AgentTool<any>[]>;
  private systemPrompts: Map<string, string>;

  // Subtask management
  private _subtasks: AMISubtask[] = [];
  private subtaskMap: Map<string, AMISubtask> = new Map();

  // Pause/resume
  private _paused = false;
  private pauseResolve: (() => void) | null = null;

  // Stop control
  private _stopped = false;

  // Currently running agent
  private currentAgent: Agent | null = null;

  constructor(opts: {
    taskId: string;
    emitter?: SSEEmitter;
    apiKey?: string;
    agentTools: Map<string, AgentTool<any>[]>;
    systemPrompts: Map<string, string>;
    maxRetries?: number;
    maxTurnsPerSubtask?: number;
    userRequest?: string;
    executorId?: string;
    taskLabel?: string;
    userId?: string;
  }) {
    this.taskId = opts.taskId;
    this.emitter = opts.emitter;
    this.apiKey = opts.apiKey;
    this.agentTools = opts.agentTools;
    this.systemPrompts = opts.systemPrompts;
    this.maxRetries = opts.maxRetries ?? 2;
    this.maxTurnsPerSubtask = opts.maxTurnsPerSubtask ?? 50;
    this.userRequest = opts.userRequest ?? "";
    this.executorId = opts.executorId ?? "";
    this.taskLabel = opts.taskLabel ?? "";
    this.userId = opts.userId;

    logger.info(
      {
        taskId: this.taskId,
        executorId: this.executorId,
        agentTypes: [...this.agentTools.keys()],
      },
      "AMITaskExecutor initialized",
    );
  }

  // ===== Public API =====

  get isPaused(): boolean {
    return this._paused;
  }

  get subtasks(): AMISubtask[] {
    return this._subtasks;
  }

  getCurrentAgent(): AgentLike | null {
    return this.currentAgent as AgentLike | null;
  }

  setSubtasks(subtasks: AMISubtask[]): void {
    this._subtasks = subtasks;
    this.subtaskMap = new Map(subtasks.map((s) => [s.id, s]));
    logger.info({ count: subtasks.length }, "Subtasks set");
  }

  stop(): void {
    this._stopped = true;
    if (this.currentAgent) {
      this.currentAgent.abort();
    }
    // Wake up if paused
    if (this.pauseResolve) {
      this.pauseResolve();
      this.pauseResolve = null;
    }
  }

  pause(): void {
    this._paused = true;
    logger.info("Executor paused");
  }

  resume(): void {
    this._paused = false;
    if (this.pauseResolve) {
      this.pauseResolve();
      this.pauseResolve = null;
    }
    logger.info("Executor resumed");
  }

  // ===== Main Execution Loop =====

  async execute(): Promise<ExecutionResult> {
    // Log full subtask plan for debugging
    for (const st of this._subtasks) {
      logger.info(
        {
          id: st.id,
          type: st.agentType,
          deps: st.dependsOn,
          content: st.content.slice(0, 150),
        },
        "Subtask queued",
      );
    }
    logger.info(
      { subtaskCount: this._subtasks.length },
      "Starting execution",
    );

    const collector = new ExecutionDataCollector();
    // Count subtasks that are already DONE (e.g., from resume)
    let completed = this._subtasks.filter((s) => s.state === SubtaskState.DONE).length;
    let failed = 0;
    const emittedFailures = new Set<string>();

    while (!this._stopped) {
      // Wait if paused
      await this.waitIfPaused();
      if (this._stopped) break;

      // Emit SSE for newly failed subtasks (from dependency propagation)
      this.emitNewlyFailed(emittedFailures, (count) => {
        failed += count;
      });

      // Find next executable subtask
      const subtask = this.getNextSubtask();

      // Emit again (getNextSubtask may fail-fast more subtasks)
      this.emitNewlyFailed(emittedFailures, (count) => {
        failed += count;
      });

      if (subtask === null) {
        // Check for stuck PENDING subtasks (deadlock)
        const stuck = this._subtasks.filter(
          (s) => s.state === SubtaskState.PENDING,
        );
        if (stuck.length > 0) {
          logger.warn(
            { stuckIds: stuck.map((s) => s.id) },
            "Subtasks stuck PENDING (circular dependency)",
          );
          for (const s of stuck) {
            s.state = SubtaskState.FAILED;
            s.error = "Blocked: circular dependency";
            failed++;
            emittedFailures.add(s.id);
            this.emitSubtaskState(s);
          }
        }
        break;
      }

      // Execute the subtask
      const success = await this.executeSubtask(subtask, collector);
      if (success) {
        completed++;
      } else {
        failed++;
      }
    }

    const result: ExecutionResult = {
      completed,
      failed,
      stopped: this._stopped,
      total: this._subtasks.length,
    };

    logger.info(result, "Execution finished");

    // Persist final task status (fire-and-forget)
    try {
      const finalStatus = this._stopped ? "failed" as const
        : failed > 0 ? "failed" as const
        : "completed" as const;
      persistTaskStatus(this.taskId, finalStatus);
    } catch { /* fire-and-forget */ }

    // Post-execution learning: fire-and-forget
    if (this.shouldTriggerLearning()) {
      const taskData = collector.buildTaskData(
        this.taskId,
        this.userRequest,
        this._subtasks,
      );
      this.learnFromExecution(taskData).catch((err) => {
        logger.warn({ err }, "Post-execution learning failed");
      });
    }

    return result;
  }

  // ===== Dependency Resolution =====

  private getNextSubtask(): AMISubtask | null {
    for (const subtask of this._subtasks) {
      if (subtask.state !== SubtaskState.PENDING) continue;

      let depsSatisfied = true;
      for (const depId of subtask.dependsOn) {
        const dep = this.subtaskMap.get(depId);
        if (!dep) {
          logger.warn(
            { subtaskId: subtask.id, depId },
            "Subtask depends on non-existent task",
          );
          depsSatisfied = false;
          break;
        }
        if (dep.state === SubtaskState.FAILED) {
          // Fail-fast propagation
          subtask.state = SubtaskState.FAILED;
          subtask.error = `Dependency '${depId}' failed: ${dep.error ?? "unknown error"}`;
          logger.warn(
            { subtaskId: subtask.id, error: subtask.error },
            "Subtask failed due to dependency",
          );
          depsSatisfied = false;
          break;
        }
        if (dep.state !== SubtaskState.DONE) {
          depsSatisfied = false;
          break;
        }
      }

      if (depsSatisfied) return subtask;
    }

    return null;
  }

  // ===== Execute Single Subtask =====

  private async executeSubtask(
    subtask: AMISubtask,
    collector: ExecutionDataCollector,
  ): Promise<boolean> {
    // Get tools for this agent type
    const tools = this.agentTools.get(subtask.agentType);
    if (!tools) {
      logger.error(
        { agentType: subtask.agentType },
        "No tools for agent type",
      );
      subtask.state = SubtaskState.FAILED;
      subtask.error = `No agent available for type: ${subtask.agentType}`;
      this.emitSubtaskState(subtask);
      return false;
    }

    const systemPrompt =
      this.systemPrompts.get(subtask.agentType) ?? "You are a helpful assistant.";

    // Mark as running
    subtask.state = SubtaskState.RUNNING;
    this.emitSubtaskRunning(subtask);

    // Execute with retries
    // Recorder is outside the while loop so the outer finally can clean it up
    // (matches Python ami_task_executor.py:497-622 structure)
    let recorder: BehaviorRecorder | null = null;

    try {
      while (subtask.retryCount <= this.maxRetries) {
        try {
          if (this._stopped) return false;
          await this.waitIfPaused();

          // Online Learning: fresh recorder for each attempt (browser subtasks only)
          if (subtask.agentType === "browser") {
            recorder = await this.startBehaviorRecorder();
          }

          logger.info(
            {
              subtaskId: subtask.id,
              attempt: subtask.retryCount + 1,
              maxAttempts: this.maxRetries + 1,
            },
            "Executing subtask",
          );

          // Build the prompt
          const prompt = this.buildPrompt(subtask);

          // Create replan tools for this subtask
          const { tools: replanToolSet, getHandoffResult } = createReplanTools(
            this,
            subtask.id,
          );

          // Validate API key before creating agent (prevents hang on missing key)
          const resolvedApiKey = requireApiKey(this.apiKey ?? getAnthropicApiKey());

          // Create a fresh agent for this subtask
          const model = getConfiguredModel();
          const agent = new Agent({
            initialState: {
              systemPrompt,
              model,
              tools: [...tools, ...replanToolSet],
              messages: [],
              thinkingLevel: "off",
            },
            getApiKey: async () => resolvedApiKey,
            streamFn: streamSimple,
          });

          this.currentAgent = agent;

          // Bridge agent events to SSE
          const agentName = `${subtask.agentType}Agent`;
          const unsubscribe = this.emitter
            ? bridgeAgentToSSE(agent, this.emitter, this.taskId, agentName)
            : () => {};

          // Loop guard: abort agent if too many turns
          let turnCount = 0;
          const unsubscribeTurnGuard = agent.subscribe((event: any) => {
            if (event.type === "turn_end") {
              turnCount++;
              if (turnCount >= this.maxTurnsPerSubtask) {
                logger.warn(
                  { subtaskId: subtask.id, turnCount },
                  "Agent exceeded max turns, aborting",
                );
                agent.abort();
              }
            }
          });

          try {
            await agentPrompt(agent, prompt);

            // Extract result text
            const messages = agent.state.messages;
            const lastAssistant = [...messages]
              .reverse()
              .find((m: any) => m.role === "assistant");

            let resultText = "";
            if (lastAssistant && "content" in lastAssistant) {
              const content = lastAssistant.content;
              if (typeof content === "string") {
                resultText = content;
              } else if (Array.isArray(content)) {
                resultText = content
                  .filter((c: any) => c.type === "text")
                  .map((c: any) => c.text ?? "")
                  .join("\n");
              }
            }

            // If agent used split_and_handoff, use the handoff summary as result
            const handoff = getHandoffResult();
            subtask.result = handoff ?? resultText;
            subtask.state = SubtaskState.DONE;
            this.emitSubtaskState(subtask);

            // Collect execution data
            try {
              collector.collectSubtaskData(agent, subtask);
            } catch (e) {
              logger.warn({ err: e }, "Failed to collect execution data");
            }

            // Online Learning: save recorded operations to Memory on success
            if (recorder) {
              await this.saveRecordedOperations(recorder, subtask);
            }

            logger.info(
              {
                subtaskId: subtask.id,
                resultLen: resultText.length,
              },
              "Subtask completed",
            );
            return true;
          } finally {
            unsubscribeTurnGuard();
            unsubscribe();
            this.currentAgent = null;
          }
        } catch (e: any) {
          // Online Learning: stop recorder from failed attempt before retry
          if (recorder) {
            await this.stopBehaviorRecorder(recorder);
            recorder = null;
          }

          subtask.retryCount++;
          subtask.error = e.message ?? String(e);

          logger.warn(
            {
              subtaskId: subtask.id,
              attempt: subtask.retryCount,
              error: subtask.error,
            },
            "Subtask failed",
          );

          if (subtask.retryCount > this.maxRetries) {
            subtask.state = SubtaskState.FAILED;
            this.emitSubtaskState(subtask);
            return false;
          }
        }
      }

      return false;
    } finally {
      // Online Learning: stop recorder to release CDP session (runs once at exit)
      if (recorder) {
        await this.stopBehaviorRecorder(recorder);
        recorder = null;
      }
    }
  }

  // ===== Prompt Building =====

  private buildPrompt(
    subtask: AMISubtask,
    browserContext?: string,
  ): string {
    const parts: string[] = [];

    // Browser state
    if (browserContext) {
      parts.push(
        `## Current Browser State\n${browserContext}\n\n` +
          "The browser is already open on this page. You do NOT need to navigate here again — start working directly.",
      );
    }

    // Task content
    parts.push(`## Your Task\n${subtask.content}`);

    // Workflow guide
    if (subtask.workflowGuide) {
      parts.push(`
## Reference: Historical Workflow

The following is a workflow from a SIMILAR past task. Use it as background reference, NOT as a step-by-step instruction.

${subtask.workflowGuide}

**Important**:
- Your current task is ONLY what's described in "Your Task" above
- This workflow covers the ENTIRE original task, but you are only responsible for YOUR subtask
- Use this workflow to understand context (e.g. which site to visit, what elements look like)
- Do NOT execute steps that go beyond your assigned task
- When your specific task is complete, STOP immediately`);
    } else {
      parts.push(`
## Note
No historical workflow guide available. Please explore and complete the task using your best judgment.`);
    }

    // Dependency results
    const depResults: string[] = [];
    for (const depId of subtask.dependsOn) {
      const dep = this.subtaskMap.get(depId);
      if (dep?.result) {
        if (dep.result.length > 2000) {
          depResults.push(
            `### Result from task '${depId}':\n` +
              `(Result truncated to 2000 chars)\n${dep.result.slice(0, 2000)}...`,
          );
        } else {
          depResults.push(`### Result from task '${depId}':\n${dep.result}`);
        }
      }
    }
    if (depResults.length > 0) {
      parts.push(
        "## Results from Previous Tasks\n" + depResults.join("\n\n"),
      );
    }

    // Replan instruction
    parts.push(REPLAN_INSTRUCTION);

    return parts.join("\n\n");
  }

  // ===== Replan Support =====

  replanSubtasks(newSubtasks: AMISubtask[]): ReplanResult {
    // Remove all PENDING subtasks
    const kept = this._subtasks.filter(
      (s) => s.state !== SubtaskState.PENDING,
    );
    const removedCount = this._subtasks.length - kept.length;
    const keptIds = kept.map((s) => s.id);

    // Validate no ID collisions with kept subtasks
    const keptIdSet = new Set(keptIds);
    for (const ns of newSubtasks) {
      if (keptIdSet.has(ns.id)) {
        throw new Error(
          `New subtask ID '${ns.id}' collides with existing non-PENDING subtask`,
        );
      }
    }

    // Validate dependency references
    const allIds = new Set([...keptIds, ...newSubtasks.map((s) => s.id)]);
    for (const ns of newSubtasks) {
      for (const depId of ns.dependsOn) {
        if (!allIds.has(depId)) {
          throw new Error(
            `New subtask '${ns.id}' depends on unknown ID '${depId}'`,
          );
        }
      }
    }

    // Apply
    this._subtasks = [...kept, ...newSubtasks];
    this.subtaskMap = new Map(this._subtasks.map((s) => [s.id, s]));

    // Re-persist entire snapshot after replan (incremental updates would miss new subtasks)
    try {
      const snapshot = buildSnapshot(
        this.taskId,
        this.userRequest,
        this._subtasks,
        "running",
      );
      saveTaskState(this.taskId, snapshot);
    } catch { /* fire-and-forget */ }

    return {
      removedCount,
      addedCount: newSubtasks.length,
      keptIds,
    };
  }

  // ===== Dynamic Subtask Addition =====

  async addSubtasksAsync(
    newSubtasks: AMISubtask[],
    afterSubtaskId?: string,
  ): Promise<string[]> {
    let insertIdx = this._subtasks.length;
    if (afterSubtaskId) {
      const dynPrefix = `${afterSubtaskId}_dyn_`;
      let found = false;
      for (let i = 0; i < this._subtasks.length; i++) {
        if (this._subtasks[i].id === afterSubtaskId) {
          found = true;
          insertIdx = i + 1;
        } else if (found && this._subtasks[i].id.startsWith(dynPrefix)) {
          insertIdx = i + 1;
        } else if (found) {
          insertIdx = i;
          break;
        }
      }
    }

    // Insert
    for (let i = 0; i < newSubtasks.length; i++) {
      this._subtasks.splice(insertIdx + i, 0, newSubtasks[i]);
      this.subtaskMap.set(newSubtasks[i].id, newSubtasks[i]);
    }

    const newIds = newSubtasks.map((s) => s.id);
    logger.info(
      { afterSubtaskId, newIds },
      "Dynamically added subtasks",
    );

    // Re-persist entire snapshot (new subtasks not in persisted version)
    try {
      const snapshot = buildSnapshot(
        this.taskId,
        this.userRequest,
        this._subtasks,
        "running",
      );
      saveTaskState(this.taskId, snapshot);
    } catch { /* fire-and-forget */ }

    // Emit SSE
    if (this.emitter) {
      this.emitter.emit({
        action: Action.dynamic_tasks_added,
        task_id: this.taskId,
        new_tasks: newSubtasks.map((s) => ({
          id: s.id,
          content: s.content,
          status: "pending",
        })),
        added_by_worker: afterSubtaskId,
        reason: "Agent-initiated task splitting",
        total_tasks_now: this._subtasks.length,
        total_tasks: this._subtasks.length,
        executor_id: this.executorId,
        task_label: this.taskLabel,
      });
    }

    return newIds;
  }

  // ===== SSE Helpers =====

  private getSubtaskProgress(subtask: AMISubtask): string {
    const total = this._subtasks.length;
    const index = this._subtasks.indexOf(subtask) + 1;
    return `[${index}/${total}]`;
  }

  private classifyError(errorMsg: string): string {
    if (!errorMsg) return "";
    const lower = errorMsg.toLowerCase();
    if (["connection", "timeout", "timed out", "network", "unreachable", "dns"].some((k) => lower.includes(k)))
      return "Network error";
    if (["429", "rate limit", "too many requests"].some((k) => lower.includes(k)))
      return "Rate limit exceeded";
    if (["500", "502", "503", "504", "internal server error"].some((k) => lower.includes(k)))
      return "Server error";
    if (["401", "unauthorized", "authentication"].some((k) => lower.includes(k)))
      return "Authentication error";
    return "";
  }

  private emitSubtaskState(subtask: AMISubtask): void {
    // Persist to disk (fire-and-forget)
    try {
      persistSubtaskState(
        this.taskId,
        subtask.id,
        subtask.state,
        subtask.result,
        subtask.error,
      );
    } catch { /* fire-and-forget */ }

    this.emitter?.emitSubtaskState(
      subtask.id,
      subtask.state,
      subtask.result?.slice(0, 500),
      subtask.retryCount,
      this.executorId,
      this.taskLabel,
    );

    // Emit agent_report for subtask completion/failure (matches Python _emit_subtask_state)
    if (!this.emitter) return;
    const progress = this.getSubtaskProgress(subtask);
    const preview = subtask.content.slice(0, 50) + (subtask.content.length > 50 ? "..." : "");

    if (subtask.state === SubtaskState.DONE) {
      this.emitter.emitAgentReport(
        `${progress} Completed: ${preview}`,
        "success",
        subtask.agentType,
        this.executorId,
        this.taskLabel,
      );
    } else if (subtask.state === SubtaskState.FAILED) {
      const errorHint = this.classifyError(subtask.error ?? "");
      const errorSuffix = errorHint ? ` (${errorHint})` : "";
      this.emitter.emitAgentReport(
        `${progress} Failed: ${preview}${errorSuffix}`,
        "error",
        subtask.agentType,
        this.executorId,
        this.taskLabel,
      );
    }
  }

  private emitSubtaskRunning(subtask: AMISubtask): void {
    // Emit agent_report for subtask starting (matches Python _emit_subtask_running)
    if (this.emitter) {
      const progress = this.getSubtaskProgress(subtask);
      const preview = subtask.content.slice(0, 80) + (subtask.content.length > 80 ? "..." : "");
      this.emitter.emitAgentReport(
        `${progress} Running: ${preview}`,
        "info",
        subtask.agentType,
        this.executorId,
        this.taskLabel,
      );
    }

    // Emit assign_task event (matches Python AssignTaskData)
    this.emitter?.emit({
      action: Action.assign_task,
      task_id: this.taskId,
      assignee_id: subtask.agentType,
      subtask_id: subtask.id,
      content: subtask.content,
      state: "running",
      failure_count: subtask.retryCount,
      worker_name: `${subtask.agentType}Agent`,
      agent_type: subtask.agentType,
      agent_id: subtask.agentType,
      executor_id: this.executorId,
      task_label: this.taskLabel,
    });

    this.emitter?.emitSubtaskState(
      subtask.id,
      SubtaskState.RUNNING,
      undefined,
      0,
      this.executorId,
      this.taskLabel,
    );

    this.emitter?.emitWorkerAssigned(
      `${subtask.agentType}Agent`,
      subtask.id,
      subtask.content.slice(0, 200),
      undefined,
      this.executorId,
      this.taskLabel,
    );
  }

  private emitNewlyFailed(
    emittedSet: Set<string>,
    addFailed: (count: number) => void,
  ): void {
    let count = 0;
    for (const s of this._subtasks) {
      if (s.state === SubtaskState.FAILED && !emittedSet.has(s.id)) {
        emittedSet.add(s.id);
        count++;
        this.emitSubtaskState(s);
      }
    }
    if (count > 0) addFailed(count);
  }

  // ===== Post-Execution Learning =====

  /**
   * Check if post-execution learning should be triggered.
   *
   * Conditions (matching Python _should_trigger_learning):
   * - Execution was not stopped/cancelled
   * - userId is available
   * - At least 1 browser subtask
   * - Total subtask count >= 2
   * - All browser subtasks succeeded
   */
  private shouldTriggerLearning(): boolean {
    if (this._stopped) return false;
    if (!this.userId) return false;

    const browserSubtasks = this._subtasks.filter(
      (s) => s.agentType === "browser",
    );
    if (browserSubtasks.length === 0) return false;
    if (this._subtasks.length < 2) return false;

    const allBrowserDone = browserSubtasks.every(
      (s) => s.state === SubtaskState.DONE,
    );
    if (!allBrowserDone) return false;

    return true;
  }

  /**
   * Fire-and-forget: send execution data to Cloud Backend for learning.
   */
  private async learnFromExecution(
    taskData: import("./schemas.js").TaskExecutionData,
  ): Promise<void> {
    logger.info(
      {
        taskId: this.taskId,
        subtasksCollected: taskData.subtasks.length,
      },
      "Triggering post-execution learning",
    );

    const payload = ExecutionDataCollector.toDict(taskData);
    const creds: RequestCredentials = {
      apiKey: this.apiKey,
      userId: this.userId,
    };

    try {
      const result = (await getCloudClient().memoryLearn(
        { user_id: this.userId!, execution_data: payload },
        creds,
      )) as Record<string, unknown>;

      logger.info(
        {
          phraseCreated: result.phrase_created,
          phraseId: result.phrase_id,
        },
        "Post-execution learning result",
      );
    } catch (err) {
      // Fire-and-forget: log but don't propagate
      logger.warn({ err }, "Post-execution learning request failed");
    }
  }

  // ===== Online Learning (BehaviorRecorder) =====

  /**
   * Start BehaviorRecorder for a browser subtask.
   * Returns the recorder instance, or null if startup fails.
   * All errors are caught — recorder failure must not block task execution.
   */
  private async startBehaviorRecorder(): Promise<BehaviorRecorder | null> {
    try {
      const session = BrowserSession.getExistingInstance(this.taskId)
        ?? BrowserSession.getDaemonSession();
      if (!session) {
        logger.debug("[OnlineLearning] No BrowserSession available, skipping recorder");
        return null;
      }

      const recorder = new BehaviorRecorder(/* enableSnapshotCapture */ false);
      await recorder.startRecording(session);
      logger.info("[OnlineLearning] Recorder started");
      return recorder;
    } catch (e) {
      logger.warn({ err: e }, "[OnlineLearning] Failed to start recorder");
      return null;
    }
  }

  /**
   * Stop a running BehaviorRecorder.
   */
  private async stopBehaviorRecorder(recorder: BehaviorRecorder): Promise<void> {
    try {
      await recorder.stopRecording();
      logger.info("[OnlineLearning] Recorder stopped");
    } catch (e) {
      logger.warn({ err: e }, "[OnlineLearning] Failed to stop recorder");
    }
  }

  /**
   * Save recorded operations to Memory via CloudClient.
   * Only called when a subtask succeeds (SubtaskState.DONE).
   */
  private async saveRecordedOperations(
    recorder: BehaviorRecorder,
    subtask: AMISubtask,
  ): Promise<void> {
    if (!this.userId) {
      logger.debug("[OnlineLearning] No userId, skipping memory save");
      return;
    }

    const operations = recorder.getOperations();
    if (operations.length === 0) {
      logger.debug("[OnlineLearning] No operations recorded, skipping");
      return;
    }

    try {
      logger.info(
        { operationCount: operations.length, subtaskId: subtask.id },
        "[OnlineLearning] Saving operations to memory",
      );

      const creds: RequestCredentials = {
        apiKey: this.apiKey,
        userId: this.userId,
      };

      const result = await getCloudClient().memoryAdd(
        {
          user_id: this.userId,
          operations,
          session_id: `${this.taskId}_${subtask.id}`,
          generate_embeddings: true,
          skip_cognitive_phrase: true,
        },
        creds,
      );

      logger.info({ result }, "[OnlineLearning] Memory save result");
    } catch (e) {
      logger.warn({ err: e }, "[OnlineLearning] Failed to save to memory");
    }
  }

  // ===== Pause Support =====

  private async waitIfPaused(): Promise<void> {
    while (this._paused && !this._stopped) {
      await new Promise<void>((resolve) => {
        this.pauseResolve = resolve;
      });
    }
  }
}
