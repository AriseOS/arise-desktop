/**
 * TaskState — per-task state management.
 *
 * Manages event queue, human response queue, user message queue,
 * conversation history, and execution metadata.
 */

import { SSEEmitter } from "../events/emitter.js";
import type { ActionData } from "../events/types.js";

// ===== Task Status =====

export enum TaskStatus {
  PENDING = "pending",
  RUNNING = "running",
  WAITING = "waiting",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
}

// ===== Conversation Entry =====

export interface ConversationEntry {
  role: "user" | "assistant" | "system" | "task_result" | "tool_call";
  content: string;
  timestamp: string;
}

// ===== Deferred helper for async queues =====

interface Deferred<T> {
  resolve: (value: T) => void;
  promise: Promise<T>;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { resolve, promise };
}

// ===== TaskState =====

const MAX_CONVERSATION_BYTES = 100 * 1024; // 100KB

export class TaskState {
  // Identity
  readonly taskId: string;
  task: string;
  userId?: string;
  projectId?: string;

  // Status
  status: TaskStatus = TaskStatus.PENDING;
  progress = 0;
  result?: unknown;
  error?: string;

  // Timestamps
  readonly createdAt: Date = new Date();
  startedAt?: Date;
  completedAt?: Date;
  updatedAt: Date = new Date();

  // Tool tracking
  toolsCalled: Record<string, unknown>[] = [];
  loopIteration = 0;

  // Conversation history
  conversationHistory: ConversationEntry[] = [];
  lastTaskResult?: string;

  // Subtask tracking
  subtasks: Record<string, unknown>[] = [];
  summaryTask?: string;

  // SSE emitter for streaming events
  readonly emitter: SSEEmitter;

  // Abort controller for cancellation
  abortController: AbortController = new AbortController();

  // Human response queue (for ask_human tool)
  private _humanResponseQueue: Deferred<string | null>[] = [];

  // User message queue (for multi-turn conversation)
  private _userMessageQueue: string[] = [];
  private _userMessageWaiters: Deferred<string | null>[] = [];

  // Pause support
  private _pauseDeferred?: Deferred<void>;

  constructor(taskId: string, task: string) {
    this.taskId = taskId;
    this.task = task;
    this.emitter = new SSEEmitter();
    this.emitter.configure(taskId);
  }

  // ===== Status transitions =====

  markRunning(): void {
    this.status = TaskStatus.RUNNING;
    this.startedAt = new Date();
    this.updatedAt = new Date();
  }

  markWaiting(): void {
    this.status = TaskStatus.WAITING;
    this.updatedAt = new Date();
  }

  markCompleted(result?: unknown): void {
    this.status = TaskStatus.COMPLETED;
    this.result = result;
    this.completedAt = new Date();
    this.updatedAt = new Date();
  }

  markFailed(error: string): void {
    this.status = TaskStatus.FAILED;
    this.error = error;
    this.completedAt = new Date();
    this.updatedAt = new Date();
  }

  markCancelled(reason?: string): void {
    this.status = TaskStatus.CANCELLED;
    this.error = reason;
    this.completedAt = new Date();
    this.updatedAt = new Date();
    this.abortController.abort();
    // Resolve pause deferred so executor doesn't hang
    if (this._pauseDeferred) {
      this._pauseDeferred.resolve();
      this._pauseDeferred = undefined;
    }
    // Drain all pending waiters so nothing hangs
    this._drainWaiters();
  }

  /** Resolve all pending deferred queues (used on cancel/cleanup). */
  private _drainWaiters(): void {
    // Drain user message waiters — resolve with null so getUserMessage() returns null
    for (const waiter of this._userMessageWaiters) {
      waiter.resolve(null);
    }
    this._userMessageWaiters = [];

    // Drain human response waiters — resolve with null so waitForHumanResponse() returns null
    for (const waiter of this._humanResponseQueue) {
      waiter.resolve(null);
    }
    this._humanResponseQueue = [];
  }

  // ===== Conversation history =====

  addConversation(role: ConversationEntry["role"], content: string): void {
    this.conversationHistory.push({
      role,
      content,
      timestamp: new Date().toISOString(),
    });

    // Auto-trim if too large
    let totalSize = this.conversationHistory.reduce(
      (sum, e) => sum + e.content.length,
      0,
    );
    while (totalSize > MAX_CONVERSATION_BYTES && this.conversationHistory.length > 2) {
      const removed = this.conversationHistory.shift()!;
      totalSize -= removed.content.length;
    }
  }

  getRecentContext(maxEntries = 10): string {
    const recent = this.conversationHistory.slice(-maxEntries);
    return recent
      .map((e) => `[${e.role}]: ${e.content}`)
      .join("\n\n");
  }

