import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import ChatBox from '../components/ChatBox';
import { TaskCard } from '../components/TaskBox';
// Workspace Tabs - New unified workspace component (Eigent-style)
import { WorkspaceTabs } from '../components/Workspace';
// Eigent Migration: Multi-agent and advanced UI components
import { AgentsPanel, AgentStatusBar } from '../components/AgentNode';
import { TokenUsage, BudgetConfigDialog } from '../components/TokenUsage';
import { HumanInteractionModal, HumanMessagesContainer } from '../components/HumanInteraction';
import { TaskList } from '../components/TaskList';
import { useAgentStore } from '../store';
import { api } from '../utils/api';
// Task decomposition panel for task planning
import TaskDecomposition from '../components/TaskDecomposition';
// Note: IntegrationList component is not yet implemented
// import IntegrationList, { IntegrationStatusBar } from '../components/IntegrationList';
import '../styles/AgentPage.css';

/**
 * Agent Page - Autonomous browser automation with Tool-calling
 *
 * Uses EigentStyleBrowserAgent with full Tool-calling architecture:
 * - SSE for real-time event streaming (migrated from WebSocket)
 * - Complete Toolkit system (NoteTaking, Search, Terminal, Human, Browser, Memory)
 * - Memory-guided planning with semantic search
 * - ChatBox for conversation history display
 * - TaskCard for task progress visualization
 * - FileBrowser for workspace files
 */
