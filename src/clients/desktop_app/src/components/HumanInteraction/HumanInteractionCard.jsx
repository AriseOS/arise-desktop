/**
 * HumanInteractionCard Component
 *
 * Inline card for displaying past human interactions in the conversation.
 */

import React from 'react';

function HumanInteractionCard({
  question,
  response,
  timestamp,
}) {
  // Format timestamp
  const formatTime = (ts) => {
    if (!ts) return '';
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="human-interaction-card">
      <span className="card-icon">💬</span>
      <div className="card-content">
        <div className="card-question">
          <span className="question-label">Q:</span>
          <span className="question-text">{question}</span>
        </div>
        {response && (
          <div className="card-response">
            <span className="response-label">A:</span>
            <span className="response-text">{response}</span>
          </div>
        )}
        {timestamp && (
          <div className="card-timestamp">{formatTime(timestamp)}</div>
        )}
      </div>
    </div>
  );
}

export default HumanInteractionCard;
