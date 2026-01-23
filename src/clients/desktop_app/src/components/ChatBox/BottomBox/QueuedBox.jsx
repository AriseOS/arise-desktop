/**
 * QueuedBox Component
 *
 * Displays queued messages waiting to be processed.
 * Supports expand/collapse and individual message removal.
 *
 * Ported from Eigent's QueuedBox component.
 */

import React, { useState, useCallback } from 'react';
import Icon from '../../Icons';

/**
 * @typedef {Object} QueuedMessage
 * @property {string} id - Unique identifier
 * @property {string} content - Message content
 * @property {number} [timestamp] - Message timestamp
 */

/**
 * QueuedBox Component
 *
 * @param {Object} props
 * @param {QueuedMessage[]} props.queuedMessages - Array of queued messages
 * @param {function} props.onRemoveQueuedMessage - Callback to remove a message
 */
function QueuedBox({
  queuedMessages = [],
  onRemoveQueuedMessage,
  className = '',
}) {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleToggleExpand = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const handleRemove = useCallback((id) => {
    if (onRemoveQueuedMessage) {
      onRemoveQueuedMessage(id);
    }
  }, [onRemoveQueuedMessage]);

  if (queuedMessages.length === 0) {
    return null;
  }

  return (
    <div className={`queued-box ${className}`}>
      {/* Header */}
      <div className="queued-box-header">
        <button
          className="queued-box-toggle"
          onClick={handleToggleExpand}
          title={isExpanded ? 'Collapse' : 'Expand'}
        >
          <Icon
            name={isExpanded ? 'chevronUp' : 'chevronDown'}
            size={16}
          />
        </button>

        <div className="queued-box-title">
          <span className="queued-count">{queuedMessages.length}</span>
          <span className="queued-label">Queued Tasks</span>
        </div>
      </div>

      {/* Queued Items */}
      <div className={`queued-box-items ${isExpanded ? 'expanded' : ''}`}>
        {queuedMessages.map((msg) => (
          <QueuedItem
            key={msg.id}
            content={msg.content}
            onRemove={() => handleRemove(msg.id)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * QueuedItem Component
 *
 * Individual queued message item.
 */
function QueuedItem({ content, onRemove }) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      className="queued-item"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="queued-item-icon">
        <Icon name="circle" size={16} />
      </div>

      <div className="queued-item-content">
        <p className="queued-item-text">{content}</p>
      </div>

      <button
        className={`queued-item-remove ${isHovered ? 'visible' : ''}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onRemove();
        }}
        title="Remove from queue"
      >
        <Icon name="x" size={16} />
      </button>
    </div>
  );
}

export default QueuedBox;
