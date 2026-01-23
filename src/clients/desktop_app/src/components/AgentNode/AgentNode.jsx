/**
 * AgentNode Component
 *
 * Displays agent information including status, current tool, progress, tasks,
 * toolkit execution logs, webview screenshots, and completion reports.
 *
 * Enhanced from eigent's agent display components with full feature parity.
 */

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import TaskState, { TaskStatus, calculateTaskCounts, filterTasksByState } from '../TaskBox/TaskState';
import Icon from '../Icons';

// Agent status types
export const AgentStatus = {
  IDLE: 'idle',
  ACTIVE: 'active',
  COMPLETED: 'completed',
  ERROR: 'error',
};

// Agent type configurations
const AGENT_CONFIGS = {
  browser: {
    icon: '🌐',
    color: '#3B82F6',
    bgColor: 'rgba(59, 130, 246, 0.1)',
    borderColor: 'rgba(59, 130, 246, 0.3)',
    name: 'Browser Agent',
  },
  reasoner: {
    icon: '🧠',
    color: '#9333EA',
    bgColor: 'rgba(147, 51, 234, 0.1)',
    borderColor: 'rgba(147, 51, 234, 0.3)',
    name: 'Reasoner',
  },
  coder: {
    icon: '💻',
    color: '#10B981',
    bgColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.3)',
    name: 'Coder Agent',
  },
  document: {
    icon: '📄',
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.1)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
    name: 'Document Agent',
  },
  social: {
    icon: '💬',
    color: '#EC4899',
    bgColor: 'rgba(236, 72, 153, 0.1)',
    borderColor: 'rgba(236, 72, 153, 0.3)',
    name: 'Social Agent',
  },
  default: {
    icon: '🤖',
    color: '#6366F1',
    bgColor: 'rgba(99, 102, 241, 0.1)',
    borderColor: 'rgba(99, 102, 241, 0.3)',
    name: 'Agent',
  },
};

// Toolkit icon mapping
const TOOLKIT_ICONS = {
  browser_control: '🌐',
  file_system: '📁',
  code_executor: '💻',
  web_search: '🔍',
  terminal: '⌨️',
  screenshot: '📷',
  default: '🔧',
};

