/**
 * AgentStatusBar Component
 *
 * Compact status bar showing agent counts by status.
 */

import React from 'react';
import { AgentStatus } from './AgentNode';

function AgentStatusBar({ agents = [], className = '' }) {
  // Count agents by status
  const statusCounts = agents.reduce((acc, agent) => {
    const status = agent.status || AgentStatus.IDLE;
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  const active = statusCounts[AgentStatus.ACTIVE] || 0;
  const completed = statusCounts[AgentStatus.COMPLETED] || 0;
  const error = statusCounts[AgentStatus.ERROR] || 0;

  return (
    <div className={`agent-status-bar ${className}`}>
      <div className={`status-item ${active > 0 ? 'active' : ''}`}>
        <span className="status-value">{active}</span>
        <span className="status-label">Active</span>
      </div>
      <div className={`status-item ${completed > 0 ? 'completed' : ''}`}>
        <span className="status-value">{completed}</span>
        <span className="status-label">Done</span>
      </div>
      {error > 0 && (
        <div className="status-item failed">
          <span className="status-value">{error}</span>
          <span className="status-label">Failed</span>
        </div>
      )}
    </div>
  );
}

export default AgentStatusBar;
