/**
 * Message List Component
 *
 * Scrollable container for chat messages with auto-scroll behavior.
 *
 * Following Eigent pattern - displays:
 * - User messages
 * - Agent final responses (step: 'end' or regular replies)
 * - TaskCard inline (Eigent pattern: task decomposition inline display)
 * - StreamingTaskList (when decomposing)
 *
 * Execution details (thinking, toolkit events, tool results) are
 * displayed in the AgentTab within WorkspaceTabs, not here.
 */

import React, { useRef, useEffect, useState, useMemo } from 'react';
import { UserMessage, AgentMessage, NoticeCard } from './MessageItem';
import { TaskCard, StreamingTaskList } from '../TaskBox';

function MessageList({
  messages,
  notices,
  task = null,  // Eigent pattern: task object for inline TaskCard
  onStartTask,  // Start task callback
  onEditTask,   // Edit task callback
}) {
  // DEBUG: Log messages to check if attachments are present
  console.log('[MessageList] Received messages:', messages.length, 'messages');
  messages.forEach((m, i) => {
    if (m.attachments || m.attaches) {
      console.log(`[MessageList] Message ${i} has attachments:`, m.attachments || m.attaches);
    }
  });

  const listRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Eigent pattern: Determine if we should show task card
  const showTaskCard = useMemo(() => {
    if (!task) return false;
    // Show TaskCard when we have taskInfo/taskRunning
    return (task.taskInfo?.length > 0 || task.taskRunning?.length > 0);
  }, [task]);

  // Eigent pattern: Determine if we're streaming decomposition
  const isStreamingDecompose = useMemo(() => {
    if (!task) return false;
    return !!task.streamingDecomposeText;
  }, [task?.streamingDecomposeText]);

  // Calculate task type (Eigent: 1=manual, 2=agent-assigned)
  const taskType = useMemo(() => {
    if (!task) return 2;
    // If taskRunning has agent-assigned tasks, use type 2
    if (task.taskRunning?.some(t => t.agent)) return 2;
    // If we have subtasks but no running, still type 2 (decomposed)
    if (task.taskInfo?.length > 0) return 2;
    return 1;
  }, [task?.taskRunning, task?.taskInfo]);

  // Check if scrolled to bottom
  const checkIfAtBottom = () => {
    if (!listRef.current) return true;
    const { scrollTop, scrollHeight, clientHeight } = listRef.current;
    return scrollHeight - scrollTop - clientHeight < 50;
  };

  // Handle scroll events
  const handleScroll = () => {
    const atBottom = checkIfAtBottom();
    isAtBottomRef.current = atBottom;
    setShowScrollButton(!atBottom);
  };

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (listRef.current && isAtBottomRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, notices]);

  // Scroll to bottom programmatically
  const scrollToBottom = () => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
      isAtBottomRef.current = true;
      setShowScrollButton(false);
    }
  };

  /**
   * Render message based on type
   *
   * Following Eigent pattern:
   * - ChatBox only displays conversation messages (user + agent responses)
   * - All execution details (notices, thinking, toolkit, iterations) go to AgentTab
   */
  const renderMessage = (item, index) => {
    // Skip ALL notices - they go to AgentTab now (Eigent pattern)
    // Notices include: Agent Active, Iteration X, toolkit events, etc.
    if (item.type === 'notice') {
      return null;
    }

    // User messages - always display
    if (item.role === 'user') {
      return <UserMessage key={`msg-${index}`} message={item} />;
    }

    // Agent/Assistant messages - only display final responses (step: 'end' or no step)
    if (item.role === 'assistant' || item.role === 'agent') {
      // Skip execution-related messages (these go to AgentTab)
      if (item.step === 'thinking' || item.step === 'tool_result' || item.step === 'decomposing') {
        return null;
      }
      // Display final response or regular agent messages
      return <AgentMessage key={`msg-${index}`} message={item} />;
    }

    // Skip thinking messages (displayed in AgentTab)
    if (item.role === 'thinking') {
      return null;
    }

    // Skip system messages (displayed in AgentTab)
    if (item.role === 'system') {
      return null;
    }

    // Skip tool results (displayed in AgentTab)
    if (item.role === 'tool_result') {
      return null;
    }

    return null;
  };

  // Combine and sort all items by timestamp
  const allItems = [
    ...messages.map(m => ({ ...m, _type: 'message' })),
    ...(notices || []).map(n => ({ ...n, type: 'notice', _type: 'notice' })),
  ].sort((a, b) => {
    const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    return timeA - timeB;
  });

  return (
    <div className="message-list" ref={listRef} onScroll={handleScroll}>
      {allItems.length === 0 && !showTaskCard && !isStreamingDecompose ? (
        <div className="message-list-empty">
          <span className="empty-icon">💬</span>
          <span className="empty-text">Start a conversation...</span>
        </div>
      ) : (
        <>
          {/* Render messages */}
          {allItems.map((item, index) => renderMessage(item, index))}

          {/* Eigent pattern: Streaming task decomposition display */}
          {isStreamingDecompose && (
            <div className="task-card-inline streaming">
              <StreamingTaskList
                streamingText={task.streamingDecomposeText}
                taskType={taskType}
              />
            </div>
          )}

          {/* Eigent pattern: TaskCard inline display */}
          {showTaskCard && !isStreamingDecompose && (
            <div className="task-card-inline">
              <TaskCard
                taskInfo={task.taskInfo || []}
                taskRunning={task.taskRunning || []}
                summaryTask={task.summaryTask || ''}
                progressValue={task.progressValue || 0}
                taskType={taskType}
                showToolkits={false}
                editable={task.isTaskEdit}
                subtaskAssignments={task.subtaskAssignments || {}}
                decompositionProgress={task.decompositionProgress || 0}
                decompositionMessage={task.decompositionMessage || ''}
                decompositionStatus={task.decompositionStatus || 'pending'}
              />
            </div>
          )}
        </>
      )}

      {/* Scroll to bottom button */}
      {showScrollButton && (
        <button className="scroll-to-bottom-btn" onClick={scrollToBottom}>
          <span>↓</span>
        </button>
      )}
    </div>
  );
}

export default MessageList;
