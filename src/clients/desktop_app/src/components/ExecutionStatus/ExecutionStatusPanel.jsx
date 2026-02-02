/**
 * ExecutionStatusPanel Component
 *
 * Displays real-time execution status of subtasks during Workforce execution.
 * Shows which subtask is being executed and by which agent.
 *
 * Features:
 * - Subtask list with status indicators (pending, running, completed, failed)
 * - Agent type badges (browser, document, code)
 * - Worker name display
 * - Progress summary
 */

import React, { useMemo } from 'react';
import { AgentBadge, getAgentConfig } from '../AgentNode/AgentNode';
import Icon from '../Icons';
import './ExecutionStatusPanel.css';

// Subtask state to display mapping
const STATE_CONFIG = {
  OPEN: { icon: '○', class: 'state-pending', label: 'Pending' },
  ASSIGNED: { icon: '◐', class: 'state-assigned', label: 'Assigned' },
  RUNNING: { icon: null, class: 'state-running', label: 'Running' }, // Uses spinner
  DONE: { icon: '✓', class: 'state-completed', label: 'Completed' },
  FAILED: { icon: '✗', class: 'state-failed', label: 'Failed' },
  // Lowercase variants for compatibility
  pending: { icon: '○', class: 'state-pending', label: 'Pending' },
  assigned: { icon: '◐', class: 'state-assigned', label: 'Assigned' },
  running: { icon: null, class: 'state-running', label: 'Running' },
  completed: { icon: '✓', class: 'state-completed', label: 'Completed' },
  done: { icon: '✓', class: 'state-completed', label: 'Completed' },
  failed: { icon: '✗', class: 'state-failed', label: 'Failed' },
};

/**
 * Get state configuration
 */
function getStateConfig(state) {
  return STATE_CONFIG[state] || STATE_CONFIG.OPEN;
}

/**
 * Status icon component
 */
function StatusIcon({ state }) {
  const config = getStateConfig(state);

  if (state === 'RUNNING' || state === 'running') {
    return (
      <span className={`status-icon ${config.class}`}>
        <span className="spinner small" />
      </span>
    );
  }

  return (
    <span className={`status-icon ${config.class}`} title={config.label}>
      {config.icon}
    </span>
  );
}

/**
 * Single subtask row
 */
function SubtaskRow({ subtask, index }) {
  const { id, content, state, agent_type, worker_name, assignee_id } = subtask;
  const stateConfig = getStateConfig(state);
  const isRunning = state === 'RUNNING' || state === 'running';
  const isCompleted = state === 'DONE' || state === 'done' || state === 'completed';
  const isFailed = state === 'FAILED' || state === 'failed';

  // Truncate content for display
  const displayContent = content && content.length > 80
    ? content.substring(0, 80) + '...'
    : content;

  return (
    <div className={`subtask-row ${stateConfig.class} ${isRunning ? 'is-running' : ''}`}>
      {/* Step number */}
      <div className="subtask-number">
        <span>{index + 1}</span>
      </div>

      {/* Content */}
      <div className="subtask-content">
        <span className="subtask-text" title={content}>
          {displayContent}
        </span>
        {/* Show worker info when assigned/running */}
        {(worker_name || assignee_id) && (
          <span className="subtask-worker">
            {worker_name || assignee_id}
          </span>
        )}
      </div>

      {/* Agent type badge */}
      <div className="subtask-agent">
        {agent_type ? (
          <AgentBadge agentType={agent_type} size="sm" showName={false} />
        ) : (
          <span className="no-agent">-</span>
        )}
      </div>

      {/* Status */}
      <div className="subtask-status">
        <StatusIcon state={state} />
      </div>
    </div>
  );
}

/**
 * Progress summary bar
 */
