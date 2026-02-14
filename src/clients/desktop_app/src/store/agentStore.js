/**
 * Agent Store - Task management using Zustand
 *
 * Each task has its own state including messages, agents, progress, etc.
 */

import { create } from 'zustand';
import { api } from '../utils/api';
import { SSEClient } from '../utils/sseClient';
import useBrowserTabStore from './browserTabStore';

// Generate unique task ID (8 char)
const generateTaskId = () => {
  return Math.random().toString(36).substring(2, 10);
};

// Reset all "live" browser tabs to "idle" when a task ends
function _resetLiveTabs() {
  const { views, setViewMode } = useBrowserTabStore.getState();
  for (const [id, view] of Object.entries(views)) {
    if (view.mode === 'live') {
      setViewMode(id, 'idle');
    }
  }
}

// SSE clients per task
const sseClients = {};

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
  browserViewId: null,      // Electron WebContentsView ID ("0"-"7") for embedded browser
  isTakeControl: false,     // Whether user has taken control (agent paused)

  // Workspace
  terminalOutput: [],
  selectedFile: null,
  fileList: [],  // Eigent: generated files list

  // Parallel executor tracking (Persistent Orchestrator)
  executors: {},  // { "exec_1": { id, label, status, subtasks, startedAt } }

  // Human interaction
  humanQuestion: null,
  humanQuestionContext: null,
  humanInteractionType: 'question',
  humanInteractionOptions: [],
  humanInteractionTimeout: null,
  humanMessages: [],
  hasWaitConfirm: false,  // Eigent: waiting for confirmation flag
  lastSimpleAnswer: null,  // Eigent: last simple answer content
  lastSimpleQuestion: null,  // Eigent: last simple question content
  isComplexTask: false,  // Eigent: whether task was classified as complex

  // Token usage
  tokenUsage: {
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    estimatedCost: null,
  },
  currentModel: '',

  // Subtask decomposition (display only, no confirmation needed)
  subtasks: [],
  streamingDecomposeText: '',  // Eigent: streaming task decomposition text

  // Decomposition progress (Phase 5 enhancement)
  decompositionProgress: 0,        // 0-100 percentage
  decompositionMessage: '',        // Current stage description (e.g., "Analyzing task complexity...")
  decompositionStatus: 'pending',  // pending | decomposing | completed

  // Eigent flags
  isPending: false,
  isContextExceeded: false,

  // Timing (Eigent: for statistics)
  taskTime: null,  // When task started
  elapsed: 0,      // Task duration in ms

  // Workforce state (CAMEL-based multi-agent coordination)
  workforce: {
    workers: [],          // Array of worker objects with status
    pendingTasks: 0,      // Count of pending tasks
    runningTasks: 0,      // Count of currently running tasks
    completedTasks: 0,    // Count of completed tasks
    failedTasks: 0,       // Count of failed tasks
    totalTasks: 0,        // Total task count
    isActive: false,      // Whether workforce is currently active
  },

  // Subtask to worker assignment mapping
  // Format: { subtask_id: { workerId, workerName, status } }
  subtaskAssignments: {},
});

