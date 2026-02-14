/**
 * SSE Emitter — queue-based event emission for streaming to clients.
 *
 * Wire format: `data: {"step": "<action>", "data": {...}}\n\n`
 */

import {
  Action,
  type ActionData,
  type BaseActionData,
  type ActivateAgentData,
  type DeactivateAgentData,
  type ActivateToolkitData,
  type DeactivateToolkitData,
  type TerminalData,
  type BrowserActionData,
  type ScreenshotData,
  type StepStartedData,
  type StepCompletedData,
  type StepFailedData,
  type NoticeData,
  type ErrorData,
  type HeartbeatData,
  type EndData,
  type AgentReportData,
  type AgentThinkingData,
  type TaskDecomposedData,
  type SubtaskStateData,
  type TaskReplannedData,
  type WaitConfirmData,
  type WorkerAssignedData,
  type WorkerCompletedData,
  type WorkerFailedData,
  type MemoryResultData,
  type WriteFileData,
  type FileAttachment,
} from "./types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("sse-emitter");

const MAX_QUEUE_SIZE = 1000;

// ===== SSE Formatting =====

export function sseJson(step: string, data: unknown): string {
  const payload = { step, data };
  return `data: ${JSON.stringify(payload)}\n\n`;
}

export function sseAction(actionData: ActionData): string {
  const action = actionData.action;
  return sseJson(action, actionData);
}

export function sseComment(comment: string): string {
  return `: ${comment}\n\n`;
}

export function sseHeartbeat(): string {
  return sseJson("heartbeat", {
    action: "heartbeat",
    message: "keep-alive",
    timestamp: new Date().toISOString(),
  });
}

// ===== Bounded async queue =====

interface Deferred<T> {
  resolve: (value: T) => void;
  reject: (error: Error) => void;
  promise: Promise<T>;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { resolve, reject, promise };
}

// ===== SSEEmitter Class =====

export class SSEEmitter {
  private _queue: ActionData[] = [];
  private _waiters: Deferred<ActionData>[] = [];
  private _closed = false;
  private _taskId?: string;
  private _agentName?: string;
  private _startTime?: number;

  configure(taskId?: string, agentName?: string): this {
    this._taskId = taskId;
    this._agentName = agentName;
    this._startTime = Date.now();
    return this;
  }

  get taskId(): string | undefined {
    return this._taskId;
  }

  get isClosed(): boolean {
    return this._closed;
  }

  emit(actionData: ActionData): void {
    if (this._closed) return;

    // Stamp task_id if configured and not already set
    if (this._taskId && !actionData.task_id) {
      actionData.task_id = this._taskId;
    }

    // Stamp timestamp if not set
    if (!actionData.timestamp) {
      actionData.timestamp = new Date().toISOString();
    }

    // If someone is waiting, resolve immediately
    if (this._waiters.length > 0) {
      const waiter = this._waiters.shift()!;
      try {
        waiter.resolve(actionData);
      } catch (err) {
        logger.warn({ action: actionData.action, err }, "Waiter resolve threw");
      }
      return;
    }

    // Otherwise buffer (drop oldest if overflow)
    if (this._queue.length >= MAX_QUEUE_SIZE) {
      const dropped = this._queue.shift();
      logger.warn(
        { droppedAction: (dropped as any)?.action, queueSize: MAX_QUEUE_SIZE },
        "SSE queue overflow — dropping oldest event",
      );
    }
    this._queue.push(actionData);
  }

  /** Get next event, with optional timeout in ms. Returns null on timeout or close. */
  async getEvent(timeoutMs?: number): Promise<ActionData | null> {
    // Drain buffer first
    if (this._queue.length > 0) {
      return this._queue.shift()!;
    }

    if (this._closed) return null;

    const deferred = createDeferred<ActionData>();
    this._waiters.push(deferred);

    if (timeoutMs === undefined) {
      return deferred.promise;
    }

    const timer = setTimeout(() => {
      const idx = this._waiters.indexOf(deferred);
      if (idx >= 0) {
        this._waiters.splice(idx, 1);
        deferred.resolve(null as unknown as ActionData);
      }
    }, timeoutMs);

    try {
      const result = await deferred.promise;
      clearTimeout(timer);
      return result;
    } catch {
      clearTimeout(timer);
      return null;
    }
  }

  close(): void {
    this._closed = true;
    // Resolve all pending waiters with null
    for (const waiter of this._waiters) {
      waiter.resolve(null as unknown as ActionData);
    }
    this._waiters = [];
  }

  // ===== Convenience Methods =====

