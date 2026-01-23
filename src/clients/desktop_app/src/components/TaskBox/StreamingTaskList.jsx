/**
 * StreamingTaskList Component
 *
 * Displays tasks being streamed from the server in real-time.
 * Parses XML-like <task>content</task> format.
 * Shows loading skeleton when no tasks parsed yet.
 *
 * Ported from Eigent's StreamingTaskList component.
 */

import React, { useMemo } from 'react';
import Icon from '../Icons';

/**
 * Parse streaming task text and extract task content
 * Supports formats:
 * - <task>content</task> - complete task
 * - <task>content - incomplete (still streaming)
 */
function parseStreamingTasks(text) {
  const tasks = [];

  if (!text) {
    return { tasks: [], isStreaming: false };
  }

  // Match complete tasks: <task>content</task>
  const completeTaskRegex = /<task>([\s\S]*?)<\/task>/g;
  let match;
  while ((match = completeTaskRegex.exec(text)) !== null) {
    const content = match[1].trim();
    if (content) {
      tasks.push(content);
    }
  }

  // Check for incomplete task (streaming): <task>content without closing tag
  const lastOpenTag = text.lastIndexOf('<task>');
  const lastCloseTag = text.lastIndexOf('</task>');

  let isStreaming = false;
  if (lastOpenTag > lastCloseTag) {
    // There's an unclosed <task> tag - extract its content
    const incompleteContent = text.substring(lastOpenTag + 6).trim();
    if (incompleteContent) {
      tasks.push(incompleteContent);
      isStreaming = true;
    }
  }

  return { tasks, isStreaming };
}

function StreamingTaskList({
  streamingText = '',
  taskType = 1,
  showHeader = true,
}) {
  const { tasks, isStreaming } = useMemo(
    () => parseStreamingTasks(streamingText),
    [streamingText]
  );

  // Show loading skeleton when no tasks have been parsed yet
  if (tasks.length === 0) {
    return (
      <div className="streaming-task-list loading">
        <div className="streaming-task-surface">
          {/* Progress bar at top */}
          <div className="streaming-progress-bar">
            <div className="streaming-progress-fill animated" />
          </div>

          {/* Loading indicator */}
          <div className="streaming-loading">
            <span className="streaming-spinner">
              <span className="spinner small" />
            </span>
            <span className="streaming-loading-text">Analyzing task...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="streaming-task-list">
      <div className="streaming-task-surface">
        {/* Progress bar at top */}
        <div className="streaming-progress-bar">
          <div className="streaming-progress-fill" style={{ width: '100%' }} />
        </div>

        {/* Header with task type badge */}
        {showHeader && (
          <div className="streaming-header">
            <span className={`task-type-badge type-${taskType}`}>
              {taskType === 1 ? 'Manual Tasks' : taskType === 2 ? 'Agent Tasks' : 'Tasks'}
            </span>
            <span className="streaming-count">
              {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
            </span>
          </div>
        )}

        {/* Task list */}
        <div className="streaming-tasks">
          {tasks.map((task, index) => {
            const isLastTask = index === tasks.length - 1;
            const isCurrentlyStreaming = isLastTask && isStreaming;

            return (
              <div
                key={`streaming-task-${index}`}
                className={`streaming-task-item ${isCurrentlyStreaming ? 'streaming' : ''}`}
              >
                {/* Task indicator */}
                <div className="streaming-task-indicator">
                  {isCurrentlyStreaming ? (
                    <span className="spinner small" />
                  ) : (
                    <span className="task-circle">○</span>
                  )}
                </div>

                {/* Task content */}
                <div className="streaming-task-content">
                  <span className="streaming-task-text">
                    {task}
                    {isCurrentlyStreaming && (
                      <span className="streaming-cursor" />
                    )}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Export parser for external use
export { parseStreamingTasks };
export default StreamingTaskList;
