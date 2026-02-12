/**
 * AgentTab - Agent execution details view
 *
 * Ported from Eigent's WorkFlow/node.tsx:
 * - Lines 751-868: Toolkit event rendering with status icons
 * - Lines 756-767: Notice/thinking display with MarkDown
 * - Lines 768-846: Toolkit item with name, method, message
 * - Lines 849-866: Report/result display
 *
 * This tab combines:
 * - Memory Paths (semantic search results)
 * - Thinking/Reasoning timeline
 * - Toolkit Events timeline (from Tool Activity Panel)
 * - Result/Error display
 */

import React, { useRef, useEffect, useMemo } from 'react';
import './AgentTab.css';

/**
 * Status icon component
 * Similar to Eigent's LoaderCircle/CircleCheckBig pattern
 */
function StatusIcon({ status }) {
  switch (status) {
    case 'running':
      return <span className="status-icon running">⟳</span>;
    case 'completed':
      return <span className="status-icon completed">✓</span>;
    case 'failed':
      return <span className="status-icon failed">✗</span>;
    default:
      return <span className="status-icon pending">○</span>;
  }
}

/**
 * Memory Paths Section
 * Shows semantic search results used for planning
 */
function MemoryPathsSection({ paths }) {
  if (!paths || paths.length === 0) return null;

  return (
    <div className="agent-tab-section memory-section">
      <div className="section-header">
        <span className="section-icon">🧠</span>
        <span className="section-title">Memory Paths</span>
        <span className="section-badge">{paths.length}</span>
      </div>
      <div className="memory-paths-list">
        {paths.map((path, index) => (
          <div key={index} className="memory-path-item">
            <span className="memory-score">
              {Math.round((path.score || 0) * 100)}%
            </span>
            <span className="memory-description">
              {path.description || path.domain || path.url || 'Unknown path'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Notice Item Component
 * Displays execution notices (Agent Active, Iteration X, etc.)
 */
function NoticeItem({ title, content, noticeType, timestamp }) {
  const getIcon = () => {
    switch (noticeType) {
      case 'info': return 'ℹ️';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      case 'success': return '✅';
      case 'memory': return '🧠';
      default: return '📋';
    }
  };

  return (
    <div className={`timeline-item notice-item ${noticeType || 'info'}`}>
      <div className="timeline-icon">
        <span className="notice-icon">{getIcon()}</span>
      </div>
      <div className="timeline-content">
        <div className="notice-header">
          <span className="notice-title">{title}</span>
        </div>
        {content && <div className="notice-text">{content}</div>}
        {timestamp && (
          <div className="timeline-time">
            {new Date(timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Thinking Item Component
 * Similar to Eigent's notice handling in node.tsx lines 756-767
 */
function ThinkingItem({ content, timestamp }) {
  return (
    <div className="timeline-item thinking-item">
      <div className="timeline-icon">
        <span className="thinking-icon">💭</span>
      </div>
      <div className="timeline-content">
        <div className="thinking-text">{content}</div>
        {timestamp && (
          <div className="timeline-time">
            {new Date(timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Toolkit Item Component
 * Ported from Eigent's node.tsx lines 768-846
 *
 * Structure:
 * - Status icon (running spinner, completed check, failed x)
 * - Toolkit name (e.g., "Browser Toolkit")
 * - Method name (e.g., "visit page")
 * - Message/input preview
 * - For browser actions: show action_type, target, page_url, etc.
 */
function ToolkitItem({ event }) {
  const {
    toolkit_name,
    method_name,
    status,
    input_preview,
    output_preview,
    timestamp,
    duration_ms,
    // Browser action specific fields
    target,
    page_url,
  } = event;

  // Format method name for display (similar to Eigent's approach)
  const displayMethodName = method_name
    ? method_name.replace(/_/g, ' ').toLowerCase()
    : 'unknown';

  // Combine input and output for message display
  const message = output_preview || input_preview || '';

  // Build browser action param display (simplified: just show target or url)
  const browserParam = useMemo(() => {
    // Show target (element/URL) or page_url, whichever is available
    return target || page_url || null;
  }, [target, page_url]);

  return (
    <div className={`timeline-item toolkit-item ${status}`}>
      <div className="timeline-icon">
        <StatusIcon status={status} />
      </div>
      <div className="timeline-content">
        <div className="toolkit-header">
          <span className="toolkit-name">{toolkit_name || 'Unknown'}</span>
          {duration_ms && (
            <span className="toolkit-duration">{duration_ms}ms</span>
          )}
        </div>
        <div className="toolkit-details">
          <span className="toolkit-method">{displayMethodName}</span>
          {message && (
            <span className="toolkit-message" title={message}>
              {message.length > 100 ? message.substring(0, 100) + '...' : message}
            </span>
          )}
        </div>
        {/* Browser action target/url */}
        {browserParam && (
          <div className="toolkit-param" title={browserParam}>
            {browserParam.length > 60 ? browserParam.substring(0, 60) + '...' : browserParam}
          </div>
        )}
        {timestamp && (
          <div className="timeline-time">
            {new Date(timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Result Section
 * Similar to Eigent's report display in node.tsx lines 849-866
 */
function ResultSection({ result, error }) {
  if (!result && !error) return null;

  const isError = !!error;
  const content = error || result;

  // Format content for display
  const formattedContent = useMemo(() => {
    if (typeof content === 'string') return content;
    try {
      return JSON.stringify(content, null, 2);
    } catch {
      return String(content);
    }
  }, [content]);

  return (
    <div className={`agent-tab-section result-section ${isError ? 'error' : 'success'}`}>
      <div className="section-header">
        <span className="section-icon">{isError ? '❌' : '✅'}</span>
        <span className="section-title">{isError ? 'Error' : 'Result'}</span>
      </div>
      <div className="result-content">
        <pre>{formattedContent}</pre>
      </div>
    </div>
  );
}

/**
 * AgentTab Main Component
 */
function AgentTab({
  taskId,
  taskStatus,
  toolkitEvents = [],
  thinkingLogs = [],
  memoryPaths = [],
  notices = [],           // Execution notices (Agent Active, Iteration X, etc.)
  loopIteration = 0,      // Current loop iteration
  currentTools = [],      // Currently executing tools
  result = null,
  error = null,
}) {
  const logRef = useRef(null);

  /**
   * Merge and sort timeline events
   * Combines notices, thinking logs, and toolkit events into single timeline
   */
  const timelineEvents = useMemo(() => {
    // Helper to convert timestamp to numeric ms
    const toTimestampMs = (ts, fallback) => {
      if (!ts) return fallback;
      if (typeof ts === 'number') return ts;
      // ISO string or other string format
      const parsed = new Date(ts).getTime();
      return isNaN(parsed) ? fallback : parsed;
    };

    const events = [];
    const now = Date.now();

    // Add notices (Agent Active, Iteration X, etc.)
    notices.forEach((notice, index) => {
      events.push({
        type: 'notice',
        title: notice.title || notice.type,
        content: notice.message || notice.content,
        noticeType: notice.type,  // info, warning, error, etc.
        timestamp: toTimestampMs(notice.timestamp, now - (notices.length - index) * 500),
        id: `notice-${index}`,
      });
    });

    // Add thinking logs
    thinkingLogs.forEach((log, index) => {
      events.push({
        type: 'thinking',
        content: log.content || log,
        timestamp: toTimestampMs(log.timestamp, now - (thinkingLogs.length - index) * 1000),
        id: `thinking-${index}`,
      });
    });

    // Internal plan tools to filter out (these are agent's internal logic, not user-facing)
    const INTERNAL_PLAN_TOOLS = [
      'get_current_plan',
      'complete_subtask',
      'add_subtask',
      'update_subtask',
      'replan_task',
    ];

    // Add toolkit events (filter out internal plan tools)
    toolkitEvents
      .filter((event) => {
        const toolName = event.name || event.tool || event.method || '';
        return !INTERNAL_PLAN_TOOLS.includes(toolName);
      })
      .forEach((event, index) => {
        events.push({
          type: 'toolkit',
          ...event,
          timestamp: toTimestampMs(event.timestamp, now - (toolkitEvents.length - index) * 100),
          id: `toolkit-${index}`,
        });
      });

    // Sort by timestamp (all are now numeric ms)
    return events.sort((a, b) => a.timestamp - b.timestamp);
  }, [notices, thinkingLogs, toolkitEvents]);

  /**
   * Auto-scroll to bottom when new events arrive
   * Similar to Eigent's logRef scrolling pattern
   */
  useEffect(() => {
    if (logRef.current && taskStatus === 'running') {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [timelineEvents.length, taskStatus]);

  const hasContent =
    memoryPaths.length > 0 ||
    timelineEvents.length > 0 ||
    result ||
    error ||
    notes;

  if (!hasContent) {
    return (
      <div className="agent-tab empty">
        <div className="empty-state">
          <span className="empty-icon">🤖</span>
          <span className="empty-text">
            {taskStatus === 'running'
              ? 'Agent is working...'
              : 'No execution details yet'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-tab">
      {/* Memory Paths Section */}
      <MemoryPathsSection paths={memoryPaths} />

      {/* Execution Timeline */}
      {timelineEvents.length > 0 && (
        <div className="agent-tab-section timeline-section">
          <div className="section-header">
            <span className="section-icon">⚡</span>
            <span className="section-title">Execution</span>
            <span className="section-badge">{timelineEvents.length}</span>
          </div>
          <div
            ref={logRef}
            className="timeline-container"
            onWheel={(e) => e.stopPropagation()}
          >
            {timelineEvents.map((event) => {
              if (event.type === 'notice') {
                return (
                  <NoticeItem
                    key={event.id}
                    title={event.title}
                    content={event.content}
                    noticeType={event.noticeType}
                    timestamp={event.timestamp}
                  />
                );
              } else if (event.type === 'thinking') {
                return (
                  <ThinkingItem
                    key={event.id}
                    content={event.content}
                    timestamp={event.timestamp}
                  />
                );
              } else {
                return <ToolkitItem key={event.id} event={event} />;
              }
            })}
          </div>
        </div>
      )}

      {/* Result/Error Section */}
      <ResultSection result={result} error={error} />
    </div>
  );
}

export default AgentTab;
