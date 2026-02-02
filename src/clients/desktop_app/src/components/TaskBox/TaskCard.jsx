/**
 * TaskCard Component
 *
 * Displays task execution status with progress, sub-tasks, and toolkit events.
 * Supports task editing, deletion, and status filtering.
 *
 * Ported from Eigent's TaskCard component with enhancements.
 */

import React, { useState, useMemo, useCallback } from 'react';
import TaskState, { TaskStatus, calculateTaskCounts, filterTasksByState } from './TaskState';
import Icon from '../Icons';

function TaskCard({
  // Task data
  taskInfo = [],
  taskRunning = [],
  toolkitEvents = [],
  summaryTask = '',
  progressValue = 0,
  taskType = 1, // 1: manual tasks, 2: agent-assigned tasks
  // Worker assignments (from agentStore.subtaskAssignments)
  subtaskAssignments = {},
  // Decomposition progress (Phase 5)
  decompositionProgress = 0,
  decompositionMessage = '',
  decompositionStatus = 'pending', // pending | decomposing | completed
  // Interaction
  isExpanded: initialExpanded = true,
  onTaskClick,
  onAddTask,
  onUpdateTask,
  onDeleteTask,
  // Display options
  showToolkits = true,
  showProgress = true,
  showWorkerAssignments = true,
  showDecompositionProgress = true,
  maxToolkitEvents = 5,
  editable = false,
}) {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [selectedState, setSelectedState] = useState(TaskStatus.ALL);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editingContent, setEditingContent] = useState('');

  // Get active tasks (prefer taskRunning over taskInfo)
  const activeTasks = useMemo(() => {
    return taskRunning.length > 0 ? taskRunning : taskInfo;
  }, [taskInfo, taskRunning]);

  // Calculate task counts using helper
  const counts = useMemo(() => {
    return calculateTaskCounts(activeTasks.filter(t => t.content !== ''));
  }, [activeTasks]);

  // Filter tasks based on selected state using helper
  const filteredTasks = useMemo(() => {
    return filterTasksByState(activeTasks, selectedState);
  }, [activeTasks, selectedState]);

  // Handle task edit
  const handleStartEdit = useCallback((task) => {
    if (!editable) return;
    setEditingTaskId(task.id);
    setEditingContent(task.content);
  }, [editable]);

  const handleSaveEdit = useCallback((taskId) => {
    if (onUpdateTask && editingContent.trim()) {
      onUpdateTask(taskId, { content: editingContent.trim() });
    }
    setEditingTaskId(null);
    setEditingContent('');
  }, [onUpdateTask, editingContent]);

  const handleCancelEdit = useCallback(() => {
    setEditingTaskId(null);
    setEditingContent('');
  }, []);

  const handleKeyDown = useCallback((e, taskId) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSaveEdit(taskId);
    } else if (e.key === 'Escape') {
      handleCancelEdit();
    }
  }, [handleSaveEdit, handleCancelEdit]);

  // Handle task delete
  const handleDelete = useCallback((taskId) => {
    if (onDeleteTask) {
      onDeleteTask(taskId);
    }
  }, [onDeleteTask]);

  // Get status icon
  const getStatusIcon = (status, task) => {
    // Reassigned takes priority
    if (task?.reAssignTo) {
      return <span className="status-icon reassigned">↻</span>;
    }

    switch (status) {
      case 'completed':
        return <span className="status-icon success">✓</span>;
      case 'running':
      case 'in_progress':
        return <span className="status-icon running"><span className="spinner small"></span></span>;
      case 'waiting':
        return <span className="status-icon waiting">⏳</span>;
      case 'failed':
        return <span className="status-icon error">✗</span>;
      case 'blocked':
        return <span className="status-icon warning">⚠</span>;
      case 'skipped':
      case '':
      default:
        return <span className="status-icon pending">○</span>;
    }
  };

  // Get status class
  const getStatusClass = (status, task) => {
    if (task?.reAssignTo) return 'task-reassigned';

    switch (status) {
      case 'completed':
        return 'task-completed';
      case 'running':
      case 'in_progress':
        return 'task-running';
      case 'waiting':
        return 'task-waiting';
      case 'failed':
        return 'task-failed';
      case 'blocked':
        return 'task-blocked';
      default:
        return 'task-pending';
    }
  };

  // Format task ID for display (e.g., "1.2.3" from "task.1.2.3")
  const formatTaskId = (taskId) => {
    if (!taskId) return '';
    const parts = taskId.split('.');

    // Handle different ID formats:
    // - "task.1.2" -> "1.2"
    // - "abc123.main" -> "main"
    // - "abc123.1" -> "1"
    if (parts.length === 1) return parts[0];

    // Remove the prefix (first part)
    parts.shift();

    // Convert numeric parts to numbers, keep non-numeric as-is
    return parts.map(p => {
      const num = Number(p);
      return isNaN(num) ? p : num;
    }).join('.');
  };

  // Get worker assignment for a task
  const getWorkerAssignment = useCallback((taskId) => {
    if (!showWorkerAssignments || !subtaskAssignments) return null;
    return subtaskAssignments[taskId] || null;
  }, [showWorkerAssignments, subtaskAssignments]);

  // Get worker status icon
  const getWorkerStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <span className="worker-status-icon running"><span className="spinner small"></span></span>;
      case 'completed':
        return <span className="worker-status-icon completed">✓</span>;
      case 'failed':
        return <span className="worker-status-icon failed">✗</span>;
      case 'assigned':
      default:
        return <span className="worker-status-icon assigned">→</span>;
    }
  };

  return (
    <div className={`task-card task-type-${taskType}`}>
      {/* Progress bar */}
      {showProgress && (
        <div className="task-progress-bar">
          <div
            className="task-progress-fill"
            style={{ width: `${progressValue}%` }}
          />
        </div>
      )}

      {/* Decomposition progress bar (Phase 5) */}
      {showDecompositionProgress && decompositionStatus === 'decomposing' && (
        <div className="decomposition-progress-container">
          <div className="decomposition-progress-bar">
            <div
              className="decomposition-progress-fill"
              style={{ width: `${decompositionProgress}%` }}
            />
          </div>
          <div className="decomposition-progress-text">
            <span className="progress-message">
              {decompositionMessage || 'Decomposing...'}
            </span>
            <span className="progress-percent">
              {decompositionProgress}%
            </span>
          </div>
        </div>
      )}

      {/* Task summary */}
      {summaryTask && (
        <div className="task-summary">
          <span className="summary-title">
            {summaryTask.split('|')[0]?.replace(/"/g, '')}
          </span>
        </div>
      )}

      {/* Header with task type and state filters */}
      <div className="task-card-header">
        <div className="task-card-header-left">
          <span className={`task-type-badge type-${taskType}`}>
            {taskType === 1 ? 'Manual' : taskType === 2 ? 'Agent' : 'Tasks'}
          </span>
          <TaskState
            all={counts.all}
            done={counts.done}
            reassigned={counts.reassigned}
            ongoing={counts.ongoing}
            pending={counts.pending}
            failed={counts.failed}
            selectedState={selectedState}
            onStateChange={setSelectedState}
            showAll={false}
          />
        </div>

        <button
          className="task-expand-btn"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <span className="expand-count">
            {counts.done}/{counts.all}
          </span>
          <Icon
            name="chevron"
            size={16}
            className={`expand-icon ${isExpanded ? 'expanded' : ''}`}
          />
        </button>
      </div>

      {/* Task list */}
      {isExpanded && (
        <div className="task-list">
          {filteredTasks.map((task, index) => (
            <div
              key={task.id || index}
              className={`task-item ${getStatusClass(task.status, task)}`}
              onClick={() => !editingTaskId && onTaskClick && onTaskClick(task)}
            >
              <div className="task-item-icon">
                {getStatusIcon(task.status, task)}
              </div>

              <div className="task-item-content">
                {/* Task number and badges */}
                <div className="task-item-header">
                  {task.id && (
                    <span className="task-number">No. {formatTaskId(task.id)}</span>
                  )}
                  {/* Worker assignment badge */}
                  {(() => {
                    const assignment = getWorkerAssignment(task.id);
                    if (assignment) {
                      return (
                        <span className={`task-badge worker-badge ${assignment.status || 'assigned'}`}>
                          {getWorkerStatusIcon(assignment.status)}
                          <span className="worker-name">{assignment.workerName || assignment.workerId}</span>
                        </span>
                      );
                    }
                    return null;
                  })()}
                  {task.reAssignTo && (
                    <span className="task-badge reassigned">
                      Reassigned to {task.reAssignTo}
                    </span>
                  )}
                  {(task.failure_count || 0) > 0 && !task.reAssignTo && (
                    <span className={`task-badge ${task.status === 'failed' ? 'failed' : task.status === 'completed' ? 'success' : ''}`}>
                      Attempt {task.failure_count}
                    </span>
                  )}
                </div>

                {/* Task content - editable or display */}
                {editingTaskId === task.id ? (
                  <div className="task-edit-container">
                    <input
                      type="text"
                      value={editingContent}
                      onChange={(e) => setEditingContent(e.target.value)}
                      onKeyDown={(e) => handleKeyDown(e, task.id)}
                      autoFocus
                      className="task-edit-input"
                    />
                    <div className="task-edit-actions">
                      <button className="task-edit-btn save" onClick={() => handleSaveEdit(task.id)}>
                        Save
                      </button>
                      <button className="task-edit-btn cancel" onClick={handleCancelEdit}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <span
                    className="task-item-text"
                    onDoubleClick={() => handleStartEdit(task)}
                  >
                    {task.content}
                  </span>
                )}

                {/* Task report */}
                {task.report && (
                  <div className="task-item-report">{task.report}</div>
                )}
              </div>

              {/* Edit/Delete actions */}
              {editable && !editingTaskId && (
                <div className="task-item-actions">
                  <button
                    className="task-action-btn edit"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStartEdit(task);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    className="task-action-btn delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(task.id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>
          ))}

          {/* Add task button */}
          {editable && onAddTask && (
            <button className="task-add-btn" onClick={onAddTask}>
              <span>+</span> Add Task
            </button>
          )}
        </div>
      )}

      {/* Toolkit events */}
      {showToolkits && toolkitEvents.length > 0 && (
        <div className="toolkit-events">
          <div className="toolkit-header">
            <span className="toolkit-label">Toolkit Activity</span>
            <span className="toolkit-count">{toolkitEvents.length}</span>
          </div>
          <div className="toolkit-events-list">
            {toolkitEvents.slice(-maxToolkitEvents).map((event, index) => (
              <div
                key={event.id || index}
                className={`toolkit-event ${event.status || ''}`}
              >
                <span className="toolkit-icon">
                  {event.status === 'running' && <span className="spinner small"></span>}
                  {event.status === 'completed' && <span className="icon-success">✓</span>}
                  {event.status === 'failed' && <span className="icon-error">✗</span>}
                </span>
                <span className="toolkit-name">{event.toolkit_name}</span>
                <span className="toolkit-method">.{event.method_name}()</span>
                {event.input_preview && (
                  <span className="toolkit-preview" title={event.input_preview}>
                    {event.input_preview.slice(0, 30)}...
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default TaskCard;