function AgentNode({
  agent,
  isActive = false,
  currentTool = null,
  progress = 0,
  tasks = [],
  toolkitEvents = [],
  webviewScreenshots = [],
  completionReport = null,
  terminalOutput = null,
  files = [],
  maxTasksDisplay = 5,
  maxToolkitDisplay = 3,
  maxScreenshotsDisplay = 4,
  isExpanded: initialExpanded = false,
  showDetails = true,
  onClick,
  onTaskClick,
  onScreenshotClick,
}) {
  const {
    id,
    name,
    type = 'default',
    status = AgentStatus.IDLE,
  } = agent;

  const config = AGENT_CONFIGS[type] || AGENT_CONFIGS.default;

  // State
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [selectedTaskState, setSelectedTaskState] = useState(TaskStatus.ALL);
  const [activeTab, setActiveTab] = useState('tasks'); // tasks, logs, report
  const contentRef = useRef(null);

  // Sync expanded state with prop
  useEffect(() => {
    setIsExpanded(initialExpanded);
  }, [initialExpanded]);

  // Calculate task counts
  const taskCounts = useMemo(() => {
    return calculateTaskCounts(tasks);
  }, [tasks]);

  // Filter tasks based on selected state
  const filteredTasks = useMemo(() => {
    return filterTasksByState(tasks, selectedTaskState);
  }, [tasks, selectedTaskState]);

  // Get status indicator color
  const getStatusColor = useCallback(() => {
    switch (status) {
      case AgentStatus.ACTIVE:
        return config.color;
      case AgentStatus.COMPLETED:
        return '#10B981';
      case AgentStatus.ERROR:
        return '#EF4444';
      default:
        return '#9CA3AF';
    }
  }, [status, config.color]);

  // Get task status icon
  const getTaskStatusIcon = (taskStatus, task) => {
    if (task?.reAssignTo) {
      return <span className="status-icon reassigned">↻</span>;
    }
    switch (taskStatus) {
      case 'completed':
        return <span className="status-icon success">✓</span>;
      case 'running':
      case 'in_progress':
        return <span className="status-icon running"><span className="spinner-small"></span></span>;
      case 'failed':
        return <span className="status-icon error">✗</span>;
      case 'blocked':
        return <span className="status-icon warning">⚠</span>;
      default:
        return <span className="status-icon pending">○</span>;
    }
  };

  // Get toolkit icon
  const getToolkitIcon = (toolkitName) => {
    const normalizedName = toolkitName?.toLowerCase().replace(/[_-]/g, '_');
    return TOOLKIT_ICONS[normalizedName] || TOOLKIT_ICONS.default;
  };

  // Toggle expanded state
  const handleToggleExpand = useCallback((e) => {
    e.stopPropagation();
    setIsExpanded((prev) => !prev);
  }, []);

  // Handle task click
  const handleTaskClick = useCallback((task) => {
    if (onTaskClick) {
      onTaskClick(task);
    }
  }, [onTaskClick]);

  // Handle screenshot click
  const handleScreenshotClick = useCallback((screenshot, index) => {
    if (onScreenshotClick) {
      onScreenshotClick(screenshot, index);
    }
  }, [onScreenshotClick]);

  const displayTasks = filteredTasks.slice(0, maxTasksDisplay);
  const remainingTasks = filteredTasks.length - maxTasksDisplay;
  const recentToolkitEvents = toolkitEvents.slice(-maxToolkitDisplay);
  const displayScreenshots = webviewScreenshots.slice(0, maxScreenshotsDisplay);

  return (
    <div
      className={`agent-node ${isActive ? 'active' : ''} ${isExpanded ? 'expanded' : ''}`}
      style={{
        background: config.bgColor,
        borderColor: isActive ? config.color : config.borderColor,
      }}
      onClick={onClick}
    >
      {/* Header */}
      <div className="agent-header">
        <div className="agent-header-left">
          <span className="agent-icon">{config.icon}</span>
          <span className="agent-name">{name || config.name || `Agent ${id}`}</span>
        </div>
        <div className="agent-header-right">
          <div className="agent-status-indicator">
            <span
              className="pulse-dot"
              style={{
                background: getStatusColor(),
                animation: status === AgentStatus.ACTIVE ? 'pulse 1.5s ease-in-out infinite' : 'none',
              }}
            />
            <span className="status-text">{status}</span>
          </div>
          {showDetails && (
            <button
              className="agent-expand-btn"
              onClick={handleToggleExpand}
              title={isExpanded ? 'Collapse' : 'Expand'}
            >
              <Icon
                name="chevron"
                size={16}
                className={`expand-icon ${isExpanded ? 'expanded' : ''}`}
              />
            </button>
          )}
        </div>
      </div>

      {/* Current Tool - Shimmer effect when active */}
      {currentTool && status === AgentStatus.ACTIVE && (
        <div className="agent-current-tool">
          <span className="tool-icon">{getToolkitIcon(currentTool)}</span>
          <span className="tool-label">Using:</span>
          <span className="tool-name shiny-text">{currentTool}</span>
        </div>
      )}

      {/* Progress Bar */}
      {progress > 0 && (
        <div className="agent-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(progress, 100)}%`,
                background: config.color,
              }}
            />
          </div>
          <span className="progress-text">{Math.round(progress)}%</span>
        </div>
      )}

      {/* Collapsed summary */}
      {!isExpanded && tasks.length > 0 && (
        <div className="agent-summary">
          <span className="summary-count">
            {taskCounts.done}/{taskCounts.all} tasks
          </span>
          {toolkitEvents.length > 0 && (
            <span className="summary-tools">
              {toolkitEvents.length} tool calls
            </span>
          )}
        </div>
      )}

      {/* Expanded content */}
      {isExpanded && showDetails && (
        <div className="agent-content" ref={contentRef}>
          {/* Tab navigation */}
          <div className="agent-tabs">
            <button
              className={`tab-btn ${activeTab === 'tasks' ? 'active' : ''}`}
              onClick={(e) => { e.stopPropagation(); setActiveTab('tasks'); }}
            >
              Tasks ({taskCounts.all})
            </button>
            <button
              className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
              onClick={(e) => { e.stopPropagation(); setActiveTab('logs'); }}
            >
              Logs ({toolkitEvents.length})
            </button>
            {completionReport && (
              <button
                className={`tab-btn ${activeTab === 'report' ? 'active' : ''}`}
                onClick={(e) => { e.stopPropagation(); setActiveTab('report'); }}
              >
                Report
              </button>
            )}
          </div>

          {/* Tasks tab */}
          {activeTab === 'tasks' && (
            <div className="agent-tasks-panel">
              {/* Task state filter */}
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
              />

              {/* Task list */}
              <div className="agent-tasks">
                {displayTasks.map((task, index) => (
                  <div
                    key={task.id || index}
                    className={`task-item ${task.status || ''} ${task.reAssignTo ? 'reassigned' : ''}`}
                    onClick={(e) => { e.stopPropagation(); handleTaskClick(task); }}
                  >
                    <div className="task-item-icon">
                      {getTaskStatusIcon(task.status, task)}
                    </div>
                    <div className="task-item-content">
                      <span className="task-name">{task.name || task.content || task.description}</span>
                      {task.reAssignTo && (
                        <span className="task-badge reassigned">→ {task.reAssignTo}</span>
                      )}
                      {(task.failure_count || 0) > 0 && (
                        <span className="task-badge attempt">Attempt {task.failure_count}</span>
                      )}
                    </div>
                  </div>
                ))}
                {remainingTasks > 0 && (
                  <span className="more-tasks">+{remainingTasks} more</span>
                )}
                {displayTasks.length === 0 && (
                  <div className="empty-state">No tasks matching filter</div>
                )}
              </div>
            </div>
          )}

          {/* Logs tab */}
          {activeTab === 'logs' && (
            <div className="agent-logs-panel">
              {/* Toolkit events */}
              <div className="toolkit-events">
                {recentToolkitEvents.map((event, index) => (
                  <div
                    key={event.id || index}
                    className={`toolkit-event ${event.status || ''}`}
                  >
                    <span className="toolkit-icon">{getToolkitIcon(event.toolkit_name)}</span>
                    <div className="toolkit-content">
                      <div className="toolkit-header">
                        <span className="toolkit-name">{event.toolkit_name}</span>
                        <span className="toolkit-method">.{event.method_name}()</span>
                        {event.status === 'running' && (
                          <span className="toolkit-status running"><span className="spinner-small"></span></span>
                        )}
                        {event.status === 'completed' && (
                          <span className="toolkit-status success">✓</span>
                        )}
                        {event.status === 'failed' && (
                          <span className="toolkit-status error">✗</span>
                        )}
                      </div>
                      {event.input_preview && (
                        <div className="toolkit-preview" title={event.input_preview}>
                          {event.input_preview.length > 50
                            ? `${event.input_preview.slice(0, 50)}...`
                            : event.input_preview}
                        </div>
                      )}
                      {event.output_preview && (
                        <div className="toolkit-output" title={event.output_preview}>
                          → {event.output_preview.length > 50
                            ? `${event.output_preview.slice(0, 50)}...`
                            : event.output_preview}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {toolkitEvents.length === 0 && (
                  <div className="empty-state">No toolkit events yet</div>
                )}
                {toolkitEvents.length > maxToolkitDisplay && (
                  <div className="more-logs">
                    Showing {maxToolkitDisplay} of {toolkitEvents.length} events
                  </div>
                )}
              </div>

              {/* Terminal output */}
              {terminalOutput && (
                <div className="terminal-preview">
                  <div className="terminal-header">Terminal Output</div>
                  <pre className="terminal-content">
                    {terminalOutput.length > 500
                      ? `${terminalOutput.slice(0, 500)}...`
                      : terminalOutput}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Report tab */}
          {activeTab === 'report' && completionReport && (
            <div className="agent-report-panel">
              <div className="report-content">
                {completionReport}
              </div>
            </div>
          )}

          {/* Webview screenshots */}
          {displayScreenshots.length > 0 && (
            <div className="agent-screenshots">
              <div className="screenshots-header">Screenshots</div>
              <div className="screenshots-grid">
                {displayScreenshots.map((screenshot, index) => (
                  <div
                    key={index}
                    className="screenshot-item"
                    onClick={(e) => { e.stopPropagation(); handleScreenshotClick(screenshot, index); }}
                  >
                    <img
                      src={screenshot.url || screenshot}
                      alt={screenshot.title || `Screenshot ${index + 1}`}
                      loading="lazy"
                    />
                    {screenshot.title && (
                      <span className="screenshot-title">{screenshot.title}</span>
                    )}
                  </div>
                ))}
              </div>
              {webviewScreenshots.length > maxScreenshotsDisplay && (
                <span className="more-screenshots">
                  +{webviewScreenshots.length - maxScreenshotsDisplay} more
                </span>
              )}
            </div>
          )}

          {/* Files preview */}
          {files.length > 0 && (
            <div className="agent-files">
              <div className="files-header">Files ({files.length})</div>
              <div className="files-list">
                {files.slice(0, 3).map((file, index) => (
                  <div key={index} className="file-item">
                    <span className="file-icon">📄</span>
                    <span className="file-name">{file.name || file}</span>
                  </div>
                ))}
                {files.length > 3 && (
                  <span className="more-files">+{files.length - 3} more</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AgentNode;