/**
 * Agent Store
 *
 * Manages multiple tasks with their individual states.
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
    let newMessageId = null;

    set((state) => {
      if (!state.tasks[taskId]) return state;

      const existingMessages = state.tasks[taskId].messages;

      // Deduplication: Skip if identical message exists within last 3 seconds
      const now = Date.now();
      const isDuplicate = existingMessages.some(m => {
        if (m.role !== role || m.content !== content) return false;
        const msgTime = new Date(m.timestamp).getTime();
        return (now - msgTime) < 3000;
      });

      if (isDuplicate) {
        console.warn('[AgentStore] Skipping duplicate message:', { role, contentPreview: content.substring(0, 50) });
        return state;
      }

      newMessageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

      const newMessage = {
        id: newMessageId,
        role,
        content,
        timestamp: new Date().toISOString(),
        ...extra,
      };

      // DEBUG: Log the created message
      console.log('[AgentStore] Created message:', {
        id: newMessage.id,
        hasAttachments: !!newMessage.attachments,
        attachmentsCount: newMessage.attachments?.length || 0,
      });

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

    // Async: Persist message to session (simple API)
    if (newMessageId && role) {
      // Map frontend role to backend role
      const backendRole = role === 'agent' ? 'assistant' : role;

      // Only persist user, assistant, system messages
      if (['user', 'assistant', 'system'].includes(backendRole)) {
        api.appendSessionMessage(backendRole, content || '', {
          messageId: newMessageId,
          attachments: extra.attachments || [],
          metadata: {
            taskId,
            reportType: extra.reportType,
            agentType: extra.agentType,
            executorId: extra.executorId,
            taskLabel: extra.taskLabel,
          },
        }).catch((error) => {
          console.warn(`[AgentStore] Failed to persist message:`, error.message);
        });
      }
    }
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

    const content = task.taskDescription;
    if (!content || !content.trim()) {
      console.error('[AgentStore] No task description');
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
      get().addMessage(taskId, 'user', content);

      // Submit to backend
      const response = await api.callAppBackend('/api/v1/quick-task/execute', {
        method: 'POST',
        body: JSON.stringify({
          task: content.trim()
        })
      });

      // Update with backend task ID (may differ from our local ID)
      get().updateTask(taskId, {
        backendTaskId: response.task_id,
        isPending: false,
      });

      // Connect SSE
      get().connectSSE(taskId, response.task_id);

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

      // ===== Eigent Multi-turn Conversation Events =====

      // wait_confirm: Simple question answered directly (no Workforce)
      // Display the answer and wait for next user input
      case 'wait_confirm':
        {
          const content = event.content || '';
          const question = event.question || '';
          // DS-11: File attachments from task execution
          const attachments = event.attachments || [];

          // Add the simple answer as an assistant message with attachments
          store.addMessage(taskId, 'assistant', content, {
            type: 'simple_answer',
            attachments: attachments,
            executorId: event.executor_id,
            taskLabel: event.task_label,
          });

          // Mark task as having a wait_confirm response
          // Eigent pattern: Set status to 'waiting' to enable input
          setStatus('waiting');
          updateTask({
            hasWaitConfirm: true,
            lastSimpleAnswer: content,
            lastSimpleQuestion: question,
          });

        }
        break;

      // confirmed: Task classified as complex, starting decomposition
      // Frontend should prepare for task decomposition events
      case 'confirmed':
        {
          const question = event.question || '';

          // Update execution phase to indicate decomposition starting
          updateTask({
            executionPhase: 'decomposing',
            isComplexTask: true,
          });

          addNotice('info', 'Task Confirmed', 'Complex task detected, starting decomposition...');
          console.log('[AgentStore] confirmed: Complex task, starting decomposition', { question: question.substring(0, 50) });
        }
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

      // Phase 5: decompose_progress event for decomposition progress tracking
      case 'decompose_progress':
        {
          const { progress, message, sub_tasks, is_final } = event.data || event;

          const progressPercent = Math.round((progress || 0) * 100);

          updateTask({
            decompositionProgress: progressPercent,
            decompositionMessage: message || '',
            decompositionStatus: is_final ? 'completed' : 'decomposing',
          });

          // If final and has subtasks, also update taskInfo
          if (is_final && sub_tasks && Array.isArray(sub_tasks)) {
            updateTask({
              taskInfo: sub_tasks,
            });
          }

          console.log(`[SSE] decompose_progress: ${progressPercent}% - ${message || ''}`);
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
          // DS-4: Added ABANDONED, ASSIGNED, WAITING state handling
          const mapState = (s) => {
            if (!s) return 'pending';
            const stateUpper = s.toUpperCase();
            if (stateUpper === 'DONE') return 'completed';
            if (stateUpper === 'FAILED') return 'failed';
            if (stateUpper === 'RUNNING') return 'running';
            if (stateUpper === 'DELETED') return 'deleted';
            if (stateUpper === 'ABANDONED') return 'abandoned';
            if (stateUpper === 'ASSIGNED') return 'assigned';
            if (stateUpper === 'WAITING') return 'waiting';
            return 'pending'; // OPEN -> pending
          };

          // Normalize subtasks with mapped status and agent_type
          const normalizedSubtasks = newSubtasks.map(t => ({
            ...t,
            status: mapState(t.state || t.status),
            agent_type: t.agent_type || null,  // Preserve agent_type from backend
          }));

          // Store subtasks under executor if executor_id present
          const executorId = event.executor_id;
          if (executorId) {
            const currentTask2 = store.tasks[taskId];
            const executors = { ...currentTask2?.executors };
            if (executors[executorId]) {
              executors[executorId] = {
                ...executors[executorId],
                subtasks: normalizedSubtasks,
              };
            }
            updateTask({ executors });
          }

          // Update task with decomposition data (display only, no confirmation needed)
          // When executor_id is present, append subtasks to support parallel executors
          const currentTask3 = store.tasks[taskId];
          const prevSubtasks = executorId ? (currentTask3?.subtasks || []) : [];
          const prevTaskRunning = executorId ? (currentTask3?.taskRunning || []) : [];
          updateTask({
            subtasks: [...prevSubtasks, ...normalizedSubtasks],
            taskInfo: [...prevSubtasks, ...normalizedSubtasks],
            taskRunning: [...prevTaskRunning, ...normalizedSubtasks.map(t => ({ ...t }))],
            summaryTask: summaryTask,
            streamingDecomposeText: '',  // Clear streaming text on completion
          });

          addNotice('info', 'Task Decomposed', `${newSubtasks.length} subtasks planned`);
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
          // DS-4: Added ABANDONED, ASSIGNED, WAITING state handling
          const mapState = (s) => {
            if (!s) return 'pending';
            const stateUpper = s.toUpperCase();
            if (stateUpper === 'DONE') return 'completed';
            if (stateUpper === 'FAILED') return 'failed';
            if (stateUpper === 'RUNNING') return 'running';
            if (stateUpper === 'DELETED') return 'deleted';
            if (stateUpper === 'ABANDONED') return 'abandoned';
            if (stateUpper === 'ASSIGNED') return 'assigned';
            if (stateUpper === 'WAITING') return 'waiting';
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

          // Update executor-specific subtask state
          const execId = (event.data || event).executor_id || event.executor_id;
          if (execId && currentTask.executors?.[execId]) {
            const executors = { ...currentTask.executors };
            const execSubtasks = (executors[execId].subtasks || []).map(t => {
              if (t.id === effectiveSubTaskId) {
                return { ...t, status: mapState(state), state, result: subTaskResult || t.result };
              }
              return t;
            });
            executors[execId] = { ...executors[execId], subtasks: execSubtasks };
            updateTask({ executors });
          }

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

      // TaskPlanningToolkit: task_replanned event (plan adjustment during execution)
      case 'task_replanned':
        {
          const allSubtasks = event.subtasks || event.data?.subtasks || [];
          const reason = event.reason || event.data?.reason || '';
          const executorId = event.executor_id || event.data?.executor_id;

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Map states to UI statuses
          const mapState = (s) => {
            if (!s) return 'pending';
            const stateUpper = s.toUpperCase();
            if (stateUpper === 'DONE') return 'completed';
            if (stateUpper === 'FAILED') return 'failed';
            if (stateUpper === 'RUNNING') return 'running';
            return 'pending';
          };

          const normalizedSubtasks = allSubtasks.map(t => ({
            ...t,
            status: mapState(t.state || t.status),
            executor_id: t.executor_id || executorId,
          }));

          if (executorId) {
            // Replace only this executor's subtasks, keep others
            const otherSubtasks = (currentTask.subtasks || []).filter(
              t => t.executor_id !== executorId
            );
            const merged = [...otherSubtasks, ...normalizedSubtasks];

            // Update executor-specific subtasks
            const executors = { ...currentTask.executors };
            if (executors[executorId]) {
              executors[executorId] = {
                ...executors[executorId],
                subtasks: normalizedSubtasks,
              };
            }

            updateTask({
              subtasks: merged,
              taskInfo: merged,
              taskRunning: merged.map(t => ({ ...t })),
              executors,
            });
          } else {
            // Legacy: replace all subtasks
            updateTask({
              subtasks: normalizedSubtasks,
              taskInfo: normalizedSubtasks,
              taskRunning: normalizedSubtasks.map(t => ({ ...t })),
            });
          }

          addNotice('info', 'Task Re-planned', `${allSubtasks.length} subtasks${reason ? `: ${reason}` : ''}`);
        }
        break;

      // Eigent: assign_task event for task assignment to agents (Phase 5: two-phase state)
      case 'assign_task':
        {
          // Support both new format (assignee_id, subtask_id) and old format (agent_id, task_id)
          const {
            assignee_id,
            subtask_id,
            content,
            state: taskState,  // "waiting" | "running"
            failure_count = 0,
            worker_name,      // New: human-readable worker name
            agent_type,       // New: worker type (browser/document/code)
            // Backward compatible fields
            agent_id,
            task_id: assignedTaskId,
          } = event.data || event;

          const actualAgentId = assignee_id || agent_id;
          const actualTaskId = subtask_id || assignedTaskId;

          if (!actualAgentId || !actualTaskId) break;

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          let updatedTaskAssigning = [...(currentTask.taskAssigning || [])];
          let updatedTaskRunning = [...(currentTask.taskRunning || [])];

          const agentIndex = updatedTaskAssigning.findIndex(a => a.agent_id === actualAgentId);

          // Find the task in taskRunning for content fallback
          const taskInRunning = updatedTaskRunning.find(t => t.id === actualTaskId);
          const taskContent = content || taskInRunning?.content || '';

          // Update taskRunning with worker_name and agent_type
          updatedTaskRunning = updatedTaskRunning.map(t => {
            if (t.id === actualTaskId) {
              return {
                ...t,
                status: taskState === 'waiting' ? 'waiting' : 'running',
                worker_name: worker_name || t.worker_name,
                agent_type: agent_type || t.agent_type,
                assignee_id: actualAgentId,
                failure_count,
              };
            }
            return t;
          });

          // Phase 1: waiting - Task assigned, waiting in queue
          if (taskState === 'waiting') {
            if (agentIndex !== -1) {
              const existingTaskIndex = updatedTaskAssigning[agentIndex].tasks?.findIndex(
                t => t.id === actualTaskId
              );
              if (existingTaskIndex === -1 || existingTaskIndex === undefined) {
                // Add task with waiting status
                updatedTaskAssigning[agentIndex] = {
                  ...updatedTaskAssigning[agentIndex],
                  tasks: [...(updatedTaskAssigning[agentIndex].tasks || []), {
                    id: actualTaskId,
                    content: taskContent,
                    status: 'waiting',
                    failure_count,
                    worker_name,
                    agent_type,
                  }],
                };
              }
            }
          }
          // Phase 2: running - Task actively being executed (or default for backward compatibility)
          else if (taskState === 'running' || !taskState) {
            if (agentIndex !== -1) {
              const existingTaskIndex = updatedTaskAssigning[agentIndex].tasks?.findIndex(
                t => t.id === actualTaskId
              );
              if (existingTaskIndex !== -1 && existingTaskIndex !== undefined) {
                // Update existing task status to running (immutable update)
                const updatedTasks = [...updatedTaskAssigning[agentIndex].tasks];
                updatedTasks[existingTaskIndex] = {
                  ...updatedTasks[existingTaskIndex],
                  status: 'running',
                  failure_count,
                  worker_name,
                  agent_type,
                };
                updatedTaskAssigning[agentIndex] = {
                  ...updatedTaskAssigning[agentIndex],
                  tasks: updatedTasks,
                };
              } else {
                // Add new task with running status
                updatedTaskAssigning[agentIndex] = {
                  ...updatedTaskAssigning[agentIndex],
                  tasks: [...(updatedTaskAssigning[agentIndex].tasks || []), {
                    id: actualTaskId,
                    content: taskContent,
                    status: 'running',
                    failure_count,
                    worker_name,
                    agent_type,
                  }],
                };
              }
            }
          }

          updateTask({
            taskRunning: updatedTaskRunning,
            taskAssigning: updatedTaskAssigning,
          });
        }
        break;

      // NOTE: task_completed event removed - Eigent multi-turn pattern uses wait_confirm instead
      // The task stays in conversation loop until user explicitly ends or navigates away

      case 'task_failed':
        // NOTE: Don't disconnect SSE or set terminal status - Eigent multi-turn pattern
        // allows retry after failure via wait_confirm event that follows
        updateTask({
          error: event.error,
          executionPhase: 'failed',
          // Clear decomposition state
          taskInfo: [],
          streamingDecomposeText: '',
          // Reset decomposition progress (Phase 5)
          decompositionProgress: 0,
          decompositionMessage: '',
          decompositionStatus: 'pending',
        });
        addNotice('error', 'Task Failed', event.error);
        // SSE stays connected - wait_confirm will follow for multi-turn retry
        break;

      // NOTE: task_cancelled event removed - cancellation is now handled via 'end' event
      // with status='cancelled', which properly disconnects SSE

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
            // Task execution finished — set 'completed' and disconnect SSE
            // Follow-up messages will go through continue_task() flow
            setStatus('completed');
            updateTask({
              executionPhase: 'completed',
              result: event.result,
              elapsed,
              taskRunning: updatedTaskRunning,
              progressValue: 100,
              // Clear decomposition state for next round
              taskInfo: [],
              streamingDecomposeText: '',
              decompositionProgress: 0,
              decompositionMessage: '',
              // Clear browser state — App.jsx will auto-navigate back
              browserViewId: null,
              isTakeControl: false,
            });
            // Reset all live tabs to idle
            _resetLiveTabs();
            // Disconnect SSE — backend task has ended
            if (sseClients[taskId]) {
              sseClients[taskId].disconnect();
              delete sseClients[taskId];
            }
          } else if (event.status === 'failed') {
            // Task failed — set 'completed' so input stays enabled for follow-up
            setStatus('completed');
            updateTask({
              executionPhase: 'failed',
              error: event.message || 'Task failed',
              elapsed,
              taskRunning: updatedTaskRunning,
              // Clear decomposition state
              taskInfo: [],
              // Clear browser state — App.jsx will auto-navigate back
              browserViewId: null,
              isTakeControl: false,
            });
            _resetLiveTabs();
            // Disconnect SSE — backend task has ended
            if (sseClients[taskId]) {
              sseClients[taskId].disconnect();
              delete sseClients[taskId];
            }
          } else if (event.status === 'cancelled') {
            // User explicitly cancelled - end the session
            setStatus('cancelled');
            updateTask({
              executionPhase: 'cancelled',
              error: 'Task cancelled',
              elapsed,
              taskRunning: updatedTaskRunning,
              // Clear decomposition state
              taskInfo: [],
              // Clear browser state — App.jsx will auto-navigate back
              browserViewId: null,
              isTakeControl: false,
            });
            _resetLiveTabs();
            addNotice('warning', 'Task Cancelled', 'Task was cancelled by user');
            // Disconnect SSE on user cancel
            if (sseClients[taskId]) {
              sseClients[taskId].disconnect();
              delete sseClients[taskId];
            }
          }

          // Clear auto-confirm timer if exists
          if (autoConfirmTimers[taskId]) {
            clearTimeout(autoConfirmTimers[taskId]);
            delete autoConfirmTimers[taskId];
          }

          console.log('[AgentStore] end event: Task ended, SSE disconnected');
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

            // Note: Don't add as message here - wait_confirm will handle the final response
            // This avoids duplicate messages in the chat view
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
      // We use browser_action to enrich existing toolkit events with browser-specific params.
      case 'browser_action':
        {
          // Update the latest Browser toolkit event with browser-specific params
          // This adds action_type, target, page_url etc. for display in AgentTab
          const currentTask = store.tasks[taskId];
          if (currentTask) {
            const toolkitEvents = [...(currentTask.toolkitEvents || [])];
            // Find the last running Browser toolkit event
            for (let i = toolkitEvents.length - 1; i >= 0; i--) {
              const evt = toolkitEvents[i];
              if (evt.toolkit_name?.toLowerCase().includes('browser') && evt.status === 'running') {
                // Enrich with browser action params
                toolkitEvents[i] = {
                  ...evt,
                  action_type: event.action_type,
                  target: event.target,
                  value: event.value,
                  page_url: event.page_url,
                  page_title: event.page_title,
                };
                updateTask({ toolkitEvents });
                break;
              }
            }
          }

          // Also update browser URL and viewId for live browser page
          const browserUpdates = {};
          if (event.page_url) browserUpdates.browserUrl = event.page_url;
          if (event.webview_id) {
            browserUpdates.browserViewId = event.webview_id;
            // Mark this tab as live in browserTabStore — supports parallel subtasks
            // each operating on a different viewId
            useBrowserTabStore.getState().setViewMode(event.webview_id, 'live');
          }
          if (Object.keys(browserUpdates).length > 0) {
            updateTask(browserUpdates);
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
          const webviewId = event.webview_id || null;

          if (screenshot) {
            const updates = {
              browserScreenshot: screenshot,
              browserUrl: url,
            };
            // Set browserViewId — App.jsx auto-navigates to live browser page
            if (webviewId) {
              updates.browserViewId = webviewId;
              useBrowserTabStore.getState().setViewMode(webviewId, 'live');
            }
            updateTask(updates);
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

      // ===== Workforce Events (CAMEL-based multi-agent coordination) =====
      case 'workforce_started':
        {
          const executorId = event.executor_id;
          const taskLabel = event.task_label;
          if (executorId) {
            const currentTask = store.tasks[taskId];
            const executors = { ...currentTask?.executors };
            executors[executorId] = {
              id: executorId,
              label: taskLabel,
              status: 'running',
              subtasks: [],
              startedAt: new Date().toISOString(),
            };
            updateTask({ executors });
          }
          updateTask({
            workforce: {
              ...store.tasks[taskId]?.workforce,
              isActive: true,
              pendingTasks: event.total_tasks || 0,
              totalTasks: event.total_tasks || 0,
              runningTasks: 0,
              completedTasks: 0,
              failedTasks: 0,
            },
          });
          addNotice('info', 'Workforce Started', 'Multi-agent coordination active');
        }
        break;

      case 'workforce_completed':
        {
          const executorId = event.executor_id;
          if (executorId) {
            const currentTask = store.tasks[taskId];
            const executors = { ...currentTask?.executors };
            if (executors[executorId]) {
              executors[executorId] = { ...executors[executorId], status: 'completed' };
            }
            updateTask({ executors });

            // Only deactivate workforce if no other executors are still running
            const hasRunningExecutors = Object.values(executors).some(
              e => e.status === 'running'
            );
            if (!hasRunningExecutors) {
              const currentWorkforce = store.tasks[taskId]?.workforce || {};
              updateTask({
                workforce: { ...currentWorkforce, isActive: false },
              });
            }
          } else {
            // Legacy: no executor_id, deactivate workforce unconditionally
            const currentWorkforce = store.tasks[taskId]?.workforce || {};
            updateTask({
              workforce: { ...currentWorkforce, isActive: false },
            });
          }
          addNotice('success', 'Workforce Completed', `Executor completed`);
        }
        break;

      case 'workforce_stopped':
        {
          const executorId = event.executor_id;
          if (executorId) {
            const currentTask = store.tasks[taskId];
            const executors = { ...currentTask?.executors };
            if (executors[executorId]) {
              executors[executorId] = { ...executors[executorId], status: 'stopped' };
            }
            updateTask({ executors });

            // Only deactivate workforce if no other executors are still running
            const hasRunningExecutors = Object.values(executors).some(
              e => e.status === 'running'
            );
            if (!hasRunningExecutors) {
              updateTask({
                workforce: { ...store.tasks[taskId]?.workforce, isActive: false },
              });
            }
          } else {
            updateTask({
              workforce: { ...store.tasks[taskId]?.workforce, isActive: false },
            });
          }
          addNotice('warning', 'Workforce Stopped', event.reason || event.message || 'Coordination stopped');
        }
        break;

      case 'worker_assigned':
        {
          const { worker_id, worker_name, subtask_id, subtask_content } = event;
          if (!subtask_id) break;

          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Update subtaskAssignments
          const updatedAssignments = {
            ...currentTask.subtaskAssignments,
            [subtask_id]: {
              workerId: worker_id,
              workerName: worker_name,
              status: 'assigned',
            },
          };

          // Update workforce workers list
          const existingWorkers = currentTask.workforce?.workers || [];
          let updatedWorkers = [...existingWorkers];
          const workerIndex = updatedWorkers.findIndex(w => w.id === worker_id);
          if (workerIndex === -1) {
            updatedWorkers.push({
              id: worker_id,
              name: worker_name,
              status: 'idle',
              currentTaskId: null,
            });
          }

          updateTask({
            subtaskAssignments: updatedAssignments,
            workforce: {
              ...currentTask.workforce,
              workers: updatedWorkers,
            },
          });
        }
        break;

      case 'worker_started':
        {
          const { worker_id, worker_name, subtask_id } = event;
          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Update worker status
          const workers = (currentTask.workforce?.workers || []).map(w =>
            w.id === worker_id
              ? { ...w, status: 'running', currentTaskId: subtask_id }
              : w
          );

          // Update subtask assignment status
          const assignments = { ...currentTask.subtaskAssignments };
          if (subtask_id && assignments[subtask_id]) {
            assignments[subtask_id] = {
              ...assignments[subtask_id],
              status: 'running',
            };
          }

          // Update workforce counts
          const workforce = currentTask.workforce || {};
          updateTask({
            workforce: {
              ...workforce,
              workers,
              runningTasks: (workforce.runningTasks || 0) + 1,
              pendingTasks: Math.max(0, (workforce.pendingTasks || 0) - 1),
            },
            subtaskAssignments: assignments,
          });

          addNotice('info', 'Worker Started', `${worker_name} started task`);
        }
        break;

      case 'worker_completed':
        {
          const { worker_id, worker_name, subtask_id, result } = event;
          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Update worker status
          const workers = (currentTask.workforce?.workers || []).map(w =>
            w.id === worker_id
              ? { ...w, status: 'idle', currentTaskId: null }
              : w
          );

          // Update subtask assignment status
          const assignments = { ...currentTask.subtaskAssignments };
          if (subtask_id && assignments[subtask_id]) {
            assignments[subtask_id] = {
              ...assignments[subtask_id],
              status: 'completed',
              result: result,
            };
          }

          // Update workforce counts
          const workforce = currentTask.workforce || {};
          updateTask({
            workforce: {
              ...workforce,
              workers,
              runningTasks: Math.max(0, (workforce.runningTasks || 0) - 1),
              completedTasks: (workforce.completedTasks || 0) + 1,
            },
            subtaskAssignments: assignments,
          });

          addNotice('success', 'Worker Completed', `${worker_name} completed task`);
        }
        break;

      case 'worker_failed':
        {
          const { worker_id, worker_name, subtask_id, error, failure_count } = event;
          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Update worker status
          const workers = (currentTask.workforce?.workers || []).map(w =>
            w.id === worker_id
              ? { ...w, status: 'idle', currentTaskId: null }
              : w
          );

          // Update subtask assignment status
          const assignments = { ...currentTask.subtaskAssignments };
          if (subtask_id && assignments[subtask_id]) {
            assignments[subtask_id] = {
              ...assignments[subtask_id],
              status: 'failed',
              error: error,
              failureCount: failure_count,
            };
          }

          // Update workforce counts
          const workforce = currentTask.workforce || {};
          updateTask({
            workforce: {
              ...workforce,
              workers,
              runningTasks: Math.max(0, (workforce.runningTasks || 0) - 1),
              failedTasks: (workforce.failedTasks || 0) + 1,
            },
            subtaskAssignments: assignments,
          });

          addNotice('error', 'Worker Failed', `${worker_name} failed: ${error || 'Unknown error'}`);
        }
        break;

      case 'dynamic_tasks_added':
        {
          const { new_tasks, total_tasks } = event;
          const currentTask = store.tasks[taskId];
          if (!currentTask) break;

          // Add new tasks to subtasks list
          const existingSubtasks = currentTask.subtasks || [];
          const newSubtasksList = new_tasks || [];
          const updatedSubtasks = [...existingSubtasks, ...newSubtasksList.map(t => ({
            id: t.id,
            content: t.content,
            status: 'pending',
          }))];

          // Update taskRunning as well
          const existingTaskRunning = currentTask.taskRunning || [];
          const updatedTaskRunning = [...existingTaskRunning, ...newSubtasksList.map(t => ({
            id: t.id,
            content: t.content,
            status: 'pending',
          }))];

          // Update workforce counts
          const workforce = currentTask.workforce || {};
          updateTask({
            subtasks: updatedSubtasks,
            taskRunning: updatedTaskRunning,
            workforce: {
              ...workforce,
              totalTasks: total_tasks || updatedSubtasks.length,
              pendingTasks: (workforce.pendingTasks || 0) + newSubtasksList.length,
            },
          });

          addNotice('info', 'Tasks Added', `${newSubtasksList.length} new tasks discovered`);
        }
        break;

      // ===== Agent Report Events (for HomePage chat-style display) =====
      case 'agent_report':
        {
          const { message, report_type, executor_id, task_label, agent_type, subtask_label } = event;
          if (message) {
            // Add agent report as a message for display in chat
            // Prefer subtask_label (specific subtask) over task_label (executor-level)
            addMessage('agent', message, {
              reportType: report_type || 'info',
              agentType: agent_type,
              executorId: executor_id,
              taskLabel: subtask_label || task_label,
            });
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
   * Pause the agent and take control of the browser.
   */
  takeControl: async (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return false;

    const backendTaskId = task.backendTaskId;
    if (!backendTaskId) return false;

    try {
      await api.callAppBackend(`/api/v1/quick-task/pause/${backendTaskId}`, {
        method: 'POST',
      });
      get().updateTask(taskId, { isTakeControl: true });
      console.log('[AgentStore] Agent paused, user took control');
      return true;
    } catch (error) {
      console.error('[AgentStore] Failed to pause agent:', error);
      return false;
    }
  },

  /**
   * Resume the agent and give back browser control.
   */
  giveBackControl: async (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return false;

    const backendTaskId = task.backendTaskId;
    if (!backendTaskId) return false;

    try {
      await api.callAppBackend(`/api/v1/quick-task/resume/${backendTaskId}`, {
        method: 'POST',
      });
      get().updateTask(taskId, { isTakeControl: false });
      console.log('[AgentStore] Agent resumed, control given back');
      return true;
    } catch (error) {
      console.error('[AgentStore] Failed to resume agent:', error);
      return false;
    }
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
   * Send user message during task execution (Eigent multi-turn conversation pattern)
   *
   * This method sends a new message while a task is running, allowing:
   * - Simple questions to be answered directly without interrupting the task
   * - Complex tasks to be decomposed and added to the execution queue
   *
   * @param {string} taskId - Task identifier
   * @param {string} message - User's message
   * @returns {Promise<{success: boolean, type?: string, answer?: string, newTasks?: number}>}
   */
  sendUserMessage: async (taskId, message) => {
    const task = get().tasks[taskId];
    if (!task) return { success: false, error: 'Task not found' };

    const backendTaskId = task.backendTaskId;
    if (!backendTaskId) return { success: false, error: 'No backend task ID' };

    // Reconnect SSE if disconnected — but NOT for completed tasks
    // Completed tasks will get a new SSE connection after continue_task returns
    if (!sseClients[taskId] && task.status !== 'completed') {
      console.log('[AgentStore] SSE disconnected, reconnecting for multi-turn...');
      get().connectSSE(taskId, backendTaskId);
    }

    // Add user message to conversation immediately
    get().addMessage(taskId, 'user', message);

    // Update status to 'running' before sending message
    // This prevents UI from staying in input mode while waiting for response
    // For 'completed' tasks, continue_task will handle the status via SSE
    if (task.status === 'waiting' || task.status === 'completed') {
      get().setTaskStatus(taskId, 'running');
      get().updateTask(taskId, {
        hasWaitConfirm: false,  // Reset the flag until next wait_confirm
      });
    }

    // Note: If status is 'running', backend will queue the message
    // and process it when the current operation completes

    try {
      const response = await api.callAppBackend(`/api/v1/quick-task/message/${backendTaskId}`, {
        method: 'POST',
        body: JSON.stringify({
          type: 'user_message',
          message: message,
        }),
      });

      if (response.success) {
        console.log('[AgentStore] User message handled:', response);

        // Handle response based on type
        if (response.type === 'queued') {
          // Eigent pattern: Message queued for multi-turn loop
          // The response will come via SSE events (wait_confirm or confirmed)
          console.log('[AgentStore] User message queued for multi-turn loop');
        } else if (response.type === 'simple_answer' && response.answer) {
          // Simple answer - add as assistant message
          get().addMessage(taskId, 'assistant', response.answer, {
            type: 'simple_answer',
          });
        } else if (response.type === 'tasks_added' && response.new_tasks > 0) {
          get().addNotice(taskId, 'info', 'Tasks Added', `${response.new_tasks} new subtask(s) added`);
        } else if (response.type === 'continued' && response.new_task_id) {
          // Task was continued with a new backend task
          // Update backendTaskId and reconnect SSE to new task
          console.log('[AgentStore] Task continued with new task:', response.new_task_id);

          // Disconnect old SSE
          if (sseClients[taskId]) {
            sseClients[taskId].disconnect();
            delete sseClients[taskId];
          }

          // Update backend task ID and status
          get().updateTask(taskId, {
            backendTaskId: response.new_task_id,
          });
          get().setTaskStatus(taskId, 'running');

          // Connect SSE to new backend task
          get().connectSSE(taskId, response.new_task_id);
        }

        return response;
      }

      return { success: false, error: response.detail || 'Unknown error' };
    } catch (error) {
      console.error('[AgentStore] Failed to send user message:', error);
      return { success: false, error: error.message };
    }
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

  /**
   * Recover running tasks on app startup (e.g. after webview reload)
   * Queries backend for tasks with status=running and restores them with SSE
   */
  recoverRunningTasks: async () => {
    try {
      const response = await api.callAppBackend('/api/v1/quick-task/tasks?status=running', {
        method: 'GET',
      });
      const runningTasks = response.tasks || [];
      if (runningTasks.length === 0) return;

      console.log(`[AgentStore] Found ${runningTasks.length} running task(s), restoring...`);

      for (const task of runningTasks) {
        try {
          await get().restoreTask(task.task_id, task.task);
          console.log(`[AgentStore] Restored running task: ${task.task_id}`);
        } catch (err) {
          console.warn(`[AgentStore] Failed to restore task ${task.task_id}:`, err.message);
        }
      }
    } catch (error) {
      console.warn('[AgentStore] Failed to recover running tasks:', error.message);
    }
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
