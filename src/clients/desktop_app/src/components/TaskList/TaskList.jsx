/**
 * TaskList Component - Displays list of tasks in sidebar
 *
 * Similar to Eigent's task list + history pattern.
 * Shows:
 * - In-memory tasks (current session)
 * - Backend history tasks (persisted, can be restored)
 *
 * Features:
 * - Auto-load history on mount
 * - Click to restore history task from backend
 * - Visual indicators for running/completed/failed status
 */

import React, { useEffect, useState, useMemo } from 'react';
import Icon from '../Icons';
import { useAgentStore } from '../../store';
import './TaskList.css';

// Status icon mapping
const statusIcons = {
  pending: 'clock',
  running: 'loader',
  completed: 'check',
  failed: 'alert',
  cancelled: 'close',
};

// Status color mapping
const statusColors = {
  pending: 'var(--text-tertiary)',
  running: 'var(--primary-main)',
  completed: 'var(--status-success-text)',
  failed: 'var(--status-error-text)',
  cancelled: 'var(--text-tertiary)',
};

function TaskListItem({ task, isActive, onClick, onDelete }) {
  const statusIcon = statusIcons[task.status] || 'circle';
  const statusColor = statusColors[task.status] || 'var(--text-tertiary)';

  // Format task description (truncate if too long)
  const displayTask = task.taskDescription?.slice(0, 50) || 'Untitled Task';
  const truncated = task.taskDescription?.length > 50;

  // Format time
  const formatTime = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div
      className={`task-list-item ${isActive ? 'active' : ''} status-${task.status}`}
      onClick={onClick}
    >
      <div className="task-item-icon" style={{ color: statusColor }}>
        <Icon name={statusIcon} size={16} className={task.status === 'running' ? 'spinning' : ''} />
      </div>
      <div className="task-item-content">
        <div className="task-item-title" title={task.taskDescription}>
          {displayTask}{truncated ? '...' : ''}
        </div>
        <div className="task-item-meta">
          <span className="task-item-status">{task.status}</span>
          <span className="task-item-time">{formatTime(task.createdAt)}</span>
        </div>
      </div>
      {(task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') && (
        <button
          className="task-item-delete"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(task.id);
          }}
          title="Remove task"
        >
          <Icon name="close" size={14} />
        </button>
      )}
    </div>
  );
}

function TaskList({ onNewTask, collapsed = false }) {
  const {
    tasks,
    activeTaskId,
    setActiveTaskId,
    removeTask,
    getTaskList,
    getRunningTasksCount,
    // History (Eigent migration)
    historyTasks,
    historyLoading,
    loadHistoryTasks,
    selectHistoryTask,
  } = useAgentStore();

  const [isCollapsed, setIsCollapsed] = useState(collapsed);

  // Load history on mount
  useEffect(() => {
    loadHistoryTasks();
  }, [loadHistoryTasks]);

  // Merge in-memory tasks with backend history
  // In-memory tasks take precedence (fresher state)
  // Key insight: frontend uses local taskId, backend uses backendTaskId
  // We need to match by backendTaskId to avoid duplicates
  const taskList = useMemo(() => {
    const taskMap = new Map();

    // Add history tasks first (backend data)
    // Key = backend task_id
    historyTasks.forEach(task => {
      taskMap.set(task.task_id, {
        id: task.task_id,  // Use backend ID for consistency
        backendTaskId: task.task_id,
        taskDescription: task.task,
        status: task.status,
        createdAt: task.created_at,
        startedAt: task.started_at,
        completedAt: task.completed_at,
        loopIteration: task.loop_iterations,
        toolsCount: task.tools_called_count,
        source: 'history',
      });
    });

    // Override with in-memory tasks (current session, fresher data)
    // Use backendTaskId as key to match with history
    Object.entries(tasks).forEach(([localTaskId, task]) => {
      // Use backendTaskId if available, otherwise use local taskId
      const effectiveId = task.backendTaskId || localTaskId;

      taskMap.set(effectiveId, {
        id: localTaskId,  // Keep local ID for store operations
        backendTaskId: task.backendTaskId,
        taskDescription: task.taskDescription,
        status: task.status,
        createdAt: task.createdAt,
        startedAt: task.startedAt,
        completedAt: task.completedAt,
        loopIteration: task.loopIteration,
        toolsCount: task.toolkitEvents?.length || 0,
        source: 'memory',
      });
    });

    // Sort by createdAt (newest first)
    return Array.from(taskMap.values())
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }, [tasks, historyTasks]);

  const runningCount = getRunningTasksCount();

  // Handle task selection (supports both memory and history tasks)
  // task.id = local taskId (for memory tasks) or backendTaskId (for history-only tasks)
  const handleTaskClick = async (task) => {
    const { id, backendTaskId, taskDescription, source } = task;

    // If task is from memory, use its local ID
    if (source === 'memory' && tasks[id]) {
      setActiveTaskId(id);
      return;
    }

    // If task has backendTaskId, check if any in-memory task matches
    if (backendTaskId) {
      const memoryTask = Object.entries(tasks).find(
        ([_, t]) => t.backendTaskId === backendTaskId
      );
      if (memoryTask) {
        setActiveTaskId(memoryTask[0]);
        return;
      }
    }

    // Task not in memory, restore from backend
    await selectHistoryTask(backendTaskId || id, taskDescription);
  };

  // Handle task deletion
  const handleDeleteTask = (taskId) => {
    removeTask(taskId);
  };

  if (isCollapsed) {
    return (
      <div className="task-list collapsed">
        <button
          className="task-list-toggle"
          onClick={() => setIsCollapsed(false)}
          title="Expand task list"
        >
          <Icon name="chevron-right" size={20} />
          {runningCount > 0 && (
            <span className="running-badge">{runningCount}</span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="task-list">
      {/* Header */}
      <div className="task-list-header">
        <div className="task-list-title">
          <span>Tasks</span>
          {taskList.length > 0 && (
            <span className="task-count">{taskList.length}</span>
          )}
        </div>
        <div className="task-list-actions">
          <button
            className="btn-icon-sm"
            onClick={onNewTask}
            title="New Task"
          >
            <Icon name="plus" size={18} />
          </button>
          <button
            className="btn-icon-sm"
            onClick={() => setIsCollapsed(true)}
            title="Collapse"
          >
            <Icon name="chevron-left" size={18} />
          </button>
        </div>
      </div>

      {/* Task List */}
      <div className="task-list-content">
        {historyLoading && taskList.length === 0 ? (
          <div className="task-list-loading">
            <Icon name="loader" size={24} className="spinning" />
            <p>Loading tasks...</p>
          </div>
        ) : taskList.length === 0 ? (
          <div className="task-list-empty">
            <Icon name="inbox" size={32} />
            <p>No tasks yet</p>
            <button className="btn btn-sm btn-primary" onClick={onNewTask}>
              Create Task
            </button>
          </div>
        ) : (
          taskList.map((task) => (
            <TaskListItem
              key={task.backendTaskId || task.id}
              task={task}
              isActive={task.id === activeTaskId || task.backendTaskId === tasks[activeTaskId]?.backendTaskId}
              onClick={() => handleTaskClick(task)}
              onDelete={handleDeleteTask}
            />
          ))
        )}
      </div>

      {/* Status Summary */}
      {taskList.length > 0 && (
        <div className="task-list-summary">
          {runningCount > 0 && (
            <span className="summary-running">
              <Icon name="loader" size={14} className="spinning" />
              {runningCount} running
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default TaskList;
