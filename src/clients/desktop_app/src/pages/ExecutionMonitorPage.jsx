import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/ExecutionMonitorPage.css';

function ExecutionMonitorPage({
  session,
  onNavigate,
  showStatus,
  workflowId,
  workflowName = 'Workflow Execution',
  initialStatus = 'running',
  initialSteps = []
}) {
  const { t } = useTranslation();
  const userId = session?.username;
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
        const data = await api.callAppBackend(`/api/v1/executions/${workflowId}/status`);
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
    showStatus(t('monitoring.toasts.stopped'), 'info');
  };

  const handleStopCancel = () => {
    setStopConfirm(false);
  };

  const handleContinue = () => {
    setStatus('running');
    showStatus(t('monitoring.toasts.resumed'), 'info');
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getStatusIcon = (stepStatus) => {
    switch (stepStatus) {
      case 'completed': return <Icon icon="checkCircle" size={16} />;
      case 'in_progress': return <Icon icon="clock" size={16} />;
      case 'failed': return <Icon icon="alertCircle" size={16} />;
      default: return <Icon icon="circle" size={16} />;
    }
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
    <div className="execution-monitor-page">
      {/* Header */}
      <div className="execution-header">
        <div className="header-left">
          <button className="back-button" onClick={() => onNavigate("main")}>
            <Icon icon="arrowLeft" />
          </button>
          <div className="header-info">
            <h1 className="execution-title">{t('monitoring.title', { name: workflowName })}</h1>
            <div className="execution-meta">
              <span className="meta-badge" data-status={status}>
                {status === 'running' && <><Icon icon="play" size={14} /> {t('monitoring.status.running')}</>}
                {status === 'paused' && <><Icon icon="pause" size={14} /> {t('monitoring.status.paused')}</>}
                {status === 'completed' && <><Icon icon="checkCircle" size={14} /> {t('monitoring.status.completed')}</>}
                {status === 'failed' && <><Icon icon="alertCircle" size={14} /> {t('monitoring.status.failed')}</>}
              </span>
              <span className="meta-time">{t('monitoring.elapsed', { time: formatTime(elapsedTime) })}</span>
              {status === 'running' && (
                <span className="meta-time">{t('monitoring.estRemaining', { time: formatTime(estimatedTimeLeft) })}</span>
              )}
            </div>
          </div>
        </div>
        <div className="header-actions">
          {status === 'running' ? (
            <button className="btn-stop" onClick={handleStopClick}>
              <Icon icon="square" />
              {t('monitoring.stop')}
            </button>
          ) : status === 'paused' ? (
            <button className="btn-continue" onClick={handleContinue}>
              <Icon icon="play" />
              {t('monitoring.continue')}
            </button>
          ) : status === 'completed' ? (
            <button className="btn-view-results" onClick={() => onNavigate('execution-result')}>
              <Icon icon="barChart" /> {t('monitoring.viewResults')}
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
          <span className="progress-steps">{t('monitoring.progress', { current: currentStep + 1, total: steps.length })}</span>
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
              <Icon icon="globe" size={14} />
              <span>{browserUrl}</span>
            </div>
          </div>
          <div className="browser-content">
            <div className="browser-placeholder">
              <div className="browser-notice">
                <h3><Icon icon="globe" size={24} /> {t('monitoring.browserTitle')}</h3>
                <p>{t('monitoring.browserNotice')}</p>
                <p className="current-action">{t('monitoring.currentAction')}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Execution Logs */}
        <div className="logs-panel">
          <div className="logs-header">
            <h3><Icon icon="fileText" size={18} /> {t('monitoring.logsTitle')}</h3>
            <div className="logs-actions">
              <button className="btn-clear-logs" onClick={() => setLogs([])}>
                {t('monitoring.clearLogs')}
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
                  <p>{t('monitoring.waitingLogs')}</p>
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
              <h3>{t('monitoring.modal.confirmStop')}</h3>
            </div>
            <div className="modal-body">
              <p>{t('monitoring.modal.areYouSure')}</p>
              <p className="warning-text">{t('monitoring.modal.warning')}</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleStopCancel}>
                {t('monitoring.modal.cancel')}
              </button>
              <button className="btn-confirm-delete" onClick={handleStopConfirm}>
                {t('monitoring.modal.stopExecution')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ExecutionMonitorPage;