function AgentPage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();

  // ============ Zustand Store ============
  // All task state and operations from store - single source of truth (Eigent pattern)
  const {
    tasks,
    activeTaskId,
    createTask,
    setActiveTaskId,
    removeTask,
    updateTask,
    addNotice,
    // Task execution methods (delegated to store)
    startTask,
    cancelTask,
    sendHumanResponse,
    // Decomposition methods (Eigent pattern: 30s auto-confirm in store)
    confirmDecomposition,
    cancelDecomposition,
    setTaskEdit,
    budget: storeBudget,
  } = useAgentStore();

  // Get active task from store (computed value)
  const activeTask = activeTaskId ? tasks[activeTaskId] : null;

  // Derive display values from active task
  const taskId = activeTaskId;
  const backendTaskId = activeTask?.backendTaskId || null;  // Backend task ID for API calls
  // For display purposes, prefer backendTaskId if available, otherwise use local taskId
  const displayTaskId = backendTaskId || taskId;
  const status = activeTask?.status || 'idle';
  const taskDescription = activeTask?.taskDescription || '';
  const messages = activeTask?.messages || [];
  const notices = activeTask?.notices || [];
  const agents = activeTask?.agents || [];
  const activeAgentId = activeTask?.activeAgentId || null;
  const toolkitEvents = activeTask?.toolkitEvents || [];
  const terminalOutput = activeTask?.terminalOutput || [];
  const memoryPaths = activeTask?.memoryPaths || [];
  const memoryLevel = activeTask?.memoryLevel || null;
  const memoryLevelReason = activeTask?.memoryLevelReason || '';
  const memoryStatesCount = activeTask?.memoryStatesCount || 0;
  const thinkingLogs = activeTask?.thinkingLogs || [];
  const browserScreenshot = activeTask?.browserScreenshot || null;
  const browserUrl = activeTask?.browserUrl || '';
  const progressValue = activeTask?.progressValue || 0;
  const executionPhase = activeTask?.executionPhase || 'initializing';
  const loopIteration = activeTask?.loopIteration || 0;
  const currentTools = activeTask?.currentTools || [];
  const result = activeTask?.result || null;
  const error = activeTask?.error || null;
  const notesContent = activeTask?.notesContent || null;
  const tokenUsage = activeTask?.tokenUsage || { inputTokens: 0, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 0 };
  const currentModel = activeTask?.currentModel || '';
  const humanQuestion = activeTask?.humanQuestion || null;
  const humanQuestionContext = activeTask?.humanQuestionContext || null;
  const humanInteractionType = activeTask?.humanInteractionType || 'question';
  const humanInteractionOptions = activeTask?.humanInteractionOptions || [];
  const humanInteractionTimeout = activeTask?.humanInteractionTimeout || null;
  const humanMessages = activeTask?.humanMessages || [];
  const subtasks = activeTask?.subtasks || [];
  const showDecomposition = activeTask?.showDecomposition || false;
  const confirmedSubtasks = activeTask?.confirmedSubtasks || [];
  // Eigent: Additional task state for ChatBox BottomBox state machine
  const taskInfo = activeTask?.taskInfo || [];
  const taskRunning = activeTask?.taskRunning || [];
  const summaryTask = activeTask?.summaryTask || '';
  const streamingDecomposeText = activeTask?.streamingDecomposeText || '';
  const isTaskEdit = activeTask?.isTaskEdit || false;
  const taskTime = activeTask?.taskTime || null;
  const elapsed = activeTask?.elapsed || 0;

  // ============ Local UI State (not task-specific) ============
  const [showTaskList, setShowTaskList] = useState(true);
  const [taskInput, setTaskInput] = useState(''); // Input field for new task
  const [selectedFile, setSelectedFile] = useState(null);
  const [showBudgetConfig, setShowBudgetConfig] = useState(false);
  const [budget, setBudget] = useState({ maxCostUsd: null, warningThreshold: 0.8 });
  const [humanResponseInput, setHumanResponseInput] = useState('');
  const [rightPanelWidth, setRightPanelWidth] = useState(480); // Default 480px (increased for tabs)
  const [isResizing, setIsResizing] = useState(false);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState('agent'); // Workspace tab state

  // Right panel resize handler
  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsResizing(true);
  };

  React.useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      // Calculate new width from right edge
      const newWidth = window.innerWidth - e.clientX;
      // Constrain between 280px and 600px
      setRightPanelWidth(Math.max(280, Math.min(600, newWidth)));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing]);

  // Note: Auto-confirm timer is now handled in agentStore (Eigent pattern)
  // Store sets up 30s timer when to_sub_tasks event is received

  // Submit task - delegates to store's startTask (Eigent pattern)
  const handleSubmit = async () => {
    if (!taskInput.trim()) return;

    // Create task in store (this sets activeTaskId automatically)
    const newTaskId = createTask(taskInput.trim());

    // Start task execution (store handles SSE connection and events)
    const success = await startTask(newTaskId, showStatus);

    if (success) {
      // Clear input only on success
      setTaskInput('');
    }
  };

  // Submit human response - delegates to store (Eigent pattern)
  const handleHumanResponse = async (response, isTimeout = false) => {
    const responseText = typeof response === 'string' ? response : humanResponseInput.trim();
    if (!responseText || !activeTaskId) return;

    const success = await sendHumanResponse(activeTaskId, responseText);
    if (success) {
      setHumanResponseInput('');
    } else {
      showStatus('Failed to send response', 'error');
    }
  };

  // Handle task decomposition confirmation (Eigent pattern: delegates to store)
  const handleDecompositionConfirm = async (editedSubtasks) => {
    if (!activeTaskId) return;
    const success = await confirmDecomposition(activeTaskId, editedSubtasks);
    if (!success) {
      showStatus('Failed to confirm plan', 'error');
    }
  };

  // Handle task decomposition cancellation (Eigent pattern: delegates to store)
  const handleDecompositionCancel = async () => {
    if (!activeTaskId) return;
    await cancelDecomposition(activeTaskId);
  };

  // Handle entering task edit mode (Eigent pattern: opens Modal for detailed editing)
  const handleEditTask = () => {
    if (!activeTaskId) return;
    setTaskEdit(activeTaskId, true);
  };

  // Handle exiting task edit mode
  const handleCloseEditTask = () => {
    if (!activeTaskId) return;
    setTaskEdit(activeTaskId, false);
  };

  // Handle budget configuration save
  const handleBudgetSave = async (newBudget) => {
    setBudget(newBudget);
    try {
      await api.callAppBackend('/api/v1/settings/budget', {
        method: 'POST',
        body: JSON.stringify(newBudget)
      });
      showStatus('Budget settings saved', 'success');
    } catch (e) {
      console.error('Failed to save budget:', e);
      showStatus(`Failed to save budget: ${e.message}`, 'error');
    }
  };

  // Dismiss human message
  const handleDismissHumanMessage = (index) => {
    if (!activeTaskId) return;
    updateTask(activeTaskId, {
      humanMessages: (humanMessages || []).filter((_, i) => i !== index)
    });
  };

  // Cancel task - delegates to store (Eigent pattern)
  const handleCancel = async () => {
    if (!activeTaskId) return;
    await cancelTask(activeTaskId, showStatus);
  };

  // Reset to start new task (clears active task selection)
  // Note: Auto-confirm timer cleanup is handled by store when task changes
  const handleReset = () => {
    // Clear local UI state
    setTaskInput('');
    setSelectedFile(null);
    setHumanResponseInput('');

    // Clear active task in store (shows idle state)
    setActiveTaskId(null);
  };

  // Get phase display text
  const getPhaseText = () => {
    switch (executionPhase) {
      case 'initializing': return 'Initializing...';
      case 'starting': return 'Starting browser...';
      case 'memory_loaded': return 'Memory loaded, planning...';
      case 'querying_reasoner': return '🧠 Querying Reasoner...';
      case 'reasoner_executing': return '🧠 Executing Reasoner workflow...';
      case 'reasoner_completed': return '🧠 Reasoner workflow completed';
      case 'memory_guided': return `🧠 Memory L1: Path-guided execution`;
      case 'executing': return `🤖 Agent Loop ${loopIteration}`;
      case 'completed': return 'Completed';
      case 'failed': return 'Failed';
      case 'cancelled': return 'Cancelled';
      default: return executionPhase;
    }
  };

  // Get Memory Level badge info
  const getMemoryLevelBadge = () => {
    if (!memoryLevel) return null;

    const config = {
      'L1': { label: 'L1', color: 'green', title: `Complete path (${memoryStatesCount} states)` },
      'L2': { label: 'L2', color: 'yellow', title: `Partial match (${memoryStatesCount} states)` },
      'L3': { label: 'L3', color: 'gray', title: 'Real-time queries' },
    };

    return config[memoryLevel] || config['L3'];
  };

  // Example tasks
  const exampleTasks = [
    'Go to google.com and search for "AI news 2024"',
    'Navigate to GitHub trending and find the top 3 repositories',
    'Go to Wikipedia and search for "Machine Learning", then summarize the first paragraph'
  ];

  // Handle new task creation from sidebar
  const handleNewTask = () => {
    // Clear local UI state
    setTaskInput('');
    setSelectedFile(null);
    setHumanResponseInput('');

    // Clear active task in store (shows idle state)
    setActiveTaskId(null);
  };

  return (
    <div className="agent-page page fade-in">
      {/* Task List Sidebar */}
      {showTaskList && (
        <TaskList
          onNewTask={handleNewTask}
          collapsed={!showTaskList}
        />
      )}

      {/* Main Content Area */}
      <div className="agent-main-content">
        {/* Compact Header Bar */}
        <div className="page-header compact">
          <div className="header-left">
            {!showTaskList && (
              <button
                className="btn-icon-sm"
                onClick={() => setShowTaskList(true)}
                title="Show Task List"
              >
                <Icon name="menu" size={20} />
              </button>
            )}
            <h1 className="page-title-compact">Agent</h1>
          </div>

          {/* Token Usage in Header (only show when task is running) */}
          {status !== 'idle' && (
            <div className="header-center">
              <TokenUsage
                usage={tokenUsage}
                budget={budget}
                model={currentModel}
                compact={true}
              />
              <button
                className="btn-icon-sm"
                onClick={() => setShowBudgetConfig(true)}
                title="Configure Budget"
              >
                <Icon name="settings" size={16} />
              </button>
            </div>
          )}

          <div className="header-right">
            <button
              className="btn-icon-sm"
              onClick={() => onNavigate('main')}
              title="Back to Home"
            >
              <Icon name="close" size={20} />
            </button>
          </div>
        </div>

        {/* Main Content */}
        <div className="agent-task-content">
          {/* Idle State - Task Input */}
          {status === 'idle' && (
            <div className="task-input-section">
              <div className="card task-card">
                <div className="input-group">
                  <label>Task Description</label>
                  <textarea
                    value={taskInput}
                    onChange={(e) => setTaskInput(e.target.value)}
                    placeholder="e.g., Go to Amazon and search for wireless headphones under $100, find the top 5 rated products and create a summary note"
                    rows={4}
                    className="task-textarea"
                  />
                </div>

                <div className="button-row">
                  <button
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={!taskInput.trim()}
                  >
                    <Icon name="play" size={18} />
                    <span>Start Task</span>
                  </button>
                </div>
              </div>

              {/* Example Tasks */}
              <div className="examples-section">
                <h3>Example Tasks</h3>
                <div className="examples-list">
                  {exampleTasks.map((example, i) => (
                    <button
                      key={i}
                      className="example-btn"
                      onClick={() => setTaskInput(example)}
                    >
                      <Icon name="sparkle" size={16} />
                      <span>{example.slice(0, 60)}...</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Feature Highlights */}
              <div className="features-section">
                <h3>Capabilities</h3>
                <div className="features-grid">
                  <div className="feature-item">
                    <span className="feature-icon">🌐</span>
                    <span className="feature-text">Browser Automation</span>
                  </div>
                  <div className="feature-item">
                    <span className="feature-icon">🔍</span>
                    <span className="feature-text">Web Search</span>
                  </div>
                  <div className="feature-item">
                    <span className="feature-icon">📝</span>
                    <span className="feature-text">Note Taking</span>
                  </div>
                  <div className="feature-item">
                    <span className="feature-icon">🧠</span>
                    <span className="feature-text">Memory-Guided</span>
                  </div>
                  <div className="feature-item">
                    <span className="feature-icon">💻</span>
                    <span className="feature-text">Terminal Commands</span>
                  </div>
                  <div className="feature-item">
                    <span className="feature-icon">👤</span>
                    <span className="feature-text">Human Assistance</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Running/Completed/Failed State - New Eigent-style Layout */}
          {status !== 'idle' && (
            <div
              className={`execution-layout ${isResizing ? 'resizing' : ''}`}
              style={{ '--right-panel-width': `${rightPanelWidth}px` }}
            >
              {/* Left Panel - Pure ChatBox (Eigent Pattern) */}
              <div className="left-panel">
                {/* ChatBox - Conversation messages + BottomBox state machine (Eigent pattern) */}
                <div className="chatbox-container">
                  <ChatBox
                    messages={messages}
                    notices={notices}
                    // Eigent pattern: Pass complete task object for BottomBox state machine
                    task={{
                      taskInfo: taskInfo,
                      taskRunning: taskRunning,
                      status: status,
                      streamingDecomposeText: streamingDecomposeText,
                      summaryTask: summaryTask,
                      progressValue: progressValue,
                      isTaskEdit: isTaskEdit,
                      taskTime: taskTime,
                      elapsed: elapsed,
                      tokens: tokenUsage?.inputTokens + tokenUsage?.outputTokens || 0,
                      showDecomposition: showDecomposition,  // Eigent: Flag to show confirm UI
                    }}
                    // Input control
                    inputValue={taskInput}
                    onInputChange={(e) => setTaskInput(e.target.value)}
                    onSendMessage={handleSubmit}
                    // Task actions
                    onStartTask={() => handleDecompositionConfirm(subtasks)}
                    onEditTask={handleEditTask}
                    onPauseResume={() => console.log('Pause/Resume not implemented')}
                    // Loading states
                    isLoading={status === 'running'}
                    disabled={status === 'running'}
                  />
                </div>

                {/* Action Buttons */}
                {(status === 'completed' || status === 'failed') && (
                  <div className="action-buttons">
                    <button className="btn btn-primary" onClick={handleReset}>
                      <Icon name="plus" size={18} />
                      <span>New Task</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Resize Handle */}
              <div
                className="resize-handle"
                onMouseDown={handleMouseDown}
                title="Drag to resize"
              />

              {/* Right Panel - WorkspaceTabs (Eigent Pattern) */}
              <div className="right-panel" style={{ width: rightPanelWidth }}>
                <WorkspaceTabs
                  activeTab={activeWorkspaceTab}
                  onTabChange={setActiveWorkspaceTab}
                  taskId={displayTaskId}
                  taskStatus={status}
                  // AgentTab data
                  toolkitEvents={toolkitEvents}
                  thinkingLogs={thinkingLogs}
                  memoryPaths={memoryPaths}
                  notices={notices}
                  loopIteration={loopIteration}
                  currentTools={currentTools}
                  result={result}
                  error={error}
                  notes={notesContent}
                  // BrowserTab data
                  browserScreenshot={browserScreenshot}
                  browserUrl={browserUrl}
                  // FilesTab data
                  workspaceFiles={[]}
                  workspacePath=""
                  // TerminalTab data
                  terminalOutput={terminalOutput}
                />
              </div>
            </div>
          )}

          {/* Status Bar - Bottom (Eigent Pattern) */}
          {status !== 'idle' && (
            <div className="task-status-bar bottom">
              <div className="task-status-left">
                {status === 'running' && (
                  <div className="status-badge running">
                    <span className="status-dot"></span>
                    <span>{getPhaseText()}</span>
                  </div>
                )}
                {status === 'completed' && (
                  <div className="status-badge completed">
                    <Icon name="check" size={14} />
                    <span>Completed</span>
                  </div>
                )}
                {status === 'failed' && (
                  <div className="status-badge failed">
                    <Icon name="alert" size={14} />
                    <span>Failed</span>
                  </div>
                )}
                {/* Memory Level Indicator */}
                {memoryLevel && (
                  <div
                    className={`memory-level-badge memory-${memoryLevel.toLowerCase()}`}
                    title={getMemoryLevelBadge()?.title || ''}
                  >
                    <span className="memory-level">{memoryLevel}</span>
                  </div>
                )}
                <span className="task-description-brief" title={taskDescription}>
                  {taskDescription.length > 60 ? taskDescription.slice(0, 60) + '...' : taskDescription}
                </span>
              </div>
              <div className="task-status-right">
                {status === 'running' && (
                  <>
                    <button className="btn-text" onClick={() => console.log('Pause not implemented')}>
                      Pause
                    </button>
                    <button className="btn-text-danger" onClick={handleCancel}>
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="page-footer">
          <div className="footer-content">
            <p>Ami v{version} • Powered by Agent with SSE</p>
            {/* Integration Status Bar - Not yet implemented */}
            {/* <IntegrationStatusBar className="footer-integrations" /> */}
            {/* Agent Status Bar (Eigent Migration) */}
            {agents.length > 0 && (
              <AgentStatusBar agents={agents} />
            )}
          </div>
        </div>
      </div>

      {/* Human Interaction Modal (Eigent Migration - Enhanced) */}
      <HumanInteractionModal
        isOpen={!!humanQuestion}
        type={humanInteractionType}
        title={humanInteractionType === 'confirmation' ? 'Confirmation Required' : 'Agent Question'}
        question={humanQuestion}
        context={humanQuestionContext}
        options={humanInteractionOptions}
        timeout={humanInteractionTimeout}
        onRespond={handleHumanResponse}
        onClose={() => {
          if (activeTaskId) {
            updateTask(activeTaskId, {
              humanQuestion: null,
              humanQuestionContext: null,
              humanInteractionOptions: [],
              humanInteractionTimeout: null
            });
          }
        }}
        placeholder="Type your response..."
      />

      {/* Human Messages Toast Container (Eigent Migration) */}
      <HumanMessagesContainer
        messages={humanMessages}
        onDismiss={handleDismissHumanMessage}
        maxVisible={3}
      />

      {/* Task Decomposition Panel - Show when decomposition is ready for confirmation or editing */}
      {(showDecomposition || isTaskEdit) && subtasks.length > 0 && (
        <div className="task-decomposition-overlay">
          <TaskDecomposition
            subtasks={subtasks}
            onConfirm={(editedSubtasks) => {
              handleDecompositionConfirm(editedSubtasks);
              if (isTaskEdit) {
                handleCloseEditTask();
              }
            }}
            onCancel={isTaskEdit ? handleCloseEditTask : handleDecompositionCancel}
            autoConfirmDelay={isTaskEdit ? 0 : 30}
            isVisible={true}
            title={isTaskEdit ? "Edit Task Plan" : "Task Plan"}
          />
        </div>
      )}

      {/* Budget Configuration Dialog (Eigent Migration) */}
      <BudgetConfigDialog
        isOpen={showBudgetConfig}
        onClose={() => setShowBudgetConfig(false)}
        budget={budget}
        onSave={handleBudgetSave}
      />


    </div >
  );
}

export default AgentPage;
