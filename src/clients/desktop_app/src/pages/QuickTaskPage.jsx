import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import { BACKEND_CONFIG } from '../config/backend';
import '../styles/QuickTaskPage.css';

/**
 * Quick Task Page - Autonomous browser automation
 *
 * Users input natural language tasks, and the EigentBrowserAgent
 * completes them autonomously using LLM-guided browser control.
 */
function QuickTaskPage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();

  // Task input state
  const [task, setTask] = useState('');

  // Execution state
  const [taskId, setTaskId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, running, completed, failed
  const [actionHistory, setActionHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Real-time progress state
  const [plan, setPlan] = useState([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [currentAction, setCurrentAction] = useState(null);
  const [executionPhase, setExecutionPhase] = useState('initializing'); // initializing, planning, executing

  // WebSocket ref
  const wsRef = useRef(null);
  const actionListRef = useRef(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Submit task
  const handleSubmit = async () => {
    if (!task.trim()) return;

    setStatus('running');
    setError(null);
    setActionHistory([]);
    setResult(null);

    try {
      const response = await api.callAppBackend('/api/v1/quick-task/execute', {
        method: 'POST',
        body: JSON.stringify({
          task: task.trim()
        })
      });

      setTaskId(response.task_id);
      showStatus('Task submitted successfully', 'success');

      // Connect WebSocket
      connectWebSocket(response.task_id);

    } catch (e) {
      console.error('Submit error:', e);
      setStatus('failed');
      setError(e.message);
      showStatus(`Failed to submit task: ${e.message}`, 'error');
    }
  };

  // Connect WebSocket for real-time progress
  const connectWebSocket = (id) => {
    const wsUrl = `${BACKEND_CONFIG.wsBase}/api/v1/quick-task/ws/${id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleProgressEvent(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (e) => {
      console.error('WebSocket error:', e);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
    };
  };

  // Auto-scroll action list to bottom
  useEffect(() => {
    if (actionListRef.current) {
      actionListRef.current.scrollTop = actionListRef.current.scrollHeight;
    }
  }, [actionHistory]);

  // Handle progress events
  const handleProgressEvent = (event) => {
    console.log('Progress event:', event);

    switch (event.event) {
      case 'connected':
        // Connection confirmed
        setExecutionPhase('initializing');
        break;

      case 'task_started':
        setStatus('running');
        setExecutionPhase('planning');
        break;

      case 'plan_generated':
        // LLM generated a plan
        setExecutionPhase('executing');
        if (event.plan) {
          setPlan(event.plan);
        }
        break;

      case 'step_started':
        // A step is about to execute
        setCurrentStep(event.step || 0);
        setCurrentAction(event.action);
        break;

      case 'step_completed':
        // A step completed successfully
        setCurrentStep(event.step || 0);
        if (event.action_history) {
          setActionHistory(event.action_history);
        }
        setCurrentAction(null);
        break;

      case 'step_failed':
        // A step failed (but task may continue)
        setCurrentStep(event.step || 0);
        if (event.action_history) {
          setActionHistory(event.action_history);
        }
        setCurrentAction(null);
        break;

      case 'task_completed':
        setStatus('completed');
        setResult(event.output);
        setExecutionPhase('completed');
        if (event.action_history) {
          setActionHistory(event.action_history);
        }
        break;

      case 'task_failed':
        setStatus('failed');
        setError(event.error);
        setExecutionPhase('failed');
        break;

      case 'task_cancelled':
        setStatus('failed');
        setError('Task was cancelled');
        setExecutionPhase('cancelled');
        break;

      case 'heartbeat':
        // Keep alive
        break;

      default:
        console.log('Unknown event:', event);
    }
  };

  // Cancel task
  const handleCancel = async () => {
    if (!taskId) return;

    try {
      await api.callAppBackend(`/api/v1/quick-task/cancel/${taskId}`, {
        method: 'POST'
      });
      showStatus('Task cancelled', 'info');
    } catch (e) {
      console.error('Cancel error:', e);
      showStatus(`Failed to cancel: ${e.message}`, 'error');
    }
  };

  // Reset to start new task
  const handleReset = () => {
    setTask('');
    setTaskId(null);
    setStatus('idle');
    setActionHistory([]);
    setResult(null);
    setError(null);
    setPlan([]);
    setCurrentStep(0);
    setCurrentAction(null);
    setExecutionPhase('initializing');

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  // Get action type icon
  const getActionIcon = (actionType) => {
    switch (actionType) {
      case 'click': return '👆';
      case 'type': return '⌨️';
      case 'navigate': return '🌐';
      case 'scroll': return '📜';
      case 'select': return '📋';
      case 'enter': return '↵';
      case 'wait': return '⏳';
      case 'back': return '◀️';
      case 'forward': return '▶️';
      case 'finish': return '✅';
      default: return '🔧';
    }
  };

  // Format action for display
  const formatAction = (action) => {
    if (!action) return '';
    const type = action.type || 'unknown';
    let detail = '';

    if (action.ref) detail = `[${action.ref}]`;
    else if (action.text) detail = `"${action.text.slice(0, 30)}${action.text.length > 30 ? '...' : ''}"`;
    else if (action.url) detail = action.url.slice(0, 40) + (action.url.length > 40 ? '...' : '');
    else if (action.selector) detail = action.selector.slice(0, 30);

    return detail ? `${type} ${detail}` : type;
  };

  // Example tasks
  const exampleTasks = [
    'Go to google.com and search for "AI news 2024"',
    'Navigate to GitHub trending and find the top 3 repositories',
    'Go to Wikipedia and search for "Machine Learning"'
  ];

  // Render action history item
  const renderActionItem = (item, index) => {
    const actionType = item.action?.type || 'unknown';
    const isSuccess = item.success;

    return (
      <div key={index} className={`action-item ${isSuccess ? 'success' : 'failed'}`}>
        <div className="action-step-number">{index + 1}</div>
        <div className="action-emoji-icon">
          {getActionIcon(actionType)}
        </div>
        <div className="action-content">
          <span className="action-type">{actionType}</span>
          {item.action?.ref && (
            <span className="action-ref">{item.action.ref}</span>
          )}
          {item.action?.text && (
            <span className="action-text">"{item.action.text.slice(0, 30)}{item.action.text.length > 30 ? '...' : ''}"</span>
          )}
          {item.action?.url && (
            <span className="action-url" title={item.action.url}>
              {item.action.url.length > 35 ? item.action.url.slice(0, 35) + '...' : item.action.url}
            </span>
          )}
          {item.action?.selector && (
            <span className="action-selector">{item.action.selector.slice(0, 25)}</span>
          )}
        </div>
        <div className={`action-status-icon ${isSuccess ? 'success' : 'failed'}`}>
          {isSuccess ? '✓' : '✗'}
        </div>
      </div>
    );
  };

  return (
    <div className="quick-task-page page fade-in">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Quick Task</h1>
          <p className="page-subtitle">
            Describe a task in natural language, AI will complete it autonomously
          </p>
        </div>
        <button
          className="btn-icon"
          onClick={() => onNavigate('main')}
          title="Back to Home"
        >
          <Icon name="close" size={24} />
        </button>
      </div>

      {/* Idle State - Task Input */}
      {status === 'idle' && (
        <div className="task-input-section">
          <div className="card task-card">
            <div className="input-group">
              <label>Task Description</label>
              <textarea
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="e.g., Go to Amazon and search for wireless headphones under $100, find the top 5 rated products"
                rows={4}
                className="task-textarea"
              />
            </div>

            <div className="button-row">
              <button
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={!task.trim()}
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
                  onClick={() => setTask(example)}
                >
                  <Icon name="sparkle" size={16} />
                  <span>{example.slice(0, 50)}...</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Running State */}
      {status === 'running' && (
        <div className="execution-section">
          <div className="card task-card">
            <div className="task-header">
              <h3>Task</h3>
              <p>{task}</p>
            </div>

            {/* Progress Section */}
            <div className="progress-section">
              <div className="progress-header">
                <div className="status-indicator running">
                  <div className="spinner"></div>
                  <span>
                    {executionPhase === 'initializing' && 'Starting browser...'}
                    {executionPhase === 'planning' && 'Analyzing page...'}
                    {executionPhase === 'executing' && `Step ${currentStep}`}
                  </span>
                </div>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleCancel}
                >
                  Cancel
                </button>
              </div>
            </div>

            {/* Plan Display */}
            {plan.length > 0 && (
              <div className="plan-section">
                <h4>Plan</h4>
                <div className="plan-list">
                  {plan.map((step, i) => {
                    // Handle both formats: string or {step, path_ref} object
                    const stepText = typeof step === 'string' ? step : step.step;
                    return (
                      <div key={i} className="plan-item">
                        <span className="plan-number">{i + 1}.</span>
                        <span className="plan-text">{stepText}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Current Action */}
            {currentAction && (
              <div className="current-action">
                <div className="current-action-label">Executing:</div>
                <div className="current-action-content">
                  <span className="action-emoji">{getActionIcon(currentAction.type)}</span>
                  <span className="action-detail">{formatAction(currentAction)}</span>
                </div>
              </div>
            )}

            {/* Action History */}
            {actionHistory.length > 0 && (
              <div className="action-history">
                <h4>Action History ({actionHistory.length})</h4>
                <div className="action-list" ref={actionListRef}>
                  {actionHistory.map((item, i) => renderActionItem(item, i))}
                </div>
              </div>
            )}

            {/* Waiting message - only show when no progress yet */}
            {actionHistory.length === 0 && !currentAction && executionPhase === 'initializing' && (
              <div className="waiting-message">
                <p>Browser is starting...</p>
                <p className="hint">This may take a moment</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Completed State */}
      {status === 'completed' && (
        <div className="result-section">
          <div className="card result-card success">
            <div className="result-header">
              <div className="result-icon success">
                <Icon name="check" size={32} />
              </div>
              <div>
                <h3>Task Completed</h3>
                <p>{task}</p>
              </div>
            </div>

            {/* Result */}
            {result && (
              <div className="result-content">
                <h4>Result</h4>
                <pre className="result-pre">
                  {typeof result === 'object'
                    ? JSON.stringify(result, null, 2)
                    : result
                  }
                </pre>
              </div>
            )}

            {/* Action History Summary */}
            {actionHistory.length > 0 && (
              <div className="action-history">
                <h4>Steps Executed ({actionHistory.length})</h4>
                <div className="action-list">
                  {actionHistory.map((item, i) => renderActionItem(item, i))}
                </div>
              </div>
            )}

            <div className="button-row">
              <button
                className="btn btn-primary"
                onClick={handleReset}
              >
                <Icon name="plus" size={18} />
                <span>New Task</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Failed State */}
      {status === 'failed' && (
        <div className="result-section">
          <div className="card result-card failed">
            <div className="result-header">
              <div className="result-icon failed">
                <Icon name="alert" size={32} />
              </div>
              <div>
                <h3>Task Failed</h3>
                <p>{task}</p>
              </div>
            </div>

            {error && (
              <div className="error-content">
                <h4>Error</h4>
                <pre className="error-pre">{error}</pre>
              </div>
            )}

            {/* Action History up to failure */}
            {actionHistory.length > 0 && (
              <div className="action-history">
                <h4>Steps Executed Before Failure</h4>
                <div className="action-list">
                  {actionHistory.map((item, i) => renderActionItem(item, i))}
                </div>
              </div>
            )}

            <div className="button-row">
              <button
                className="btn btn-secondary"
                onClick={handleReset}
              >
                <Icon name="refresh" size={18} />
                <span>Try Again</span>
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  handleReset();
                }}
              >
                <Icon name="plus" size={18} />
                <span>New Task</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="page-footer">
        <p>Ami v{version} • Quick Task powered by EigentBrowserAgent</p>
      </div>
    </div>
  );
}

export default QuickTaskPage;
