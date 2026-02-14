/**
 * SSE Event Types — matches Python Pydantic models exactly for frontend compatibility.
 *
 * Wire format: `data: {"step": "<action>", "data": {...}}\n\n`
 * NO `event:` prefix lines.
 */

// ===== Action Constants =====

export const Action = {
  // User -> Backend (Input Actions)
  improve: "improve",
  update_task: "update_task",
  start: "start",
  stop: "stop",
  pause: "pause",
  resume: "resume",
  supplement: "supplement",
  human_response: "human_response",

  // Task lifecycle
  task_state: "task_state",
  new_task_state: "new_task_state",
  task_started: "task_started",
  task_completed: "task_completed",
  task_failed: "task_failed",
  task_cancelled: "task_cancelled",

  // Planning
  plan_started: "plan_started",
  plan_progress: "plan_progress",
  plan_generated: "plan_generated",

  // Task decomposition
  task_decomposed: "task_decomposed",
  subtask_state: "subtask_state",
  task_replanned: "task_replanned",
  streaming_decompose: "streaming_decompose",
  decompose_progress: "decompose_progress",

  // Workforce events
  workforce_started: "workforce_started",
  workforce_completed: "workforce_completed",
  workforce_stopped: "workforce_stopped",
  worker_assigned: "worker_assigned",
  worker_started: "worker_started",
  worker_completed: "worker_completed",
  worker_failed: "worker_failed",
  dynamic_tasks_added: "dynamic_tasks_added",
  assign_task: "assign_task",

  // Agent lifecycle
  activate_agent: "activate_agent",
  deactivate_agent: "deactivate_agent",
  agent_thinking: "agent_thinking",
  agent_started: "agent_started",

  // Step/iteration execution
  step_started: "step_started",
  step_progress: "step_progress",
  step_completed: "step_completed",
  step_failed: "step_failed",
  loop_iteration: "loop_iteration",

  // Toolkit events
  activate_toolkit: "activate_toolkit",
  deactivate_toolkit: "deactivate_toolkit",
  tool_started: "tool_started",
  tool_completed: "tool_completed",
  tool_failed: "tool_failed",
  tool_executed: "tool_executed",

  // Specific tool events
  terminal: "terminal",
  browser_action: "browser_action",
  write_file: "write_file",
  screenshot: "screenshot",

  // User interaction
  ask: "ask",
  notice: "notice",
  human_question: "human_question",
  human_message: "human_message",
  wait_confirm: "wait_confirm",
  confirmed: "confirmed",

  // Agent report
  agent_report: "agent_report",

  // Memory events
  memory_query: "memory_query",
  memory_result: "memory_result",
  memory_loaded: "memory_loaded",
  memory_level: "memory_level",
  memory_event: "memory_event",

  // Reasoner events
  reasoner_query_started: "reasoner_query_started",
  reasoner_workflow_started: "reasoner_workflow_started",
  reasoner_navigate: "reasoner_navigate",
  reasoner_intent_executed: "reasoner_intent_executed",
  reasoner_intent_failed: "reasoner_intent_failed",
  reasoner_workflow_completed: "reasoner_workflow_completed",
  reasoner_fallback: "reasoner_fallback",

  // LLM events
  llm_request: "llm_request",
  llm_response: "llm_response",
  llm_reasoning: "llm_reasoning",
  llm_error: "llm_error",
  context_too_long: "context_too_long",
  context_warning: "context_warning",

  // System events
  heartbeat: "heartbeat",
  error: "error",
  end: "end",
  connected: "connected",
} as const;

export type ActionType = (typeof Action)[keyof typeof Action];

// ===== Terminal action types (stream closes after these) =====

export const TERMINAL_ACTIONS = new Set<string>([
  Action.end,
]);

// ===== Base Action Data =====

export interface BaseActionData {
  action: string;
  timestamp?: string;
  task_id?: string;
}

// ===== Task Lifecycle Events =====

