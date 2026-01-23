# Frontend Implementation Migration Guide

## Overview

This document describes the frontend features needed to support the migrated backend capabilities, based on Eigent's frontend implementation patterns.

## Architecture Comparison

### Eigent Frontend Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| React | UI Framework | 18.3.1 |
| Vite | Build Tool | 5.4.11 |
| Electron | Desktop App | 33.2.0 |
| TypeScript | Type Safety | 5.4.2 |
| **Zustand** | State Management | 5.0.4 |
| @microsoft/fetch-event-source | **SSE Streaming** | - |
| @xyflow/react | Workflow Visualization | 12.6.4 |
| xterm.js | Terminal Emulation | 5.5.0 |
| Radix UI | Component Library | v1-2 |
| Sonner | Toast Notifications | 2.0.6 |

### 2ami Frontend Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| React | UI Framework | 18.2.0 |
| Vite | Build Tool | 4.4.5 |
| Tauri | Desktop App | 2.9.0 |
| JavaScript | Language | ES2022 |
| **Local State (Hooks)** | State Management | - |
| **WebSocket** | Real-time Events | - |
| React Flow | Workflow Visualization | 11.11.4 |
| - | Terminal (N/A) | - |
| Custom CSS | Component Styling | - |
| Custom | Toast (StatusMessage) | - |

### Key Differences

| Feature | Eigent | 2ami |
|---------|--------|------|
| Real-time Events | **SSE** (fetch-event-source) | **WebSocket** |
| State Management | Zustand (global stores) | Local hooks (component state) |
| TypeScript | Yes | No (JavaScript) |
| Electron IPC | Yes (window.ipcRenderer) | Tauri invoke API |
| Component Library | Radix UI + shadcn | Custom CSS |

---

## Frontend Features to Implement

### 1. Multi-Agent Workflow Visualization

**Eigent Implementation** (`src/components/WorkFlow/`)

Eigent uses React Flow to visualize the multi-agent orchestration:

```tsx
// WorkFlow/node.tsx - Agent node component
const agentMap = {
  developer_agent: {
    name: "Developer Agent",
    icon: <CodeXml size={16} />,
    textColor: "text-emerald-700",
    bgColor: "bg-emerald-100",
  },
  browser_agent: {
    name: "Browser Agent",
    icon: <Globe size={16} />,
    textColor: "text-blue-700",
    bgColor: "bg-blue-100",
  },
  document_agent: {
    name: "Document Agent",
    icon: <FileText size={16} />,
    textColor: "text-yellow-700",
    bgColor: "bg-yellow-100",
  },
  // ... more agents
};
```

**Migration for 2ami** (`src/pages/QuickTaskPage.jsx`)

Add multi-agent visualization:

```jsx
// Add to QuickTaskPage.jsx

// Agent configuration
const AGENT_CONFIG = {
  browser_agent: {
    name: 'Browser Agent',
    icon: '🌐',
    color: '#3B82F6', // blue
    bgColor: 'rgba(59, 130, 246, 0.1)',
  },
  developer_agent: {
    name: 'Developer Agent',
    icon: '💻',
    color: '#10B981', // emerald
    bgColor: 'rgba(16, 185, 129, 0.1)',
  },
  document_agent: {
    name: 'Document Agent',
    icon: '📄',
    color: '#F59E0B', // yellow
    bgColor: 'rgba(245, 158, 11, 0.1)',
  },
  question_confirm_agent: {
    name: 'Confirmation Agent',
    icon: '❓',
    color: '#8B5CF6', // purple
    bgColor: 'rgba(139, 92, 246, 0.1)',
  },
};

// Agent display component
function AgentNode({ agent, tasks, isActive }) {
  const config = AGENT_CONFIG[agent.type] || {
    name: agent.name,
    icon: '🤖',
    color: '#6B7280',
    bgColor: 'rgba(107, 114, 128, 0.1)',
  };

  const completedTasks = tasks.filter(t => t.status === 'completed').length;
  const totalTasks = tasks.length;

  return (
    <div
      className={`agent-node ${isActive ? 'active' : ''}`}
      style={{ borderColor: config.color, backgroundColor: config.bgColor }}
    >
      <div className="agent-header">
        <span className="agent-icon">{config.icon}</span>
        <span className="agent-name">{config.name}</span>
        {isActive && <span className="agent-status-indicator">⏳</span>}
      </div>
      <div className="agent-progress">
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{
              width: `${(completedTasks / totalTasks) * 100}%`,
              backgroundColor: config.color,
            }}
          />
        </div>
        <span className="progress-text">{completedTasks}/{totalTasks}</span>
      </div>
      <div className="agent-tasks">
        {tasks.slice(0, 3).map((task, idx) => (
          <div key={idx} className={`task-item ${task.status}`}>
            {task.status === 'completed' ? '✓' : task.status === 'running' ? '⏳' : '○'}
            {task.content.slice(0, 50)}...
          </div>
        ))}
        {tasks.length > 3 && (
          <div className="more-tasks">+{tasks.length - 3} more</div>
        )}
      </div>
    </div>
  );
}
```