  // ===== Human response queue =====

  /** Wait for a human response. Resolves when provideHumanResponse() is called. */
  waitForHumanResponse(timeoutMs = 300_000): Promise<string | null> {
    const deferred = createDeferred<string | null>();
    this._humanResponseQueue.push(deferred);

    const timer = setTimeout(() => {
      // Remove stale deferred so provideHumanResponse doesn't resolve a dead consumer
      const idx = this._humanResponseQueue.indexOf(deferred);
      if (idx >= 0) this._humanResponseQueue.splice(idx, 1);
    }, timeoutMs);

    return Promise.race([
      deferred.promise.then((v) => { clearTimeout(timer); return v; }),
      new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), timeoutMs),
      ),
    ]);
  }

  /** Provide a human response to the waiting ask_human tool. */
  provideHumanResponse(response: string): boolean {
    const waiter = this._humanResponseQueue.shift();
    if (waiter) {
      waiter.resolve(response);
      return true;
    }
    return false;
  }

  // ===== User message queue =====

  /** Put a user message into the queue for multi-turn processing. */
  putUserMessage(message: string): void {
    // If someone is waiting, resolve immediately
    if (this._userMessageWaiters.length > 0) {
      const waiter = this._userMessageWaiters.shift()!;
      waiter.resolve(message);
      return;
    }
    this._userMessageQueue.push(message);
  }

  /** Get the next user message, with optional timeout. Returns null on timeout or cancel. */
  getUserMessage(timeoutMs?: number): Promise<string | null> {
    // Drain buffer first
    if (this._userMessageQueue.length > 0) {
      return Promise.resolve(this._userMessageQueue.shift()!);
    }

    const deferred = createDeferred<string | null>();
    this._userMessageWaiters.push(deferred);

    if (timeoutMs === undefined) {
      return deferred.promise;
    }

    const timer = setTimeout(() => {
      // Remove stale deferred so putUserMessage doesn't resolve a dead consumer
      const idx = this._userMessageWaiters.indexOf(deferred);
      if (idx >= 0) this._userMessageWaiters.splice(idx, 1);
    }, timeoutMs);

    return Promise.race([
      deferred.promise.then((v) => { clearTimeout(timer); return v; }),
      new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), timeoutMs),
      ),
    ]);
  }

  /**
   * Cancel the most recent getUserMessage() waiter.
   * Used when an executor wins the Promise.race in waitForEvent() —
   * the losing getUserMessage() deferred must be removed so it doesn't
   * consume the next putUserMessage() call.
   */
  cancelLastGetUserMessage(): void {
    const waiter = this._userMessageWaiters.pop();
    if (waiter) {
      waiter.resolve(null); // resolve the orphaned promise to prevent leaks
    }
  }

  /** Check if there are pending user messages without consuming them. */
  get hasPendingUserMessages(): boolean {
    return this._userMessageQueue.length > 0;
  }

  // ===== Pause/Resume =====

  /** Pause execution. Returns a promise that resolves when resume() is called. */
  async pause(): Promise<void> {
    this.status = TaskStatus.WAITING;
    this.updatedAt = new Date();
    this._pauseDeferred = createDeferred<void>();
    return this._pauseDeferred.promise;
  }

  /** Resume paused execution. No-op if already cancelled/completed/failed. */
  resume(): boolean {
    if (this.status === TaskStatus.CANCELLED ||
        this.status === TaskStatus.COMPLETED ||
        this.status === TaskStatus.FAILED) {
      return false;
    }
    if (this._pauseDeferred) {
      this.status = TaskStatus.RUNNING;
      this.updatedAt = new Date();
      this._pauseDeferred.resolve();
      this._pauseDeferred = undefined;
      return true;
    }
    return false;
  }

  get isPaused(): boolean {
    return this._pauseDeferred !== undefined;
  }

  // ===== Duration =====

  get durationSeconds(): number | undefined {
    if (!this.startedAt) return undefined;
    const end = this.completedAt ?? new Date();
    return (end.getTime() - this.startedAt.getTime()) / 1000;
  }

  // ===== Serialization =====

  toJSON(): Record<string, unknown> {
    return {
      task_id: this.taskId,
      task: this.task,
      status: this.status,
      progress: this.progress,
      result: this.result,
      error: this.error,
      created_at: this.createdAt.toISOString(),
      started_at: this.startedAt?.toISOString(),
      completed_at: this.completedAt?.toISOString(),
      user_id: this.userId,
      project_id: this.projectId,
      loop_iterations: this.loopIteration,
      tools_called_count: this.toolsCalled.length,
      has_result: this.result !== undefined,
      has_error: this.error !== undefined,
      subtasks: this.subtasks,
      summary_task: this.summaryTask,
    };
  }
}
