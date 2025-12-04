import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import '../styles/WorkflowExecutionLivePage.css';

const WS_BASE = "ws://127.0.0.1:8765";

function WorkflowExecutionLivePage({
  session,
  onNavigate,
  showStatus,
  taskId,
  workflowName = 'Workflow Execution'
}) {
  const userId = session?.username;
  const [status, setStatus] = useState('connecting'); // 'connecting', 'running', 'completed', 'failed'
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [totalSteps, setTotalSteps] = useState(0);
  const [steps, setSteps] = useState([]);
  const [logs, setLogs] = useState([]);
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
      showStatus('No task ID provided', 'error');
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
      const ws = new WebSocket(`${WS_BASE}/ws/workflow/${taskId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected to workflow progress stream');
        setWsConnected(true);
        setStatus('running');
        setCurrentMessage('Connected. Waiting for updates...');
        reconnectAttemptsRef.current = 0; // Reset reconnect counter on successful connection

        // Start heartbeat
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000); // Send heartbeat every 30 seconds
      };

      ws.onmessage = (event) => {
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
            showStatus('Unable to connect to workflow stream', 'error');
            setCurrentMessage('Connection failed. Please check if the workflow is running.');
          } else {
            setCurrentMessage('Connection lost. Reconnecting...');
            reconnectTimeoutRef.current = setTimeout(() => {
              console.log(`[WS] Attempting to reconnect (attempt ${reconnectAttemptsRef.current})...`);
              connectWebSocket();
            }, 3000);
          }
        }
      };
    } catch (error) {
      console.error('[WS] Failed to create WebSocket connection:', error);
      showStatus('Failed to connect to workflow stream', 'error');
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
        addLogEntry({
          level: data.log.level || 'info',
          message: data.log.message,
          time: data.log.time
        });
      }

      // Handle completion
      if (data.status === 'completed' || data.status === 'failed') {
        shouldReconnectRef.current = false;
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
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
    setLogs(prevLogs => [...prevLogs, logEntry]);
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
                {status === 'connecting' && <><Icon icon="loader" size={14} /> Connecting</>}
                {status === 'running' && <><Icon icon="play" size={14} /> Running</>}
                {status === 'completed' && <><Icon icon="checkCircle" size={14} /> Completed</>}
                {status === 'failed' && <><Icon icon="alertCircle" size={14} /> Failed</>}
              </span>
              <span className="meta-time">Elapsed: {formatTime(elapsedTime)}</span>
              <span className={`connection-status ${wsConnected ? 'connected' : 'disconnected'}`}>
                <Icon icon={wsConnected ? "wifi" : "wifiOff"} size={14} />
                {wsConnected ? 'Live' : 'Offline'}
              </span>
            </div>
          </div>
        </div>
        <div className="header-actions">
          {status === 'completed' && (
            <button className="btn-view-results" onClick={() => onNavigate('execution-result', { taskId })}>
              <Icon icon="barChart" /> View Results
            </button>
          )}
          {status === 'failed' && (
            <button className="btn-back" onClick={() => onNavigate('main')}>
              <Icon icon="home" /> Back to Home
            </button>
          )}
        </div>
      </div>

      {/* Progress Section */}
      <div className="progress-section">
        <div className="progress-header">
          <h2><Icon icon="activity" size={20} /> Workflow Progress</h2>
          <span className="progress-text">
            {currentStep >= 0 ? `Step ${currentStep + 1}/${totalSteps}` : 'Initializing...'}
          </span>
        </div>

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
                Waiting for workflow steps...
              </div>
            ) : (
              steps.map((step, idx) => (
                <div
                  key={step.id}
                  className={`timeline-step ${step.status}`}
                  ref={step.status === 'in_progress' ? currentStepRef : null}
                >
                  <div className="timeline-node">
                    {step.status === 'in_progress' && <div className="node-pulse" />}
                  </div>
                  <div className="timeline-content">
                    <div className="step-name">{step.name}</div>
                    {step.duration && (
                      <div className="step-duration">{step.duration.toFixed(1)}s</div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Logs Section */}
      <div className="logs-section">
        <div className="logs-header">
          <h3><Icon icon="fileText" size={18} /> Execution Logs</h3>
          <div className="logs-actions">
            <button className="btn-clear-logs" onClick={() => setLogs([])}>
              Clear
            </button>
          </div>
        </div>
        <div className="logs-content">
          {logs.length === 0 ? (
            <div className="logs-empty">
              <p>Waiting for logs...</p>
            </div>
          ) : (
            <div className="logs-list">
              {logs.map((log, idx) => (
                <div key={idx} className="log-entry" data-level={log.level}>
                  <span className="log-icon">{getLogIcon(log.level)}</span>
                  <span className="log-time">{log.time}</span>
                  <span className="log-message" style={{ color: getLogColor(log.level) }}>
                    {log.message}
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default WorkflowExecutionLivePage;
