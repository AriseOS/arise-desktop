import React, { useState, useEffect, useRef } from 'react';
import '../styles/ExecutionMonitorPage.css';

const API_BASE = "http://127.0.0.1:8765";

function ExecutionMonitorPage({
  onNavigate,
  showStatus,
  workflowId,
  workflowName = 'Workflow Execution',
  initialStatus = 'running',
  initialSteps = []
}) {
  const [status, setStatus] = useState(initialStatus); // 'running', 'paused', 'completed', 'failed'
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [logs, setLogs] = useState([]);
  const [browserUrl, setBrowserUrl] = useState('');
  const [elapsedTime, setElapsedTime] = useState(0);
  const [estimatedTimeLeft, setEstimatedTimeLeft] = useState(0);
  const [steps, setSteps] = useState(initialSteps);
  const [stopConfirm, setStopConfirm] = useState(false);

  const logsEndRef = useRef(null);

  // Fetch execution status from API
  useEffect(() => {
    if (!workflowId) return;

    // Time tracking
    const timeInterval = setInterval(() => {
      setElapsedTime(prev => prev + 1);
    }, 1000);

    // Poll for execution updates
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/execution/${workflowId}/status`);
        if (response.ok) {
          const data = await response.json();
          setStatus(data.status);
          setProgress(data.progress || 0);
          setCurrentStep(data.current_step || 0);
          setBrowserUrl(data.browser_url || '');
          setEstimatedTimeLeft(data.estimated_time_left || 0);

          if (data.steps) {
            setSteps(data.steps);
          }

          if (data.new_logs) {
            setLogs(prev => [...prev, ...data.new_logs]);
          }

          if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(pollInterval);
          }
        }
      } catch (error) {
        console.error('Failed to fetch execution status:', error);
      }
    }, 2000);

    return () => {
      clearInterval(timeInterval);
      clearInterval(pollInterval);
    };
  }, [workflowId]);

  // Auto-scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleStopClick = () => {
    setStopConfirm(true);
  };

  const handleStopConfirm = () => {
    setStopConfirm(false);
    setStatus('paused');
    showStatus('⏸ Execution stopped', 'info');
  };

  const handleStopCancel = () => {
    setStopConfirm(false);
  };

  const handleContinue = () => {
    setStatus('running');
    showStatus('▶️ Execution resumed', 'info');
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getStatusIcon = (stepStatus) => {
    switch (stepStatus) {
      case 'completed': return '✅';
      case 'in_progress': return '⏳';
      case 'failed': return '❌';
      default: return '⏸';
    }
  };

  const getLogIcon = (level) => {
    switch (level) {
      case 'success': return '✅';
      case 'error': return '❌';
      case 'warning': return '⚠️';
      default: return 'ℹ️';
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
    <div className="execution-monitor-page">
      {/* Header */}
      <div className="execution-header">
        <div className="header-left">
          <button className="back-button" onClick={() => onNavigate("main")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div className="header-info">
            <h1 className="execution-title">Execution: {workflowName}</h1>
            <div className="execution-meta">
              <span className="meta-badge" data-status={status}>
                {status === 'running' && '▶️ Running'}
                {status === 'paused' && '⏸ Paused'}
                {status === 'completed' && '✅ Completed'}
                {status === 'failed' && '❌ Failed'}
              </span>
              <span className="meta-time">Elapsed: {formatTime(elapsedTime)}</span>
              {status === 'running' && (
                <span className="meta-time">Est. remaining: {formatTime(estimatedTimeLeft)}</span>
              )}
            </div>
          </div>
        </div>
        <div className="header-actions">
          {status === 'running' ? (
            <button className="btn-stop" onClick={handleStopClick}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12"></rect>
              </svg>
              Stop
            </button>
          ) : status === 'paused' ? (
            <button className="btn-continue" onClick={handleContinue}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Continue
            </button>
          ) : status === 'completed' ? (
            <button className="btn-view-results" onClick={() => onNavigate('execution-result')}>
              📊 View Results
            </button>
          ) : null}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="progress-section">
        <div className="progress-bar-container">
          <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
        </div>
        <div className="progress-info">
          <span className="progress-percent">{progress}%</span>
          <span className="progress-steps">Step {currentStep + 1} of {steps.length}</span>
        </div>
      </div>

      {/* Main Content: Browser + Logs */}
      <div className="execution-content">
        {/* Browser Window */}
        <div className="browser-panel">
          <div className="browser-header">
            <div className="browser-controls">
              <span className="browser-dot red"></span>
              <span className="browser-dot yellow"></span>
              <span className="browser-dot green"></span>
            </div>
            <div className="browser-url">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="2" y1="12" x2="22" y2="12"/>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
              </svg>
              <span>{browserUrl}</span>
            </div>
          </div>
          <div className="browser-content">
            <div className="browser-placeholder">
              <div className="browser-notice">
                <h3>🌐 Browser Window</h3>
                <p>Real-time browser view will be displayed here</p>
                <p className="current-action">Current: Scraping product 10/25</p>
              </div>
            </div>
          </div>
        </div>

        {/* Execution Logs */}
        <div className="logs-panel">
          <div className="logs-header">
            <h3>📋 Execution Logs</h3>
            <div className="logs-actions">
              <button className="btn-clear-logs" onClick={() => setLogs([])}>
                Clear
              </button>
            </div>
          </div>
          <div className="logs-content">
            {/* Step Summary */}
            <div className="steps-summary">
              {steps.map((step, idx) => (
                <div key={step.id} className={`step-card ${step.status}`}>
                  <div className="step-header">
                    <span className="step-icon">{getStatusIcon(step.status)}</span>
                    <span className="step-number">{idx + 1}.</span>
                    <span className="step-name">{step.name}</span>
                    {step.duration && (
                      <span className="step-duration">({step.duration}s)</span>
                    )}
                  </div>
                  {step.result && (
                    <div className="step-result">→ {step.result}</div>
                  )}
                </div>
              ))}
            </div>

            {/* Detailed Logs */}
            <div className="logs-list">
              {logs.length === 0 ? (
                <div className="logs-empty">
                  <p>Waiting for logs...</p>
                </div>
              ) : (
                logs.map((log, idx) => (
                  <div key={idx} className="log-entry" data-level={log.level}>
                    <span className="log-icon">{getLogIcon(log.level)}</span>
                    <span className="log-time">{log.time}</span>
                    <span className="log-message" style={{ color: getLogColor(log.level) }}>
                      {log.message}
                    </span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>
      </div>

      {/* Stop Confirmation Modal */}
      {stopConfirm && (
        <div className="modal-overlay" onClick={handleStopCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Confirm Stop Execution</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to stop execution?</p>
              <p className="warning-text">Completed data will be saved.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleStopCancel}>
                Cancel
              </button>
              <button className="btn-confirm-delete" onClick={handleStopConfirm}>
                Stop Execution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ExecutionMonitorPage;
