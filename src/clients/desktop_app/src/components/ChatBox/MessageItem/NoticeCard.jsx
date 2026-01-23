/**
 * Notice Card Component
 *
 * Displays system notifications and status updates in the chat.
 * Used for events like task started, memory loaded, etc.
 */

import React from 'react';
import Icon from '../../Icons';

function NoticeCard({ notice }) {
  const { type, title, message, timestamp, data } = notice;

  // Get icon based on notice type
  const getIcon = () => {
    switch (type) {
      case 'info':
        return <Icon name="info" size={16} />;
      case 'success':
        return <Icon name="check" size={16} />;
      case 'warning':
        return <Icon name="alert" size={16} />;
      case 'error':
        return <Icon name="alert" size={16} />;
      case 'memory':
        return <span className="notice-emoji">🧠</span>;
      case 'tool':
        return <span className="notice-emoji">🔧</span>;
      case 'browser':
        return <span className="notice-emoji">🌐</span>;
      default:
        return <Icon name="info" size={16} />;
    }
  };

  // Get background color class
  const getTypeClass = () => {
    switch (type) {
      case 'success':
        return 'notice-success';
      case 'warning':
        return 'notice-warning';
      case 'error':
        return 'notice-error';
      case 'memory':
        return 'notice-memory';
      default:
        return 'notice-info';
    }
  };

  return (
    <div className={`notice-card ${getTypeClass()}`}>
      <div className="notice-icon">{getIcon()}</div>
      <div className="notice-content">
        {title && <div className="notice-title">{title}</div>}
        {message && <div className="notice-message">{message}</div>}
        {data && (
          <div className="notice-data">
            {typeof data === 'object' ? (
              <pre>{JSON.stringify(data, null, 2)}</pre>
            ) : (
              data
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default NoticeCard;