export interface TaskStateData extends BaseActionData {
  action: typeof Action.task_state;
  status: string;
  task: string;
  progress: number;
  plan?: Record<string, unknown>[];
  current_step?: Record<string, unknown>;
  working_directory?: string;
  user_id?: string;
  project_id?: string;
}

export interface TaskCompletedData extends BaseActionData {
  action: typeof Action.task_completed;
  output?: unknown;
  tools_called: Record<string, unknown>[];
  loop_iterations: number;
  duration_seconds?: number;
}

export interface TaskFailedData extends BaseActionData {
  action: typeof Action.task_failed;
  error: string;
  tools_called: Record<string, unknown>[];
  step?: number;
}

export interface TaskCancelledData extends BaseActionData {
  action: typeof Action.task_cancelled;
  reason?: string;
}

// ===== Planning Events =====

export interface PlanStartedData extends BaseActionData {
  action: typeof Action.plan_started;
  task: string;
}

export interface PlanProgressData extends BaseActionData {
  action: typeof Action.plan_progress;
  progress: number;
  message?: string;
}

export interface PlanGeneratedData extends BaseActionData {
  action: typeof Action.plan_generated;
  steps: Record<string, unknown>[];
  total_steps: number;
  method?: string;
}

// ===== Task Decomposition Events =====

export interface TaskDecomposedData extends BaseActionData {
  action: typeof Action.task_decomposed;
  subtasks: Record<string, unknown>[];
  summary_task?: string;
  original_task_id?: string;
  total_subtasks: number;
  executor_id?: string;
  task_label?: string;
}

export interface SubtaskStateData extends BaseActionData {
  action: typeof Action.subtask_state;
  subtask_id: string;
  state: string;
  result?: string;
  failure_count: number;
  executor_id?: string;
  task_label?: string;
}

export interface TaskReplannedData extends BaseActionData {
  action: typeof Action.task_replanned;
  subtasks: Record<string, unknown>[];
  original_task_id?: string;
  reason?: string;
  executor_id?: string;
  task_label?: string;
}

export interface StreamingDecomposeData extends BaseActionData {
  action: typeof Action.streaming_decompose;
  text: string;
}

export interface DecomposeProgressData extends BaseActionData {
  action: typeof Action.decompose_progress;
  progress: number;
  message?: string;
  sub_tasks?: Record<string, unknown>[];
  is_final: boolean;
}

// ===== Agent Lifecycle Events =====

export interface ActivateAgentData extends BaseActionData {
  action: typeof Action.activate_agent;
  agent_name: string;
  agent_id?: string;
  process_task_id?: string;
  message?: string;
  executor_id?: string;
  task_label?: string;
}

export interface DeactivateAgentData extends BaseActionData {
  action: typeof Action.deactivate_agent;
  agent_name: string;
  agent_id?: string;
  process_task_id?: string;
  message?: string;
  error?: string;
  tokens_used?: number;
  duration_seconds?: number;
  executor_id?: string;
  task_label?: string;
}

export interface AgentThinkingData extends BaseActionData {
  action: typeof Action.agent_thinking;
  agent_name: string;
  thinking: string;
  step?: number;
}

// ===== Step Execution Events =====

export interface StepStartedData extends BaseActionData {
  action: typeof Action.step_started;
  step_index: number;
  step_name: string;
  step_description?: string;
}

export interface StepProgressData extends BaseActionData {
  action: typeof Action.step_progress;
  step_index: number;
  progress: number;
  message?: string;
}

export interface StepCompletedData extends BaseActionData {
  action: typeof Action.step_completed;
  step_index: number;
  step_name: string;
  result?: string;
  duration_seconds?: number;
}

export interface StepFailedData extends BaseActionData {
  action: typeof Action.step_failed;
  step_index: number;
  step_name: string;
  error: string;
  recoverable: boolean;
}

// ===== Toolkit Events =====

export interface ActivateToolkitData extends BaseActionData {
  action: typeof Action.activate_toolkit;
  toolkit_name: string;
  method_name: string;
  agent_name?: string;
  process_task_id?: string;
  input_preview?: string;
  message?: string;
}

