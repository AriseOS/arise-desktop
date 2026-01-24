/**
 * WorkforceStatusPanel Component
 *
 * Displays the status of all workers in the workforce.
 * Shows worker list, their current status, and task assignments.
 *
 * Features:
 * - Real-time worker status updates (idle, running, completed, failed)
 * - Task count summary (pending, running, completed, failed)
 * - Worker progress indicators
 * - Collapsible worker details
 *
 * Based on Eigent's workforce UI patterns.
 */

import React, { useState, useMemo } from 'react';
import Icon from '../Icons';
import './WorkforceStatusPanel.css';

// Worker status enum
const WorkerStatus = {
  IDLE: 'idle',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
};

// Get status icon for worker
const getStatusIcon = (status) => {
  switch (status) {
    case WorkerStatus.RUNNING:
      return <span className="worker-status-icon running"><span className="spinner small"></span></span>;
    case WorkerStatus.COMPLETED:
      return <span className="worker-status-icon completed">✓</span>;
    case WorkerStatus.FAILED:
      return <span className="worker-status-icon failed">✗</span>;
    case WorkerStatus.IDLE:
    default:
      return <span className="worker-status-icon idle">○</span>;
  }
};

// Get status class for styling
const getStatusClass = (status) => {
  switch (status) {
    case WorkerStatus.RUNNING:
      return 'status-running';
    case WorkerStatus.COMPLETED:
      return 'status-completed';
    case WorkerStatus.FAILED:
      return 'status-failed';
    case WorkerStatus.IDLE:
    default:
      return 'status-idle';
  }
};

// Worker card component
function WorkerCard({ worker, isActive, onClick }) {
  const statusClass = getStatusClass(worker.status);

  return (
    <div
      className={`worker-card ${statusClass} ${isActive ? 'active' : ''}`}
      onClick={() => onClick && onClick(worker)}
    >
      <div className="worker-card-header">
        <div className="worker-icon">
          <Icon name="bot" size={20} />
        </div>
        <div className="worker-info">
          <span className="worker-name">{worker.name || worker.id}</span>
          <span className="worker-type">{worker.type || 'Agent'}</span>
        </div>
        <div className="worker-status">
          {getStatusIcon(worker.status)}
        </div>
      </div>

      {worker.currentTaskId && (
        <div className="worker-current-task">
          <span className="task-label">Working on:</span>
          <span className="task-id">{worker.currentTaskId}</span>
        </div>
      )}

      {worker.progress !== undefined && worker.status === WorkerStatus.RUNNING && (
        <div className="worker-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${worker.progress}%` }}
            />
          </div>
          <span className="progress-text">{worker.progress}%</span>
        </div>
      )}
    </div>
  );
}

// Main component
function WorkforceStatusPanel({
  workforce = {},
  subtaskAssignments = {},
  isCollapsed: initialCollapsed = false,
  onWorkerClick,
  onToggleCollapse,
}) {
  const [isCollapsed, setIsCollapsed] = useState(initialCollapsed);

  // Extract data from workforce state
  const {
    workers = [],
    pendingTasks = 0,
    runningTasks = 0,
    completedTasks = 0,
    failedTasks = 0,
    totalTasks = 0,
    isActive = false,
  } = workforce;

  // Calculate summary stats
  const summary = useMemo(() => {
    const runningWorkers = workers.filter(w => w.status === WorkerStatus.RUNNING).length;
    const idleWorkers = workers.filter(w => w.status === WorkerStatus.IDLE).length;

    return {
      totalWorkers: workers.length,
      runningWorkers,
      idleWorkers,
      completedPercentage: totalTasks > 0
        ? Math.round((completedTasks / totalTasks) * 100)
        : 0,
    };
  }, [workers, completedTasks, totalTasks]);

  // Toggle collapse
  const handleToggle = () => {
    const newCollapsed = !isCollapsed;
    setIsCollapsed(newCollapsed);
    if (onToggleCollapse) {
      onToggleCollapse(newCollapsed);
    }
  };

  // Don't render if workforce is not active and has no workers
  if (!isActive && workers.length === 0) {
    return null;
  }

  return (
    <div className={`workforce-status-panel ${isCollapsed ? 'collapsed' : ''}`}>
      {/* Header */}
      <div className="workforce-header" onClick={handleToggle}>
        <div className="workforce-header-left">
          <span className="workforce-icon">👥</span>
          <span className="workforce-title">AI Workforce</span>
          {isActive && (
            <span className="workforce-active-badge">
              <span className="pulse-dot"></span>
              Active
            </span>
          )}
        </div>

        <div className="workforce-header-right">
          {/* Task summary badges */}
          <div className="workforce-summary">
            {pendingTasks > 0 && (
              <span className="summary-badge pending">
                <span className="badge-icon">○</span>
                {pendingTasks}
              </span>
            )}
            {runningTasks > 0 && (
              <span className="summary-badge running">
                <span className="spinner small"></span>
                {runningTasks}
              </span>
            )}
            {completedTasks > 0 && (
              <span className="summary-badge completed">
                <span className="badge-icon">✓</span>
                {completedTasks}
              </span>
            )}
            {failedTasks > 0 && (
              <span className="summary-badge failed">
                <span className="badge-icon">✗</span>
                {failedTasks}
              </span>
            )}
          </div>

          {/* Worker count */}
          <span className="workforce-worker-count">
            {summary.runningWorkers}/{summary.totalWorkers} workers
          </span>

          {/* Expand/collapse icon */}
          <Icon
            name="chevron"
            size={16}
            className={`expand-icon ${isCollapsed ? '' : 'expanded'}`}
          />
        </div>
      </div>

      {/* Progress bar */}
      {totalTasks > 0 && (
        <div className="workforce-progress-bar">
          <div
            className="workforce-progress-fill"
            style={{ width: `${summary.completedPercentage}%` }}
          />
        </div>
      )}

      {/* Worker list */}
      {!isCollapsed && workers.length > 0 && (
        <div className="workforce-workers-list">
          {workers.map((worker) => (
            <WorkerCard
              key={worker.id}
              worker={worker}
              isActive={worker.status === WorkerStatus.RUNNING}
              onClick={onWorkerClick}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isCollapsed && workers.length === 0 && isActive && (
        <div className="workforce-empty">
          <span>Initializing workers...</span>
        </div>
      )}
    </div>
  );
}

export { WorkerStatus };
export default WorkforceStatusPanel;
