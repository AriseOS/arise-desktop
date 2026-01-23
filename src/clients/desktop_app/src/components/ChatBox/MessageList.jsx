/**
 * Message List Component
 *
 * Scrollable container for chat messages with auto-scroll behavior.
 * Displays user messages, agent messages, and system notices.
 */

import React, { useRef, useEffect, useState } from 'react';
import { UserMessage, AgentMessage, NoticeCard } from './MessageItem';

function MessageList({ messages, notices }) {
  const listRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

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

  // Render message based on type
  const renderMessage = (item, index) => {
    if (item.type === 'notice') {
      return <NoticeCard key={`notice-${index}`} notice={item} />;
    }

    if (item.role === 'user') {
      return <UserMessage key={`msg-${index}`} message={item} />;
    }

    if (item.role === 'assistant' || item.role === 'agent') {
      return <AgentMessage key={`msg-${index}`} message={item} />;
    }

    // Thinking messages (agent reasoning)
    if (item.role === 'thinking') {
      return (
        <AgentMessage
          key={`thinking-${index}`}
          message={{
            ...item,
            step: 'thinking',
            thinking: true,
          }}
        />
      );
    }

    // System messages
    if (item.role === 'system') {
      return (
        <NoticeCard
          key={`sys-${index}`}
          notice={{
            type: 'info',
            message: item.content,
            timestamp: item.timestamp,
          }}
        />
      );
    }

    // Tool results
    if (item.role === 'tool_result') {
      return (
        <AgentMessage
          key={`tool-${index}`}
          message={{
            ...item,
            step: 'tool_result',
          }}
        />
      );
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
      {allItems.length === 0 ? (
        <div className="message-list-empty">
          <span className="empty-icon">💬</span>
          <span className="empty-text">Start a conversation...</span>
        </div>
      ) : (
        allItems.map((item, index) => renderMessage(item, index))
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
