/**
 * TaskList Component - Displays list of tasks in sidebar
 *
 * Similar to Eigent's task list pattern.
 * Shows all tasks with status indicators and allows switching between them.
 */

import React, { useEffect, useState } from 'react';
import Icon from '../Icons';
import { useAgentStore } from '../../store';
import { api } from '../../utils/api';
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
  } = useAgentStore();

  const [isCollapsed, setIsCollapsed] = useState(collapsed);

  // Get sorted task list
  const taskList = getTaskList();
  const runningCount = getRunningTasksCount();

  // Handle task selection
  const handleTaskClick = (taskId) => {
    setActiveTaskId(taskId);
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
        {taskList.length === 0 ? (
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
              key={task.id}
              task={task}
              isActive={task.id === activeTaskId}
              onClick={() => handleTaskClick(task.id)}
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
