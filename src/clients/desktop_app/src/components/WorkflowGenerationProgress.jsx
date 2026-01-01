import React, { useEffect, useRef } from 'react';
import Icon from './Icons';
import '../styles/WorkflowGenerationProgress.css';

/**
 * Split-layout progress display for workflow generation.
 * Left: High-level Stages
 * Right: Detailed Activity/Skill Log (Lovable style)
 *
 * Props:
 *   stageStatuses: Object mapping stage IDs to their status/details
 *   currentStage: Current active stage ID
 *   logs: Array of { type, message, timestamp, ... }
 *   onCancel: Callback
 */

const STAGES = [
  { id: 'analyzing', label: 'Analyzing Context', icon: 'search' },
  { id: 'understanding', label: 'Developing Strategy', icon: 'brain' },
  { id: 'generating', label: 'Drafting Workflow', icon: 'cpu' },
  { id: 'validating', label: 'Verifying Logic', icon: 'checkCircle' },
  { id: 'complete', label: 'Complete', icon: 'checkCircle' }
];

function WorkflowGenerationProgress({
  stageStatuses = {},
  currentStage = 'analyzing',
  logs = [],
  onCancel = null
}) {
  const scrollRef = useRef(null);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Helper for stage visual state
  const getVisualState = (stageId, index) => {
    if (stageStatuses[stageId]?.status) {
      return stageStatuses[stageId].status;
    }
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (index < currentIndex) return 'completed';
    if (index === currentIndex) return 'active';
    return 'pending';
  };

  const getLogIcon = (type) => {
    switch (type) {
      case 'intent': return 'zap';
      case 'thinking': return 'loader';
      case 'analyzing': return 'search';
      case 'success': return 'check';
      case 'error': return 'alertCircle';
      default: return 'info';
    }
  };

  return (
    <div className="workflow-generation-container">
      <div className="lovable-card">

        {/* Left Panel: Stages */}
        <div className="stages-panel">
          <div className="panel-header">
            <h2>Generation Progress</h2>
            <p>AI is analyzing and building your workflow</p>
            <div className="time-estimate-hint">
              <Icon icon="clock" size={12} />
              <span>~5-10 mins required</span>
            </div>
          </div>

          <div className="stages-list">
            {STAGES.map((s, index) => {
              const visualState = getVisualState(s.id, index);
              // We don't show details here anymore, details are in the log

              return (
                <div key={s.id} className={`stage-row ${visualState}`}>
                  <div className="stage-indicator">
                    {visualState === 'completed' ? (
                      <div className="indicator-dot completed"><Icon icon="check" size={14} /></div>
                    ) : visualState === 'active' ? (
                      <div className="indicator-dot active">
                        <div className="spinner-ring" />
                      </div>
                    ) : visualState === 'failed' ? (
                      <div className="indicator-dot failed"><Icon icon="x" size={14} /></div>
                    ) : (
                      <div className="indicator-dot pending" />
                    )}
                    {index < STAGES.length - 1 && <div className="stage-connector" />}
                  </div>
                  <span className="stage-label">{s.label}</span>
                </div>
              );
            })}
          </div>

          {onCancel && currentStage !== 'complete' && currentStage !== 'failed' && (
            <div className="cancel-section">
              <button className="cancel-btn" onClick={onCancel}>Cancel Generation</button>
            </div>
          )}
        </div>

        {/* Right Panel: Activity Log */}
        <div className="activity-panel">
          <div className="activity-header">
            <h3><Icon icon="terminal" size={16} /> Activity Log</h3>
            {logs.length > 0 && <span className="live-badge">LIVE</span>}
          </div>

          <div className="log-stream">
            {logs.length === 0 ? (
              <div className="empty-log">Waiting for events...</div>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className={`log-entry ${log.type}`} style={{ animationDelay: `${idx * 0.05}s` }}>
                  <div className="log-icon-wrapper">
                    <Icon icon={getLogIcon(log.type)} size={14} className={log.type === 'thinking' ? 'spinning' : ''} />
                  </div>
                  <div className="log-content">
                    <span className="log-message">{log.message}</span>
                    <span className="log-time">{log.timestamp}</span>
                  </div>
                </div>
              ))
            )}
            <div ref={scrollRef} />
          </div>
        </div>

      </div>
    </div>
  );
}

export default WorkflowGenerationProgress;
