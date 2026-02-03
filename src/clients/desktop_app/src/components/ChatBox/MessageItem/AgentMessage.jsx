/**
 * Agent Message Component
 *
 * Displays agent/assistant final response messages in the chat interface.
 * Following Eigent pattern - only shows conversation responses, not execution details.
 *
 * DS-11: Added support for file attachments with rich previews.
 * Supports markdown rendering for rich content display.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Icon from '../../Icons';
import FileAttachmentCard from './FileAttachmentCard';

function AgentMessage({ message }) {
  const { content, timestamp, step, attaches, attachments } = message;

  // DS-11: Use new attachments field, fallback to legacy attaches
  const fileAttachments = attachments || attaches || [];

  // DEBUG
  if (fileAttachments.length > 0) {
    console.log('[AgentMessage] Rendering with attachments:', fileAttachments);
  }

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
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}

        {/* DS-11: File attachments with rich previews */}
        {fileAttachments && fileAttachments.length > 0 && (
          <div className="message-attachments">
            {fileAttachments.map((file, index) => (
              // Check if it's new format (FileAttachment) or legacy format
              file.file_path ? (
                <FileAttachmentCard key={`file-${index}`} file={file} />
              ) : (
                // Legacy format fallback
                <div key={`attach-${index}`} className="attachment-item legacy">
                  <Icon name="file" size={14} />
                  <span className="attachment-name">{file.fileName || file.name}</span>
                </div>
              )
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMessage;
