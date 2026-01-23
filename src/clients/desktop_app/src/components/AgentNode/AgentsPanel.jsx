/**
 * AgentsPanel Component
 *
 * Container for displaying multiple agents and their status.
 * Enhanced to support toolkit events, screenshots, and completion reports.
 */

import React, { useState, useMemo, useCallback } from 'react';
import AgentNode, { AgentStatus } from './AgentNode';
import AgentStatusBar from './AgentStatusBar';

function AgentsPanel({
  agents = [],
  activeAgentId = null,
  currentTools = {},
  toolkitEventsByAgent = {},
  screenshotsByAgent = {},
  completionReportsByAgent = {},
  terminalOutputByAgent = {},
  filesByAgent = {},
  expandedAgentId = null,
  showStatusBar = true,
  onAgentClick,
  onAgentExpand,
  onTaskClick,
  onScreenshotClick,
}) {
  const [localExpandedId, setLocalExpandedId] = useState(expandedAgentId);

  // Handle agent expansion
  const handleAgentExpand = useCallback((agentId) => {
    const newExpandedId = localExpandedId === agentId ? null : agentId;
    setLocalExpandedId(newExpandedId);
    if (onAgentExpand) {
      onAgentExpand(newExpandedId);
    }
  }, [localExpandedId, onAgentExpand]);

  // Count agents by status
  const statusCounts = useMemo(() => {
    return agents.reduce((acc, agent) => {
      const status = agent.status || AgentStatus.IDLE;
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {});
  }, [agents]);

  // Calculate total progress
  const totalProgress = useMemo(() => {
    if (agents.length === 0) return 0;
    const sum = agents.reduce((acc, agent) => acc + (agent.progress || 0), 0);
    return Math.round(sum / agents.length);
  }, [agents]);

  if (agents.length === 0) {
    return (
      <div className="agents-panel">
        <div className="panel-header">
          <span className="panel-icon">🤖</span>
          <span className="panel-title">Agents</span>
          <span className="panel-count">0</span>
        </div>
        <div className="agents-empty">
          <span>No agents active</span>
        </div>
      </div>
    );
  }

  return (
    <div className="agents-panel">
      {/* Header */}
      <div className="panel-header">
        <div className="panel-header-left">
          <span className="panel-icon">🤖</span>
          <span className="panel-title">Agents</span>
          <span className="panel-count">{agents.length}</span>
        </div>
        {totalProgress > 0 && (
          <div className="panel-progress">
            <span className="progress-text">{totalProgress}%</span>
          </div>
        )}
      </div>

      {/* Status bar summary */}
      {showStatusBar && (
        <AgentStatusBar agents={agents} />
      )}

      {/* Agents List */}
      <div className="agents-list">
        {agents.map((agent) => {
          const agentId = agent.id;
          const isExpanded = localExpandedId === agentId || (activeAgentId === agentId && localExpandedId === null);

          return (
            <AgentNode
              key={agentId}
              agent={agent}
              isActive={agentId === activeAgentId}
              currentTool={currentTools[agentId]}
              progress={agent.progress}
              tasks={agent.tasks || []}
              toolkitEvents={toolkitEventsByAgent[agentId] || agent.toolkitEvents || []}
              webviewScreenshots={screenshotsByAgent[agentId] || agent.screenshots || []}
              completionReport={completionReportsByAgent[agentId] || agent.completionReport}
              terminalOutput={terminalOutputByAgent[agentId] || agent.terminalOutput}
              files={filesByAgent[agentId] || agent.files || []}
              isExpanded={isExpanded}
              showDetails={true}
              onClick={() => {
                handleAgentExpand(agentId);
                if (onAgentClick) onAgentClick(agent);
              }}
              onTaskClick={onTaskClick}
              onScreenshotClick={onScreenshotClick}
            />
          );
        })}
      </div>
    </div>
  );
}

export default AgentsPanel;