**CSS for Agent Nodes**:

```css
/* Add to QuickTaskPage.css */

.agents-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.agent-node {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 2px solid transparent;
  transition: all var(--transition-fast);
}

.agent-node.active {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.agent-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.agent-icon {
  font-size: 1.25rem;
}

.agent-name {
  font-weight: 600;
  color: var(--text-primary);
}

.agent-status-indicator {
  margin-left: auto;
  animation: pulse 1.5s infinite;
}

.agent-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.agent-tasks {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: 0.875rem;
}

.task-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
}

.task-item.completed {
  color: var(--color-success);
}

.task-item.running {
  color: var(--primary-main);
}
```

---

### 2. Real-time Event Handling (SSE vs WebSocket)

**Eigent SSE Implementation** (`chatStore.ts`):

```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source';

// SSE connection with AbortController
const abortController = new AbortController();
activeSSEControllers[taskId] = abortController;

fetchEventSource(api, {
  method: "POST",
  openWhenHidden: true,
  signal: abortController.signal,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ task_id: taskId, question: task }),

  async onmessage(event) {
    const agentMessages = JSON.parse(event.data);

    // Event type handling
    switch (agentMessages.step) {
      case "create_agent":
        // Add agent to taskAssigning
        break;
      case "activate_toolkit":
        // Tool execution started
        break;
      case "deactivate_toolkit":
        // Tool execution completed
        break;
      case "task_state":
        // Task status update
        break;
      case "wait_confirm":
        // Human confirmation needed
        break;
      case "end":
        // Task completed
        break;
    }
  },

  onclose() {
    delete activeSSEControllers[taskId];
  },

  onerror(err) {
    console.error('SSE error:', err);
    throw err; // Throw to trigger reconnect
  }
});
```

**2ami WebSocket Implementation** (keep current approach, enhance):

```jsx
// QuickTaskPage.jsx - Enhanced WebSocket handling

// New event types to handle
const handleProgressEvent = (event) => {
  switch (event.event) {
    // === Agent Lifecycle Events ===
    case 'agent_created':
      // Add new agent to agents list
      setAgents(prev => [...prev, {
        agent_id: event.agent_id,
        name: event.agent_name,
        type: event.agent_type,
        tasks: [],
        status: 'idle',
      }]);
      break;

    case 'agent_activated':
      // Mark agent as active, show tool being executed
      setAgents(prev => prev.map(agent =>
        agent.agent_id === event.agent_id
          ? { ...agent, status: 'active', currentTool: event.tool_name }
          : agent
      ));
      break;

    // === Task Assignment Events ===
    case 'task_assigned':
      // Assign task to agent
      setAgents(prev => prev.map(agent =>
        agent.agent_id === event.assignee_id
          ? {
              ...agent,
              tasks: [...agent.tasks, {
                task_id: event.task_id,
                content: event.content,
                status: 'waiting',
              }]
            }
          : agent
      ));
      break;

    case 'task_state_changed':
      // Update task status within agent
      setAgents(prev => prev.map(agent => ({
        ...agent,
        tasks: agent.tasks.map(task =>
          task.task_id === event.task_id
            ? { ...task, status: event.state, result: event.result }
            : task
        )
      })));
      break;

    // === Budget Events ===
    case 'budget_warning':
      setBudgetStatus({
        warning: true,
        usage: event.usage,
        percentage: event.percentage_used,
      });
      showStatus(`Warning: ${Math.round(event.percentage_used.cost * 100)}% of budget used`, 'warning');
      break;

    case 'budget_exceeded':
      setBudgetStatus({
        exceeded: true,
        usage: event.usage,
        action: event.action,
      });
      showStatus('Budget exceeded!', 'error');
      break;

    // === Existing events (keep) ===
    case 'tool_started':
    case 'tool_executed':
    case 'human_question':
    case 'task_completed':
    // ... keep existing handlers
  }
};
```

