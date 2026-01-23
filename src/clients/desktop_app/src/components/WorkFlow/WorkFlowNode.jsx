/**
 * WorkFlowNode Component
 *
 * Custom node component for React Flow that displays agent information.
 * Used within the WorkFlow component.
 *
 * Features:
 * - Expandable/collapsible view
 * - Agent status and progress display
 * - Task list with status filtering
 * - Toolkit execution logs
 * - Webview screenshots grid
 */

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { NodeResizer } from '@xyflow/react';
import TaskState, { TaskStatus, calculateTaskCounts, filterTasksByState } from '../TaskBox/TaskState';
import Icon from '../Icons';

// Agent type configurations
const AGENT_CONFIGS = {
  browser: {
    icon: '🌐',
    color: '#3B82F6',
    bgColor: 'rgba(59, 130, 246, 0.08)',
    borderColor: 'rgba(59, 130, 246, 0.2)',
    name: 'Browser Agent',
  },
  coder: {
    icon: '💻',
    color: '#10B981',
    bgColor: 'rgba(16, 185, 129, 0.08)',
    borderColor: 'rgba(16, 185, 129, 0.2)',
    name: 'Developer Agent',
  },
  document: {
    icon: '📄',
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.08)',
    borderColor: 'rgba(245, 158, 11, 0.2)',
    name: 'Document Agent',
  },
  reasoner: {
    icon: '🧠',
    color: '#9333EA',
    bgColor: 'rgba(147, 51, 234, 0.08)',
    borderColor: 'rgba(147, 51, 234, 0.2)',
    name: 'Reasoner',
  },
  social: {
    icon: '💬',
    color: '#EC4899',
    bgColor: 'rgba(236, 72, 153, 0.08)',
    borderColor: 'rgba(236, 72, 153, 0.2)',
    name: 'Social Agent',
  },
  default: {
    icon: '🤖',
    color: '#6366F1',
    bgColor: 'rgba(99, 102, 241, 0.08)',
    borderColor: 'rgba(99, 102, 241, 0.2)',
    name: 'Agent',
  },
};

// Status colors
const STATUS_COLORS = {
  idle: '#9CA3AF',
  active: null, // Use agent color
  completed: '#10B981',
  error: '#EF4444',
};

