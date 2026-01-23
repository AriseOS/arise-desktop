import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import ChatBox from '../components/ChatBox';
import { TaskCard } from '../components/TaskBox';
import { FileBrowser, FilePreview, TerminalOutput } from '../components/Workspace';
// Eigent Migration: Multi-agent and advanced UI components
import { AgentsPanel, AgentStatusBar } from '../components/AgentNode';
import { TokenUsage, BudgetConfigDialog } from '../components/TokenUsage';
import { HumanInteractionModal, HumanMessagesContainer } from '../components/HumanInteraction';
import { TaskList } from '../components/TaskList';
import { useAgentStore } from '../store';
import { api } from '../utils/api';
// Note: TaskDecomposition and IntegrationList components are not yet implemented
// import TaskDecomposition, { DecompositionSummary } from '../components/TaskDecomposition';
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
  const status = activeTask?.status || 'idle';
  const taskDescription = activeTask?.taskDescription || '';
  const messages = activeTask?.messages || [];
  const notices = activeTask?.notices || [];
  const agents = activeTask?.agents || [];
  const activeAgentId = activeTask?.activeAgentId || null;
  const toolkitEvents = activeTask?.toolkitEvents || [];
  const terminalOutput = activeTask?.terminalOutput || [];
  const memoryPaths = activeTask?.memoryPaths || [];
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

  // ============ Local UI State (not task-specific) ============
  const [showTaskList, setShowTaskList] = useState(true);
  const [taskInput, setTaskInput] = useState(''); // Input field for new task
  const [selectedFile, setSelectedFile] = useState(null);
  const [showBudgetConfig, setShowBudgetConfig] = useState(false);
  const [budget, setBudget] = useState({ maxCostUsd: null, warningThreshold: 0.8 });
  const [humanResponseInput, setHumanResponseInput] = useState('');
  const [rightPanelWidth, setRightPanelWidth] = useState(380); // Default 380px
  const [isResizing, setIsResizing] = useState(false);

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
      case 'executing': return `🤖 Agent Loop ${loopIteration}`;
      case 'completed': return 'Completed';
      case 'failed': return 'Failed';
      case 'cancelled': return 'Cancelled';
      default: return executionPhase;
    }
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

          {/* Running/Completed/Failed State */}
          {status !== 'idle' && (
            <div
              className={`execution-layout ${isResizing ? 'resizing' : ''}`}
              style={{ '--right-panel-width': `${rightPanelWidth}px` }}
            >
              {/* Left Panel - Chat & Progress */}
              <div className="left-panel">
                {/* Compact Task Status Bar */}
                <div className="task-status-bar">
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
                    <span className="task-description-brief" title={taskDescription}>
                      {taskDescription.length > 50 ? taskDescription.slice(0, 50) + '...' : taskDescription}
                    </span>
                  </div>
                  <div className="task-status-right">
                    {status === 'running' && (
                      <button className="btn-text-danger" onClick={handleCancel}>
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Collapsible Tool Activity */}
                {toolkitEvents.length > 0 && (
                  <details className="tool-activity-panel" open>
                    <summary className="tool-activity-header">
                      <span className="tool-activity-title">
                        <Icon name="tool" size={14} />
                        Tool Activity
                      </span>
                      <span className="tool-activity-count">{toolkitEvents.length}</span>
                    </summary>
                    <div className="tool-activity-list">
                      {toolkitEvents.slice(-30).map((event, index) => (
                        <div key={event.id || index} className={`tool-activity-item ${event.status || ''}`}>
                          <span className="tool-status-icon">
                            {event.status === 'running' && <span className="spinner-tiny"></span>}
                            {event.status === 'completed' && '✓'}
                            {event.status === 'failed' && '✗'}
                          </span>
                          <span className="tool-name">{event.toolkit_name}</span>
                          <span className="tool-method">.{event.method_name}()</span>
                          {event.input_preview && (
                            <span className="tool-input" title={event.input_preview}>
                              {event.input_preview.length > 60
                                ? event.input_preview.slice(0, 60) + '...'
                                : event.input_preview}
                            </span>
                          )}
                          {event.page_url && (
                            <a
                              href={event.page_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="tool-url"
                              title={event.page_url}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {new URL(event.page_url).hostname}
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Memory Paths */}
                {memoryPaths.length > 0 && (
                  <div className="memory-paths-card">
                    <h4>
                      <span className="memory-icon">🧠</span>
                      Memory Reference ({memoryPaths.length} paths)
                    </h4>
                    <div className="memory-paths-list">
                      {memoryPaths.map((path, i) => (
                        <div key={i} className="memory-path-item">
                          <span className="path-score">{(path.score * 100).toFixed(0)}%</span>
                          <span className="path-description">{path.description || path.domain}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ChatBox */}
                <div className="chatbox-container">
                  <ChatBox
                    messages={messages}
                    notices={notices}
                  />
                </div>

                {/* Result Section */}
                {status === 'completed' && result && (
                  <div className="result-card">
                    <h4>Result</h4>
                    <pre className="result-content">
                      {typeof result === 'object' ? JSON.stringify(result, null, 2) : result}
                    </pre>
                  </div>
                )}

                {/* Error Section */}
                {status === 'failed' && error && (
                  <div className="error-card">
                    <h4>Error</h4>
                    <pre className="error-content">{error}</pre>
                  </div>
                )}

                {/* Notes Section */}
                {notesContent && (
                  <div className="notes-card">
                    <h4>
                      <span className="notes-icon">📝</span>
                      Research Notes
                    </h4>
                    <pre className="notes-content">{notesContent}</pre>
                  </div>
                )}

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

              {/* Right Panel - Workspace */}
              <div className="right-panel" style={{ width: rightPanelWidth }}>
                {/* Multi-Agent Panel */}
                {agents.length > 0 && (
                  <div className="workspace-section agents-section">
                    <AgentsPanel
                      agents={agents}
                      activeAgentId={activeAgentId}
                      onAgentClick={(agentId) => {
                        if (activeTaskId) {
                          updateTask(activeTaskId, { activeAgentId: agentId });
                        }
                      }}
                    />
                  </div>
                )}

                {/* Task Decomposition Summary - Not yet implemented */}
                {/* {confirmedSubtasks.length > 0 && (
                <div className="workspace-section decomposition-section">
                  <DecompositionSummary
                    subtasks={confirmedSubtasks}
                    status={status}
                  />
                </div>
              )} */}

                {/* File Browser and Preview */}
                <div className="workspace-section file-browser-section">
                  <FileBrowser
                    taskId={backendTaskId}
                    onFileSelect={setSelectedFile}
                    selectedFile={selectedFile}
                  />
                </div>

                {/* File Preview */}
                {selectedFile && (
                  <div className="workspace-section file-preview-section">
                    <FilePreview
                      taskId={backendTaskId}
                      filePath={selectedFile}
                      onClose={() => setSelectedFile(null)}
                    />
                  </div>
                )}

                {/* Terminal Output */}
                <div className="workspace-section terminal-section">
                  <TerminalOutput
                    output={terminalOutput}
                    title="Terminal Output"
                  />
                </div>
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

      {/* Task Decomposition Modal - Not yet implemented */}
      {/* {showDecomposition && (
        <div className="task-decomposition-overlay">
          <TaskDecomposition
            subtasks={subtasks}
            onConfirm={handleDecompositionConfirm}
            onCancel={handleDecompositionCancel}
            autoConfirmDelay={30}
            isVisible={showDecomposition}
            title="Task Plan"
          />
        </div>
      )} */}

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
