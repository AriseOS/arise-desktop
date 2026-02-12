/**
 * WorkspaceTabs - Dynamic workspace with tab switching
 *
 * Ported from Eigent's workspace architecture:
 * - Home.tsx: Dynamic workspace switching based on activeWorkSpace
 * - WorkSpaceMenu/index.tsx: Tab toggle group for workspace selection
 * - BrowserAgentWorkSpace/index.tsx: Browser view
 * - TerminalAgentWrokSpace/index.tsx: Terminal view
 * - Folder/index.tsx: File browser view
 * - WorkFlow/node.tsx: Agent execution details with toolkit timeline
 *
 * Key differences from Eigent:
 * - Eigent uses agent-based workspace switching (browser_agent, developer_agent, etc.)
 * - We use tab-based switching (Agent, Browser, Files, Terminal)
 * - Eigent shows toolkit events inside WorkFlow nodes
 * - We show toolkit events in dedicated AgentTab
 */

import React, { useState, useEffect, useCallback } from 'react';
import './WorkspaceTabs.css';

// Tab components
import AgentTab from './tabs/AgentTab';
import BrowserTab from './tabs/BrowserTab';
import FilesTab from './tabs/FilesTab';
import TerminalTab from './tabs/TerminalTab';

/**
 * Tab configuration
 * Following Eigent's agentMap pattern for consistent styling
 */
const TAB_CONFIG = {
  agent: {
    id: 'agent',
    label: 'Agent',
    icon: '🤖',
    description: 'Execution details',
  },
  browser: {
    id: 'browser',
    label: 'Browser',
    icon: '🌐',
    description: 'Browser view',
  },
  files: {
    id: 'files',
    label: 'Files',
    icon: '📁',
    description: 'Workspace files',
  },
  terminal: {
    id: 'terminal',
    label: 'Terminal',
    icon: '💻',
    description: 'Terminal output',
  },
};

/**
 * WorkspaceTabs Component
 *
 * Main container for the right panel workspace.
 * Implements tab switching similar to Eigent's ToggleGroup pattern.
 */
function WorkspaceTabs({
  // Tab state
  activeTab = 'agent',
  onTabChange,

  // Task context
  taskId,
  taskStatus,

  // AgentTab data
  toolkitEvents = [],
  thinkingLogs = [],
  memoryPaths = [],
  notices = [],           // Execution notices (Agent Active, Iteration X, etc.)
  loopIteration = 0,      // Current loop iteration
  currentTools = [],      // Currently executing tools
  result = null,
  error = null,

  // BrowserTab data
  browserScreenshot = null,
  browserUrl = '',

  // FilesTab data
  workspaceFiles = [],
  workspacePath = '',

  // TerminalTab data
  terminalOutput = [],
}) {
  // Local state for tab if not controlled
  const [localActiveTab, setLocalActiveTab] = useState(activeTab);

  // Sync with external activeTab
  useEffect(() => {
    setLocalActiveTab(activeTab);
  }, [activeTab]);

  /**
   * Handle tab change
   * Following Eigent's onValueChange pattern from WorkSpaceMenu
   */
  const handleTabChange = useCallback(
    (tabId) => {
      setLocalActiveTab(tabId);
      if (onTabChange) {
        onTabChange(tabId);
      }
    },
    [onTabChange]
  );

  /**
   * Get badge count for tab
   * Similar to Eigent's nuwFileNum badge logic
   */
  const getTabBadge = (tabId) => {
    switch (tabId) {
      case 'agent':
        // Show count of running toolkit events
        const runningCount = toolkitEvents.filter(
          (e) => e.status === 'running'
        ).length;
        return runningCount > 0 ? runningCount : null;
      case 'files':
        // Show new files count
        return workspaceFiles.length > 0 ? workspaceFiles.length : null;
      case 'terminal':
        // Show if there's new output
        return terminalOutput.length > 0 ? '•' : null;
      default:
        return null;
    }
  };

  /**
   * Render tab content based on active tab
   * Following Eigent's conditional rendering pattern in Home.tsx
   */
  const renderTabContent = () => {
    switch (localActiveTab) {
      case 'agent':
        return (
          <AgentTab
            taskId={taskId}
            taskStatus={taskStatus}
            toolkitEvents={toolkitEvents}
            thinkingLogs={thinkingLogs}
            memoryPaths={memoryPaths}
            notices={notices}
            loopIteration={loopIteration}
            currentTools={currentTools}
            result={result}
            error={error}
          />
        );
      case 'browser':
        return (
          <BrowserTab
            taskId={taskId}
            screenshot={browserScreenshot}
            url={browserUrl}
          />
        );
      case 'files':
        return (
          <FilesTab
            taskId={taskId}
            files={workspaceFiles}
            workspacePath={workspacePath}
          />
        );
      case 'terminal':
        return <TerminalTab taskId={taskId} output={terminalOutput} />;
      default:
        return null;
    }
  };

  return (
    <div className="workspace-tabs">
      {/* Tab Header - Similar to Eigent's ToggleGroup */}
      <div className="workspace-tabs-header">
        <div className="workspace-tabs-list">
          {Object.values(TAB_CONFIG).map((tab) => {
            const badge = getTabBadge(tab.id);
            const isActive = localActiveTab === tab.id;

            return (
              <button
                key={tab.id}
                className={`workspace-tab-button ${isActive ? 'active' : ''}`}
                onClick={() => handleTabChange(tab.id)}
                title={tab.description}
              >
                <span className="workspace-tab-icon">{tab.icon}</span>
                <span className="workspace-tab-label">{tab.label}</span>
                {badge && <span className="workspace-tab-badge">{badge}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content - Similar to Eigent's dynamic workspace rendering */}
      <div className="workspace-tabs-content">{renderTabContent()}</div>
    </div>
  );
}

export default WorkspaceTabs;
