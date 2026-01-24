/**
 * Agent Message Component
 *
 * Displays agent/assistant final response messages in the chat interface.
 * Following Eigent pattern - only shows conversation responses, not execution details.
 *
 * Supports markdown rendering for rich content display.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import Icon from '../../Icons';

function AgentMessage({ message }) {
  const { content, timestamp, step, attaches } = message;

  // Format timestamp
  const formatTime = (ts) => {
    if (!ts) return '';
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Determine message style based on step type
  const getMessageClass = () => {
    if (step === 'error') return 'error-message';
    if (step === 'end') return 'final-response';
    return '';
  };

  return (
    <div className={`agent-message ${getMessageClass()}`}>
      <div className="message-header">
        <div className="message-avatar agent-avatar">
          <Icon name="bot" size={16} />
        </div>
        <span className="message-sender">Ami</span>
        {timestamp && (
          <span className="message-time">{formatTime(timestamp)}</span>
        )}
      </div>
      <div className="message-content">
        {content && (
          <div className="message-text markdown-content">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
        {/* File attachments from agent response (Eigent pattern) */}
        {attaches && attaches.length > 0 && (
          <div className="message-attachments">
            {attaches.map((file, index) => (
              <div key={`attach-${index}`} className="attachment-item">
                <Icon name="file" size={14} />
                <span className="attachment-name">{file.fileName || file.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMessage;