export interface DeactivateToolkitData extends BaseActionData {
  action: typeof Action.deactivate_toolkit;
  toolkit_name: string;
  method_name: string;
  agent_name?: string;
  process_task_id?: string;
  output_preview?: string;
  success: boolean;
  duration_ms?: number;
  message?: string;
}

// ===== Tool-Specific Events =====

export interface TerminalData extends BaseActionData {
  action: typeof Action.terminal;
  command: string;
  output?: string;
  exit_code?: number;
  working_directory?: string;
  duration_ms?: number;
}

export interface BrowserActionData extends BaseActionData {
  action: typeof Action.browser_action;
  action_type: string;
  target?: string;
  value?: string;
  success: boolean;
  screenshot_url?: string;
  page_url?: string;
  page_title?: string;
  webview_id?: string;
}

export interface WriteFileData extends BaseActionData {
  action: typeof Action.write_file;
  file_path: string;
  file_name: string;
  file_size?: number;
  content_preview?: string;
  mime_type?: string;
}

export interface ScreenshotData extends BaseActionData {
  action: typeof Action.screenshot;
  screenshot: string;
  url?: string;
  page_title?: string;
  tab_id?: string;
  webview_id?: string;
}

// ===== User Interaction Events =====

export interface AskData extends BaseActionData {
  action: typeof Action.ask;
  question: string;
  context?: string;
  options?: string[];
  timeout_seconds?: number;
  default?: string;
}

export interface NoticeData extends BaseActionData {
  action: typeof Action.notice;
  level: string;
  title: string;
  message: string;
  duration_ms?: number;
}

export interface HumanResponseData extends BaseActionData {
  action: typeof Action.human_response;
  response: string;
  question_id?: string;
}

export interface FilePreviewData {
  thumbnail?: string;
  table_preview?: string[][];
  table_total_rows?: number;
  table_headers?: string[];
  text_preview?: string;
  text_total_lines?: number;
  folder_files?: string[];
  folder_total_size?: number;
  folder_file_count?: number;
  pdf_page_count?: number;
}

export interface FileAttachment {
  file_name: string;
  file_path: string;
  file_type: string;
  mime_type?: string;
  file_size?: number;
  preview?: FilePreviewData;
}

export interface WaitConfirmData extends BaseActionData {
  action: typeof Action.wait_confirm;
  content: string;
  question: string;
  context: string;
  attachments?: FileAttachment[];
  executor_id?: string;
  task_label?: string;
}

export interface ConfirmedData extends BaseActionData {
  action: typeof Action.confirmed;
  question: string;
}

export interface AgentReportData extends BaseActionData {
  action: typeof Action.agent_report;
  message: string;
  report_type: string;
  agent_type?: string;
  executor_id?: string;
  task_label?: string;
  subtask_label?: string;
}

// ===== Memory Events =====

export interface MemoryQueryData extends BaseActionData {
  action: typeof Action.memory_query;
  query: string;
  top_k: number;
}

export interface MemoryResultData extends BaseActionData {
  action: typeof Action.memory_result;
  paths_count: number;
  paths: Record<string, unknown>[];
  has_workflow: boolean;
  method?: string;
}

export interface MemoryLevelData extends BaseActionData {
  action: typeof Action.memory_level;
  level: string;
  reason: string;
  states_count: number;
  method: string;
  paths?: Record<string, unknown>[];
}

export interface MemoryEventData extends BaseActionData {
  action: typeof Action.memory_event;
  event_type: string;
  data: Record<string, unknown>;
  memory_level?: string;
}

// ===== System Events =====

export interface HeartbeatData extends BaseActionData {
  action: typeof Action.heartbeat;
  message: string;
}

export interface ErrorData extends BaseActionData {
  action: typeof Action.error;
  error: string;
  error_type?: string;
  recoverable: boolean;
  details?: Record<string, unknown>;
}

export interface EndData extends BaseActionData {
  action: typeof Action.end;
  status: string;
  message?: string;
  result?: unknown;
}