---

### 3. Task Decomposition UI

**Eigent Implementation** (`chatStore.ts` - to_sub_tasks event):

```typescript
if (agentMessages.step === "to_sub_tasks") {
  // Clear streaming text
  clearStreamingDecomposeText(currentTaskId);

  // Add notice message
  addMessages(currentTaskId, {
    id: generateUniqueId(),
    role: "agent",
    content: "",
    step: 'notice_card',
  });

  // Add task decomposition message
  addMessages(currentTaskId, {
    id: generateUniqueId(),
    role: "agent",
    content: "",
    step: 'to_sub_tasks',
    taskType: 1,
    showType: "list",
    isConfirm: false,
    task_id: currentTaskId
  });

  // Set auto-confirm timer (30 seconds)
  autoConfirmTimers[currentTaskId] = setTimeout(() => {
    handleConfirmTask(project_id, currentId, type);
  }, 30000);

  // Update task info
  setTaskInfo(currentTaskId, agentMessages.data.sub_tasks);
  setTaskRunning(currentTaskId, agentMessages.data.sub_tasks);
}
```

**Migration for 2ami**:

```jsx
// Add task decomposition panel to QuickTaskPage.jsx

// State
const [decomposedTasks, setDecomposedTasks] = useState([]);
const [showTaskDecomposition, setShowTaskDecomposition] = useState(false);
const [taskDecompositionConfirmed, setTaskDecompositionConfirmed] = useState(false);
const autoConfirmTimerRef = useRef(null);

// Handle decomposition event
case 'task_decomposed':
  setDecomposedTasks(event.subtasks || []);
  setShowTaskDecomposition(true);
  setTaskDecompositionConfirmed(false);

  // Auto-confirm after 30 seconds
  if (autoConfirmTimerRef.current) {
    clearTimeout(autoConfirmTimerRef.current);
  }
  autoConfirmTimerRef.current = setTimeout(() => {
    handleConfirmDecomposition();
  }, 30000);
  break;

// Confirm decomposition
const handleConfirmDecomposition = async () => {
  if (autoConfirmTimerRef.current) {
    clearTimeout(autoConfirmTimerRef.current);
  }

  // Send confirmation via WebSocket
  if (wsRef.current) {
    wsRef.current.send(JSON.stringify({
      type: 'confirm_decomposition',
      task_id: taskId,
      confirmed: true,
    }));
  }

  setTaskDecompositionConfirmed(true);
  setShowTaskDecomposition(false);
};

// Edit task
const handleEditTask = (index, newContent) => {
  setDecomposedTasks(prev =>
    prev.map((task, i) =>
      i === index ? { ...task, content: newContent } : task
    )
  );
};

// Render
{showTaskDecomposition && (
  <div className="task-decomposition-panel">
    <div className="decomposition-header">
      <h3>Task Plan</h3>
      <span className="auto-confirm-timer">
        Auto-confirming in {autoConfirmSeconds}s
      </span>
    </div>
    <div className="subtasks-list">
      {decomposedTasks.map((task, index) => (
        <div key={task.id || index} className="subtask-item">
          <span className="subtask-number">{index + 1}</span>
          <input
            type="text"
            value={task.content}
            onChange={(e) => handleEditTask(index, e.target.value)}
            className="subtask-input"
          />
          <button
            className="subtask-delete"
            onClick={() => handleDeleteTask(index)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
    <div className="decomposition-actions">
      <button className="btn-secondary" onClick={() => setShowTaskDecomposition(false)}>
        Edit More
      </button>
      <button className="btn-primary" onClick={handleConfirmDecomposition}>
        Confirm & Execute
      </button>
    </div>
  </div>
)}
```

---

### 4. Budget/Token Usage Display

