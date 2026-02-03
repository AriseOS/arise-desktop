/**
 * Chat Store
 *
 * Global state management for task execution using Zustand.
 * Manages task lifecycle, messages, agents, and SSE connections.
 *
 * Ported from Eigent's chatStore with adaptations for 2ami.
 *
 * Conversation Memory Integration:
 * - createTask: Creates a conversation record for persistence
 * - addMessage: Asynchronously persists messages to conversation history
 * - loadConversationHistory: Loads historical conversations
 */

import { createStore } from 'zustand/vanilla';
import { SSEClient, SSEEventTypes } from '../utils/sseClient';
import { api } from '../utils/api';

// Task status types
export const TaskStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  PAUSED: 'pause',
  FINISHED: 'finished',
  FAILED: 'failed',
};

// Task types
export const TaskType = {
  NORMAL: 'normal',
  REPLAY: 'replay',
  SHARE: 'share',
};

// Initial task state
const createInitialTask = (taskId, type = TaskType.NORMAL) => ({
  id: taskId,
  type,
  status: TaskStatus.PENDING,
  // Conversation persistence
  conversationId: null, // Linked conversation ID for history persistence
  // Messages and conversation
  messages: [],
  summaryTask: '',
  hasMessages: false,
  // Task decomposition
  taskInfo: [], // Manual subtasks (type 1)
  taskRunning: [], // Agent-assigned tasks (type 2)
  taskAssigning: [], // Assigned agents
  streamingDecomposeText: '', // Streaming task decomposition
  isTaskEdit: false,
  hasWaitConfirm: false, // Simple query response flag
  // Execution state - tracks subtask assignments and worker status
  executionState: {
    subtasks: [], // [{id, content, agent_type, state, assignee_id, worker_name}]
    workers: [],  // [{id, name, type, status, current_task_id}]
    isActive: false,
    totalTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
  },
  // Agents
  agents: [],
  activeAgent: null,
  // Workspace
  fileList: [],
  webViewUrls: [],
  terminalOutput: [],
  activeWorkSpace: null, // 'workflow' | 'documentWorkSpace' | null
  selectedFile: null,
  // Human interaction
  activeAsk: '',
  askList: [],
  // Progress and timing
  progressValue: 0,
  taskTime: null,
  elapsed: 0,
  delayTime: 0,
  // Tokens
  tokens: 0,
  tokenUsage: {
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
  },
  // Flags
  isPending: false,
  isTakeControl: false,
  isContextExceeded: false,
  hasAddWorker: false,
  // Attachments
  attaches: [],
  // Snapshots (for webview screenshots)
  snapshots: [],
  snapshotsTemp: [],
  // COT (Chain of Thought)
  cotList: [],
  // File tracking
  newFileNum: 0,
});

// Track active SSE connections
const activeSSEClients = {};

// Auto-confirm timers
const autoConfirmTimers = {};

