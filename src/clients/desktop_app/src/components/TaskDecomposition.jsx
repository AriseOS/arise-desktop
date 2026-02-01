/**
 * TaskDecomposition Component
 *
 * Displays task decomposition plan with editable subtasks and auto-confirm timer.
 * Based on Eigent's task confirmation workflow (to_sub_tasks event).
 *
 * Note: Agent assignment is handled by Coordinator during execution, not shown
 * in the planning phase (following Eigent's pattern).
 *
 * Features:
 * - Editable subtask list
 * - Auto-confirm countdown timer (30s default)
 * - Add/remove subtasks
 * - Reorder subtasks
 */
import React, { useState, useEffect, useRef } from 'react';
import Icon from './Icons';
import { AgentBadge } from './AgentNode';

// Default auto-confirm delay in seconds
const DEFAULT_AUTO_CONFIRM_DELAY = 30;

/**
 * Task Decomposition Panel
 */
function TaskDecomposition({
  subtasks = [],
  onConfirm,
  onCancel,
  onEdit,
  autoConfirmDelay = DEFAULT_AUTO_CONFIRM_DELAY,
  isVisible = true,
  title = 'Task Plan',
}) {
  const [editedSubtasks, setEditedSubtasks] = useState(subtasks);
  const [timeLeft, setTimeLeft] = useState(autoConfirmDelay);
  const [isPaused, setIsPaused] = useState(false);
  const timerRef = useRef(null);

  // Update local state when subtasks change
  useEffect(() => {
    setEditedSubtasks(subtasks);
  }, [subtasks]);

  // Auto-confirm countdown
  useEffect(() => {
    if (!isVisible || isPaused || timeLeft <= 0) return;

    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          handleConfirm();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isVisible, isPaused, timeLeft]);

  // Reset timer when subtasks change
  useEffect(() => {
    setTimeLeft(autoConfirmDelay);
    setIsPaused(false);
  }, [subtasks, autoConfirmDelay]);

  const handleConfirm = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    onConfirm?.(editedSubtasks);
  };

  const handleCancel = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    onCancel?.();
  };

  const handlePauseTimer = () => {
    setIsPaused(true);
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
  };

  const handleResumeTimer = () => {
    setIsPaused(false);
  };

  const handleEditTask = (index, field, value) => {
    setEditedSubtasks(prev =>
      prev.map((task, i) =>
        i === index ? { ...task, [field]: value } : task
      )
    );
    onEdit?.(index, field, value);
    // Pause timer when editing
    handlePauseTimer();
  };

  const handleDeleteTask = (index) => {
    setEditedSubtasks(prev => prev.filter((_, i) => i !== index));
    handlePauseTimer();
  };

  const handleAddTask = () => {
    const newTask = {
      id: `task_${Date.now()}`,
      content: '',
      dependencies: [],
      priority: editedSubtasks.length + 1,
    };
    setEditedSubtasks(prev => [...prev, newTask]);
    handlePauseTimer();
  };

  const handleMoveTask = (index, direction) => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= editedSubtasks.length) return;

    const newSubtasks = [...editedSubtasks];
    [newSubtasks[index], newSubtasks[newIndex]] = [newSubtasks[newIndex], newSubtasks[index]];
    setEditedSubtasks(newSubtasks);
    handlePauseTimer();
  };

  if (!isVisible) return null;

  return (
    <div className="task-decomposition-panel">
      {/* Header */}
      <div className="decomposition-header">
        <div className="header-left">
          <span className="header-icon">📋</span>
          <h3>{title}</h3>
          <span className="subtask-count">{editedSubtasks.length} subtasks</span>
        </div>
        <div className="header-right">
          {/* Auto-confirm timer */}
          <div className={`auto-confirm-timer ${isPaused ? 'paused' : ''}`}>
            {isPaused ? (
              <button
                className="timer-btn resume"
                onClick={handleResumeTimer}
                title="Resume auto-confirm"
              >
                <Icon name="play" size={14} />
                <span>Resume</span>
              </button>
            ) : (
              <>
                <span className="timer-label">Auto-confirm in</span>
                <span className="timer-value">{timeLeft}s</span>
                <button
                  className="timer-btn pause"
                  onClick={handlePauseTimer}
                  title="Pause auto-confirm"
                >
                  <Icon name="pause" size={14} />
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Subtasks List */}
      <div className="subtasks-list">
        {editedSubtasks.map((task, index) => (
          <SubtaskItem
            key={task.id || index}
            task={task}
            index={index}
            totalCount={editedSubtasks.length}
            onEdit={(field, value) => handleEditTask(index, field, value)}
            onDelete={() => handleDeleteTask(index)}
            onMoveUp={() => handleMoveTask(index, 'up')}
            onMoveDown={() => handleMoveTask(index, 'down')}
          />
        ))}

        {/* Add Task Button */}
        <button className="add-task-btn" onClick={handleAddTask}>
          <Icon name="plus" size={16} />
          <span>Add Subtask</span>
        </button>
      </div>

      {/* Actions */}
      <div className="decomposition-actions">
        <button className="btn btn-secondary" onClick={handleCancel}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={handleConfirm}
          disabled={editedSubtasks.length === 0}
        >
          <Icon name="check" size={16} />
          <span>Confirm & Execute</span>
        </button>
      </div>
    </div>
  );
}

