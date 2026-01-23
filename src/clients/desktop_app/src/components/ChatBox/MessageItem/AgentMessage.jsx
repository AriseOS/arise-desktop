/**
 * Agent Message Component
 *
 * Displays agent/assistant messages in the chat interface.
 * Supports markdown rendering and various content types.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import Icon from '../../Icons';

function AgentMessage({ message }) {
  const { content, timestamp, step, thinking } = message;

  // Format timestamp
  const formatTime = (ts) => {
    if (!ts) return '';
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Determine message style based on step type
  const getMessageClass = () => {
    if (step === 'thinking' || thinking) return 'thinking-message';
    if (step === 'error') return 'error-message';
    if (step === 'tool_result') return 'tool-result-message';
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
        {thinking && (
          <div className="thinking-indicator">
            <span className="thinking-dots">
              <span></span>
              <span></span>
              <span></span>
            </span>
            <span className="thinking-text">Thinking...</span>
          </div>
        )}
        {content && (
          <div className="message-text markdown-content">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMessage;
