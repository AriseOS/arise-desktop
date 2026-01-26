/**
 * Agent Store - Task management using Zustand
 *
 * Inspired by Eigent's chatStore pattern for managing multiple concurrent tasks.
 * Each task has its own state including messages, agents, progress, etc.
 */

import { create } from 'zustand';
import { api } from '../utils/api';
import { SSEClient } from '../utils/sseClient';

// Generate unique task ID (8 char)
const generateTaskId = () => {
  return Math.random().toString(36).substring(2, 10);
};

// SSE clients per task
const sseClients = {};

// Auto-confirm timers per task (Eigent pattern: 30s auto-confirm)
const autoConfirmTimers = {};

// Internal agent names to filter out (Eigent pattern)
const INTERNAL_AGENT_NAMES = [
  'mcp_agent', 'new_worker_agent', 'task_agent',
  'task_summary_agent', 'coordinator_agent', 'question_confirm_agent'
];

/**
 * Check if backend is ready (Eigent pattern: waitForBackendReady)
 * @param {number} timeout - Total timeout in ms
 * @param {number} interval - Check interval in ms
 * @returns {Promise<boolean>} - Whether backend is ready
 */
const checkBackendReady = async (timeout = 15000, interval = 500) => {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    try {
      const response = await api.callAppBackend('/api/v1/health', {
        method: 'GET',
      });
      if (response && (response.status === 'ok' || response.status === 'healthy')) {
        return true;
      }
    } catch (error) {
      // Backend not ready yet, continue waiting
      console.log('[AgentStore] Backend not ready, retrying...');
    }
    await new Promise(resolve => setTimeout(resolve, interval));
  }

  return false;
};

// Initial task state template (Eigent-aligned)
const createInitialTaskState = (taskDescription = '', type = 'normal') => ({
  // Basic info (Eigent: type field for normal/replay/share)
  type,  // 'normal' | 'replay' | 'share'
  taskDescription,
  summaryTask: '',  // Eigent: task summary for display
  status: 'pending', // pending | running | completed | failed | cancelled
  createdAt: new Date().toISOString(),
  startedAt: null,
  completedAt: null,

  // Execution state
  executionPhase: 'initializing',
  loopIteration: 0,
  progressValue: 0,
  result: null,
  error: null,

  // Messages and conversation
  messages: [],
  notices: [],

  // Task decomposition (Eigent pattern)
  taskInfo: [],        // Decomposed subtasks (original)
  taskRunning: [],     // Currently running tasks (progress)
  taskAssigning: [],   // Tasks assigned to agents

  // Multi-agent state
  agents: [],
  activeAgentId: null,

  // Tools and toolkits
  currentTools: [],
  toolkitEvents: [],

  // Memory
  memoryPaths: [],
  memoryLevel: null,        // "L1" | "L2" | "L3" | null
  memoryLevelReason: '',    // Why this level was determined
  memoryMethod: '',         // "cognitive_phrase_match" | "task_dag" | "none"
  memoryStatesCount: 0,     // Number of states found

  // Thinking/Reasoning (for AgentTab display)
  thinkingLogs: [],  // Agent reasoning history

  // Browser state (for BrowserTab display)
  browserScreenshot: null,  // Current browser screenshot (base64 image)
  browserUrl: '',           // Current browser URL

  // Workspace
  terminalOutput: [],
  notesContent: null,
  selectedFile: null,
  fileList: [],  // Eigent: generated files list

  // Human interaction
  humanQuestion: null,
  humanQuestionContext: null,
  humanInteractionType: 'question',
  humanInteractionOptions: [],
  humanInteractionTimeout: null,
  humanMessages: [],
  hasWaitConfirm: false,  // Eigent: waiting for confirmation flag

  // Token usage
  tokenUsage: {
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    estimatedCost: null,
  },
  currentModel: '',

  // Subtask decomposition
  subtasks: [],
  showDecomposition: false,
  confirmedSubtasks: [],
  streamingDecomposeText: '',  // Eigent: streaming task decomposition text

  // Eigent flags
  isPending: false,
  isTaskEdit: false,
  isTakeControl: false,
  isContextExceeded: false,

  // Timing (Eigent: for statistics)
  taskTime: null,  // When task started
  elapsed: 0,      // Task duration in ms
});

/**
 * Agent Store
 *
 * Manages multiple tasks with their individual states.
 * Similar to Eigent's chatStore pattern.
 */
