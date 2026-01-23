/**
 * TaskState Component
 *
 * Displays task status badges with counts and filtering capability.
 * Supports: all, done, reassigned, ongoing, pending, failed states.
 *
 * Ported from Eigent's TaskState component with enhancements.
 */

import React from 'react';
import Icon from '../Icons';

// Task status types
export const TaskStatus = {
  ALL: 'all',
  DONE: 'done',
  REASSIGNED: 'reassigned',
  ONGOING: 'ongoing',
  PENDING: 'pending',
  FAILED: 'failed',
};

// Status configuration
const STATUS_CONFIG = {
  [TaskStatus.ALL]: {
    icon: null,
    label: 'All',
    colorClass: 'state-all',
  },
  [TaskStatus.DONE]: {
    icon: '✓',
    label: 'Done',
    colorClass: 'state-done',
  },
  [TaskStatus.REASSIGNED]: {
    icon: '↻',
    label: 'Reassigned',
    colorClass: 'state-reassigned',
  },
  [TaskStatus.ONGOING]: {
    icon: null, // Uses spinner
    label: 'Ongoing',
    colorClass: 'state-ongoing',
    isSpinner: true,
  },
  [TaskStatus.PENDING]: {
    icon: '◔',
    label: 'Pending',
    colorClass: 'state-pending',
  },
  [TaskStatus.FAILED]: {
    icon: '✗',
    label: 'Failed',
    colorClass: 'state-failed',
  },
};

function TaskState({
  all = 0,
  done = 0,
  reassigned = 0,
  ongoing = 0,
  pending = 0,
  failed = 0,
  selectedState = TaskStatus.ALL,
  onStateChange,
  clickable = true,
  forceVisible = false,
  showAll = true,
  animateOngoing = true,
}) {
  // Handle state click
  const handleClick = (state) => {
    if (!clickable || !onStateChange) return;
    onStateChange(state);
  };

  // Check if state is selected
  const isSelected = (state) => selectedState === state;

  // State badge component
  const StateBadge = ({ state, count }) => {
    // Don't render if count is 0 and not forced visible (except for ALL)
    if (count === 0 && !forceVisible && state !== TaskStatus.ALL) return null;
    // Don't render ALL if showAll is false
    if (state === TaskStatus.ALL && !showAll) return null;

    const config = STATUS_CONFIG[state];

    return (
      <div
        className={`task-state-badge ${config.colorClass} ${isSelected(state) ? 'selected' : ''} ${clickable ? 'clickable' : ''}`}
        onClick={() => handleClick(state)}
      >
        <span className={`badge-icon ${config.isSpinner && animateOngoing ? 'spinning' : ''}`}>
          {config.isSpinner ? (
            <span className="spinner-icon"></span>
          ) : config.icon ? (
            config.icon
          ) : (
            <Icon name="list" size={12} />
          )}
        </span>
        <span className="badge-label">{config.label}</span>
        <span className="badge-count">{count}</span>
      </div>
    );
  };

  return (
    <div className="task-state-container">
      <StateBadge state={TaskStatus.ALL} count={all} />
      <StateBadge state={TaskStatus.DONE} count={done} />
      <StateBadge state={TaskStatus.REASSIGNED} count={reassigned} />
      <StateBadge state={TaskStatus.ONGOING} count={ongoing} />
      <StateBadge state={TaskStatus.PENDING} count={pending} />
      <StateBadge state={TaskStatus.FAILED} count={failed} />
    </div>
  );
}

/**
 * Helper function to calculate task counts from a list of tasks
 */
export function calculateTaskCounts(tasks = []) {
  const counts = {
    all: tasks.length,
    done: 0,
    reassigned: 0,
    ongoing: 0,
    pending: 0,
    failed: 0,
  };

  tasks.forEach((task) => {
    // Reassigned takes priority
    if (task.reAssignTo) {
      counts.reassigned++;
      return;
    }

    const status = task.status || '';

    switch (status) {
      case 'completed':
        counts.done++;
        break;
      case 'failed':
        counts.failed++;
        break;
      case 'running':
      case 'in_progress':
        counts.ongoing++;
        break;
      case 'skipped':
      case 'waiting':
      case '':
        counts.pending++;
        break;
      default:
        counts.pending++;
    }
  });

  return counts;
}

/**
 * Helper function to filter tasks by state
 */
export function filterTasksByState(tasks = [], state) {
  if (state === TaskStatus.ALL) {
    return tasks;
  }

  return tasks.filter((task) => {
    // Reassigned takes priority
    if (task.reAssignTo) {
      return state === TaskStatus.REASSIGNED;
    }

    const status = task.status || '';

    switch (state) {
      case TaskStatus.DONE:
        return status === 'completed';
      case TaskStatus.FAILED:
        return status === 'failed';
      case TaskStatus.ONGOING:
        return status === 'running' || status === 'in_progress';
      case TaskStatus.PENDING:
        return status === 'skipped' || status === 'waiting' || status === '';
      default:
        return true;
    }
  });
}

export default TaskState;