/**
 * Single subtask item
 */
function SubtaskItem({
  task,
  index,
  totalCount,
  onEdit,
  onDelete,
  onMoveUp,
  onMoveDown,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef(null);

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleContentChange = (e) => {
    onEdit('content', e.target.value);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      setIsEditing(false);
    } else if (e.key === 'Escape') {
      setIsEditing(false);
    }
  };

  return (
    <div className="subtask-item">
      {/* Step Number */}
      <div className="subtask-number">
        <span>{index + 1}</span>
      </div>

      {/* Content */}
      <div className="subtask-content">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={task.content || ''}
            onChange={handleContentChange}
            onBlur={() => setIsEditing(false)}
            onKeyDown={handleKeyDown}
            className="subtask-input"
            placeholder="Describe this subtask..."
          />
        ) : (
          <span
            className="subtask-text"
            onClick={() => setIsEditing(true)}
            title="Click to edit"
          >
            {task.content || task.description || 'Click to edit...'}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="subtask-actions">
        <button
          className="action-btn"
          onClick={onMoveUp}
          disabled={index === 0}
          title="Move up"
        >
          <Icon name="chevronUp" size={14} />
        </button>
        <button
          className="action-btn"
          onClick={onMoveDown}
          disabled={index === totalCount - 1}
          title="Move down"
        >
          <Icon name="chevronDown" size={14} />
        </button>
        <button
          className="action-btn delete"
          onClick={onDelete}
          title="Delete"
        >
          <Icon name="trash" size={14} />
        </button>
      </div>
    </div>
  );
}

/**
 * Compact decomposition summary (for display after confirmation)
 */
export function DecompositionSummary({ subtasks = [], status = 'pending' }) {
  const completedCount = subtasks.filter(t =>
    t.status === 'completed' || t.state === 'completed'
  ).length;

  return (
    <div className="decomposition-summary">
      <div className="summary-header">
        <span className="summary-icon">📋</span>
        <span className="summary-title">Task Plan</span>
        <span className="summary-progress">
          {completedCount}/{subtasks.length}
        </span>
      </div>
      <div className="summary-list">
        {subtasks.map((task, idx) => {
          const taskStatus = task.status || task.state || 'pending';
          return (
            <div key={task.id || idx} className={`summary-item ${taskStatus}`}>
              <span className="summary-number">{idx + 1}</span>
              <span className="summary-content">
                {(task.content || task.description || '').slice(0, 40)}...
              </span>
              <AgentBadge agentType={task.agent_type} size="sm" showName={false} />
              <span className={`summary-status ${taskStatus}`}>
                {taskStatus === 'completed' ? '✓' :
                 taskStatus === 'running' ? '⏳' :
                 taskStatus === 'failed' ? '✕' : '○'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TaskDecomposition;
