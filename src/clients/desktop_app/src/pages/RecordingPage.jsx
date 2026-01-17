import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingPage.css';

function RecordingPage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [recordUrl, setRecordUrl] = useState("https://www.google.com");
  const [recordTitle, setRecordTitle] = useState("");
  const [recordDescription, setRecordDescription] = useState("");

  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [operationsCount, setOperationsCount] = useState(0);
  const [capturedOperations, setCapturedOperations] = useState([]);
  const operationsListRef = useRef(null);

  const [uploading, setUploading] = useState(false);

  // Poll for operations while recording
  useEffect(() => {
    if (!recording) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const result = await api.callAppBackend('/api/v1/recordings/current/operations', {
          method: "GET"
        });
        if (result.is_recording) {
          setCapturedOperations(result.operations || []);
          setOperationsCount(result.operations_count || 0);
        }
      } catch (error) {
        console.error('Failed to poll operations:', error);
      }
    }, 500);

    return () => {
      clearInterval(pollInterval);
    };
  }, [recording]);

  // Auto-scroll to bottom when new operations are added
  useEffect(() => {
    if (operationsListRef.current) {
      operationsListRef.current.scrollTop = operationsListRef.current.scrollHeight;
    }
  }, [capturedOperations]);

  // Get operation type label with icon
  const getOperationTypeLabel = (type) => {
    const typeLabels = {
      'click': { text: t('recording.ops.click'), icon: 'mousePointer' },
      'input': { text: t('recording.ops.input'), icon: 'keyboard' },
      'navigate': { text: t('recording.ops.navigate'), icon: 'globe' },
      'scroll': { text: t('recording.ops.scroll'), icon: 'arrowDown' },
      'select': { text: t('recording.ops.select'), icon: 'list' },
      'submit': { text: t('recording.ops.submit'), icon: 'checkCircle' },
      'hover': { text: t('recording.ops.hover'), icon: 'mousePointer' },
      'keydown': { text: t('recording.ops.keydown'), icon: 'keyboard' },
      'change': { text: t('recording.ops.change'), icon: 'edit' }
    };
    const label = typeLabels[type] || { text: type || t('recording.ops.op'), icon: 'mapPin' };
    return (
      <>
        <Icon icon={label.icon} size={14} />
        <span>{label.text}</span>
      </>
    );
  };

  // Start recording
  const handleStartRecording = async () => {
    if (!recordUrl || !recordTitle || !recordDescription) {
      showStatus(t('recording.hints.required'), "error");
      return;
    }

    try {
      showStatus(t('recording.hints.starting'), "info");

      const result = await api.callAppBackend('/api/v1/recordings/start', {
        method: "POST",
        body: JSON.stringify({
          url: recordUrl,
          user_id: userId,
          title: recordTitle,
          description: recordDescription,
          task_metadata: { task_description: recordDescription }
        })
      });
      setRecording(true);
      setSessionId(result.session_id);
      showStatus(t('recording.hints.started'), "success");
    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(t('recording.hints.startFailed', { error: error.message }), "error");
    }
  };

  // Stop recording
  const handleStopRecording = async () => {
    try {
      showStatus(t('recording.hints.stopping'), "info");

      const result = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });
      setRecording(false);
      setOperationsCount(result.operations_count);
      showStatus(t('recording.hints.stopped', { count: result.operations_count }), "success");
    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(t('recording.hints.stopFailed', { error: error.message }), "error");
      setRecording(false);
    }
  };

  // Upload recording
  const handleUpload = async () => {
    if (!sessionId) {
      showStatus(t('recording.hints.noRecording'), "error");
      return;
    }

    try {
      setUploading(true);
      showStatus(t('recording.hints.uploadingToast'), "info");

      const result = await api.callAppBackend(`/api/v1/recordings/${sessionId}/upload`, {
        method: "POST",
        body: JSON.stringify({
          task_description: recordDescription,
          user_id: userId
        })
      });
      showStatus(t('recording.hints.uploadSuccess'), "success");

      // Return to main page after successful upload
      setTimeout(() => {
        onNavigate("main");
      }, 2000);
    } catch (error) {
      console.error("Upload error:", error);
      showStatus(t('recording.hints.uploadFailed', { error: error.message }), "error");
    } finally {
      setUploading(false);
    }
  };

  // Navigate to generation page with recording info
  const handleQuickGenerate = () => {
    if (!sessionId) {
      showStatus(t('recording.hints.noGenRecording'), "error");
      return;
    }

    onNavigate('generation', {
      recordingId: sessionId,
      recordingName: recordDescription || sessionId,
      taskDescription: recordDescription || '',
      userQuery: ''
    });
  };

  return (
    <div className="page recording-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")} disabled={recording}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="video" size={28} /> {t('recording.title')}</div>
      </div>

      <div className="record-content">
        <div className="record-form">
          {/* Step 1: Configuration */}
          {!recording && !sessionId && (
            <div className="form-section">
              <h3>{t('recording.configTitle')}</h3>

              <div className="input-group">
                <label>
                  <span>{t('recording.urlLabel')} <span className="required">*</span></span>
                </label>
                <input
                  type="text"
                  value={recordUrl}
                  onChange={(e) => setRecordUrl(e.target.value)}
                  placeholder="https://www.google.com"
                />
              </div>

              <div className="input-group">
                <label>
                  <span>{t('recording.titleLabel')} <span className="required">*</span></span>
                  <span className="input-hint">{recordTitle.length}/50</span>
                </label>
                <input
                  type="text"
                  value={recordTitle}
                  onChange={(e) => setRecordTitle(e.target.value)}
                  placeholder={t('recording.titlePlaceholder')}
                  maxLength={50}
                />
              </div>

              <div className="input-group">
                <label>
                  <span>{t('recording.descLabel')} <span className="required">*</span></span>
                  <span className="input-hint">{recordDescription.length}/500</span>
                </label>
                <textarea
                  value={recordDescription}
                  onChange={(e) => setRecordDescription(e.target.value)}
                  placeholder={t('recording.descPlaceholder')}
                  maxLength={500}
                  rows={6}
                />
              </div>

              <button
                className="start-record-button"
                onClick={handleStartRecording}
              >
                <Icon icon="circle" size={20} fill="currentColor" />
                <span>{t('recording.startBtn')}</span>
              </button>
            </div>
          )}

          {/* Step 2: Recording in progress */}
          {recording && (
            <div className="recording-status">
              <div className="recording-indicator">
                <div className="recording-dot"></div>
                <span>{t('recording.statusRecording')}</span>
              </div>

              {/* Operations display */}
              <div className="operations-display">
                <div className="operations-header">
                  <span className="operations-title">{t('recording.capturedOps')}</span>
                  <span className="operations-count">{t('recording.opsCount', { count: capturedOperations.length })}</span>
                </div>
                <div className="operations-list" ref={operationsListRef}>
                  {capturedOperations.length === 0 ? (
                    <div className="empty-operations">
                      <div className="empty-icon"><Icon icon="clipboard" size={48} /></div>
                      <div className="empty-text">{t('recording.waitingOps')}</div>
                      <div className="empty-hint">{t('recording.performActions')}</div>
                    </div>
                  ) : (
                    capturedOperations.map((op, index) => (
                      <div key={index} className="operation-item">
                        <div className="operation-index">{index + 1}</div>
                        <div className="operation-details">
                          <div className="operation-type">{getOperationTypeLabel(op.type)}</div>
                          <div className="operation-info">
                            {op.element?.textContent && (
                              <div className="operation-text">
                                {op.element.textContent.slice(0, 50)}
                                {op.element.textContent.length > 50 ? '...' : ''}
                              </div>
                            )}
                            {op.data?.value && (
                              <div className="operation-value">
                                {t('recording.ops.input')}: {op.data.value.slice(0, 30)}
                                {op.data.value.length > 30 ? '...' : ''}
                              </div>
                            )}
                            {op.url && (
                              <div className="operation-url">
                                {(() => {
                                  try {
                                    return new URL(op.url).hostname;
                                  } catch {
                                    return op.url;
                                  }
                                })()}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <button
                className="start-record-button recording"
                onClick={handleStopRecording}
              >
                <Icon icon="square" size={20} />
                <span>{t('recording.stopBtn')}</span>
              </button>
            </div>
          )}

          {/* Step 3: Recording completed, ready to upload */}
          {sessionId && !recording && (
            <div className="recording-complete">
              <div className="complete-icon"><Icon icon="checkCircle" size={48} /></div>
              <h3>{t('recording.completeTitle')}</h3>

              <div className="recording-summary">
                <div className="summary-item">
                  <span className="label">{t('recording.summary.sessionId')}</span>
                  <span className="value">{sessionId}</span>
                </div>
                <div className="summary-item">
                  <span className="label">{t('recording.summary.title')}</span>
                  <span className="value">{recordTitle}</span>
                </div>
                <div className="summary-item">
                  <span className="label">{t('recording.summary.opsCount')}</span>
                  <span className="value">{t('recording.opsCount', { count: operationsCount })}</span>
                </div>
                <div className="summary-item">
                  <span className="label">{t('recording.summary.desc')}</span>
                  <span className="value description">{recordDescription}</span>
                </div>
              </div>

              <div className="action-buttons">
                <button
                  className="btn btn-primary"
                  onClick={handleQuickGenerate}
                  disabled={uploading}
                >
                  <Icon icon="zap" size={16} />
                  <span>{t('recording.quickGenerate')}</span>
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={handleUpload}
                  disabled={uploading}
                >
                  {uploading ? (
                    <>
                      <div className="btn-spinner"></div>
                      <span>{t('recording.uploading')}</span>
                    </>
                  ) : (
                    <>
                      <Icon icon="upload" size={16} />
                      <span>{t('recording.uploadCloud')}</span>
                    </>
                  )}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setSessionId("");
                    setOperationsCount(0);
                    setRecordTitle("");
                    setRecordDescription("");
                  }}
                  disabled={uploading}
                >
                  <Icon icon="refreshCw" size={16} />
                  <span>{t('recording.reRecord')}</span>
                </button>
              </div>

              <p className="upload-hint">
                {t('recording.hints.quickGen')}<br />
                {t('recording.hints.upload')}
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );
}

export default RecordingPage;