function ProgressSummary({ totalTasks, completedTasks, runningTasks, failedTasks }) {
  const pendingTasks = totalTasks - completedTasks - runningTasks - failedTasks;
  const progress = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  return (
    <div className="execution-progress">
      {/* Progress bar */}
      <div className="progress-bar-container">
        <div
          className="progress-bar-fill"
          style={{ width: `${progress}%` }}
        />
        {failedTasks > 0 && (
          <div
            className="progress-bar-failed"
            style={{ width: `${(failedTasks / totalTasks) * 100}%` }}
          />
        )}
      </div>

      {/* Status badges */}
      <div className="progress-badges">
        {pendingTasks > 0 && (
          <span className="badge badge-pending">
            <span className="badge-icon">○</span>
            <span className="badge-count">{pendingTasks}</span>
          </span>
        )}
        {runningTasks > 0 && (
          <span className="badge badge-running">
            <span className="spinner tiny" />
            <span className="badge-count">{runningTasks}</span>
          </span>
        )}
        {completedTasks > 0 && (
          <span className="badge badge-completed">
            <span className="badge-icon">✓</span>
            <span className="badge-count">{completedTasks}</span>
          </span>
        )}
        {failedTasks > 0 && (
          <span className="badge badge-failed">
            <span className="badge-icon">✗</span>
            <span className="badge-count">{failedTasks}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Main ExecutionStatusPanel component
 */
function ExecutionStatusPanel({
  executionState = {},
  isCollapsed: initialCollapsed = false,
  onToggleCollapse,
}) {
  const {
    subtasks = [],
    isActive = false,
    totalTasks = 0,
    completedTasks = 0,
    runningTasks = 0,
    failedTasks = 0,
  } = executionState;

  const [isCollapsed, setIsCollapsed] = React.useState(initialCollapsed);

  // Calculate actual counts from subtasks if not provided
  const counts = useMemo(() => {
    if (subtasks.length === 0) {
      return { total: totalTasks, completed: completedTasks, running: runningTasks, failed: failedTasks };
    }

    const completed = subtasks.filter(s =>
      s.state === 'DONE' || s.state === 'done' || s.state === 'completed'
    ).length;
    const running = subtasks.filter(s =>
      s.state === 'RUNNING' || s.state === 'running'
    ).length;
    const failed = subtasks.filter(s =>
      s.state === 'FAILED' || s.state === 'failed'
    ).length;

    return {
      total: subtasks.length,
      completed,
      running,
      failed,
    };
  }, [subtasks, totalTasks, completedTasks, runningTasks, failedTasks]);

  // Don't render if no subtasks
  if (subtasks.length === 0 && !isActive) {
    return null;
  }

  const handleToggle = () => {
    const newCollapsed = !isCollapsed;
    setIsCollapsed(newCollapsed);
    onToggleCollapse?.(newCollapsed);
  };

  return (
    <div className={`execution-status-panel ${isCollapsed ? 'collapsed' : ''}`}>
      {/* Header */}
      <div className="execution-header" onClick={handleToggle}>
        <div className="header-left">
          <span className="header-icon">🏃</span>
          <span className="header-title">Execution Status</span>
          {isActive && (
            <span className="active-badge">
              <span className="pulse-dot" />
              Active
            </span>
          )}
        </div>

        <div className="header-right">
          <span className="task-count">
            {counts.completed}/{counts.total}
          </span>
          <Icon
            name="chevron"
            size={16}
            className={`expand-icon ${isCollapsed ? '' : 'expanded'}`}
          />
        </div>
      </div>

      {/* Progress */}
      <ProgressSummary
        totalTasks={counts.total}
        completedTasks={counts.completed}
        runningTasks={counts.running}
        failedTasks={counts.failed}
      />

      {/* Subtask list */}
      {!isCollapsed && subtasks.length > 0 && (
        <div className="subtask-list">
          <div className="subtask-list-header">
            <span className="col-number">#</span>
            <span className="col-content">Subtask</span>
            <span className="col-agent">Agent</span>
            <span className="col-status">Status</span>
          </div>
          {subtasks.map((subtask, index) => (
            <SubtaskRow
              key={subtask.id || index}
              subtask={subtask}
              index={index}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default ExecutionStatusPanel;
