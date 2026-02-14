/**
 * Agent Pipeline Schemas — subtask model, state enum, decomposition types.
 *
 * Ported from ami_task_executor.py (SubtaskState, AMISubtask).
 */

// ===== Subtask State Enum =====

export enum SubtaskState {
  PENDING = "PENDING",
  RUNNING = "RUNNING",
  DONE = "DONE",
  FAILED = "FAILED",
}

// ===== AMI Subtask =====

export interface AMISubtask {
  /** Sequential ID (e.g., "1", "2", "3") */
  id: string;
  /** Task description (self-contained) */
  content: string;
  /** Agent type: "browser" | "document" | "code" | "multi_modal" */
  agentType: string;
  /** IDs of subtasks this depends on */
  dependsOn: string[];

  /** Memory/workflow guidance — injected directly into prompt */
  workflowGuide?: string;
  /** Memory level: L1=exact match, L2=partial, L3=no match */
  memoryLevel: string;

  /** Execution state */
  state: SubtaskState;
  /** Result text from agent */
  result?: string;
  /** Error message if failed */
  error?: string;
  /** Number of retry attempts */
  retryCount: number;
}

/** Create a new AMISubtask with defaults */
export function createSubtask(opts: {
  id: string;
  content: string;
  agentType: string;
  dependsOn?: string[];
  workflowGuide?: string;
  memoryLevel?: string;
}): AMISubtask {
  return {
    id: opts.id,
    content: opts.content,
    agentType: opts.agentType,
    dependsOn: opts.dependsOn ?? [],
    workflowGuide: opts.workflowGuide,
    memoryLevel: opts.memoryLevel ?? "L3",
    state: SubtaskState.PENDING,
    retryCount: 0,
  };
}

// ===== Execution Result =====

export interface ExecutionResult {
  completed: number;
  failed: number;
  stopped: boolean;
  total: number;
}

// ===== Executor Handle (for OrchestratorSession) =====

export interface ExecutorHandle {
  executorId: string;
  taskLabel: string;
  /** null during planning phase */
  executor: TaskExecutorLike | null;
  /** Promise that resolves when plan+execute completes */
  promise: Promise<ExecutionResult>;
  /** Resolve/reject for the promise (for external cancellation) */
  abortController: AbortController;
  subtasks: AMISubtask[];
  startedAt: Date;
  workspaceFolder: string;
}

/** Minimal interface for TaskExecutor (avoid circular imports) */
export interface TaskExecutorLike {
  stop(): void;
  pause(): void;
  resume(): void;
  readonly isPaused: boolean;
  getCurrentAgent(): AgentLike | null;
  getRunningAgents(): Map<string, AgentLike>;
  replanSubtasks(newSubtasks: AMISubtask[]): ReplanResult;
}

/** Minimal interface for Agent (avoid circular imports) */
export interface AgentLike {
  abort(): void;
  steer?(message: any): void;
}

// ===== Replan Result =====

export interface ReplanResult {
  removedCount: number;
  addedCount: number;
  keptIds: string[];
}

// ===== Tool Record (for execution data collector) =====

export interface ToolUseRecord {
  thinking: string;
  toolName: string;
  inputSummary: string;
  success: boolean;
  resultSummary: string;
  judgment: string;
  currentUrl: string;
}

// ===== Subtask Execution Data =====

export interface SubtaskExecutionData {
  subtaskId: string;
  content: string;
  agentType: string;
  dependsOn: string[];
  state: string;
  resultSummary: string;
  toolRecords: ToolUseRecord[];
}

// ===== Task Execution Data =====

export interface TaskExecutionData {
  taskId: string;
  userRequest: string;
  subtasks: SubtaskExecutionData[];
  completedCount: number;
  failedCount: number;
  totalCount: number;
}

// ===== Task State Snapshot (for persistence & resume) =====

export interface SubtaskSnapshot {
  id: string;
  content: string;
  agentType: string;
  dependsOn: string[];
  workflowGuide?: string;
  memoryLevel: string;
  state: string;
  result?: string;
  error?: string;
}

export interface TaskStateSnapshot {
  taskId: string;
  userRequest: string;
  status: "running" | "completed" | "failed";
  memoryPlan?: Record<string, unknown>;
  subtasks: SubtaskSnapshot[];
  createdAt: string;
  updatedAt: string;
}
