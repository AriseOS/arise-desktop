/**
 * HumanMessagesContainer Component
 *
 * Container for displaying human interaction toast messages.
 */

import React from 'react';

function HumanMessagesContainer({
  messages = [],
  onDismiss,
  maxVisible = 3,
}) {
  // Only show the most recent messages
  const visibleMessages = messages.slice(-maxVisible);

  if (visibleMessages.length === 0) {
    return null;
  }

  return (
    <div className="human-messages-container">
      {visibleMessages.map((msg, index) => (
        <div key={msg.id || index} className="human-message-toast">
          <div className="toast-header">
            <span className="toast-icon">💬</span>
            <span className="toast-title">{msg.title || 'Agent Message'}</span>
            <button
              className="toast-close"
              onClick={() => onDismiss && onDismiss(messages.indexOf(msg))}
            >
              ✕
            </button>
          </div>
          <div className="toast-body">
            {msg.description || msg.message}
          </div>
        </div>
      ))}
    </div>
  );
}

export default HumanMessagesContainer;
