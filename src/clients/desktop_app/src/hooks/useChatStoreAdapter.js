/**
 * useChatStoreAdapter Hook
 *
 * Bridge between vanilla Zustand store and React components.
 * Subscribes to store changes and returns reactive state.
 *
 * Ported from Eigent's useChatStoreAdapter hook.
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import chatStore from '../store/chatStore';

/**
 * Hook to use the chat store in React components
 *
 * @param {string} taskId - Optional specific task ID to track
 * @returns {Object} Store state and actions
 */
function useChatStoreAdapter(taskId = null) {
  // Subscribe to store state
  const [storeState, setStoreState] = useState(() => chatStore.getState());

  useEffect(() => {
    // Subscribe to store changes
    const unsubscribe = chatStore.subscribe((state) => {
      setStoreState(state);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // Get the active task ID (provided or from store)
  const activeTaskId = taskId || storeState.activeTaskId;

  // Get the active task
  const activeTask = useMemo(() => {
    return activeTaskId ? storeState.tasks[activeTaskId] : null;
  }, [storeState.tasks, activeTaskId]);

  // Memoized actions bound to active task
  const actions = useMemo(() => {
    const store = chatStore.getState();
    return {
      // Task management
      createTask: store.createTask,
      removeTask: store.removeTask,
      setActiveTaskId: store.setActiveTaskId,

      // Current task actions (auto-bind to activeTaskId)
      updateTask: (updates) => activeTaskId && store.updateTask(activeTaskId, updates),
      addMessage: (message) => activeTaskId && store.addMessage(activeTaskId, message),
      addMessages: (messages) => activeTaskId && store.addMessages(activeTaskId, messages),

      // Task decomposition
      setStreamingDecomposeText: (text) => activeTaskId && store.setStreamingDecomposeText(activeTaskId, text),
      setTaskInfo: (taskInfo) => activeTaskId && store.setTaskInfo(activeTaskId, taskInfo),
      setTaskRunning: (taskRunning) => activeTaskId && store.setTaskRunning(activeTaskId, taskRunning),
      updateTaskRunningItem: (itemId, updates) => activeTaskId && store.updateTaskRunningItem(activeTaskId, itemId, updates),
      setTaskAssigning: (taskAssigning) => activeTaskId && store.setTaskAssigning(activeTaskId, taskAssigning),

      // Agent management
      upsertAgent: (agent) => activeTaskId && store.upsertAgent(activeTaskId, agent),
      setActiveAgent: (agentId) => activeTaskId && store.setActiveAgent(activeTaskId, agentId),

      // Human interaction
      setActiveAsk: (ask) => activeTaskId && store.setActiveAsk(activeTaskId, ask),
      setAskList: (askList) => activeTaskId && store.setAskList(activeTaskId, askList),

      // Workspace
      setActiveWorkSpace: (workspace) => activeTaskId && store.setActiveWorkSpace(activeTaskId, workspace),
      addFile: (file) => activeTaskId && store.addFile(activeTaskId, file),
      addWebViewUrl: (urlInfo) => activeTaskId && store.addWebViewUrl(activeTaskId, urlInfo),
      addTerminalOutput: (output) => activeTaskId && store.addTerminalOutput(activeTaskId, output),

      // Progress and timing
      setProgressValue: (value) => activeTaskId && store.setProgressValue(activeTaskId, value),
      updateTokenUsage: (tokenUsage, isDelta) => activeTaskId && store.updateTokenUsage(activeTaskId, tokenUsage, isDelta),

      // Task status
      setTaskStatus: (status) => activeTaskId && store.setTaskStatus(activeTaskId, status),
      startTaskTimer: () => activeTaskId && store.startTaskTimer(activeTaskId),

      // SSE connection
      connectSSE: (options) => activeTaskId && store.connectSSE(activeTaskId, options),
      disconnectSSE: () => activeTaskId && store.disconnectSSE(activeTaskId),

      // Auto-confirm timer
      startAutoConfirmTimer: (onConfirm, timeout) => activeTaskId && store.startAutoConfirmTimer(activeTaskId, onConfirm, timeout),
      clearAutoConfirmTimer: () => activeTaskId && store.clearAutoConfirmTimer(activeTaskId),

      // Reset
      reset: store.reset,
    };
  }, [activeTaskId]);

  // Computed values for active task
  const computed = useMemo(() => {
    if (!activeTask) {
      return {
        isRunning: false,
        isFinished: false,
        isPaused: false,
        isFailed: false,
        hasMessages: false,
        hasTaskInfo: false,
        hasTaskRunning: false,
        hasPendingConfirm: false,
        totalTasks: 0,
        completedTasks: 0,
        progressPercent: 0,
      };
    }

    const taskList = activeTask.taskRunning.length > 0 ? activeTask.taskRunning : activeTask.taskInfo;
    const completedTasks = taskList.filter((t) => t.status === 'completed').length;

    return {
      isRunning: activeTask.status === 'running',
      isFinished: activeTask.status === 'finished',
      isPaused: activeTask.status === 'pause',
      isFailed: activeTask.status === 'failed',
      hasMessages: activeTask.messages.length > 0,
      hasTaskInfo: activeTask.taskInfo.length > 0,
      hasTaskRunning: activeTask.taskRunning.length > 0,
      hasPendingConfirm: activeTask.messages.some((m) => m.step === 'to_sub_tasks' && !m.isConfirm),
      totalTasks: taskList.length,
      completedTasks,
      progressPercent: taskList.length > 0 ? Math.round((completedTasks / taskList.length) * 100) : 0,
    };
  }, [activeTask]);

  return {
    // Store state
    chatStore: storeState,
    tasks: storeState.tasks,
    activeTaskId,
    activeTask,

    // Actions
    ...actions,

    // Computed values
    ...computed,
  };
}

export default useChatStoreAdapter;