  emitAgentActivate(
    agentName?: string,
    agentId?: string,
    message = "",
  ): void {
    this.emit({
      action: Action.activate_agent,
      agent_name: agentName ?? this._agentName ?? "Agent",
      agent_id: agentId,
      process_task_id: this._taskId,
      message,
    } as ActivateAgentData);
  }

  emitAgentDeactivate(
    agentName?: string,
    agentId?: string,
    message = "",
    tokensUsed?: number,
  ): void {
    const durationSeconds = this._startTime
      ? (Date.now() - this._startTime) / 1000
      : undefined;

    this.emit({
      action: Action.deactivate_agent,
      agent_name: agentName ?? this._agentName ?? "Agent",
      agent_id: agentId,
      process_task_id: this._taskId,
      message,
      tokens_used: tokensUsed,
      duration_seconds: durationSeconds,
    } as DeactivateAgentData);
  }

  emitToolkitActivate(
    toolkitName: string,
    methodName: string,
    inputPreview?: string,
    message = "",
    agentName?: string,
  ): void {
    this.emit({
      action: Action.activate_toolkit,
      toolkit_name: toolkitName,
      method_name: methodName,
      agent_name: agentName ?? this._agentName,
      process_task_id: this._taskId,
      input_preview: inputPreview?.slice(0, 200),
      message,
    } as ActivateToolkitData);
  }

  emitToolkitDeactivate(
    toolkitName: string,
    methodName: string,
    outputPreview?: string,
    success = true,
    durationMs?: number,
    message = "",
    agentName?: string,
  ): void {
    this.emit({
      action: Action.deactivate_toolkit,
      toolkit_name: toolkitName,
      method_name: methodName,
      agent_name: agentName ?? this._agentName,
      process_task_id: this._taskId,
      output_preview: outputPreview?.slice(0, 200),
      success,
      duration_ms: durationMs,
      message,
    } as DeactivateToolkitData);
  }

  emitAgentThinking(
    content: string,
    agentName?: string,
    step?: number,
  ): void {
    this.emit({
      action: Action.agent_thinking,
      agent_name: agentName ?? this._agentName ?? "Agent",
      thinking: content,
      step,
    } as AgentThinkingData);
  }

  emitTerminal(
    command: string,
    output?: string,
    exitCode?: number,
    workingDirectory?: string,
    durationMs?: number,
  ): void {
    this.emit({
      action: Action.terminal,
      command,
      output: output?.slice(0, 2000),
      exit_code: exitCode,
      working_directory: workingDirectory,
      duration_ms: durationMs,
    } as TerminalData);
  }

  emitBrowserAction(
    actionType: string,
    target?: string,
    value?: string,
    success = true,
    pageUrl?: string,
    pageTitle?: string,
    screenshotUrl?: string,
    webviewId?: string,
  ): void {
    this.emit({
      action: Action.browser_action,
      action_type: actionType,
      target,
      value,
      success,
      page_url: pageUrl,
      page_title: pageTitle,
      screenshot_url: screenshotUrl,
      webview_id: webviewId,
    } as BrowserActionData);
  }

  emitScreenshot(
    screenshot: string,
    url?: string,
    pageTitle?: string,
    tabId?: string,
    webviewId?: string,
  ): void {
    this.emit({
      action: Action.screenshot,
      screenshot,
      url,
      page_title: pageTitle,
      tab_id: tabId,
      webview_id: webviewId,
    } as ScreenshotData);
  }

  emitWriteFile(
    filePath: string,
    fileName: string,
    fileSize?: number,
    contentPreview?: string,
    mimeType?: string,
  ): void {
    this.emit({
      action: Action.write_file,
      file_path: filePath,
      file_name: fileName,
      file_size: fileSize,
      content_preview: contentPreview,
      mime_type: mimeType,
    } as WriteFileData);
  }

  emitNotice(
    title: string,
    message: string,
    level = "info",
    durationMs?: number,
  ): void {
    this.emit({
      action: Action.notice,
      level,
      title,
      message,
      duration_ms: durationMs,
    } as NoticeData);
  }

  emitError(
    error: string,
    errorType?: string,
    recoverable = true,
    details?: Record<string, unknown>,
  ): void {
    this.emit({
      action: Action.error,
      error,
      error_type: errorType,
      recoverable,
      details,
    } as ErrorData);
  }

  emitHeartbeat(): void {
    this.emit({
      action: Action.heartbeat,
      message: "keep-alive",
    } as HeartbeatData);
  }

  emitAgentReport(
    message: string,
    reportType = "info",
    agentType?: string,
    executorId?: string,
    taskLabel?: string,
    subtaskLabel?: string,
  ): void {
    this.emit({
      action: Action.agent_report,
      message,
      report_type: reportType,
      agent_type: agentType,
      executor_id: executorId,
      task_label: taskLabel,
      subtask_label: subtaskLabel,
    } as AgentReportData);
  }