// Create the store
const chatStore = createStore((set, get) => ({
  // State
  tasks: {},
  activeTaskId: null,

  // === Task Management ===

  /**
   * Create a new task
   *
   * Also creates a conversation record for message persistence.
   * The conversation is created asynchronously to avoid blocking.
   */
  createTask: (taskId, type = TaskType.NORMAL) => {
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: createInitialTask(taskId, type),
      },
      activeTaskId: taskId,
    }));

    // Asynchronously create conversation for persistence
    // Don't block task creation, handle errors silently
    api.createConversation({
      title: `Task ${taskId}`,
      taskId: taskId,
      tags: [type],
    }).then((result) => {
      if (result.conversation_id) {
        // Update task with conversation ID
        set((state) => {
          const task = state.tasks[taskId];
          if (!task) return state;
          return {
            tasks: {
              ...state.tasks,
              [taskId]: {
                ...task,
                conversationId: result.conversation_id,
              },
            },
          };
        });
        console.log(`[ChatStore] Created conversation ${result.conversation_id} for task ${taskId}`);
      }
    }).catch((error) => {
      console.warn(`[ChatStore] Failed to create conversation for task ${taskId}:`, error.message);
    });

    return taskId;
  },

  /**
   * Get a task by ID
   */
  getTask: (taskId) => {
    return get().tasks[taskId];
  },

  /**
   * Get the active task
   */
  getActiveTask: () => {
    const { tasks, activeTaskId } = get();
    return activeTaskId ? tasks[activeTaskId] : null;
  },

  /**
   * Set active task ID
   */
  setActiveTaskId: (taskId) => {
    set({ activeTaskId: taskId });
  },

  /**
   * Update a task
   */
  updateTask: (taskId, updates) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            ...updates,
          },
        },
      };
    });
  },

  /**
   * Remove a task
   */
  removeTask: (taskId) => {
    // Cleanup SSE connection
    if (activeSSEClients[taskId]) {
      activeSSEClients[taskId].disconnect();
      delete activeSSEClients[taskId];
    }

    // Cleanup auto-confirm timer
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    }

    set((state) => {
      const newTasks = { ...state.tasks };
      delete newTasks[taskId];

      return {
        tasks: newTasks,
        activeTaskId: state.activeTaskId === taskId ? null : state.activeTaskId,
      };
    });
  },

  // === Message Management ===

  /**
   * Add a message to a task
   *
   * Also persists the message to conversation history asynchronously.
   */
  addMessage: (taskId, message) => {
    const messageId = `msg_${Date.now()}`;
    const timestamp = new Date().toISOString();

    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: [
              ...task.messages,
              {
                id: messageId,
                timestamp,
                ...message,
              },
            ],
          },
        },
      };
    });

    // Asynchronously persist message to conversation history
    const task = get().tasks[taskId];
    if (task?.conversationId && message.role) {
      // Map frontend role to backend role (user, assistant, system)
      const role = message.role === 'agent' ? 'assistant' : message.role;

      // Only persist user, assistant, system messages (not internal events)
      if (['user', 'assistant', 'system'].includes(role)) {
        api.appendConversationMessage(task.conversationId, {
          role,
          content: message.content || '',
          agentId: message.agent_id || message.agentId,
          attachments: message.attachments || [],
          metadata: {
            step: message.step,
            data: message.data,
            messageId,
          },
        }).catch((error) => {
          console.warn(`[ChatStore] Failed to persist message ${messageId}:`, error.message);
        });
      }
    }
  },

  /**
   * Add multiple messages to a task
   */
  addMessages: (taskId, messages) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      const newMessages = messages.map((msg) => ({
        id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        timestamp: new Date().toISOString(),
        ...msg,
      }));

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: [...task.messages, ...newMessages],
            hasMessages: true,
          },
        },
      };
    });
  },

  /**
   * Set messages (replace all)
   */
  setMessages: (taskId, messages) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: [...messages],
            hasMessages: messages.length > 0,
          },
        },
      };
    });
  },

  /**
   * Update a single message
   */
  updateMessage: (taskId, messageId, updates) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: task.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          },
        },
      };
    });
  },

  /**
   * Remove a message
   */
  removeMessage: (taskId, messageId) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      const newMessages = task.messages.filter((msg) => msg.id !== messageId);
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: newMessages,
            hasMessages: newMessages.length > 0,
          },
        },
      };
    });
  },

  /**
   * Get the last user message from active task
   */
  getLastUserMessage: () => {
    const { tasks, activeTaskId } = get();
    if (!activeTaskId || !tasks[activeTaskId]) return null;

    const task = tasks[activeTaskId];
    for (let i = task.messages.length - 1; i >= 0; i--) {
      if (task.messages[i].role === 'user') {
        return task.messages[i];
      }
    }
    return null;
  },

  /**
   * Set hasMessages flag
   */
  setHasMessages: (taskId, hasMessages) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            hasMessages,
          },
        },
      };
    });
  },

  /**
   * Set summary task
   *
   * Also updates the conversation title for persistence.
   */
  setSummaryTask: (taskId, summaryTask) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            summaryTask,
          },
        },
      };
    });

    // Update conversation title asynchronously
    if (summaryTask) {
      get().updateConversationInfo(taskId, { title: summaryTask });
    }
  },

  /**
   * Set file attachments
   */
  setAttaches: (taskId, attaches) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            attaches: [...attaches],
          },
        },
      };
    });
  },

  /**
   * Set hasWaitConfirm flag
   */
  setHasWaitConfirm: (taskId, hasWaitConfirm) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            hasWaitConfirm,
          },
        },
      };
    });
  },

  // === Task Decomposition ===

  /**
   * Set streaming decompose text
   */
  setStreamingDecomposeText: (taskId, text) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            streamingDecomposeText: text,
          },
        },
      };
    });
  },

  /**
   * Clear streaming decompose text
   */
  clearStreamingDecomposeText: (taskId) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            streamingDecomposeText: '',
          },
        },
      };
    });
  },

  /**
   * Set task info (manual subtasks)
   */
  setTaskInfo: (taskId, taskInfo) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskInfo,
          },
        },
      };
    });
  },

  /**
   * Set task running (agent-assigned tasks)
   */
  setTaskRunning: (taskId, taskRunning) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskRunning,
          },
        },
      };
    });
  },

  /**
   * Update a single task in taskRunning
   */
  updateTaskRunningItem: (taskId, itemId, updates) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskRunning: task.taskRunning.map((item) =>
              item.id === itemId ? { ...item, ...updates } : item
            ),
          },
        },
      };
    });
  },

  /**
   * Set task assigning (agents)
   */
  setTaskAssigning: (taskId, taskAssigning) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskAssigning,
          },
        },
      };
    });
  },

  /**
   * Update execution state (subtask assignments and worker status)
   */
  updateExecutionState: (taskId, updates) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            executionState: {
              ...task.executionState,
              ...updates,
            },
          },
        },
      };
    });
  },

  /**
   * Update or add a subtask in execution state
   */
  upsertExecutionSubtask: (taskId, subtaskData) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      const subtasks = [...(task.executionState?.subtasks || [])];
      const existingIndex = subtasks.findIndex((s) => s.id === subtaskData.id);

      if (existingIndex >= 0) {
        // Update existing subtask
        subtasks[existingIndex] = { ...subtasks[existingIndex], ...subtaskData };
      } else {
        // Add new subtask
        subtasks.push(subtaskData);
      }

      // Recalculate counts
      const completedTasks = subtasks.filter((s) => s.state === 'DONE' || s.state === 'completed').length;
      const runningTasks = subtasks.filter((s) => s.state === 'RUNNING' || s.state === 'running').length;
      const failedTasks = subtasks.filter((s) => s.state === 'FAILED' || s.state === 'failed').length;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            executionState: {
              ...task.executionState,
              subtasks,
              totalTasks: subtasks.length,
              completedTasks,
              runningTasks,
              failedTasks,
            },
          },
        },
      };
    });
  },

  /**
   * Add a new task info item (for manual task editing)
   */
  addTaskInfo: () => {
    const { activeTaskId, tasks } = get();
    if (!activeTaskId || !tasks[activeTaskId]) return;

    set((state) => ({
      tasks: {
        ...state.tasks,
        [activeTaskId]: {
          ...state.tasks[activeTaskId],
          taskInfo: [
            ...state.tasks[activeTaskId].taskInfo,
            { id: `task_${Date.now()}`, content: '', status: 'pending' },
          ],
        },
      },
    }));
  },

  /**
   * Update a task info item by index
   */
  updateTaskInfo: (index, content) => {
    const { activeTaskId, tasks } = get();
    if (!activeTaskId || !tasks[activeTaskId]) return;

    set((state) => ({
      tasks: {
        ...state.tasks,
        [activeTaskId]: {
          ...state.tasks[activeTaskId],
          taskInfo: state.tasks[activeTaskId].taskInfo.map((item, i) =>
            i === index ? { ...item, content } : item
          ),
        },
      },
    }));
  },

  /**
   * Delete a task info item by index
   */
  deleteTaskInfo: (index) => {
    const { activeTaskId, tasks } = get();
    if (!activeTaskId || !tasks[activeTaskId]) return;

    set((state) => ({
      tasks: {
        ...state.tasks,
        [activeTaskId]: {
          ...state.tasks[activeTaskId],
          taskInfo: state.tasks[activeTaskId].taskInfo.filter((_, i) => i !== index),
        },
      },
    }));
  },

  /**
   * Set isTaskEdit flag
   */
  setIsTaskEdit: (taskId, isTaskEdit) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            isTaskEdit,
          },
        },
      };
    });
  },

  // === Agent Management ===

  /**
   * Add or update an agent
   */
  upsertAgent: (taskId, agent) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      const existingIndex = task.agents.findIndex((a) => a.agent_id === agent.agent_id);
      let newAgents;

      if (existingIndex >= 0) {
        newAgents = [...task.agents];
        newAgents[existingIndex] = { ...newAgents[existingIndex], ...agent };
      } else {
        newAgents = [...task.agents, agent];
      }

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            agents: newAgents,
          },
        },
      };
    });
  },

  /**
   * Set active agent
   */
  setActiveAgent: (taskId, agentId) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            activeAgent: agentId,
          },
        },
      };
    });
  },

  // === Human Interaction ===

  /**
   * Set active ask (human interaction prompt)
   */
  setActiveAsk: (taskId, ask) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            activeAsk: ask,
          },
        },
      };
    });
  },

  /**
   * Set ask list
   */
  setAskList: (taskId, askList) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            askList,
          },
        },
      };
    });
  },

  // === Workspace ===

  /**
   * Set active workspace
   */
  setActiveWorkSpace: (taskId, workspace) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            activeWorkSpace: workspace,
          },
        },
      };
    });
  },

  /**
   * Add file to file list
   */
  addFile: (taskId, file) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            fileList: [...task.fileList, file],
          },
        },
      };
    });
  },

  /**
   * Add webview URL
   */
  addWebViewUrl: (taskId, urlInfo) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            webViewUrls: [...task.webViewUrls, urlInfo],
          },
        },
      };
    });
  },

  /**
   * Set webview URLs (replace all)
   */
  setWebViewUrls: (taskId, webViewUrls) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            webViewUrls,
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
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            terminalOutput: [...task.terminalOutput, output],
          },
        },
      };
    });
  },

  /**
   * Add file to file list (with processTaskId for agent tracking)
   */
  addFileList: (taskId, processTaskId, fileInfo) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            fileList: [...task.fileList, { ...fileInfo, processTaskId }],
            newFileNum: (task.newFileNum || 0) + 1,
          },
        },
      };
    });
  },

  /**
   * Set file list (with processTaskId filter)
   */
  setFileList: (taskId, processTaskId, fileList) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      // Keep files from other processes, replace files from this process
      const otherFiles = task.fileList.filter((f) => f.processTaskId !== processTaskId);
      const newFiles = fileList.map((f) => ({ ...f, processTaskId }));

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            fileList: [...otherFiles, ...newFiles],
          },
        },
      };
    });
  },

  /**
   * Set selected file
   */
  setSelectedFile: (taskId, selectedFile) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            selectedFile,
          },
        },
      };
    });
  },

  /**
   * Set newFileNum
   */
  setNewFileNum: (taskId, newFileNum) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            newFileNum,
          },
        },
      };
    });
  },

  /**
   * Set snapshots (webview screenshots)
   */
  setSnapshots: (taskId, snapshots) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            snapshots,
          },
        },
      };
    });
  },

  /**
   * Add to snapshotsTemp (temporary screenshot storage)
   */
  setSnapshotsTemp: (taskId, snapshot) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            snapshotsTemp: [...task.snapshotsTemp, snapshot],
          },
        },
      };
    });
  },

  // === Progress and Timing ===

  /**
   * Set progress value
   */
  setProgressValue: (taskId, value) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            progressValue: value,
          },
        },
      };
    });
  },

  /**
   * Compute progress value based on completed tasks
   */
  computedProgressValue: (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return;

    const { taskRunning } = task;
    if (!taskRunning || taskRunning.length === 0) return;

    const completed = taskRunning.filter((t) => t.status === 'done').length;
    const total = taskRunning.length;
    const value = Math.round((completed / total) * 100);

    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          progressValue: value,
        },
      },
    }));
  },

  /**
   * Update token usage
   */
  updateTokenUsage: (taskId, tokenUsage, isDelta = false) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      let newTokenUsage;
      if (isDelta) {
        newTokenUsage = {
          inputTokens: (task.tokenUsage.inputTokens || 0) + (tokenUsage.inputTokens || 0),
          outputTokens: (task.tokenUsage.outputTokens || 0) + (tokenUsage.outputTokens || 0),
          cacheCreationTokens: (task.tokenUsage.cacheCreationTokens || 0) + (tokenUsage.cacheCreationTokens || 0),
          cacheReadTokens: (task.tokenUsage.cacheReadTokens || 0) + (tokenUsage.cacheReadTokens || 0),
        };
      } else {
        newTokenUsage = { ...task.tokenUsage, ...tokenUsage };
      }

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            tokenUsage: newTokenUsage,
            tokens: newTokenUsage.inputTokens + newTokenUsage.outputTokens,
          },
        },
      };
    });
  },

  /**
   * Add tokens (increment)
   */
  addTokens: (taskId, tokens) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            tokens: (task.tokens || 0) + tokens,
          },
        },
      };
    });
  },

  /**
   * Get tokens for a task
   */
  getTokens: (taskId) => {
    const task = get().tasks[taskId];
    return task?.tokens || 0;
  },

  /**
   * Set task time
   */
  setTaskTime: (taskId, taskTime) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskTime,
          },
        },
      };
    });
  },

  /**
   * Set elapsed time
   */
  setElapsed: (taskId, elapsed) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            elapsed,
          },
        },
      };
    });
  },

  /**
   * Get formatted task time string
   */
  getFormattedTaskTime: (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return '0s';

    let totalMs = task.elapsed || 0;
    if (task.taskTime) {
      totalMs += Date.now() - task.taskTime;
    }

    const totalSeconds = Math.floor(totalMs / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  },

  /**
   * Set delay time for replay
   */
  setDelayTime: (taskId, delayTime) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            delayTime,
          },
        },
      };
    });
  },

  // === Task Status ===

  /**
   * Set task status
   */
  setTaskStatus: (taskId, status) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status,
          },
        },
      };
    });

    // Update conversation status when task ends
    if (status === TaskStatus.FINISHED || status === TaskStatus.FAILED) {
      const conversationStatus = status === TaskStatus.FINISHED ? 'completed' : 'failed';
      get().updateConversationStatus(taskId, conversationStatus);
    }
  },

  /**
   * Start task timer
   */
  startTaskTimer: (taskId) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            taskTime: Date.now(),
          },
        },
      };
    });
  },

  /**
   * Stop a task (abort SSE and cleanup)
   */
  stopTask: (taskId) => {
    // Disconnect SSE
    if (activeSSEClients[taskId]) {
      activeSSEClients[taskId].disconnect();
      delete activeSSEClients[taskId];
    }

    // Clear auto-confirm timer
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    }

    // Update task status
    const now = Date.now();
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      const elapsed = task.elapsed + (task.taskTime ? now - task.taskTime : 0);

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status: TaskStatus.FINISHED,
            elapsed,
            taskTime: null,
          },
        },
      };
    });
  },

  /**
   * Set isPending flag
   */
  setIsPending: (taskId, isPending) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            isPending,
          },
        },
      };
    });
  },

  /**
   * Set isTakeControl flag
   */
  setIsTakeControl: (taskId, isTakeControl) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            isTakeControl,
          },
        },
      };
    });
  },

  /**
   * Set isContextExceeded flag
   */
  setIsContextExceeded: (taskId, isContextExceeded) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            isContextExceeded,
          },
        },
      };
    });
  },

  /**
   * Set hasAddWorker flag
   */
  setHasAddWorker: (taskId, hasAddWorker) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            hasAddWorker,
          },
        },
      };
    });
  },

  /**
   * Set task type
   */
  setType: (taskId, type) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            type,
          },
        },
      };
    });
  },

  /**
   * Set COT (Chain of Thought) list
   */
  setCotList: (taskId, cotList) => {
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            cotList,
          },
        },
      };
    });
  },

  /**
   * Set next task ID (for task chaining)
   */
  setNextTaskId: (nextTaskId) => {
    set({ nextTaskId });
  },

  /**
   * Clear all tasks
   */
  clearTasks: () => {
    // Disconnect all SSE connections
    Object.keys(activeSSEClients).forEach((taskId) => {
      activeSSEClients[taskId].disconnect();
      delete activeSSEClients[taskId];
    });

    // Clear all auto-confirm timers
    Object.keys(autoConfirmTimers).forEach((taskId) => {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    });

    set({
      tasks: {},
      activeTaskId: null,
      nextTaskId: null,
    });
  },

  // === Task Execution ===

  /**
   * Start a task (send to backend and begin execution)
   *
   * @param {string} taskId - Task ID
   * @param {string} type - Task type ('normal', 'replay', 'share')
   * @param {string} shareToken - Share token (for shared tasks)
   * @param {number} delayTime - Delay time for replay
   * @param {string} messageContent - Optional message content
   * @param {Array} messageAttaches - Optional file attachments
   */
  startTask: async (taskId, type = 'normal', shareToken = null, delayTime = 0, messageContent = null, messageAttaches = []) => {
    const {
      tasks,
      setDelayTime,
      setType,
      setIsPending,
      setTaskStatus,
      startTaskTimer,
      setActiveWorkSpace,
      addMessage,
      connectSSE,
    } = get();

    const task = tasks[taskId];
    if (!task) {
      console.error('[startTask] Task not found:', taskId);
      return;
    }

    // Set replay delay time if applicable
    if (type === 'replay' && delayTime > 0) {
      setDelayTime(taskId, delayTime);
      setType(taskId, type);
    }

    // Mark as pending while starting
    setIsPending(taskId, true);

    try {
      // Get the last user message for the API call
      let content = messageContent;
      if (!content) {
        const userMessage = task.messages.find((m) => m.role === 'user');
        content = userMessage?.content || '';
      }

      // Prepare request body
      const requestBody = {
        message: content,
        task_id: taskId,
        type,
      };

      if (shareToken) {
        requestBody.share_token = shareToken;
      }

      if (messageAttaches && messageAttaches.length > 0) {
        requestBody.attachments = messageAttaches.map((f) => ({
          file_name: f.fileName,
          file_path: f.filePath,
        }));
      }

      // TODO: Call backend API to start task
      // const response = await fetch('/api/v1/quick-task/start', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(requestBody),
      // });

      // Update task state
      setTaskStatus(taskId, TaskStatus.RUNNING);
      startTaskTimer(taskId);
      setActiveWorkSpace(taskId, 'workflow');
      setIsPending(taskId, false);

      // Connect SSE for task updates
      connectSSE(taskId);

    } catch (error) {
      console.error('[startTask] Error:', error);
      setIsPending(taskId, false);
      addMessage(taskId, {
        role: 'agent',
        content: `Error starting task: ${error.message}`,
      });
    }
  },

  /**
   * Confirm task decomposition and start execution
   *
   * @param {string} projectId - Project ID
   * @param {string} taskId - Task ID
   * @param {string} type - Optional type override
   */
  handleConfirmTask: async (projectId, taskId, type = null) => {
    const {
      tasks,
      setMessages,
      setActiveWorkSpace,
      setTaskStatus,
      setTaskTime,
      setTaskInfo,
      setTaskRunning,
      setIsTaskEdit,
      clearAutoConfirmTimer,
    } = get();

    if (!taskId) return;

    const task = tasks[taskId];
    if (!task) return;

    // Clear any pending auto-confirm timer
    clearAutoConfirmTimer(taskId);

    // Record task start time
    setTaskTime(taskId, Date.now());

    // Filter out empty tasks
    const taskInfo = task.taskInfo.filter((t) => t.content && t.content.trim() !== '');
    setTaskInfo(taskId, taskInfo);

    const taskRunning = task.taskRunning.filter((t) => t.content && t.content.trim() !== '');
    setTaskRunning(taskId, taskRunning);

    if (!type) {
      // TODO: Call backend API to confirm and start task
      // await fetch(`/api/v1/task/${projectId}`, {
      //   method: 'PUT',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify({ task: taskInfo }),
      // });
      // await fetch(`/api/v1/task/${projectId}/start`, { method: 'POST' });

      setActiveWorkSpace(taskId, 'workflow');
      setTaskStatus(taskId, TaskStatus.RUNNING);
    }

    // Update message to mark as confirmed
    const messages = [...task.messages];
    const cardTaskIndex = messages.findLastIndex((m) => m.step === 'to_sub_tasks');
    if (cardTaskIndex !== -1) {
      messages[cardTaskIndex] = {
        ...messages[cardTaskIndex],
        isConfirm: true,
        taskType: 2,
      };
      setMessages(taskId, messages);
    }

    // Reset editing state
    setIsTaskEdit(taskId, false);
  },

  // === SSE Connection Management ===

  /**
   * Connect SSE for a task
   */
  connectSSE: (taskId, options = {}) => {
    const { onEvent, onError, onClose } = options;

    // Disconnect existing connection
    if (activeSSEClients[taskId]) {
      activeSSEClients[taskId].disconnect();
    }

    const client = new SSEClient();
    activeSSEClients[taskId] = client;

    const handleEvent = (event) => {
      // Process event and update store
      get().handleSSEEvent(taskId, event);
      // Call external handler if provided
      if (onEvent) onEvent(event);
    };

    client.connect(taskId, {
      onEvent: handleEvent,
      onError: (error) => {
        console.error(`SSE error for task ${taskId}:`, error);
        if (onError) onError(error);
      },
      onClose: () => {
        console.log(`SSE closed for task ${taskId}`);
        delete activeSSEClients[taskId];
        if (onClose) onClose();
      },
    });

    return client;
  },

  /**
   * Disconnect SSE for a task
   */
  disconnectSSE: (taskId) => {
    if (activeSSEClients[taskId]) {
      activeSSEClients[taskId].disconnect();
      delete activeSSEClients[taskId];
    }
  },

  /**
   * Handle SSE event
   */
  handleSSEEvent: (taskId, event) => {
    const eventType = event.event || event.action;
    const store = get();

    switch (eventType) {
      case 'connected':
      case SSEEventTypes.CONNECTED:
        store.setTaskStatus(taskId, TaskStatus.RUNNING);
        store.startTaskTimer(taskId);
        break;

      case 'task_started':
      case SSEEventTypes.TASK_STARTED:
        store.setTaskStatus(taskId, TaskStatus.RUNNING);
        break;

      case 'decompose_text':
        // Streaming task decomposition
        store.setStreamingDecomposeText(taskId, event.text || event.content || '');
        break;

      case 'to_sub_tasks':
      case 'task_decomposed':
        store.setTaskInfo(taskId, event.subtasks || event.tasks || []);
        store.setStreamingDecomposeText(taskId, '');
        // Initialize execution state with subtasks (including agent_type)
        {
          const subtasks = (event.subtasks || event.tasks || []).map((st) => ({
            id: st.id,
            content: st.content,
            state: st.state || st.status || 'OPEN',
            agent_type: st.agent_type,
          }));
          store.updateExecutionState(taskId, {
            subtasks,
            totalTasks: subtasks.length,
            completedTasks: 0,
            runningTasks: 0,
            failedTasks: 0,
          });
        }
        // Add message for confirmation
        store.addMessage(taskId, {
          role: 'agent',
          content: 'Task decomposition complete',
          step: 'to_sub_tasks',
          isConfirm: false,
          data: { tasks: event.subtasks || event.tasks || [] },
        });
        break;

      case 'confirmed':
        // Task confirmed, update message
        store.updateTask(taskId, {
          messages: store.getTask(taskId)?.messages.map((msg) =>
            msg.step === 'to_sub_tasks' ? { ...msg, isConfirm: true } : msg
          ),
        });
        break;

      case 'task_assign':
      case 'assign_task':
        // Legacy handling for backwards compatibility
        if (event.agent) {
          store.upsertAgent(taskId, event.agent);
        }
        if (event.tasks) {
          store.setTaskRunning(taskId, event.tasks);
        }
        // New: Update execution state with subtask assignment
        if (event.subtask_id) {
          store.upsertExecutionSubtask(taskId, {
            id: event.subtask_id,
            content: event.content,
            state: event.state === 'running' ? 'RUNNING' : 'ASSIGNED',
            assignee_id: event.assignee_id || event.agent_id,
            worker_name: event.worker_name,
            agent_type: event.agent_type,
            failure_count: event.failure_count || 0,
          });
        }
        break;

      case 'workforce_started':
        store.updateExecutionState(taskId, {
          isActive: true,
          totalTasks: event.total_tasks || 0,
        });
        break;

      case 'workforce_completed':
        store.updateExecutionState(taskId, {
          isActive: false,
        });
        break;

      case 'workforce_stopped':
        store.updateExecutionState(taskId, {
          isActive: false,
        });
        break;

      case 'subtask_state':
        // Update subtask state (OPEN, RUNNING, DONE, FAILED)
        if (event.subtask_id) {
          store.upsertExecutionSubtask(taskId, {
            id: event.subtask_id,
            state: event.state,
            result: event.result,
            failure_count: event.failure_count,
          });
        }
        break;

      case 'worker_completed':
        if (event.subtask_id) {
          store.upsertExecutionSubtask(taskId, {
            id: event.subtask_id,
            state: 'DONE',
            result: event.result,
          });
        }
        break;

      case 'worker_failed':
        if (event.subtask_id) {
          store.upsertExecutionSubtask(taskId, {
            id: event.subtask_id,
            state: 'FAILED',
            error: event.error,
            failure_count: event.failure_count,
          });
        }
        break;

      case 'agent_created':
      case 'agent_started':
        if (event.agent_id || event.agent_name) {
          store.upsertAgent(taskId, {
            agent_id: event.agent_id || `agent_${Date.now()}`,
            name: event.agent_name || 'Agent',
            type: event.agent_type || 'browser_agent',
            status: 'active',
            tools: event.tools || [],
            tasks: [],
            log: [],
          });
          store.setActiveAgent(taskId, event.agent_id);
        }
        break;

      case 'activate_agent':
        if (event.agent_id) {
          store.setActiveAgent(taskId, event.agent_id);
        }
        break;

      case 'deactivate_agent':
        if (event.tokens_used || event.tokens) {
          store.updateTokenUsage(taskId, {
            inputTokens: event.tokens_used || event.tokens,
          }, true);
        }
        break;

      case 'token_usage':
      case 'usage_update':
        store.updateTokenUsage(taskId, {
          inputTokens: event.input_tokens || event.total_input_tokens,
          outputTokens: event.output_tokens || event.total_output_tokens,
          cacheCreationTokens: event.cache_creation_tokens,
          cacheReadTokens: event.cache_read_tokens,
        }, event.is_delta === true);
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

      case 'write_file':
        store.addFile(taskId, {
          name: event.file_name || event.file_path,
          path: event.file_path,
          timestamp: new Date().toISOString(),
        });
        break;

      case 'human_ask':
        store.setActiveAsk(taskId, event.question || event.message);
        store.addMessage(taskId, {
          role: 'agent',
          content: event.question || event.message,
          step: 'human_ask',
          data: event,
        });
        break;

      case 'progress':
        store.setProgressValue(taskId, event.value || event.progress || 0);
        break;

      case 'task_completed':
      case SSEEventTypes.TASK_COMPLETED:
        store.setTaskStatus(taskId, TaskStatus.FINISHED);
        store.setProgressValue(taskId, 100);
        if (event.output) {
          store.addMessage(taskId, {
            role: 'agent',
            content: typeof event.output === 'string' ? event.output : JSON.stringify(event.output),
            step: 'result',
            // DS-11: Include file attachments if present
            attachments: event.attachments || [],
          });
        }
        break;

      case 'task_failed':
      case SSEEventTypes.TASK_FAILED:
        store.setTaskStatus(taskId, TaskStatus.FAILED);
        store.addMessage(taskId, {
          role: 'agent',
          content: event.error || 'Task failed',
          step: 'error',
        });
        break;

      case 'end':
        if (event.status === 'completed') {
          store.setTaskStatus(taskId, TaskStatus.FINISHED);
        } else if (event.status === 'failed') {
          store.setTaskStatus(taskId, TaskStatus.FAILED);
        }
        break;

      case 'screenshot':
      case 'browser_screenshot':
        // Add screenshot to snapshots
        if (event.screenshot || event.image) {
          store.setSnapshotsTemp(taskId, {
            url: event.url,
            image: event.screenshot || event.image,
            timestamp: event.timestamp || new Date().toISOString(),
          });
        }
        break;

      case 'webview_url':
      case 'browser_navigated':
        if (event.url) {
          store.addWebViewUrl(taskId, {
            url: event.url,
            processTaskId: event.process_task_id || event.agent_id,
          });
        }
        break;

      case 'context_too_long':
      case 'budget_not_enough':
        store.setIsContextExceeded(taskId, true);
        store.addMessage(taskId, {
          role: 'system',
          content: eventType === 'context_too_long'
            ? 'Context limit exceeded. Please start a new conversation.'
            : 'Budget limit reached. Please check your account.',
          step: eventType,
        });
        break;

      case 'wait_confirm':
        store.setHasWaitConfirm(taskId, true);
        break;

      case 'ask_list':
        store.setAskList(taskId, event.messages || event.ask_list || []);
        break;

      case 'cot':
      case 'chain_of_thought':
        if (event.cot || event.thought) {
          const task = store.getTask(taskId);
          store.setCotList(taskId, [...(task?.cotList || []), event.cot || event.thought]);
        }
        break;

      case 'workspace':
      case 'active_workspace':
        store.setActiveWorkSpace(taskId, event.workspace || event.active_workspace);
        break;

      case 'toolkit_started':
      case 'toolkit_completed':
      case 'toolkit_failed':
        // Update agent with toolkit event
        const agentId = event.agent_id;
        if (agentId) {
          const task = store.getTask(taskId);
          const agent = task?.agents?.find((a) => a.agent_id === agentId);
          if (agent) {
            const toolkitEvent = {
              type: eventType.replace('toolkit_', ''),
              toolkit: event.toolkit_name,
              method: event.method_name,
              timestamp: event.timestamp,
              inputs: event.inputs,
              outputs: event.outputs,
            };
            store.upsertAgent(taskId, {
              ...agent,
              log: [...(agent.log || []), toolkitEvent],
            });
          }
        }
        break;

      case 'task_paused':
        store.setTaskStatus(taskId, TaskStatus.PAUSED);
        break;

      case 'task_resumed':
        store.setTaskStatus(taskId, TaskStatus.RUNNING);
        break;

      default:
        // Unknown event, log for debugging
        console.log('Unhandled SSE event:', eventType, event);
    }
  },

  // === Auto-confirm Timer ===

  /**
   * Start auto-confirm timer for task decomposition
   */
  startAutoConfirmTimer: (taskId, onConfirm, timeout = 30000) => {
    // Clear existing timer
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
    }

    autoConfirmTimers[taskId] = setTimeout(() => {
      onConfirm();
      delete autoConfirmTimers[taskId];
    }, timeout);
  },

  /**
   * Clear auto-confirm timer
   */
  clearAutoConfirmTimer: (taskId) => {
    if (autoConfirmTimers[taskId]) {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    }
  },

  // === Replay ===

  /**
   * Replay a task
   * Creates a new task with the same content and starts it
   *
   * @param {string} taskId - The task ID to replay
   * @param {string} question - The question/content to replay
   * @param {number} delay - Delay before starting (in seconds)
   */
  replay: async (taskId, question, delay = 0.2) => {
    const { createTask, addMessage, startTask, setActiveTaskId } = get();

    // Create new task with replay type
    createTask(taskId, TaskType.REPLAY);

    // Add the original question as user message
    addMessage(taskId, {
      role: 'user',
      content: question.split('|')[0], // Handle any separator in question
    });

    // Start the task after a small delay
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay * 1000));
    }

    // TODO: Call backend API to start replay
    // await startTask(taskId, 'replay');

    setActiveTaskId(taskId);
  },

  /**
   * Replay the active task
   * Extracts question from the current task and creates a replay
   */
  replayActiveTask: async () => {
    const { activeTaskId, tasks, replay } = get();

    if (!activeTaskId || !tasks[activeTaskId]) {
      console.error('No active task to replay');
      return;
    }

    const task = tasks[activeTaskId];

    // Find the first user message to use as the question
    const userMessage = task.messages.find((msg) => msg.role === 'user');
    const question = userMessage?.content || 'Replay task';

    // Generate a new task ID for the replay
    const replayTaskId = `replay_${activeTaskId}_${Date.now()}`;

    await replay(replayTaskId, question, 0.2);

    return replayTaskId;
  },

  // === Pause/Resume ===

  /**
   * Pause the current running task
   */
  pauseTask: (taskId) => {
    const task = get().tasks[taskId];
    if (!task || task.status !== TaskStatus.RUNNING) return;

    const now = Date.now();
    const elapsed = task.elapsed + (task.taskTime ? now - task.taskTime : 0);

    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          status: TaskStatus.PAUSED,
          elapsed,
          taskTime: null,
        },
      },
    }));

    // TODO: Call backend API to pause
    // fetchPut(`/task/${projectId}/take-control`, { action: 'pause' });
  },

  /**
   * Resume a paused task
   */
  resumeTask: (taskId) => {
    const task = get().tasks[taskId];
    if (!task || task.status !== TaskStatus.PAUSED) return;

    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          status: TaskStatus.RUNNING,
          taskTime: Date.now(),
        },
      },
    }));

    // TODO: Call backend API to resume
    // fetchPut(`/task/${projectId}/take-control`, { action: 'resume' });
  },

  /**
   * Toggle pause/resume for a task
   */
  togglePauseResume: (taskId) => {
    const task = get().tasks[taskId];
    if (!task) return;

    if (task.status === TaskStatus.RUNNING) {
      get().pauseTask(taskId);
    } else if (task.status === TaskStatus.PAUSED) {
      get().resumeTask(taskId);
    }
  },

  // === Reset ===

  /**
   * Reset the store
   */
  reset: () => {
    // Cleanup all SSE connections
    Object.keys(activeSSEClients).forEach((taskId) => {
      activeSSEClients[taskId].disconnect();
      delete activeSSEClients[taskId];
    });

    // Cleanup all timers
    Object.keys(autoConfirmTimers).forEach((taskId) => {
      clearTimeout(autoConfirmTimers[taskId]);
      delete autoConfirmTimers[taskId];
    });

    set({
      tasks: {},
      activeTaskId: null,
    });
  },

  // === Conversation History ===

  /**
   * Load a conversation from history into a task
   *
   * @param {string} conversationId - Conversation ID to load
   * @returns {Promise<string|null>} Task ID if loaded successfully, null otherwise
   */
  loadConversation: async (conversationId) => {
    try {
      // Get conversation details
      const conversation = await api.getConversation(conversationId);
      if (!conversation) {
        console.error(`[ChatStore] Conversation not found: ${conversationId}`);
        return null;
      }

      // Get conversation messages
      const messagesResult = await api.getConversationMessages(conversationId, { limit: 100 });

      // Create a task ID (use original task_id if available, otherwise generate)
      const taskId = conversation.task_ids?.[0] || `loaded_${conversationId}`;

      // Map messages from backend format to frontend format
      const messages = (messagesResult.messages || []).map((msg, index) => ({
        id: `msg_loaded_${index}`,
        timestamp: msg.timestamp,
        role: msg.role === 'assistant' ? 'agent' : msg.role,
        content: msg.content,
        agent_id: msg.agent_id,
        attachments: msg.attachments || [],
        step: msg.metadata?.step,
        data: msg.metadata?.data,
      }));

      // Create task with loaded messages
      set((state) => ({
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...createInitialTask(taskId, TaskType.NORMAL),
            conversationId,
            messages,
            hasMessages: messages.length > 0,
            summaryTask: conversation.summary || conversation.title,
            status: conversation.status === 'completed' ? TaskStatus.FINISHED :
                    conversation.status === 'failed' ? TaskStatus.FAILED :
                    TaskStatus.PENDING,
          },
        },
        activeTaskId: taskId,
      }));

      console.log(`[ChatStore] Loaded conversation ${conversationId} as task ${taskId} with ${messages.length} messages`);
      return taskId;
    } catch (error) {
      console.error(`[ChatStore] Failed to load conversation ${conversationId}:`, error);
      return null;
    }
  },

  /**
   * List recent conversations
   *
   * @param {number} limit - Maximum number of conversations to return
   * @returns {Promise<Array>} List of conversation summaries
   */
  listRecentConversations: async (limit = 20) => {
    try {
      const result = await api.listConversations({ limit, status: null });
      return result.conversations || [];
    } catch (error) {
      console.error('[ChatStore] Failed to list conversations:', error);
      return [];
    }
  },

  /**
   * Search conversations
   *
   * @param {string} query - Search query
   * @param {number} limit - Maximum number of results
   * @returns {Promise<Array>} List of matching conversations
   */
  searchConversations: async (query, limit = 10) => {
    try {
      const result = await api.searchConversations(query, { limit });
      return result.results || [];
    } catch (error) {
      console.error('[ChatStore] Failed to search conversations:', error);
      return [];
    }
  },

  /**
   * Update conversation status when task ends
   *
   * @param {string} taskId - Task ID
   * @param {string} status - New status (completed, failed)
   */
  updateConversationStatus: async (taskId, status) => {
    const task = get().tasks[taskId];
    if (!task?.conversationId) return;

    try {
      await api.updateConversation(task.conversationId, { status });
      console.log(`[ChatStore] Updated conversation ${task.conversationId} status to ${status}`);
    } catch (error) {
      console.warn(`[ChatStore] Failed to update conversation status:`, error.message);
    }
  },

  /**
   * Update conversation title and summary
   *
   * @param {string} taskId - Task ID
   * @param {object} updates - Updates (title, summary)
   */
  updateConversationInfo: async (taskId, { title, summary }) => {
    const task = get().tasks[taskId];
    if (!task?.conversationId) return;

    const updates = {};
    if (title) updates.title = title;
    if (summary) updates.summary = summary;

    if (Object.keys(updates).length === 0) return;

    try {
      await api.updateConversation(task.conversationId, updates);
      console.log(`[ChatStore] Updated conversation ${task.conversationId} info`);
    } catch (error) {
      console.warn(`[ChatStore] Failed to update conversation info:`, error.message);
    }
  },

  /**
   * Delete a conversation
   *
   * @param {string} conversationId - Conversation ID to delete
   * @returns {Promise<boolean>} True if deleted successfully
   */
  deleteConversation: async (conversationId) => {
    try {
      await api.deleteConversation(conversationId);
      console.log(`[ChatStore] Deleted conversation ${conversationId}`);
      return true;
    } catch (error) {
      console.error(`[ChatStore] Failed to delete conversation ${conversationId}:`, error);
      return false;
    }
  },
}));

export default chatStore;