export interface ContextWarningData extends BaseActionData {
  action: typeof Action.context_warning;
  current_length: number;
  max_length: number;
  usage_percent: number;
  message: string;
  entries_count: number;
}

// ===== Workforce Events =====

export interface WorkforceStartedData extends BaseActionData {
  action: typeof Action.workforce_started;
  total_tasks: number;
  workers_count: number;
  description?: string;
  executor_id?: string;
  task_label?: string;
}

export interface WorkforceCompletedData extends BaseActionData {
  action: typeof Action.workforce_completed;
  completed_count: number;
  failed_count: number;
  total_count: number;
  duration_seconds?: number;
  executor_id?: string;
  task_label?: string;
}

export interface WorkforceStoppedData extends BaseActionData {
  action: typeof Action.workforce_stopped;
  reason?: string;
  completed_count: number;
  pending_count: number;
  executor_id?: string;
  task_label?: string;
}

export interface WorkerAssignedData extends BaseActionData {
  action: typeof Action.worker_assigned;
  worker_name: string;
  worker_id?: string;
  subtask_id: string;
  subtask_content: string;
  executor_id?: string;
  task_label?: string;
}

export interface WorkerStartedData extends BaseActionData {
  action: typeof Action.worker_started;
  worker_name: string;
  worker_id?: string;
  subtask_id: string;
  executor_id?: string;
  task_label?: string;
}

export interface WorkerCompletedData extends BaseActionData {
  action: typeof Action.worker_completed;
  worker_name: string;
  worker_id?: string;
  subtask_id: string;
  result_preview?: string;
  duration_seconds?: number;
  executor_id?: string;
  task_label?: string;
}

export interface WorkerFailedData extends BaseActionData {
  action: typeof Action.worker_failed;
  worker_name: string;
  worker_id?: string;
  subtask_id: string;
  error: string;
  failure_count: number;
  will_retry: boolean;
  executor_id?: string;
  task_label?: string;
}

export interface DynamicTasksAddedData extends BaseActionData {
  action: typeof Action.dynamic_tasks_added;
  new_tasks: Record<string, unknown>[];
  added_by_worker?: string;
  reason?: string;
  total_tasks_now: number;
  total_tasks: number;
  executor_id?: string;
  task_label?: string;
}

export interface AssignTaskData extends BaseActionData {
  action: typeof Action.assign_task;
  assignee_id: string;
  subtask_id: string;
  content: string;
  state: string;
  failure_count: number;
  worker_name?: string;
  agent_type?: string;
  agent_id?: string;
  executor_id?: string;
  task_label?: string;
}

// ===== Union type for all action data =====

export type ActionData =
  | TaskStateData
  | TaskCompletedData
  | TaskFailedData
  | TaskCancelledData
  | PlanStartedData
  | PlanProgressData
  | PlanGeneratedData
  | TaskDecomposedData
  | SubtaskStateData
  | TaskReplannedData
  | StreamingDecomposeData
  | DecomposeProgressData
  | ActivateAgentData
  | DeactivateAgentData
  | AgentThinkingData
  | StepStartedData
  | StepProgressData
  | StepCompletedData
  | StepFailedData
  | ActivateToolkitData
  | DeactivateToolkitData
  | TerminalData
  | BrowserActionData
  | WriteFileData
  | ScreenshotData
  | AskData
  | NoticeData
  | HumanResponseData
  | WaitConfirmData
  | ConfirmedData
  | AgentReportData
  | MemoryQueryData
  | MemoryResultData
  | MemoryLevelData
  | MemoryEventData
  | HeartbeatData
  | ErrorData
  | EndData
  | ContextWarningData
  | WorkforceStartedData
  | WorkforceCompletedData
  | WorkforceStoppedData
  | WorkerAssignedData
  | WorkerStartedData
  | WorkerCompletedData
  | WorkerFailedData
  | DynamicTasksAddedData
  | AssignTaskData
  | BaseActionData;
