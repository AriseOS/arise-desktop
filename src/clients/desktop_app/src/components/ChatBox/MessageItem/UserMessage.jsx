/**
 * User Message Component
 *
 * Displays user messages in the chat interface.
 * Supports text content and file attachments.
 */

import React from 'react';
import Icon from '../../Icons';

function UserMessage({ message }) {
  const { content, timestamp, attachments } = message;

  // Format timestamp
  const formatTime = (ts) => {
    if (!ts) return '';
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="user-message">
      <div className="message-header">
        <div className="message-avatar user-avatar">
          <Icon name="user" size={16} />
        </div>
        <span className="message-sender">You</span>
        {timestamp && (
          <span className="message-time">{formatTime(timestamp)}</span>
        )}
      </div>
      <div className="message-content">
        <div className="message-text">{content}</div>
        {attachments && attachments.length > 0 && (
          <div className="message-attachments">
            {attachments.map((file, i) => (
              <div key={i} className="attachment-item">
                <Icon name="file" size={14} />
                <span className="attachment-name">{file.name || file}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default UserMessage;