**Eigent Implementation** (`Toast/creditsToast.tsx`):

```tsx
import { toast } from 'sonner';

export const showCreditsToast = () => {
  toast.error("Budget limit reached", {
    description: "You've reached your token limit. Please upgrade your plan.",
    duration: Infinity,
    closeButton: true,
  });
};
```

**Migration for 2ami**:

```jsx
// Add to QuickTaskPage.jsx

// State
const [tokenUsage, setTokenUsage] = useState({
  inputTokens: 0,
  outputTokens: 0,
  totalTokens: 0,
  estimatedCost: 0,
  model: '',
});

const [budgetConfig, setBudgetConfig] = useState({
  maxTokens: null,
  maxCostUsd: null,
  warningThreshold: 0.8,
});

// Handle token update events
case 'token_usage_update':
  setTokenUsage(prev => ({
    inputTokens: prev.inputTokens + (event.input_tokens || 0),
    outputTokens: prev.outputTokens + (event.output_tokens || 0),
    totalTokens: prev.totalTokens + (event.total_tokens || 0),
    estimatedCost: event.estimated_cost || prev.estimatedCost,
    model: event.model || prev.model,
  }));
  break;

// Render token usage indicator
function TokenUsageIndicator({ usage, budget }) {
  const percentUsed = budget.maxCostUsd
    ? (usage.estimatedCost / budget.maxCostUsd) * 100
    : null;

  const isWarning = percentUsed && percentUsed >= budget.warningThreshold * 100;

  return (
    <div className={`token-usage-indicator ${isWarning ? 'warning' : ''}`}>
      <div className="usage-stats">
        <span className="stat">
          <span className="label">Tokens:</span>
          <span className="value">{usage.totalTokens.toLocaleString()}</span>
        </span>
        <span className="stat">
          <span className="label">Cost:</span>
          <span className="value">${usage.estimatedCost.toFixed(4)}</span>
        </span>
      </div>
      {percentUsed !== null && (
        <div className="budget-progress">
          <div
            className="budget-fill"
            style={{ width: `${Math.min(percentUsed, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
```

**CSS**:

```css
.token-usage-indicator {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  font-size: 0.875rem;
}

.token-usage-indicator.warning {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.usage-stats {
  display: flex;
  gap: var(--space-4);
}

.stat {
  display: flex;
  gap: var(--space-1);
}

.stat .label {
  color: var(--text-secondary);
}

.stat .value {
  color: var(--text-primary);
  font-weight: 500;
  font-family: monospace;
}

.budget-progress {
  height: 4px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}

.budget-fill {
  height: 100%;
  background: var(--primary-main);
  transition: width 0.3s ease;
}

.token-usage-indicator.warning .budget-fill {
  background: #F59E0B;
}
```

---

### 5. Human-in-the-Loop Confirmation UI

**Eigent Implementation** (wait_confirm event + Dialog):

```typescript
// chatStore.ts
if (agentMessages.step === "wait_confirm") {
  const { content, question } = agentMessages.data;
  setHasWaitComfirm(currentTaskId, true);
  setIsPending(currentTaskId, false);

  addMessages(currentTaskId, {
    id: generateUniqueId(),
    role: "agent",
    content: content,
    step: "wait_confirm",
    isConfirm: false,
  });
}
```

**Enhanced 2ami Implementation**:

```jsx
// QuickTaskPage.jsx - Enhanced human interaction

// State
const [humanInteraction, setHumanInteraction] = useState({
  visible: false,
  type: 'question', // 'question' | 'confirmation' | 'notification'
  question: '',
  context: '',
  options: [], // For multiple choice
  timeout: null, // Auto-timeout for confirmations
});

// Handle events
case 'human_question':
  setHumanInteraction({
    visible: true,
    type: 'question',
    question: event.question,
    context: event.context || '',
    options: event.options || [],
    timeout: null,
  });
  break;

case 'human_confirmation':
  setHumanInteraction({
    visible: true,
    type: 'confirmation',
    question: event.message,
    context: event.details || '',
    options: [
      { label: 'Confirm', value: 'yes' },
      { label: 'Cancel', value: 'no' },
    ],
    timeout: event.timeout || 30,
  });
  // Start timeout countdown
  startConfirmationTimeout(event.timeout || 30);
  break;

case 'human_notification':
  // Show as toast, don't block
  showStatus(event.message, event.level || 'info');
  setHumanMessages(prev => [...prev, {
    title: event.title,
    message: event.message,
    timestamp: new Date().toISOString(),
  }]);
  break;

// Render human interaction modal
function HumanInteractionModal({ interaction, onRespond, onClose }) {
  const [response, setResponse] = useState('');
  const [timeLeft, setTimeLeft] = useState(interaction.timeout);

  useEffect(() => {
    if (!interaction.timeout) return;

    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          onRespond('timeout');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [interaction.timeout]);

  return (
    <div className="human-interaction-modal">
      <div className="modal-content">
        <div className="modal-header">
          <span className="modal-icon">
            {interaction.type === 'question' ? '❓' : '⚠️'}
          </span>
          <h3>
            {interaction.type === 'question' ? 'Agent Question' : 'Confirmation Required'}
          </h3>
          {timeLeft && (
            <span className="timeout-badge">
              {timeLeft}s
            </span>
          )}
        </div>

        <div className="modal-body">
          <p className="question-text">{interaction.question}</p>
          {interaction.context && (
            <div className="context-box">
              <pre>{interaction.context}</pre>
            </div>
          )}

          {interaction.options.length > 0 ? (
            <div className="options-list">
              {interaction.options.map((option, idx) => (
                <button
                  key={idx}
                  className={`option-btn ${option.value === 'yes' ? 'primary' : 'secondary'}`}
                  onClick={() => onRespond(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-response">
              <textarea
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                placeholder="Type your response..."
                rows={3}
              />
              <button
                className="submit-btn"
                onClick={() => onRespond(response)}
                disabled={!response.trim()}
              >
                Send Response
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

---

### 6. Integration List for Cloud Services

**Eigent Implementation** (`IntegrationList/index.tsx`):

```tsx
const integrations = [
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    icon: <Calendar />,
    description: 'Manage calendar events',
    authType: 'oauth',
    provider: 'google',
  },
  {
    id: 'google_drive',
    name: 'Google Drive',
    icon: <HardDrive />,
    description: 'Access and manage files',
    authType: 'oauth',
    provider: 'google',
  },
  // ... more integrations
];

// OAuth flow
const handleInstall = async (integration) => {
  if (integration.authType === 'oauth') {
    // Open OAuth window
    window.ipcRenderer.invoke('open-oauth', {
      provider: integration.provider,
      scopes: integration.scopes,
    });

    // Poll for completion
    const pollInterval = setInterval(async () => {
      const status = await fetchGet(`/oauth/status/${integration.provider}`);
      if (status.completed) {
        clearInterval(pollInterval);
        setInstalledIntegrations(prev => [...prev, integration.id]);
      }
    }, 1500);
  }
};
```

**Migration for 2ami** (new page/component):

```jsx
// components/IntegrationList.jsx

const INTEGRATIONS = [
  {
    id: 'gmail',
    name: 'Gmail',
    icon: '📧',
    description: 'Send and receive emails',
    authType: 'oauth',
    provider: 'google',
    scopes: ['gmail.readonly', 'gmail.send'],
    envVars: ['GMAIL_CREDENTIALS_PATH'],
  },
  {
    id: 'google_drive',
    name: 'Google Drive',
    icon: '📁',
    description: 'Access and manage files',
    authType: 'oauth',
    provider: 'google',
    scopes: ['drive.readonly', 'drive.file'],
    envVars: ['GDRIVE_CREDENTIALS_PATH'],
  },
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    icon: '📅',
    description: 'Manage calendar events',
    authType: 'oauth',
    provider: 'google',
    scopes: ['calendar'],
    envVars: ['GCAL_CREDENTIALS_PATH'],
  },
  {
    id: 'notion',
    name: 'Notion',
    icon: '📝',
    description: 'Access Notion pages and databases',
    authType: 'token',
    envVars: ['NOTION_API_KEY'],
  },
];

function IntegrationList({ onIntegrationChange }) {
  const [installed, setInstalled] = useState([]);
  const [configuring, setConfiguring] = useState(null);

  useEffect(() => {
    // Load installed integrations from backend
    loadInstalledIntegrations();
  }, []);

  const loadInstalledIntegrations = async () => {
    try {
      const response = await api.callAppBackend('/api/v1/integrations/list');
      setInstalled(response.installed || []);
    } catch (e) {
      console.error('Failed to load integrations:', e);
    }
  };

  const handleInstall = async (integration) => {
    if (integration.authType === 'oauth') {
      // Start OAuth flow via Tauri
      const { invoke } = await import('@tauri-apps/api/tauri');
      await invoke('open_oauth', {
        provider: integration.provider,
        scopes: integration.scopes,
      });

      // Poll for completion
      const checkStatus = async () => {
        const status = await api.callAppBackend(
          `/api/v1/integrations/oauth-status/${integration.provider}`
        );
        if (status.completed) {
          setInstalled(prev => [...prev, integration.id]);
          onIntegrationChange?.(integration.id, 'installed');
        } else if (!status.failed) {
          setTimeout(checkStatus, 1500);
        }
      };
      checkStatus();

    } else if (integration.authType === 'token') {
      // Show token configuration dialog
      setConfiguring(integration);
    }
  };

  const handleUninstall = async (integrationId) => {
    try {
      await api.callAppBackend(`/api/v1/integrations/uninstall/${integrationId}`, {
        method: 'POST',
      });
      setInstalled(prev => prev.filter(id => id !== integrationId));
      onIntegrationChange?.(integrationId, 'uninstalled');
    } catch (e) {
      console.error('Failed to uninstall:', e);
    }
  };

  return (
    <div className="integration-list">
      <h3>Cloud Integrations</h3>
      <div className="integrations-grid">
        {INTEGRATIONS.map(integration => (
          <IntegrationCard
            key={integration.id}
            integration={integration}
            installed={installed.includes(integration.id)}
            onInstall={() => handleInstall(integration)}
            onUninstall={() => handleUninstall(integration.id)}
          />
        ))}
      </div>

      {configuring && (
        <TokenConfigDialog
          integration={configuring}
          onSave={(config) => {
            saveIntegrationConfig(configuring.id, config);
            setConfiguring(null);
          }}
          onClose={() => setConfiguring(null)}
        />
      )}
    </div>
  );
}

function IntegrationCard({ integration, installed, onInstall, onUninstall }) {
  return (
    <div className={`integration-card ${installed ? 'installed' : ''}`}>
      <div className="integration-icon">{integration.icon}</div>
      <div className="integration-info">
        <h4>{integration.name}</h4>
        <p>{integration.description}</p>
      </div>
      <div className="integration-status">
        {installed ? (
          <>
            <span className="status-dot installed" />
            <button className="btn-uninstall" onClick={onUninstall}>
              Uninstall
            </button>
          </>
        ) : (
          <button className="btn-install" onClick={onInstall}>
            Install
          </button>
        )}
      </div>
    </div>
  );
}
```

---

### 7. State Management Migration

**Eigent Zustand Pattern**:

```typescript
// chatStore.ts
const chatStore = createStore<ChatStore>()((set, get) => ({
  activeTaskId: null,
  tasks: {},

  create(id) {
    const taskId = id || generateUniqueId();
    set((state) => ({
      activeTaskId: taskId,
      tasks: {
        ...state.tasks,
        [taskId]: { /* initial task state */ },
      },
    }));
    return taskId;
  },

  addMessages(taskId, message) {
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          messages: [...state.tasks[taskId].messages, message],
        },
      },
    }));
  },
}));
```

**2ami Option 1: Keep Local State (simpler for now)**

Keep current approach with React hooks for simplicity. Good for single-page task execution.

**2ami Option 2: Add Zustand for Complex State (recommended for multi-agent)**

```jsx
// store/taskStore.js
import { create } from 'zustand';

export const useTaskStore = create((set, get) => ({
  // Active task
  activeTaskId: null,
  tasks: {},

  // Agents
  agents: {},

  // Create task
  createTask: (taskId) => {
    set((state) => ({
      activeTaskId: taskId,
      tasks: {
        ...state.tasks,
        [taskId]: {
          status: 'pending',
          agents: [],
          subtasks: [],
          messages: [],
          tokenUsage: { input: 0, output: 0, cost: 0 },
          startedAt: Date.now(),
        },
      },
    }));
  },

  // Add agent
  addAgent: (taskId, agent) => {
    set((state) => ({
      agents: {
        ...state.agents,
        [agent.agent_id]: agent,
      },
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          agents: [...state.tasks[taskId].agents, agent.agent_id],
        },
      },
    }));
  },

  // Update agent status
  updateAgent: (agentId, updates) => {
    set((state) => ({
      agents: {
        ...state.agents,
        [agentId]: {
          ...state.agents[agentId],
          ...updates,
        },
      },
    }));
  },

  // Add subtask to agent
  addSubtask: (agentId, subtask) => {
    set((state) => ({
      agents: {
        ...state.agents,
        [agentId]: {
          ...state.agents[agentId],
          tasks: [...(state.agents[agentId].tasks || []), subtask],
        },
      },
    }));
  },

  // Update token usage
  addTokenUsage: (taskId, usage) => {
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          ...state.tasks[taskId],
          tokenUsage: {
            input: state.tasks[taskId].tokenUsage.input + usage.input,
            output: state.tasks[taskId].tokenUsage.output + usage.output,
            cost: usage.cost,
          },
        },
      },
    }));
  },

  // Clear task
  clearTask: (taskId) => {
    set((state) => {
      const { [taskId]: removed, ...remainingTasks } = state.tasks;
      return { tasks: remainingTasks };
    });
  },
}));
```

---

## Event Types Reference

### Backend → Frontend Events (WebSocket)

| Event | Data | Purpose |
|-------|------|---------|
| `agent_created` | agent_id, agent_name, agent_type, tools | New agent registered |
| `agent_activated` | agent_id, tool_name, tool_input | Agent started tool execution |
| `task_assigned` | task_id, assignee_id, content, state | Task assigned to agent |
| `task_state_changed` | task_id, state, result, failure_count | Task status update |
| `tool_started` | tool_name, tool_input | Tool execution began |
| `tool_executed` | tool_name, result_preview, error | Tool execution completed |
| `budget_warning` | usage, percentage_used | Budget threshold reached |
| `budget_exceeded` | usage, action | Budget limit exceeded |
| `human_question` | question, context, options | Agent needs input |
| `human_confirmation` | message, details, timeout | Action confirmation needed |
| `task_decomposed` | subtasks, summary | Task split into subtasks |
| `task_completed` | output, notes, tools_called | Task finished |
| `task_failed` | error, notes | Task failed |

### Frontend → Backend Events (WebSocket)

| Event | Data | Purpose |
|-------|------|---------|
| `human_response` | response | Answer to agent question |
| `confirm_decomposition` | task_id, confirmed | Approve task plan |
| `cancel_task` | task_id | Request task cancellation |
| `edit_subtask` | task_id, subtask_id, content | Modify subtask |

---

## File Structure

```
src/clients/desktop_app/src/
├── pages/
│   └── QuickTaskPage.jsx        # MODIFY: Add multi-agent support
├── components/
│   ├── AgentNode.jsx            # NEW: Agent visualization
│   ├── TaskDecomposition.jsx    # NEW: Task plan editor
│   ├── TokenUsage.jsx           # NEW: Budget indicator
│   ├── HumanInteraction.jsx     # NEW: Enhanced Q&A modal
│   └── IntegrationList.jsx      # NEW: Cloud service integrations
├── store/
│   └── taskStore.js             # NEW: Zustand store (optional)
└── styles/
    └── QuickTaskPage.css        # MODIFY: Add new component styles
```

---

## Implementation Priority

1. **Phase 1** (High Priority):
   - Enhanced event handling for agent lifecycle
   - Token/budget usage display
   - Task decomposition panel

2. **Phase 2** (Medium Priority):
   - Multi-agent visualization (AgentNode)
   - Human interaction enhancements
   - Zustand state management

3. **Phase 3** (Lower Priority):
   - Integration list UI
   - OAuth flow handling
   - Advanced workflow visualization

---

## References

- Eigent frontend: `third-party/eigent/src/`
- 2ami frontend: `src/clients/desktop_app/src/`
- Zustand docs: https://github.com/pmndrs/zustand
- React Flow docs: https://reactflow.dev/
