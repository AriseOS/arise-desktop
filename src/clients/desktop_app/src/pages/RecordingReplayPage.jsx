import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingReplayPage.css';

function RecordingReplayPage({ session, onNavigate, showStatus, navigationData }) {
  const { sessionId, userId, recordingName } = navigationData || {};

  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [replaying, setReplaying] = useState(false);
  const [replayResult, setReplayResult] = useState(null);
  const [currentOperation, setCurrentOperation] = useState(0);

  // Replay options
  const [waitBetween, setWaitBetween] = useState(0.5);
  const [stopOnError, setStopOnError] = useState(false);

  // Load recording preview
  useEffect(() => {
    loadPreview();
  }, [sessionId, userId]);

  const loadPreview = async () => {
    if (!sessionId || !userId) {
      showStatus("Missing session or user information", "error");
      onNavigate('main');
      return;
    }

    try {
      setLoading(true);
      const result = await api.callAppBackend(
        `/api/v1/recordings/${sessionId}/replay/preview?user_id=${userId}`,
        { method: "GET" }
      );
      setPreview(result);
    } catch (error) {
      console.error("Failed to load preview:", error);
      showStatus(`Failed to load recording: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleStartReplay = async () => {
    try {
      setReplaying(true);
      setReplayResult(null);
      setCurrentOperation(0);
      showStatus("Starting replay...", "info");

      const result = await api.callAppBackend(
        `/api/v1/recordings/${sessionId}/replay`,
        {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            wait_between_operations: waitBetween,
            stop_on_error: stopOnError,
            start_from_index: 0,
            end_at_index: null
          })
        }
      );

      setReplayResult(result);

      if (result.status === "completed" && result.execution_summary) {
        const successRate = (result.execution_summary.success_rate * 100).toFixed(1);
        showStatus(`Replay completed! Success rate: ${successRate}%`, "success");
      } else {
        showStatus(`Replay failed: ${result.error || "Unknown error"}`, "error");
      }
    } catch (error) {
      console.error("Replay failed:", error);
      showStatus(`Replay failed: ${error.message}`, "error");
    } finally {
      setReplaying(false);
    }
  };

  const getOperationIcon = (type) => {
    const icons = {
      'navigate': 'globe',
      'click': 'mousePointer',
      'input': 'keyboard',
      'select': 'type',
      'scroll': 'arrowDown',
      'copy_action': 'copy',
      'paste_action': 'clipboard',
      'dataload': 'loader',
      'test': 'checkCircle'
    };
    return icons[type] || 'circle';
  };

  const getStatusBadge = (status) => {
    const badges = {
      'success': { text: '✓ Success', className: 'status-success' },
      'failed': { text: '✗ Failed', className: 'status-failed' },
      'skipped': { text: '○ Skipped', className: 'status-skipped' }
    };
    return badges[status] || { text: status, className: '' };
  };

  if (loading) {
    return (
      <div className="page replay-page">
        <div className="page-header">
          <button className="back-button" onClick={() => onNavigate("main")}>
            <Icon icon="arrowLeft" />
          </button>
          <div className="page-title"><Icon icon="play" size={28} /> Replay Recording</div>
        </div>
        <div className="replay-content">
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading recording...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="page replay-page">
        <div className="page-header">
          <button className="back-button" onClick={() => onNavigate("main")}>
            <Icon icon="arrowLeft" />
          </button>
          <div className="page-title"><Icon icon="play" size={28} /> Replay Recording</div>
        </div>
        <div className="replay-content">
          <div className="error-state">
            <Icon icon="alertCircle" size={48} />
            <p>Recording not found</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page replay-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")} disabled={replaying}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="play" size={28} /> Replay Recording</div>
      </div>

      <div className="replay-content">
        {/* Recording Information */}
        <div className="replay-section">
          <h2 className="section-title">
            <Icon icon="info" size={20} /> Recording Information
          </h2>
          <div className="recording-info">
            <div className="info-item">
              <span className="label">Name:</span>
              <span className="value">{recordingName || sessionId}</span>
            </div>
            <div className="info-item">
              <span className="label">Session ID:</span>
              <span className="value">{preview.session_id}</span>
            </div>
            <div className="info-item">
              <span className="label">Created:</span>
              <span className="value">{new Date(preview.created_at).toLocaleString()}</span>
            </div>
            <div className="info-item">
              <span className="label">Total Operations:</span>
              <span className="value">{preview.operations_count}</span>
            </div>
          </div>

          {/* Operation Type Summary */}
          <div className="operation-summary">
            <h3>Operation Types:</h3>
            <div className="operation-types">
              {Object.entries(preview.operation_summary).map(([type, count]) => (
                <div key={type} className="type-badge">
                  <Icon icon={getOperationIcon(type)} size={14} />
                  <span>{type}: {count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Replay Options */}
        {!replayResult && (
          <div className="replay-section">
            <h2 className="section-title">
              <Icon icon="settings" size={20} /> Replay Options
            </h2>
            <div className="replay-options">
              <div className="option-item">
                <label>
                  <span>Wait between operations:</span>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    step="0.1"
                    value={waitBetween}
                    onChange={(e) => setWaitBetween(parseFloat(e.target.value))}
                    disabled={replaying}
                  />
                  <span className="unit">seconds</span>
                </label>
              </div>
              <div className="option-item">
                <label>
                  <input
                    type="checkbox"
                    checked={stopOnError}
                    onChange={(e) => setStopOnError(e.target.checked)}
                    disabled={replaying}
                  />
                  <span>Stop on first error</span>
                </label>
              </div>
            </div>

            <button
              className="btn btn-primary btn-large"
              onClick={handleStartReplay}
              disabled={replaying}
            >
              {replaying ? (
                <>
                  <div className="btn-spinner"></div>
                  <span>Replaying...</span>
                </>
              ) : (
                <>
                  <Icon icon="play" size={20} />
                  <span>Start Replay</span>
                </>
              )}
            </button>

            <div className="replay-hint">
              <Icon icon="info" size={16} />
              <span>
                Replay will open a new browser window and execute all recorded operations step-by-step.
                The browser will remain open after completion for you to inspect the results.
              </span>
            </div>
          </div>
        )}

        {/* Replay Results */}
        {replayResult && (
          <div className="replay-section">
            <h2 className="section-title">
              <Icon icon={replayResult.status === "completed" ? "checkCircle" : "alertCircle"} size={20} />
              Replay Results
            </h2>

            {replayResult.status === "failed" ? (
              <div className="error-state">
                <Icon icon="alertCircle" size={48} />
                <p>Replay failed: {replayResult.error || "Unknown error"}</p>
              </div>
            ) : replayResult.execution_summary ? (
              <>
                <div className="replay-summary">
                  <div className="summary-card success">
                    <div className="card-value">{replayResult.execution_summary.successful}</div>
                    <div className="card-label">Successful</div>
                  </div>
                  <div className="summary-card failed">
                    <div className="card-value">{replayResult.execution_summary.failed}</div>
                    <div className="card-label">Failed</div>
                  </div>
                  <div className="summary-card skipped">
                    <div className="card-value">{replayResult.execution_summary.skipped}</div>
                    <div className="card-label">Skipped</div>
                  </div>
                  <div className="summary-card rate">
                    <div className="card-value">
                      {(replayResult.execution_summary.success_rate * 100).toFixed(1)}%
                    </div>
                    <div className="card-label">Success Rate</div>
                  </div>
                </div>

                {replayResult.timing && (
                  <div className="timing-info">
                    <span>Duration: {replayResult.timing.duration_seconds.toFixed(1)}s</span>
                    <span>Completed: {new Date(replayResult.timing.ended_at).toLocaleTimeString()}</span>
                  </div>
                )}
              </>
            ) : null}

            {/* Operation Details */}
            {replayResult.execution_summary && replayResult.operation_results && (
              <div className="operation-results">
                <h3>Operation Details:</h3>
                <div className="operations-list">
                  {replayResult.operation_results.map((result, index) => {
                    const badge = getStatusBadge(result.status);
                    return (
                      <div key={index} className={`operation-result ${badge.className}`}>
                        <div className="result-index">#{result.index + 1}</div>
                        <div className="result-details">
                          <div className="result-type">
                            <Icon icon={getOperationIcon(result.type)} size={14} />
                            <span>{result.type}</span>
                          </div>
                          <div className="result-status">
                            <span className={`status-badge ${badge.className}`}>{badge.text}</span>
                          </div>
                          {result.error && (
                            <div className="result-error">
                              <Icon icon="alertCircle" size={12} />
                              <span>{result.error}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="action-buttons">
              <button
                className="btn btn-primary"
                onClick={() => {
                  setReplayResult(null);
                  setCurrentOperation(0);
                }}
              >
                <Icon icon="refreshCw" size={16} />
                <span>Replay Again</span>
              </button>

              <button
                className="btn btn-secondary"
                onClick={() => onNavigate('main')}
              >
                <Icon icon="home" size={16} />
                <span>Back to Home</span>
              </button>
            </div>
          </div>
        )}

        {/* Operations Preview */}
        {!replayResult && (
          <div className="replay-section">
            <h2 className="section-title">
              <Icon icon="list" size={20} /> Operations Preview
            </h2>
            <div className="operations-preview">
              {preview.operations.slice(0, 20).map((op, index) => (
                <div key={index} className="preview-operation">
                  <div className="op-index">#{index + 1}</div>
                  <div className="op-icon">
                    <Icon icon={getOperationIcon(op.type)} size={14} />
                  </div>
                  <div className="op-details">
                    <div className="op-type">{op.type}</div>
                    {op.url && (
                      <div className="op-url">{new URL(op.url).hostname}</div>
                    )}
                  </div>
                </div>
              ))}
              {preview.operations.length > 20 && (
                <div className="preview-more">
                  ... and {preview.operations.length - 20} more operations
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default RecordingReplayPage;