  emitEnd(status: string, message?: string, result?: unknown): void {
    this.emit({
      action: Action.end,
      status,
      message,
      result,
    } as EndData);
  }

  emitWaitConfirm(
    content: string,
    question: string,
    context = "initial",
    attachments?: FileAttachment[],
    executorId?: string,
    taskLabel?: string,
  ): void {
    this.emit({
      action: Action.wait_confirm,
      content,
      question,
      context,
      attachments,
      executor_id: executorId,
      task_label: taskLabel,
    } as WaitConfirmData);
  }

  emitTaskDecomposed(
    subtasks: Record<string, unknown>[],
    summaryTask?: string,
    originalTaskId?: string,
  ): void {
    this.emit({
      action: Action.task_decomposed,
      subtasks,
      summary_task: summaryTask,
      original_task_id: originalTaskId,
      total_subtasks: subtasks.length,
    } as TaskDecomposedData);
  }

  emitSubtaskState(
    subtaskId: string,
    state: string,
    result?: string,
    failureCount = 0,
    executorId?: string,
    taskLabel?: string,
  ): void {
    this.emit({
      action: Action.subtask_state,
      subtask_id: subtaskId,
      state,
      result,
      failure_count: failureCount,
      executor_id: executorId,
      task_label: taskLabel,
    } as SubtaskStateData);
  }

  emitTaskReplanned(
    subtasks: Record<string, unknown>[],
    originalTaskId?: string,
    reason?: string,
  ): void {
    this.emit({
      action: Action.task_replanned,
      subtasks,
      original_task_id: originalTaskId,
      reason,
    } as TaskReplannedData);
  }

  emitWorkerAssigned(
    workerName: string,
    subtaskId: string,
    subtaskContent: string,
    workerId?: string,
    executorId?: string,
    taskLabel?: string,
  ): void {
    this.emit({
      action: Action.worker_assigned,
      worker_name: workerName,
      worker_id: workerId,
      subtask_id: subtaskId,
      subtask_content: subtaskContent,
      executor_id: executorId,
      task_label: taskLabel,
    } as WorkerAssignedData);
  }

  emitWorkerCompleted(
    workerName: string,
    subtaskId: string,
    resultPreview?: string,
    durationSeconds?: number,
    workerId?: string,
    executorId?: string,
    taskLabel?: string,
  ): void {
    this.emit({
      action: Action.worker_completed,
      worker_name: workerName,
      worker_id: workerId,
      subtask_id: subtaskId,
      result_preview: resultPreview,
      duration_seconds: durationSeconds,
      executor_id: executorId,
      task_label: taskLabel,
    } as WorkerCompletedData);
  }

  emitWorkerFailed(
    workerName: string,
    subtaskId: string,
    error: string,
    failureCount = 0,
    willRetry = false,
    workerId?: string,
    executorId?: string,
    taskLabel?: string,
  ): void {
    this.emit({
      action: Action.worker_failed,
      worker_name: workerName,
      worker_id: workerId,
      subtask_id: subtaskId,
      error,
      failure_count: failureCount,
      will_retry: willRetry,
      executor_id: executorId,
      task_label: taskLabel,
    } as WorkerFailedData);
  }

  emitMemoryResult(
    pathsCount: number,
    paths: Record<string, unknown>[],
    hasWorkflow = false,
    method?: string,
  ): void {
    this.emit({
      action: Action.memory_result,
      paths_count: pathsCount,
      paths,
      has_workflow: hasWorkflow,
      method,
    } as MemoryResultData);
  }

  emitStepStarted(
    stepIndex: number,
    stepName: string,
    stepDescription?: string,
  ): void {
    this.emit({
      action: Action.step_started,
      step_index: stepIndex,
      step_name: stepName,
      step_description: stepDescription,
    } as StepStartedData);
  }

  emitStepCompleted(
    stepIndex: number,
    stepName: string,
    result?: string,
    durationSeconds?: number,
  ): void {
    this.emit({
      action: Action.step_completed,
      step_index: stepIndex,
      step_name: stepName,
      result: result?.slice(0, 500),
      duration_seconds: durationSeconds,
    } as StepCompletedData);
  }

  emitStepFailed(
    stepIndex: number,
    stepName: string,
    error: string,
    recoverable = true,
  ): void {
    this.emit({
      action: Action.step_failed,
      step_index: stepIndex,
      step_name: stepName,
      error,
      recoverable,
    } as StepFailedData);
  }
}
