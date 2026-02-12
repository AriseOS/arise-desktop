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
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import Icon from '../../Icons';
import FileAttachmentCard from './FileAttachmentCard';
import { getAgentConfig } from '../../AgentNode/AgentNode';

// Allow <details>/<summary> and list tags through sanitizer, block dangerous tags
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames || []),
    'details', 'summary',
  ],
};

function AgentMessage({ message }) {
  const { content, timestamp, step, attaches, attachments, executorId, taskLabel, agentType } = message;

  // DS-11: Use new attachments field, fallback to legacy attaches
  const fileAttachments = attachments || attaches || [];

  // Get agent config for icon/color differentiation
  const agentConfig = agentType ? getAgentConfig(agentType) : null;

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
        <div className="message-avatar agent-avatar"
          style={agentConfig ? { background: agentConfig.bgColor } : undefined}
        >
          {agentConfig ? (
            <span style={{ fontSize: '14px' }}>{agentConfig.icon}</span>
          ) : (
            <Icon name="bot" size={16} />
          )}
        </div>
        <span className="message-sender">{agentConfig ? agentConfig.name : 'Ami'}</span>
        {(taskLabel || executorId) && (
          <span className="executor-badge" style={{
            fontSize: '11px',
            padding: '1px 6px',
            marginLeft: '6px',
            borderRadius: '8px',
            backgroundColor: agentConfig?.bgColor || 'var(--color-surface-subtle, #e8e8e8)',
            color: agentConfig?.color || 'var(--color-text-secondary, #666)',
            border: agentConfig ? `1px solid ${agentConfig.borderColor}` : 'none',
          }}
            title={executorId ? `Executor: ${executorId}` : ''}
          >
            {taskLabel || executorId}
          </span>
        )}
        {timestamp && (
          <span className="message-time">{formatTime(timestamp)}</span>
        )}
      </div>
      <div className="message-content">
        {content && (
          <div className="message-text markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}>{content}</ReactMarkdown>
          </div>
        )}

        {/* DS-11: File attachments with rich previews */}
        {fileAttachments && fileAttachments.length > 0 && (
          <div className="message-attachments">
            {fileAttachments.map((file, index) => {
              try {
                // Check if it's new format (FileAttachment) or legacy format
                if (file.file_path) {
                  return <FileAttachmentCard key={`file-${index}`} file={file} />;
                } else {
                  // Legacy format fallback
                  return (
                    <div key={`attach-${index}`} className="attachment-item legacy">
                      <Icon name="file" size={14} />
                      <span className="attachment-name">{file.fileName || file.name}</span>
                    </div>
                  );
                }
              } catch (error) {
                console.error(`[AgentMessage] Error rendering attachment ${index}:`, error, file);
                return (
                  <div key={`error-${index}`} className="attachment-item error">
                    <Icon name="alert" size={14} />
                    <span>Error loading attachment</span>
                  </div>
                );
              }
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMessage;