export const useAgentStore = create((set, get) => ({
  // Active task tracking
  activeTaskId: null,

  // All tasks keyed by taskId
  tasks: {},

  // Budget settings (global)
  budget: {
    maxCostUsd: null,
    warningThreshold: 0.8,
  },

  // ============ Task Lifecycle ============

  /**
   * Create a new task (Eigent-aligned: supports external ID and type)
   * @param {string} taskDescription - The task description
   * @param {string} id - Optional external task ID (for replay/share)
   * @param {string} type - Task type: 'normal' | 'replay' | 'share'
   * @returns {string} The new task ID
   */
  createTask: (taskDescription = '', id = null, type = 'normal') => {
    const taskId = id || generateTaskId();

    set((state) => ({
      activeTaskId: taskId,
      tasks: {
        ...state.tasks,
        [taskId]: createInitialTaskState(taskDescription, type),
      },
    }));

    console.log('[AgentStore] Created task:', taskId, 'type:', type);
    return taskId;
  },

  /**
   * Set the active task
   */
  setActiveTaskId: (taskId) => {
    set({ activeTaskId: taskId });
  },

  /**
   * Remove a task
   */
  removeTask: (taskId) => {
    // Cleanup SSE connection
    if (sseClients[taskId]) {
      sseClients[taskId].disconnect();
      delete sseClients[taskId];
    }

    set((state) => {
      const { [taskId]: removed, ...remainingTasks } = state.tasks;
      const newActiveTaskId = state.activeTaskId === taskId
        ? Object.keys(remainingTasks)[0] || null
        : state.activeTaskId;

      return {
        tasks: remainingTasks,
        activeTaskId: newActiveTaskId,
      };
    });

    console.log('[AgentStore] Removed task:', taskId);
  },

  /**
   * Clear all tasks
   */
  clearAllTasks: () => {
    // Cleanup all SSE connections
    Object.keys(sseClients).forEach(taskId => {
      sseClients[taskId].disconnect();
      delete sseClients[taskId];
    });

    set({ tasks: {}, activeTaskId: null });
    console.log('[AgentStore] Cleared all tasks');
  },

  // ============ Task State Updates ============

  /**
   * Update a specific task's state
   */
  updateTask: (taskId, updates) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            ...updates,
          },
        },
      };
    });
  },

  /**
   * Set task status
   */
  setTaskStatus: (taskId, status) => {
    const updates = { status };

    if (status === 'running' && !get().tasks[taskId]?.startedAt) {
      updates.startedAt = new Date().toISOString();
    }

    if (status === 'completed' || status === 'failed' || status === 'cancelled') {
      updates.completedAt = new Date().toISOString();
    }

    get().updateTask(taskId, updates);
  },

  /**
   * Add a message to task
   */
  addMessage: (taskId, role, content, extra = {}) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const newMessage = {
        role,
        content,
        timestamp: new Date().toISOString(),
        ...extra,
      };

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            messages: [...state.tasks[taskId].messages, newMessage],
          },
        },
      };
    });
  },

  /**
   * Add a notice to task
   */
  addNotice: (taskId, type, title, message, data = null) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const newNotice = {
        type,
        title,
        message,
        data,
        timestamp: new Date().toISOString(),
      };

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            notices: [...state.tasks[taskId].notices, newNotice],
          },
        },
      };
    });
  },

  /**
   * Update agents list
   */
  updateAgents: (taskId, agentUpdater) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const currentAgents = state.tasks[taskId].agents;
      const newAgents = typeof agentUpdater === 'function'
        ? agentUpdater(currentAgents)
        : agentUpdater;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            agents: newAgents,
          },
        },
      };
    });
  },

  /**
   * Add toolkit event
   * Includes deduplication to prevent duplicate entries from multiple event sources
   */
  addToolkitEvent: (taskId, event) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const existingEvents = state.tasks[taskId].toolkitEvents;

      // Deduplicate: Check if there's already a running event with same toolkit+method
      // This prevents duplicate entries when both activate_toolkit and browser_action fire
      const isDuplicate = existingEvents.some(e =>
        e.toolkit_name === event.toolkit_name &&
        e.method_name === event.method_name &&
        e.status === 'running'
      );

      if (isDuplicate) {
        console.log('[AgentStore] Skipping duplicate toolkit event:', event.toolkit_name, event.method_name);
        return state;
      }

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            toolkitEvents: [...existingEvents, {
              ...event,
              timestamp: new Date().toISOString(),
            }],
          },
        },
      };
    });
  },

  /**
   * Update toolkit event status
   */
  updateToolkitEvent: (taskId, toolkitName, methodName, updates) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const toolkitEvents = state.tasks[taskId].toolkitEvents.map(e =>
        e.toolkit_name === toolkitName && e.method_name === methodName && e.status === 'running'
          ? { ...e, ...updates }
          : e
      );

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            toolkitEvents,
          },
        },
      };
    });
  },

  /**
   * Add terminal output
   */
  addTerminalOutput: (taskId, output) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            terminalOutput: [...state.tasks[taskId].terminalOutput, output],
          },
        },
      };
    });
  },

  /**
   * Update token usage
   */
  updateTokenUsage: (taskId, usage) => {
    set((state) => {
      if (!state.tasks[taskId]) return state;

      const currentUsage = state.tasks[taskId].tokenUsage;
      const isDelta = usage.is_delta === true;

      let newUsage;

      // If total_* fields are present, use them directly
      if (usage.total_input_tokens !== undefined || usage.total_output_tokens !== undefined) {
        newUsage = {
          inputTokens: usage.total_input_tokens ?? currentUsage.inputTokens,
          outputTokens: usage.total_output_tokens ?? currentUsage.outputTokens,
          cacheCreationTokens: usage.total_cache_creation_tokens ?? currentUsage.cacheCreationTokens,
          cacheReadTokens: usage.total_cache_read_tokens ?? currentUsage.cacheReadTokens,
          estimatedCost: usage.estimated_cost ?? usage.total_cost ?? currentUsage.estimatedCost,
        };
      } else if (isDelta) {
        // Delta mode: accumulate values
        newUsage = {
          inputTokens: (currentUsage.inputTokens || 0) + (usage.input_tokens || 0),
          outputTokens: (currentUsage.outputTokens || 0) + (usage.output_tokens || 0),
          cacheCreationTokens: (currentUsage.cacheCreationTokens || 0) + (usage.cache_creation_tokens || 0),
          cacheReadTokens: (currentUsage.cacheReadTokens || 0) + (usage.cache_read_tokens || 0),
          estimatedCost: usage.estimated_cost ?? currentUsage.estimatedCost,
        };
      } else {
        // Default mode: treat as totals (replace)
        newUsage = {
          inputTokens: usage.input_tokens ?? currentUsage.inputTokens,
          outputTokens: usage.output_tokens ?? currentUsage.outputTokens,
          cacheCreationTokens: usage.cache_creation_tokens ?? currentUsage.cacheCreationTokens,
          cacheReadTokens: usage.cache_read_tokens ?? currentUsage.cacheReadTokens,
          estimatedCost: usage.estimated_cost ?? currentUsage.estimatedCost,
        };
      }

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...state.tasks[taskId],
            tokenUsage: newUsage,
            currentModel: usage.model || state.tasks[taskId].currentModel,
          },
        },
      };
    });
  },

  // ============ Task Execution ============

  /**
   * Start task execution (Eigent-aligned)
   * Includes backend ready check and timing
   */
  startTask: async (taskId, showStatusCallback) => {
    const state = get();
    const task = state.tasks[taskId];

    if (!task) {
      console.error('[AgentStore] Task not found:', taskId);
      return false;
    }

    try {
      // Eigent: Check if backend is ready (15 second timeout)
      const isBackendReady = await checkBackendReady(15000, 500);
      if (!isBackendReady) {
        console.error('[AgentStore] Backend not ready after timeout');
        get().setTaskStatus(taskId, 'failed');
        get().updateTask(taskId, {
          error: 'Backend service not available. Please try again later.',
          executionPhase: 'failed',
        });
        get().addMessage(taskId, 'system', 'Backend service is not available. Please check if the daemon is running.');
        if (showStatusCallback) {
          showStatusCallback('Backend not ready. Is the daemon running?', 'error');
        }
        return false;
      }

      // Update status to running and record start time (Eigent: taskTime)
      get().setTaskStatus(taskId, 'running');
      get().updateTask(taskId, {
        executionPhase: 'starting',
        taskTime: Date.now(),  // Eigent: record task start time
        isPending: true,
      });

      // Add user message
      get().addMessage(taskId, 'user', task.taskDescription);

      // Submit to backend
      const response = await api.callAppBackend('/api/v1/quick-task/execute', {
        method: 'POST',
        body: JSON.stringify({
          task: task.taskDescription.trim()
        })
      });

      // Update with backend task ID (may differ from our local ID)
      get().updateTask(taskId, {
        backendTaskId: response.task_id,
        isPending: false,
      });

      // Connect SSE
      get().connectSSE(taskId, response.task_id);

      if (showStatusCallback) {
        showStatusCallback('Task submitted successfully', 'success');
      }

      return true;
    } catch (error) {
      console.error('[AgentStore] Failed to start task:', error);
      get().setTaskStatus(taskId, 'failed');
      get().updateTask(taskId, {
        error: error.message,
        executionPhase: 'failed',
        isPending: false,
      });

      if (showStatusCallback) {
        showStatusCallback(`Failed to submit task: ${error.message}`, 'error');
      }

      return false;
    }
  },

  /**
   * Connect SSE for task updates
   */
  connectSSE: (taskId, backendTaskId) => {
    // Disconnect existing connection
    if (sseClients[taskId]) {
      sseClients[taskId].disconnect();
    }

    const client = new SSEClient();
    sseClients[taskId] = client;

    client.connect(backendTaskId, {
      onEvent: (event) => get().handleSSEEvent(taskId, event),
      onError: (error) => {
        console.error('[AgentStore] SSE error for task', taskId, error);
        get().addNotice(taskId, 'error', 'Connection Error', error.message);
      },
      onClose: () => {
        console.log('[AgentStore] SSE closed for task', taskId);
      }
    });
  },

  /**
   * Handle SSE event
   */
  handleSSEEvent: (taskId, event) => {
    const store = get();
    const eventType = event.event || event.action;

    // Helper functions scoped to this task
    const updateTask = (updates) => store.updateTask(taskId, updates);
    const addMessage = (role, content, extra) => store.addMessage(taskId, role, content, extra);
    const addNotice = (type, title, message, data) => store.addNotice(taskId, type, title, message, data);
    const setStatus = (status) => store.setTaskStatus(taskId, status);

    switch (eventType) {
      case 'connected':
        updateTask({ executionPhase: 'initializing' });
        addNotice('info', 'Connected', 'SSE stream connected');
        break;

      case 'task_started':
        setStatus('running');
        updateTask({ executionPhase: 'starting' });
        addNotice('info', 'Task Started', 'Agent is starting...');
        break;

      case 'memory_loaded':
      case 'memory_result':
        {
          const paths = event.paths || [];
          const level = event.level || (paths.length > 0 ? 'L2' : 'L3');

          updateTask({
            memoryPaths: paths,
            memoryLevel: level,
            executionPhase: 'memory_loaded',
          });

          if (paths.length > 0) {
            addNotice('memory', 'Memory Loaded', `Found ${paths.length} relevant paths [${level}]`);
          }
        }
        break;

      // Memory Level Determination Event (from P0-1)
      case 'memory_level':
        {
          const { level, reason, states_count, method, paths } = event;

          updateTask({
            memoryLevel: level,
            memoryLevelReason: reason || '',
            memoryMethod: method || '',
            memoryStatesCount: states_count || 0,
            memoryPaths: paths || [],
            executionPhase: level === 'L1' ? 'memory_guided' : 'executing',
          });

          // Show level-specific notice
          const levelMessages = {
            'L1': `Memory L1: Complete path found (${states_count || 0} states)`,
            'L2': `Memory L2: Partial match (${states_count || 0} states)`,
            'L3': 'Memory L3: Using real-time queries',
          };

          addNotice('memory', 'Memory Level', levelMessages[level] || `Memory: ${level}`);
        }
        break;

      case 'agent_started':
      case 'agent_created':
      case 'create_agent':  // Eigent event name
        {
          const agentName = event.agent_name || event.data?.agent_name;
          const agentId = event.agent_id || event.data?.agent_id || `agent_${Date.now()}`;

          // Eigent: Filter out internal agents
          if (INTERNAL_AGENT_NAMES.includes(agentName)) {
            break;
          }

          updateTask({ executionPhase: 'executing' });

          if (agentId || agentName) {
            store.updateAgents(taskId, (prev) => {
              const exists = prev.some(a => a.id === agentId || a.name === agentName);
              if (exists) return prev;

              // Eigent-aligned agent structure
              return [...prev, {
                id: agentId,
                agent_id: agentId,  // Eigent uses agent_id
                type: event.agent_type || agentName || 'browser_agent',
                name: agentName || 'Agent',
                status: 'active',
                progress: 0,
                currentAction: null,
                tools: event.tools || event.data?.tools || [],
                tasks: [],  // Eigent: tasks assigned to this agent
                log: [],    // Eigent: execution log
              }];
            });
            updateTask({ activeAgentId: agentId });
          }
          addNotice('info', 'Agent Created', agentName || 'Agent initialized');
        }
        break;

      case 'activate_agent':
        updateTask({ executionPhase: 'executing' });
        if (event.agent_id || event.agent_name) {
          store.updateAgents(taskId, (prev) => {
            const existingAgent = prev.find(a =>
              a.id === event.agent_id || a.name === event.agent_name
            );
            if (existingAgent) {
              return prev.map(a =>
                a.id === existingAgent.id
                  ? { ...a, status: 'active', currentAction: event.message }
                  : a
              );
            }
            return [...prev, {
              id: event.agent_id || `agent_${Date.now()}`,
              type: event.agent_name,
              name: event.agent_name,
              status: 'active',
              progress: 0,
              currentAction: event.message,
            }];
          });
          if (event.agent_id) {
            updateTask({ activeAgentId: event.agent_id });
          }
        }
        addNotice('info', 'Agent Active', event.message || event.agent_name || 'Agent working');
        break;

      case 'deactivate_agent':
        if (event.agent_id) {
          store.updateAgents(taskId, (prev) =>
            prev.map(a => a.id === event.agent_id ? { ...a, status: 'completed' } : a)
          );
        }
        if (event.tokens_used || event.tokens) {
          store.updateTokenUsage(taskId, {
            input_tokens: event.tokens_used || event.tokens || 0,
            is_delta: true,
          });
        }
        break;

      case 'toolkit_started':
      case 'activate_toolkit':
        store.addToolkitEvent(taskId, {
          toolkit_name: event.toolkit_name,
          method_name: event.method_name,
          agent_name: event.agent_name,
          input_preview: event.input_preview,
          status: 'running',
        });
        break;

      case 'toolkit_completed':
      case 'deactivate_toolkit':
        store.updateToolkitEvent(taskId, event.toolkit_name, event.method_name, {
          status: event.success === false ? 'failed' : 'completed',
          output_preview: event.output_preview,
        });
        break;

      case 'terminal':
      case 'terminal_output':
        if (event.command) {
          store.addTerminalOutput(taskId, `$ ${event.command}`);
        }
        if (event.output) {
          store.addTerminalOutput(taskId, event.output);
        }
        break;

      case 'loop_iteration':
        updateTask({
          loopIteration: event.step || 0,
          currentTools: event.tools_called || [],
        });
        break;

      case 'progress_update':
        if (event.progress !== undefined) {
          updateTask({ progressValue: event.progress });
        }
        break;

      case 'token_usage':
      case 'usage_update':
        store.updateTokenUsage(taskId, event);
        break;

      case 'human_question':
      case 'ask':
        updateTask({
          humanQuestion: event.question || event.content,
          humanQuestionContext: event.context,
          humanInteractionType: 'question',
        });
        addNotice('info', 'Human Input Required', event.question || event.content);
        break;

      // Eigent: streaming_decompose event for real-time task decomposition text
      case 'streaming_decompose':
      case 'decomposing':
        {
          const text = event.text || event.content || '';
          if (text) {
            updateTask({
              streamingDecomposeText: text,
            });
          }
        }
        break;

      case 'task_decomposed':
      case 'to_sub_tasks':
        {
          const newSubtasks = event.subtasks || event.tasks || event.data?.sub_tasks || [];
          const summaryTask = event.summary_task || event.data?.summary_task || '';

          // Eigent: Check if this is multi-turn after completion
          const currentTask = store.tasks[taskId];
          const isMultiTurnAfterCompletion = currentTask?.status === 'completed';
          if (isMultiTurnAfterCompletion) {
            setStatus('pending');  // Reset status for new round
          }

          // Map TaskPlanningToolkit states to UI states
          const mapState = (s) => {
            if (!s) return 'pending';
            const stateUpper = s.toUpperCase();
            if (stateUpper === 'DONE') return 'completed';
            if (stateUpper === 'FAILED') return 'failed';
            if (stateUpper === 'RUNNING') return 'running';
            if (stateUpper === 'DELETED') return 'deleted';
            return 'pending'; // OPEN -> pending
          };

          // Normalize subtasks with mapped status
          const normalizedSubtasks = newSubtasks.map(t => ({
            ...t,
            status: mapState(t.state || t.status),
          }));

          // Update task with decomposition data (Eigent pattern)
          // Clear streamingDecomposeText when decomposition is complete
          updateTask({
            subtasks: normalizedSubtasks,
            taskInfo: normalizedSubtasks,
            taskRunning: normalizedSubtasks.map(t => ({ ...t })),
            summaryTask: summaryTask,
            showDecomposition: true,
            isTaskEdit: false,
            streamingDecomposeText: '',  // Clear streaming text on completion
          });

          addNotice('info', 'Task Decomposed', `${newSubtasks.length} subtasks planned`);

          // Eigent: Setup 30 second auto-confirm timer
          if (autoConfirmTimers[taskId]) {
            clearTimeout(autoConfirmTimers[taskId]);
          }
          autoConfirmTimers[taskId] = setTimeout(() => {
            const task = get().tasks[taskId];
            // Only auto-confirm if not edited and not taken control
            if (task && !task.isTaskEdit && !task.isTakeControl && task.showDecomposition) {
              get().confirmDecomposition(taskId, task.subtasks);
              get().addNotice(taskId, 'info', 'Auto-Confirmed', 'Task plan auto-confirmed after 30 seconds');
            }
            delete autoConfirmTimers[taskId];
          }, 30000);
        }
        break;

      // Eigent: task_state event for subtask progress tracking
      case 'task_state':
      // TaskPlanningToolkit: subtask_state event (from update_task_state)
      case 'subtask_state':
        {
          const { state, task_id: subTaskId, subtask_id, result: subTaskResult, failure_count } = event.data || event;
          const effectiveSubTaskId = subTaskId || subtask_id;
          if (!effectiveSubTaskId) break;

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Map TaskPlanningToolkit states to UI states
          const mapState = (s) => {
            if (!s) return 'pending';
            const stateUpper = s.toUpperCase();
            if (stateUpper === 'DONE') return 'completed';
            if (stateUpper === 'FAILED') return 'failed';
            if (stateUpper === 'RUNNING') return 'running';
            if (stateUpper === 'DELETED') return 'deleted';
            return 'pending'; // OPEN -> pending
          };

          // Update taskRunning status
          const updatedTaskRunning = (currentTask.taskRunning || []).map(t => {
            if (t.id === effectiveSubTaskId) {
              return {
                ...t,
                status: mapState(state),
                failure_count: failure_count || 0,
                result: subTaskResult || t.result,
              };
            }
            return t;
          });

          // Update subtasks as well (for TaskDecomposition component)
          const updatedSubtasks = (currentTask.subtasks || []).map(t => {
            if (t.id === effectiveSubTaskId) {
              return {
                ...t,
                status: mapState(state),
                state: state,
                failure_count: failure_count || 0,
                result: subTaskResult || t.result,
              };
            }
            return t;
          });

          // Update taskAssigning (agent task status)
          const updatedTaskAssigning = (currentTask.taskAssigning || []).map(agent => {
            const taskIndex = agent.tasks?.findIndex(t => t.id === effectiveSubTaskId);
            if (taskIndex !== -1 && agent.tasks) {
              const updatedTasks = [...agent.tasks];
              updatedTasks[taskIndex] = {
                ...updatedTasks[taskIndex],
                status: mapState(state),
                failure_count: failure_count || 0,
              };
              return { ...agent, tasks: updatedTasks };
            }
            return agent;
          });

          updateTask({
            taskRunning: updatedTaskRunning,
            subtasks: updatedSubtasks,
            taskAssigning: updatedTaskAssigning,
          });

          // Eigent: Add failure message if retries exceeded
          if (state === 'FAILED' && failure_count >= 3 && subTaskResult) {
            addMessage('agent', subTaskResult, { step: 'failed' });
          }
        }
        break;

      // TaskPlanningToolkit: task_replanned event
      case 'task_replanned':
        {
          const newSubtasks = event.subtasks || event.data?.subtasks || [];
          const reason = event.reason || event.data?.reason || '';

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Replace subtasks with new plan
          updateTask({
            subtasks: newSubtasks,
            taskInfo: newSubtasks,
            taskRunning: newSubtasks.map(t => ({ ...t, status: 'pending' })),
            showDecomposition: true,
          });

          addNotice('info', 'Task Re-planned', `${newSubtasks.length} new subtasks${reason ? `: ${reason}` : ''}`);
        }
        break;

      // Eigent: assign_task event for task assignment to agents
      case 'assign_task':
        {
          const { agent_id, task_id: assignedTaskId, agent_name } = event.data || event;
          if (!agent_id || !assignedTaskId) break;

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Find the task in taskRunning
          const taskToAssign = (currentTask.taskRunning || []).find(t => t.id === assignedTaskId);
          if (!taskToAssign) break;

          // Update taskAssigning - add task to agent
          let updatedTaskAssigning = [...(currentTask.taskAssigning || [])];
          const agentIndex = updatedTaskAssigning.findIndex(a => a.agent_id === agent_id);

          if (agentIndex !== -1) {
            // Agent exists, add task to it
            const existingTaskIndex = updatedTaskAssigning[agentIndex].tasks?.findIndex(t => t.id === assignedTaskId);
            if (existingTaskIndex === -1 || existingTaskIndex === undefined) {
              updatedTaskAssigning[agentIndex] = {
                ...updatedTaskAssigning[agentIndex],
                tasks: [...(updatedTaskAssigning[agentIndex].tasks || []), { ...taskToAssign, status: 'running' }],
              };
            }
          }

          // Update taskRunning status to running
          const updatedTaskRunning = (currentTask.taskRunning || []).map(t =>
            t.id === assignedTaskId ? { ...t, status: 'running' } : t
          );

          updateTask({
            taskRunning: updatedTaskRunning,
            taskAssigning: updatedTaskAssigning,
          });
        }
        break;

      case 'task_completed':
        setStatus('completed');
        updateTask({
          result: event.output,
          notesContent: event.notes,
          executionPhase: 'completed',
          progressValue: 100,
          // Clear decomposition state to avoid showing confirm button after completion
          showDecomposition: false,
          taskInfo: [],
          streamingDecomposeText: '',
        });
        if (event.output) {
          addMessage('assistant', typeof event.output === 'string' ? event.output : JSON.stringify(event.output, null, 2));
        }
        // Disconnect SSE
        if (sseClients[taskId]) {
          sseClients[taskId].disconnect();
          delete sseClients[taskId];
        }
        break;

      case 'task_failed':
        setStatus('failed');
        updateTask({
          error: event.error,
          notesContent: event.notes,
          executionPhase: 'failed',
          // Clear decomposition state
          showDecomposition: false,
          taskInfo: [],
          streamingDecomposeText: '',
        });
        addNotice('error', 'Task Failed', event.error);
        if (sseClients[taskId]) {
          sseClients[taskId].disconnect();
          delete sseClients[taskId];
        }
        break;

      case 'task_cancelled':
        setStatus('cancelled');
        updateTask({
          error: 'Task was cancelled',
          executionPhase: 'cancelled',
          // Clear decomposition state
          showDecomposition: false,
          taskInfo: [],
          streamingDecomposeText: '',
        });
        addNotice('warning', 'Task Cancelled', 'Task was cancelled by user');
        if (sseClients[taskId]) {
          sseClients[taskId].disconnect();
          delete sseClients[taskId];
        }
        break;

      case 'end':
        {
          const currentTask = store.tasks[taskId];

          // Eigent: Calculate elapsed time
          let elapsed = 0;
          if (currentTask?.taskTime) {
            elapsed = Date.now() - currentTask.taskTime;
          } else if (currentTask?.startedAt) {
            elapsed = Date.now() - new Date(currentTask.startedAt).getTime();
          }

          // Eigent: Mark incomplete tasks as skipped
          const updatedTaskRunning = (currentTask?.taskRunning || []).map(t => {
            if (t.status !== 'completed' && t.status !== 'failed') {
              return { ...t, status: 'skipped' };
            }
            return t;
          });

          if (event.status === 'completed') {
            setStatus('completed');
            updateTask({
              executionPhase: 'completed',
              result: event.result,
              elapsed,
              taskRunning: updatedTaskRunning,
              progressValue: 100,
            });
          } else if (event.status === 'failed') {
            setStatus('failed');
            updateTask({
              executionPhase: 'failed',
              error: event.message || 'Task failed',
              elapsed,
              taskRunning: updatedTaskRunning,
            });
          } else if (event.status === 'cancelled') {
            setStatus('cancelled');
            updateTask({
              executionPhase: 'cancelled',
              error: 'Task cancelled',
              elapsed,
              taskRunning: updatedTaskRunning,
            });
          }

          // Cleanup SSE connection
          if (sseClients[taskId]) {
            sseClients[taskId].disconnect();
            delete sseClients[taskId];
          }

          // Clear auto-confirm timer if exists
          if (autoConfirmTimers[taskId]) {
            clearTimeout(autoConfirmTimers[taskId]);
            delete autoConfirmTimers[taskId];
          }
        }
        break;

      // ===== Agent Thinking/Reasoning Events =====
      case 'agent_thinking':
      case 'llm_reasoning':
        {
          const thinking = event.thinking || event.reasoning || event.content || '';
          const step = event.step || store.tasks[taskId]?.loopIteration || 0;
          const agentName = event.agent_name || 'Agent';
          const timestamp = event.timestamp || new Date().toISOString();

          if (thinking) {
            // Add to thinkingLogs for AgentTab display
            const thinkingLog = {
              id: `thinking_${Date.now()}`,
              content: thinking,
              step,
              agentName,
              timestamp,
            };

            const currentTask = store.tasks[taskId];
            updateTask({
              thinkingLogs: [...(currentTask?.thinkingLogs || []), thinkingLog],
            });

            // Also add as message for backward compatibility
            addMessage('thinking', thinking, {
              step,
              agentName,
              timestamp,
            });
          }

          // Update agent's current thinking state
          if (event.agent_id || event.agent_name) {
            store.updateAgents(taskId, (prev) =>
              prev.map(a =>
                (a.id === event.agent_id || a.name === event.agent_name)
                  ? { ...a, currentThinking: thinking, currentStep: step }
                  : a
              )
            );
          }
        }
        break;

      // ===== Step Execution Events =====
      case 'step_started':
        {
          const stepIndex = event.step_index ?? event.step ?? 0;
          const stepName = event.step_name || `Step ${stepIndex}`;
          updateTask({
            loopIteration: stepIndex,
            executionPhase: 'executing',
            currentStepName: stepName,
            currentStepDescription: event.step_description,
          });
          addNotice('info', stepName, event.step_description || 'Step started');
        }
        break;

      case 'step_progress':
        {
          const progress = event.progress ?? 0;
          updateTask({
            progressValue: Math.round(progress * 100),
            currentStepMessage: event.message,
          });
        }
        break;

      case 'step_completed':
        {
          const stepName = event.step_name || `Step ${event.step_index}`;
          addNotice('success', `${stepName} completed`, event.result || '');
        }
        break;

      case 'step_failed':
        {
          const stepName = event.step_name || `Step ${event.step_index}`;
          addNotice('error', `${stepName} failed`, event.error || 'Unknown error');
          if (!event.recoverable) {
            setStatus('failed');
            updateTask({
              error: event.error,
              executionPhase: 'failed',
            });
          }
        }
        break;

      // ===== Browser Action Events =====
      // Note: browser_action events are supplementary - toolkit events are already
      // handled by activate_toolkit/deactivate_toolkit from @listen_toolkit decorator.
      // We only use browser_action for additional context, NOT for adding toolkit events.
      case 'browser_action':
        {
          // Do NOT add toolkit events here - they are already added by
          // activate_toolkit/deactivate_toolkit events from the @listen_toolkit decorator.
          // This prevents duplicate entries in the timeline.

          // Only update browser URL if provided (for BrowserTab display)
          if (event.page_url) {
            updateTask({ browserUrl: event.page_url });
          }
        }
        break;

      // ===== Notice/Notification Events =====
      case 'notice':
        {
          const level = event.level || 'info';
          const title = event.title || 'Notice';
          const message = event.message || '';
          addNotice(level, title, message);
        }
        break;

      // ===== Error Events =====
      case 'error':
        {
          const errorMsg = event.error || 'Unknown error';
          const recoverable = event.recoverable !== false;

          addNotice('error', 'Error', errorMsg);

          if (!recoverable) {
            setStatus('failed');
            updateTask({
              error: errorMsg,
              executionPhase: 'failed',
            });
          }
        }
        break;

      // ===== Context Warning Events =====
      case 'context_warning':
        {
          const usagePercent = event.usage_percent || 80;
          updateTask({
            isContextExceeded: usagePercent >= 95,
            contextUsagePercent: usagePercent,
          });
          addNotice('warning', 'Context Warning', event.message || `Context usage at ${usagePercent}%`);
        }
        break;

      case 'heartbeat':
        // Ignore heartbeats
        break;

      // ===== Browser Screenshot Events (for BrowserTab) =====
      case 'screenshot':
      case 'browser_screenshot':
        {
          const screenshot = event.screenshot || event.image || event.data;
          const url = event.url || event.page_url || '';

          if (screenshot) {
            updateTask({
              browserScreenshot: screenshot,
              browserUrl: url,
            });
          }
        }
        break;

      case 'browser_navigated':
      case 'webview_url':
        {
          const url = event.url || event.page_url || '';
          if (url) {
            updateTask({ browserUrl: url });
          }
        }
        break;

      default:
        console.log('[AgentStore] Unknown SSE event:', eventType, event);
    }
  },

  /**
   * Cancel/stop a task (Eigent-aligned: comprehensive cleanup)
   * Eigent's stopTask does: 1) abort SSE, 2) clear timers, 3) update status
   */
  cancelTask: async (taskId, showStatusCallback) => {
    const task = get().tasks[taskId];

    // 1. Cleanup SSE connection (Eigent pattern: try-catch with cleanup)
    try {
      if (sseClients[taskId]) {
        console.log(`[AgentStore] Stopping SSE connection for task ${taskId}`);
        sseClients[taskId].disconnect();
        delete sseClients[taskId];
      }
    } catch (error) {
      console.warn('[AgentStore] Error disconnecting SSE:', error);
      try {
        delete sseClients[taskId];
      } catch (cleanupError) {
        console.warn('[AgentStore] Error cleaning up SSE reference:', cleanupError);
      }
    }

    // 2. Clear auto-confirm timer (Eigent pattern)
    try {
      if (autoConfirmTimers[taskId]) {
        clearTimeout(autoConfirmTimers[taskId]);
        delete autoConfirmTimers[taskId];
      }
    } catch (error) {
      console.warn('[AgentStore] Error clearing auto-confirm timer:', error);
    }

    // 3. Update task status locally
    try {
      get().setTaskStatus(taskId, 'cancelled');
      get().updateTask(taskId, {
        executionPhase: 'cancelled',
        error: 'Task was cancelled by user',
      });
    } catch (error) {
      console.error('[AgentStore] Error updating task status:', error);
    }

    // 4. Call backend to cancel (optional, may fail if already stopped)
    if (task?.backendTaskId) {
      try {
        await api.callAppBackend(`/api/v1/quick-task/cancel/${task.backendTaskId}`, {
          method: 'POST'
        });
      } catch (error) {
        // Backend cancel may fail if task already stopped, that's ok
        console.warn('[AgentStore] Backend cancel failed (may be already stopped):', error);
      }
    }

    if (showStatusCallback) {
      showStatusCallback('Task cancelled', 'info');
    }

    return true;
  },

  /**
   * Send human response for a task
   */
  sendHumanResponse: async (taskId, response) => {
    const task = get().tasks[taskId];
    if (!task || !sseClients[taskId]) return false;

    try {
      await sseClients[taskId].sendHumanResponse(response);

      get().addMessage(taskId, 'user', response);
      get().updateTask(taskId, {
        humanQuestion: null,
        humanQuestionContext: null,
        humanInteractionOptions: [],
        humanInteractionType: 'question',
        humanInteractionTimeout: null,
      });

      return true;
    } catch (error) {
      console.error('[AgentStore] Failed to send human response:', error);
      return false;
    }
  },

  /**
   * Confirm task decomposition (Eigent pattern)
   * Called after user confirms or 30s auto-confirm
   */
  confirmDecomposition: async (taskId, subtasks) => {
    const task = get().tasks[taskId];
    if (!task) return false;

    // Don't confirm if task is already completed, failed, or cancelled
    const terminalStates = ['completed', 'finished', 'failed', 'cancelled'];
    if (terminalStates.includes(task.status)) {
      console.log(`[AgentStore] Ignoring confirmation for ${taskId}: task already ${task.status}`);
      return false;
    }

    // Don't confirm if decomposition is not showing (already confirmed or not in decomposition phase)
    if (!task.showDecomposition && !task.isTaskEdit) {
      console.log(`[AgentStore] Ignoring confirmation for ${taskId}: not in decomposition phase`);
      return false;
    }

    // Clear auto-confirm timer
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    }

    // Update local state
    get().updateTask(taskId, {
      confirmedSubtasks: subtasks.map(t => ({ ...t, status: 'pending' })),
      showDecomposition: false,
      isTaskEdit: false,
    });

    // Call backend to confirm subtasks
    const backendTaskId = task.backendTaskId;
    if (backendTaskId) {
      try {
        await api.callAppBackend(`/api/v1/quick-task/${backendTaskId}/confirm-subtasks`, {
          method: 'POST',
          body: JSON.stringify({ subtasks })
        });
        get().addNotice(taskId, 'info', 'Plan Confirmed', `Executing ${subtasks.length} subtasks`);
        return true;
      } catch (error) {
        console.error('[AgentStore] Failed to confirm subtasks:', error);
        return false;
      }
    }

    return true;
  },

  /**
   * Cancel task decomposition
   */
  cancelDecomposition: async (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return false;

    // Clear auto-confirm timer
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    }

    get().updateTask(taskId, {
      showDecomposition: false,
      subtasks: [],
      isTaskEdit: false,
    });

    // Call backend to cancel
    const backendTaskId = task.backendTaskId;
    if (backendTaskId) {
      try {
        await api.callAppBackend(`/api/v1/quick-task/${backendTaskId}/cancel-subtasks`, {
          method: 'POST'
        });
      } catch (error) {
        console.error('[AgentStore] Failed to cancel subtasks:', error);
      }
    }

    return true;
  },

  /**
   * Set task edit mode (Eigent: prevents auto-confirm while editing)
   */
  setTaskEdit: (taskId, isEditing) => {
    get().updateTask(taskId, { isTaskEdit: isEditing });
  },

  /**
   * Set take control mode (Eigent: user takes manual control)
   */
  setTakeControl: (taskId, isTakeControl) => {
    get().updateTask(taskId, { isTakeControl });
  },

  // ============ History & Task Restoration (Eigent Migration) ============

  /**
   * History tasks from backend (metadata only, not full state)
   */
  historyTasks: [],
  historyLoading: false,
  historyError: null,

  /**
   * Load history tasks from backend
   * Similar to Eigent's fetchHistoryTasks
   */
  loadHistoryTasks: async () => {
    set({ historyLoading: true, historyError: null });

    try {
      const response = await api.callAppBackend('/api/v1/quick-task/tasks', {
        method: 'GET',
      });

      set({
        historyTasks: response.tasks || [],
        historyLoading: false,
      });

      console.log('[AgentStore] Loaded history tasks:', response.tasks?.length || 0);
      return response.tasks || [];
    } catch (error) {
      console.error('[AgentStore] Failed to load history tasks:', error);
      set({
        historyError: error.message,
        historyLoading: false,
      });
      throw error;
    }
  },

  /**
   * Restore a task from backend
   * Similar to Eigent's replay function
   *
   * @param {string} taskId - Backend task ID to restore
   * @param {string} taskDescription - Task description (for display)
   */
  restoreTask: async (taskId, taskDescription) => {
    const store = get();

    // Check if task already in memory
    if (store.tasks[taskId]) {
      console.log('[AgentStore] Task already in memory, activating:', taskId);
      set({ activeTaskId: taskId });
      return store.tasks[taskId];
    }

    console.log('[AgentStore] Restoring task from backend:', taskId);

    // Fetch task detail from backend
    const detail = await api.callAppBackend(`/api/v1/quick-task/${taskId}/detail`, {
      method: 'GET',
    });

    // Create task with restored data
    const taskState = {
      ...createInitialTaskState(detail.task, 'replay'),

      // IMPORTANT: Set backendTaskId for proper event routing and display
      backendTaskId: taskId,  // taskId here is the backend task ID

      // Override with backend data
      taskDescription: detail.task,
      status: detail.status,
      progressValue: detail.progress * 100,
      executionPhase: detail.status === 'running' ? 'executing' : detail.status,

      // Timestamps
      createdAt: detail.created_at,
      startedAt: detail.started_at,
      completedAt: detail.completed_at,

      // Execution state
      loopIteration: detail.loop_iterations,
      currentStep: detail.current_step,

      // Results
      result: detail.result,
      error: detail.error,
      notesContent: detail.notes_content,

      // Convert backend messages to frontend format
      // Use 'role' field to match addMessage() format
      messages: detail.messages.map((msg, index) => ({
        id: `msg_${index}`,
        role: msg.role,
        content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
        timestamp: msg.timestamp,
      })),

      // Convert backend toolkit events
      toolkitEvents: detail.toolkit_events.map((event, index) => ({
        id: `toolkit_${index}`,
        toolkit_name: event.toolkit_name,
        method_name: event.method_name,
        status: event.status,
        input_preview: event.input_preview,
        output_preview: event.output_preview,
        timestamp: event.timestamp,
        duration_ms: event.duration_ms,
      })),

      // Convert backend thinking logs
      thinkingLogs: detail.thinking_logs.map((log, index) => ({
        id: `thinking_${index}`,
        content: log.content,
        step: log.step,
        agentName: log.agent_name,
        timestamp: log.timestamp,
      })),
    };

    // Add task to store
    set((state) => ({
      activeTaskId: taskId,
      tasks: {
        ...state.tasks,
        [taskId]: taskState,
      },
    }));

    console.log('[AgentStore] Task restored:', taskId, 'status:', detail.status);

    // If task is still running, reconnect SSE
    if (detail.status === 'running') {
      console.log('[AgentStore] Task is running, reconnecting SSE...');
      store.connectSSE(taskId, taskId);
    }

    return taskState;
  },

  /**
   * Handle task selection from history list
   * Similar to Eigent's handleSetActive
   */
  selectHistoryTask: async (taskId, taskDescription) => {
    const store = get();

    // If task in memory, just activate it
    if (store.tasks[taskId]) {
      set({ activeTaskId: taskId });
      return;
    }

    // Otherwise restore from backend
    await store.restoreTask(taskId, taskDescription);
  },

  // ============ Selectors (for convenience) ============

  /**
   * Get current active task
   */
  getActiveTask: () => {
    const state = get();
    return state.activeTaskId ? state.tasks[state.activeTaskId] : null;
  },

  /**
   * Get all tasks as array (sorted by creation time, newest first)
   */
  getTaskList: () => {
    const state = get();
    return Object.entries(state.tasks)
      .map(([id, task]) => ({ id, ...task }))
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  },

  /**
   * Get running tasks count
   */
  getRunningTasksCount: () => {
    const state = get();
    return Object.values(state.tasks).filter(t => t.status === 'running').length;
  },
}));

export default useAgentStore;