function WorkFlowNode({ id, data, selected }) {
  const {
    agent,
    isExpanded = false,
    isActive = false,
    currentTool = null,
    toolkitEvents = [],
    screenshots = [],
    onExpandChange,
    onClick,
  } = data;

  const {
    agent_id,
    name,
    type = 'default',
    status = 'idle',
    tasks = [],
    tools = [],
    progress = 0,
    completionReport = null,
  } = agent || {};

  const config = AGENT_CONFIGS[type] || AGENT_CONFIGS.default;
  const nodeRef = useRef(null);
  const [selectedTaskState, setSelectedTaskState] = useState(TaskStatus.ALL);

  // Prevent wheel events from propagating to canvas
  useEffect(() => {
    const node = nodeRef.current;
    if (!node) return;

    const handleWheel = (e) => {
      e.stopPropagation();
    };

    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, []);

  // Calculate task counts
  const taskCounts = useMemo(() => {
    return calculateTaskCounts(tasks);
  }, [tasks]);

  // Filter tasks
  const filteredTasks = useMemo(() => {
    return filterTasksByState(tasks, selectedTaskState);
  }, [tasks, selectedTaskState]);

  // Get status color
  const statusColor = useMemo(() => {
    if (status === 'active') return config.color;
    return STATUS_COLORS[status] || STATUS_COLORS.idle;
  }, [status, config.color]);

  // Handle expand toggle
  const handleToggleExpand = useCallback(
    (e) => {
      e.stopPropagation();
      if (onExpandChange) {
        onExpandChange(id, !isExpanded);
      }
    },
    [id, isExpanded, onExpandChange]
  );

  // Handle node click
  const handleClick = useCallback(
    (e) => {
      e.stopPropagation();
      if (onClick) {
        onClick();
      }
    },
    [onClick]
  );

  // Get task status icon
  const getTaskStatusIcon = (taskStatus, task) => {
    if (task?.reAssignTo) {
      return <span className="task-status-icon reassigned">↻</span>;
    }
    switch (taskStatus) {
      case 'completed':
        return <span className="task-status-icon success">✓</span>;
      case 'running':
      case 'in_progress':
        return <span className="task-status-icon running"><span className="spinner-tiny"></span></span>;
      case 'failed':
        return <span className="task-status-icon error">✗</span>;
      case 'blocked':
        return <span className="task-status-icon warning">⚠</span>;
      default:
        return <span className="task-status-icon pending">○</span>;
    }
  };

  const displayTasks = filteredTasks.slice(0, 5);
  const remainingTasks = filteredTasks.length - 5;
  const displayScreenshots = screenshots.slice(0, 4);

  return (
    <div
      ref={nodeRef}
      className={`workflow-node ${isExpanded ? 'expanded' : ''} ${isActive ? 'active' : ''} ${selected ? 'selected' : ''}`}
      style={{
        '--agent-color': config.color,
        '--agent-bg': config.bgColor,
        '--agent-border': isActive ? config.color : config.borderColor,
        width: isExpanded ? 640 : 320,
      }}
      onClick={handleClick}
    >
      {/* Node Resizer (only in edit mode) */}
      {selected && (
        <NodeResizer
          minWidth={320}
          maxWidth={800}
          minHeight={200}
          handleStyle={{ width: 8, height: 8 }}
        />
      )}

      {/* Header */}
      <div className="node-header">
        <div className="node-header-left">
          <span className="node-icon">{config.icon}</span>
          <div className="node-title-group">
            <span className="node-name">{name || config.name}</span>
            <span className="node-type">{type}</span>
          </div>
        </div>
        <div className="node-header-right">
          <div className="node-status">
            <span
              className="status-dot"
              style={{
                background: statusColor,
                animation: status === 'active' ? 'pulse 1.5s ease-in-out infinite' : 'none',
              }}
            />
            <span className="status-label">{status}</span>
          </div>
          <button
            className="node-expand-btn"
            onClick={handleToggleExpand}
            title={isExpanded ? 'Collapse' : 'Expand'}
          >
            <Icon
              name="chevron"
              size={14}
              className={`expand-icon ${isExpanded ? 'expanded' : ''}`}
            />
          </button>
        </div>
      </div>

      {/* Current Tool */}
      {currentTool && status === 'active' && (
        <div className="node-current-tool">
          <span className="tool-indicator">Using:</span>
          <span className="tool-name shiny-text">{currentTool}</span>
        </div>
      )}

      {/* Progress */}
      {progress > 0 && (
        <div className="node-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${Math.min(progress, 100)}%` }}
            />
          </div>
          <span className="progress-text">{Math.round(progress)}%</span>
        </div>
      )}

      {/* Summary (collapsed) */}
      {!isExpanded && tasks.length > 0 && (
        <div className="node-summary">
          <span className="summary-stat">
            {taskCounts.done}/{taskCounts.all} tasks
          </span>
          {toolkitEvents.length > 0 && (
            <span className="summary-stat">{toolkitEvents.length} tool calls</span>
          )}
        </div>
      )}

      {/* Expanded Content */}
      {isExpanded && (
        <div className="node-content">
          {/* Tools list */}
          {tools.length > 0 && (
            <div className="node-tools">
              <div className="section-header">Tools</div>
              <div className="tools-list">
                {tools.slice(0, 4).map((tool, index) => (
                  <span key={index} className="tool-tag">
                    {tool}
                  </span>
                ))}
                {tools.length > 4 && (
                  <span className="tool-tag more">+{tools.length - 4}</span>
                )}
              </div>
            </div>
          )}

          {/* Tasks */}
          {tasks.length > 0 && (
            <div className="node-tasks">
              <div className="section-header">Tasks</div>
              <TaskState
                all={taskCounts.all}
                done={taskCounts.done}
                reassigned={taskCounts.reassigned}
                ongoing={taskCounts.ongoing}
                pending={taskCounts.pending}
                failed={taskCounts.failed}
                selectedState={selectedTaskState}
                onStateChange={setSelectedTaskState}
                showAll={false}
                compact={true}
              />
              <div className="tasks-list">
                {displayTasks.map((task, index) => (
                  <div
                    key={task.id || index}
                    className={`task-row ${task.status || ''}`}
                  >
                    {getTaskStatusIcon(task.status, task)}
                    <span className="task-content">
                      {task.content || task.name || task.description}
                    </span>
                    {task.reAssignTo && (
                      <span className="task-badge reassigned">→ {task.reAssignTo}</span>
                    )}
                  </div>
                ))}
                {remainingTasks > 0 && (
                  <div className="tasks-more">+{remainingTasks} more tasks</div>
                )}
              </div>
            </div>
          )}

          {/* Toolkit Events */}
          {toolkitEvents.length > 0 && (
            <div className="node-toolkit-events">
              <div className="section-header">Recent Activity</div>
              <div className="events-list">
                {toolkitEvents.slice(-3).map((event, index) => (
                  <div key={event.id || index} className={`event-row ${event.status || ''}`}>
                    <span className="event-icon">
                      {event.status === 'running' && <span className="spinner-tiny"></span>}
                      {event.status === 'completed' && '✓'}
                      {event.status === 'failed' && '✗'}
                    </span>
                    <span className="event-name">{event.toolkit_name}</span>
                    <span className="event-method">.{event.method_name}()</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Screenshots */}
          {displayScreenshots.length > 0 && (
            <div className="node-screenshots">
              <div className="section-header">Screenshots</div>
              <div className="screenshots-grid">
                {displayScreenshots.map((screenshot, index) => (
                  <div key={index} className="screenshot-thumb">
                    <img
                      src={screenshot.url || screenshot}
                      alt={screenshot.title || `Screenshot ${index + 1}`}
                      loading="lazy"
                    />
                  </div>
                ))}
              </div>
              {screenshots.length > 4 && (
                <div className="screenshots-more">+{screenshots.length - 4} more</div>
              )}
            </div>
          )}

          {/* Completion Report */}
          {completionReport && (
            <div className="node-report">
              <div className="section-header">Report</div>
              <div className="report-content">{completionReport}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default WorkFlowNode;
