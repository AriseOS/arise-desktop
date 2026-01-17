import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import { BACKEND_CONFIG } from '../config/backend';
import '../styles/WorkflowExecutionLivePage.css';

const WS_BASE = BACKEND_CONFIG.wsBase; // WebSocket uses backend config

function WorkflowExecutionLivePage({
  session,
  onNavigate,
  showStatus,
  taskId,
  workflowName = 'Workflow Execution'
}) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [status, setStatus] = useState('connecting'); // 'connecting', 'running', 'stopping', 'stopped', 'completed', 'failed'
  const [isStopping, setIsStopping] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [totalSteps, setTotalSteps] = useState(0);
  const [steps, setSteps] = useState([]);
  const [logs, setLogs] = useState([]);
  const [expandedLogs, setExpandedLogs] = useState(new Set());
  const [currentMessage, setCurrentMessage] = useState('Connecting...');
  const [elapsedTime, setElapsedTime] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);

  const wsRef = useRef(null);
  const logsEndRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const shouldReconnectRef = useRef(true);
  const reconnectAttemptsRef = useRef(0);
  const timelineContainerRef = useRef(null);
  const currentStepRef = useRef(null);

  // WebSocket connection management
  useEffect(() => {
    if (!taskId) {
      showStatus(t('workflowExecution.noTaskId'), 'error');
      return;
    }

    connectWebSocket();

    // Cleanup on unmount
    return () => {
      console.log('[WS] Cleaning up WebSocket connection');
      shouldReconnectRef.current = false;

      if (wsRef.current) {
        console.log('[WS] Closing WebSocket connection');
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = null;
      }
    };
  }, [taskId]);

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket(`${WS_BASE}/ws/v1/executions/${taskId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected to workflow progress stream');
        setWsConnected(true);
        setStatus('running');
        setCurrentMessage(t('workflowExecution.waitingForUpdates'));
        reconnectAttemptsRef.current = 0; // Reset reconnect counter on successful connection

        // Start heartbeat
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000); // Send heartbeat every 30 seconds
      };

      ws.onmessage = (event) => {
        // Ignore heartbeat responses
        if (event.data === 'pong') {
          return;
        }
        try {
          const data = JSON.parse(event.data);
          handleProgressUpdate(data);
        } catch (error) {
          console.error('[WS] Failed to parse message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[WS] WebSocket error:', error);
        setWsConnected(false);
        // Don't show error popup immediately - let onclose handle reconnection
        // Only log the error for debugging purposes
      };

      ws.onclose = () => {
        console.log('[WS] Connection closed');
        setWsConnected(false);

        // Clear heartbeat
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }

        // Attempt to reconnect if we should
        if (shouldReconnectRef.current) {
          reconnectAttemptsRef.current += 1;

          // Only show error if reconnect attempts exceed threshold
          if (reconnectAttemptsRef.current > 3) {
            showStatus(t('workflowExecution.failedToConnect'), 'error');
            setCurrentMessage(t('workflowExecution.connectionFailed'));
          } else {
            setCurrentMessage(t('workflowExecution.connectionLost'));
            reconnectTimeoutRef.current = setTimeout(() => {
              console.log(`[WS] Attempting to reconnect (attempt ${reconnectAttemptsRef.current})...`);
              connectWebSocket();
            }, 3000);
          }
        }
      };
    } catch (error) {
      console.error('[WS] Failed to create WebSocket connection:', error);
      showStatus(t('workflowExecution.failedLog'), 'error');
    }
  };

  const handleProgressUpdate = (data) => {
    console.log('[WS] Progress update:', data);

    if (data.type === 'initial_status') {
      // Handle initial status message
      const initialData = data.data;
      setStatus(initialData.status);
      setProgress(initialData.progress);
      setCurrentStep(initialData.current_step);
      setTotalSteps(initialData.total_steps);
      setCurrentMessage(initialData.message);

      // Set steps if provided in initial status
      if (initialData.steps) {
        setSteps(initialData.steps);
      }

      return;
    }

    if (data.type === 'progress_update') {
      setStatus(data.status);
      setProgress(data.progress);
      setCurrentStep(data.current_step);
      setTotalSteps(data.total_steps);
      setCurrentMessage(data.message);

      // Update steps if provided
      if (data.steps) {
        setSteps(data.steps);
      }

      // Update step info if available
      if (data.step_info) {
        updateStepInfo(data.current_step, data.step_info);
      }

      // Add log entry from message
      if (data.message) {
        addLogEntry({
          level: data.status === 'failed' ? 'error' : 'info',
          message: data.message,
          time: new Date(data.timestamp).toLocaleTimeString()
        });
      }

      // Add log entry if provided
      if (data.log) {
        const logEntry = {
          level: data.log.level || 'info',
          message: data.log.message,
          time: data.log.time,
          metadata: data.log.metadata || null
        };

        // Debug: log when code content is received
        if (logEntry.metadata && logEntry.metadata.content_type === 'code') {
          console.log('[Debug] Code content received:', {
            hasScriptContent: !!logEntry.metadata.script_content,
            scriptLength: logEntry.metadata.script_content?.length,
            metadata: logEntry.metadata
          });
        }

        addLogEntry(logEntry);
      }

      // Handle completion/stopped states
      if (data.status === 'completed' || data.status === 'failed' || data.status === 'stopped') {
        shouldReconnectRef.current = false;
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }

        // Reset stopping state when workflow actually stops
        if (data.status === 'stopped') {
          setIsStopping(false);
        }
      }
    }
  };

  const updateStepInfo = (stepIndex, stepInfo) => {
    setSteps(prevSteps => {
      const newSteps = [...prevSteps];

      // Ensure array is large enough
      while (newSteps.length <= stepIndex) {
        newSteps.push({
          id: newSteps.length,
          name: `Step ${newSteps.length + 1}`,
          status: 'pending'
        });
      }

      // Update step
      newSteps[stepIndex] = {
        ...newSteps[stepIndex],
        id: stepIndex,
        name: stepInfo.name || newSteps[stepIndex].name,
        status: stepInfo.status,
        result: stepInfo.result,
        duration: stepInfo.duration
      };

      return newSteps;
    });
  };

  const addLogEntry = (logEntry) => {
    setLogs(prevLogs => {
      // Check if this is a dynamic update (has update_id in metadata)
      const updateId = logEntry.metadata?.update_id;

      if (updateId) {
        // Find existing log with same update_id
        const existingIndex = prevLogs.findIndex(
          log => log.metadata?.update_id === updateId
        );

        if (existingIndex >= 0) {
          // Update existing log
          const newLogs = [...prevLogs];
          newLogs[existingIndex] = {
            ...newLogs[existingIndex],
            message: logEntry.message,
            metadata: logEntry.metadata,
            time: logEntry.time
          };
          return newLogs;
        }
      }

      // Add new log entry
      return [...prevLogs, logEntry];
    });
  };

  const toggleLogExpand = (idx) => {
    setExpandedLogs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(idx)) {
        newSet.delete(idx);
      } else {
        newSet.add(idx);
      }
      return newSet;
    });
  };

  // Time tracking
  useEffect(() => {
    if (status === 'running') {
      const interval = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);

      return () => clearInterval(interval);
    }
  }, [status]);

  // Auto-scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Auto-scroll timeline to current step
  useEffect(() => {
    if (currentStepRef.current && timelineContainerRef.current) {
      currentStepRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
  }, [currentStep]);

  // Handle stop workflow
  const handleStopWorkflow = async () => {
    if (isStopping || status !== 'running') return;

    setIsStopping(true);
    setStatus('stopping');
    setCurrentMessage(t('workflowExecution.stopping'));

    try {
      const result = await api.stopWorkflow(taskId);
      if (result.success) {
        showStatus(t('workflowExecution.stopRequested'), 'info');
        // Status will be updated via WebSocket when workflow actually stops
      } else {
        showStatus(result.error || t('workflowExecution.failedToStop'), 'error');
        setIsStopping(false);
        setStatus('running');
      }
    } catch (error) {
      console.error('Failed to stop workflow:', error);
      showStatus(t('workflowExecution.stopFailed', { error: error.message }), 'error');
      setIsStopping(false);
      setStatus('running');
    }
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getLogIcon = (level) => {
    switch (level) {
      case 'success': return <Icon icon="check" size={14} />;
      case 'error': return <Icon icon="x" size={14} />;
      case 'warning': return <Icon icon="alertTriangle" size={14} />;
      default: return <Icon icon="info" size={14} />;
    }
  };

  const getLogColor = (level) => {
    switch (level) {
      case 'success': return '#10B981';
      case 'error': return '#EF4444';
      case 'warning': return '#F59E0B';
      default: return '#888';
    }
  };

  // Recursive step renderer
  const renderSteps = (stepList, depth = 0) => {
    return stepList.map((step, idx) => {
      // Check for nested children (v2 'do', or generic 'steps'/'children')
      const children = step.do || step.steps || step.children;
      const hasChildren = children && children.length > 0;
      const isLoop = step.type === 'loop' || 'foreach' in step; // Identify loop intent

      // Indentation style
      const indentStyle = {
        marginLeft: `${depth * 20}px`,
        borderLeft: depth > 0 ? '2px solid var(--border-color)' : 'none',
        paddingLeft: depth > 0 ? '12px' : '0'
      };

      return (
        <div key={step.id || `step-${idx}-${depth}`} style={indentStyle}>
          <div
            className={`timeline-step ${step.status}`}
            ref={step.status === 'in_progress' ? currentStepRef : null}
          >
            <div className="timeline-node">
              {step.status === 'in_progress' && <div className="node-pulse" />}
              {/* Optional: Show icon for loops */}
              {isLoop && <Icon icon="repeat" size={12} style={{ marginBottom: 2 }} />}
            </div>
            <div className="timeline-content">
              <div className="step-name">
                {step.name || step.intent_name || (isLoop ? `Loop: ${step.as || 'Items'}` : `Step ${idx + 1}`)}
              </div>
              {step.duration && (
                <div className="step-duration">{step.duration.toFixed(1)}s</div>
              )}
            </div>
          </div>

          {/* Render Children Recursively */}
          {hasChildren && (
            <div className="step-children" style={{ marginTop: '8px' }}>
              {renderSteps(children, depth + 1)}
            </div>
          )}
        </div>
      );
    });
  };


  return (
    <div className="workflow-execution-live-page">
      {/* Header */}
      <div className="execution-header">
        <div className="header-left">
          <button className="back-button" onClick={() => onNavigate("main")}>
            <Icon icon="arrowLeft" />
          </button>
          <div className="header-info">
            <h1 className="execution-title">{workflowName}</h1>
            <div className="execution-meta">
              <span className="meta-badge" data-status={status}>
                {status === 'connecting' && <><Icon icon="loader" size={14} /> {t('workflowExecution.status.connecting')}</>}
                {status === 'running' && <><Icon icon="play" size={14} /> {t('workflowExecution.status.running')}</>}
                {status === 'stopping' && <><Icon icon="loader" size={14} /> {t('workflowExecution.status.stopping')}</>}
                {status === 'stopped' && <><Icon icon="square" size={14} /> {t('workflowExecution.status.stopped')}</>}
                {status === 'completed' && <><Icon icon="checkCircle" size={14} /> {t('workflowExecution.status.completed')}</>}
                {status === 'failed' && <><Icon icon="alertCircle" size={14} /> {t('workflowExecution.status.failed')}</>}
              </span>
              <span className="meta-time">{t('workflowExecution.elapsed', { time: formatTime(elapsedTime) })}</span>
              <span className={`connection-status ${wsConnected ? 'connected' : 'disconnected'}`}>
                <Icon icon={wsConnected ? "wifi" : "wifiOff"} size={14} />
                {wsConnected ? t('workflowExecution.live') : t('workflowExecution.offline')}
              </span>
            </div>
          </div>
        </div>
        <div className="header-actions">
          {(status === 'running' || status === 'stopping') && (
            <button
              className="btn-stop"
              onClick={handleStopWorkflow}
              disabled={isStopping || status === 'stopping'}
            >
              <Icon icon={isStopping ? "loader" : "square"} />
              {isStopping ? t('workflowExecution.stopping') : t('workflowExecution.stop')}
            </button>
          )}
          {status === 'completed' && (
            <button className="btn-view-results" onClick={() => onNavigate('execution-result', { taskId })}>
              <Icon icon="barChart" /> {t('workflowExecution.viewResults')}
            </button>
          )}
          {(status === 'failed' || status === 'stopped') && (
            <button className="btn-back" onClick={() => onNavigate('main')}>
              <Icon icon="home" /> {t('workflowExecution.backToHome')}
            </button>
          )}
        </div>
      </div>

      {/* Progress Section */}
      <div className="progress-section">
        <div className="progress-header">
          <h2><Icon icon="activity" size={20} /> {t('workflowExecution.progressTitle')}</h2>
          <span className="progress-text">
            {currentStep >= 0
              ? t('workflowExecution.stepProgress', { current: currentStep + 1, total: totalSteps })
              : t('workflowExecution.initializing')}
          </span>
        </div>

        {/* Cold Start Notice */}
        {status === 'running' && (
          <div className="cold-start-notice" style={{
            marginBottom: '1rem',
            padding: '0.75rem',
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            borderRadius: '8px',
            color: '#1e40af',
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem'
          }}>
            <Icon icon="info" size={16} />
            <span>
              <strong>{t('workflowExecution.coldStart.title')}</strong> {t('workflowExecution.coldStart.content')}
            </span>
          </div>
        )}

        {/* Progress Bar */}
        <div className="progress-bar-container">
          <div
            className="progress-bar-fill"
            style={{ width: `${progress}%` }}
            data-status={status}
          ></div>
        </div>
        <div className="progress-info">
          <span className="progress-percent">{progress}%</span>
          <span className="progress-message">{currentMessage}</span>
        </div>

        {/* Timeline */}
        <div className="timeline-container" ref={timelineContainerRef}>
          <div className="timeline">
            {steps.length === 0 ? (
              <div className="timeline-empty" style={{
                color: 'var(--text-tertiary)',
                fontSize: '13px',
                textAlign: 'center',
                padding: '40px 0'
              }}>
                {t('workflowExecution.waitingForSteps')}
              </div>
            ) : (
              renderSteps(steps)
            )}
          </div>
        </div>
      </div>

      {/* Logs Section */}
      <div className="logs-section">
        <div className="logs-header">
          <h3><Icon icon="fileText" size={18} /> {t('workflowExecution.logsTitle')}</h3>
          <div className="logs-actions">
            <button className="btn-clear-logs" onClick={() => setLogs([])}>
              {t('workflowExecution.clearLogs')}
            </button>
          </div>
        </div>
        <div className="logs-content">
          {logs.length === 0 ? (
            <div className="logs-empty">
              <p>{t('workflowExecution.waitingForLogs')}</p>
            </div>
          ) : (
            <div className="logs-list">
              {logs.map((log, idx) => {
                const hasMetadata = log.metadata && Object.keys(log.metadata).length > 0;
                const isExpanded = expandedLogs.has(idx);

                return (
                  <div key={idx} className="log-entry" data-level={log.level}>
                    <div className="log-main">
                      <span className="log-icon">
                        {log.metadata?.update_id && !log.metadata?.completed ? (
                          <Icon icon="loader" size={14} className="spinning-loader" />
                        ) : (
                          getLogIcon(log.level)
                        )}
                      </span>
                      <span className="log-time">{log.time}</span>
                      <span className="log-message" style={{ color: getLogColor(log.level) }}>
                        {log.message}
                      </span>
                      {hasMetadata && (
                        <button
                          className="log-expand-btn"
                          onClick={() => toggleLogExpand(idx)}
                          title={isExpanded ? t('workflowExecution.hideDetails') : t('workflowExecution.showDetails')}
                        >
                          <Icon icon={isExpanded ? "chevron-up" : "chevron-down"} size={14} />
                        </button>
                      )}
                    </div>
                    {hasMetadata && isExpanded && (
                      <div className="log-metadata">
                        {log.metadata.content_type === 'code' ? (
                          log.metadata.script_content ? (
                            <div className="code-content">
                              <div className="code-header">
                                <span className="code-label">
                                  {log.metadata.language || 'code'}
                                </span>
                                <span className="code-label" style={{ fontSize: '10px' }}>
                                  {log.metadata.script_content.length} chars
                                </span>
                              </div>
                              <pre className="code-block">
                                <code>{log.metadata.script_content}</code>
                              </pre>
                            </div>
                          ) : (
                            <div style={{ padding: '8px', color: 'var(--status-error-text)' }}>
                              {t('workflowExecution.codeContentMissing', { keys: Object.keys(log.metadata).join(', ') })}
                              <pre style={{ marginTop: '8px' }}>{JSON.stringify(log.metadata, null, 2)}</pre>
                            </div>
                          )
                        ) : (
                          <pre>{JSON.stringify(log.metadata, null, 2)}</pre>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

export default WorkflowExecutionLivePage;
