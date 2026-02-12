import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingAnalysisPage.css';

function RecordingAnalysisPage({ session, pageData, onNavigate, showStatus }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const taskDescription = pageData?.taskDescription || '';
  const [isAdding, setIsAdding] = useState(false);
  const [isAdded, setIsAdded] = useState(false);
  const [operations, setOperations] = useState([]);
  const [loadingOps, setLoadingOps] = useState(true);

  const sessionId = pageData?.sessionId;
  const recordingName = pageData?.name || t('analysis.unnamedTask');

  // Fetch operations on mount
  useEffect(() => {
    if (!sessionId || !userId) {
      setLoadingOps(false);
      return;
    }

    const fetchOperations = async () => {
      try {
        const detail = await api.callAppBackend(
          `/api/v1/recordings/${sessionId}?user_id=${userId}`
        );
        setOperations(detail?.operations || []);
      } catch (error) {
        console.error("Failed to load operations:", error);
      } finally {
        setLoadingOps(false);
      }
    };

    fetchOperations();
  }, [sessionId, userId]);

  // Compute duration from first/last operation timestamps
  const getDuration = () => {
    if (operations.length < 2) return null;
    const startMs = operations[0].timestamp ? new Date(operations[0].timestamp).getTime() : 0;
    const endMs = operations[operations.length - 1].timestamp ? new Date(operations[operations.length - 1].timestamp).getTime() : 0;
    if (!startMs || !endMs) return null;
    const totalSeconds = Math.round((endMs - startMs) / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
  };

  const getOperationTypeLabel = (type) => {
    const typeMap = {
      'click': { text: t('recording.ops.click'), icon: 'circle' },
      'type': { text: t('recording.ops.input'), icon: 'hash' },
      'input': { text: t('recording.ops.input'), icon: 'hash' },
      'navigate': { text: t('recording.ops.navigate'), icon: 'globe' },
      'scroll': { text: t('recording.ops.scroll'), icon: 'chevronDown' },
      'select': { text: t('recording.ops.select'), icon: 'list' },
      'submit': { text: t('recording.ops.submit'), icon: 'checkCircle' },
      'hover': { text: t('recording.ops.hover'), icon: 'circle' },
      'keydown': { text: t('recording.ops.keydown'), icon: 'hash' },
      'enter': { text: t('recording.ops.submit'), icon: 'checkCircle' },
      'change': { text: t('recording.ops.change'), icon: 'edit' },
      'copy': { text: t('recording.ops.copy'), icon: 'clipboard' },
      'paste': { text: t('recording.ops.paste'), icon: 'clipboard' },
      'dataload': { text: t('recording.ops.dataload'), icon: 'download' }
    };
    const label = typeMap[type] || { text: type || t('recording.ops.op'), icon: 'circle' };
    return (
      <>
        <Icon icon={label.icon} size={14} />
        <span>{label.text}</span>
      </>
    );
  };

  const handleAddToMemory = async () => {
    try {
      setIsAdding(true);

      const result = await api.addToMemory(userId, {
        recordingId: sessionId,
        generateEmbeddings: true
      });

      setIsAdded(true);
      showStatus(t('analysis.addedToMemory', {
        states: result.states_added || 0,
        merged: result.states_merged || 0,
        sequences: result.intent_sequences_added || 0
      }), "success");

    } catch (error) {
      console.error("Add to memory error:", error);
      showStatus(t('analysis.addToMemoryFailed', { error: error.message }), "error");
    } finally {
      setIsAdding(false);
    }
  };

  const duration = getDuration();

  const renderPatternBadges = () => {
    const badges = [];

    if (detectedPatterns.loop_detected) {
      badges.push(
        <div key="loop" className="pattern-badge loop">
          <span className="badge-icon"><Icon icon="refreshCw" size={14} /></span>
          <span className="badge-text">{t('analysis.loopPattern')}</span>
          {detectedPatterns.loop_count && (
            <span className="badge-detail">{t('analysis.loopCount', { count: detectedPatterns.loop_count })}</span>
          )}
        </div>
      );
    }

    if (detectedPatterns.extracted_fields && detectedPatterns.extracted_fields.length > 0) {
      badges.push(
        <div key="extraction" className="pattern-badge extraction">
          <span className="badge-icon"><Icon icon="database" size={14} /></span>
          <span className="badge-text">{t('analysis.dataExtraction')}</span>
          <span className="badge-detail">
            {t('analysis.fields', { fields: detectedPatterns.extracted_fields.join(', ') })}
          </span>
        </div>
      );
    }

    if (detectedPatterns.navigation_depth) {
      badges.push(
        <div key="navigation" className="pattern-badge navigation">
          <span className="badge-icon"><Icon icon="globe" size={14} /></span>
          <span className="badge-text">{t('analysis.navigation')}</span>
          <span className="badge-detail">{t('analysis.depth', { depth: detectedPatterns.navigation_depth })}</span>
        </div>
      );
    }

    return badges;
  };

  return (
    <div className="recording-analysis-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="checkCircle" /> {t('analysis.title')}</div>
      </div>

      <div className="analysis-container">
        {/* Header */}
        <div className="complete-header">
          <div className="complete-icon"><Icon icon="checkCircle" size={32} /></div>
          <h2>{recordingName}</h2>
        </div>

        {/* Stats bar */}
        <div className="complete-stats">
          <span className="stats-count">
            <Icon icon="list" size={14} />
            {t('recording.opsCount', { count: operations.length })}
          </span>
          {duration && (
            <>
              <span className="stats-separator">·</span>
              <span className="stats-duration">
                <Icon icon="clock" size={14} />
                {duration}
              </span>
            </>
          )}
        </div>

        {/* Task Description */}
        {taskDescription && (
          <div className="task-description">
            <span className="task-description-label"><Icon icon="fileText" size={14} /> {t('analysis.taskDesc')}</span>
            <p className="task-description-text">{taskDescription}</p>
          </div>
        )}

        {/* Operations Timeline */}
        <div className="operations-display">
          <div className="operations-header">
            <span className="operations-title">{t('recording.capturedOps')}</span>
            <span className="operations-count">{operations.length}</span>
          </div>
          <div className="operations-list">
            {loadingOps ? (
              <div className="empty-operations">
                <div className="empty-text">{t('common.loading')}</div>
              </div>
            ) : operations.length === 0 ? (
              <div className="empty-operations">
                <div className="empty-icon"><Icon icon="clipboard" size={36} /></div>
                <div className="empty-text">{t('recording.waitingOps')}</div>
              </div>
            ) : (
              operations.map((op, index) => (
                <div key={index} className="operation-item">
                  <div className="operation-index">{index + 1}</div>
                  <div className="operation-details">
                    <div className="operation-type">{getOperationTypeLabel(op.type)}</div>
                    <div className="operation-info">
                      {op.text && (
                        <div className="operation-text">
                          {op.text.slice(0, 50)}
                          {op.text.length > 50 ? '...' : ''}
                        </div>
                      )}
                      {op.value && (
                        <div className="operation-value">
                          {t('recording.ops.input')}: {op.value.slice(0, 30)}
                          {op.value.length > 30 ? '...' : ''}
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

        {/* Action Buttons */}
        <div className="action-buttons">
          <button
            className="btn-secondary"
            onClick={() => onNavigate("main")}
          >
            {t('analysis.cancel')}
          </button>
          <button
            className="btn-primary"
            onClick={handleAddToMemory}
            disabled={isAdding || isAdded}
          >
            <span className="btn-icon"><Icon icon={isAdded ? "checkCircle" : "layers"} /></span>
            <span>{isAdding ? t('analysis.addingToMemory') : (isAdded ? t('common.success') : t('analysis.addToMemoryBtn'))}</span>
          </button>
          <button
            className="btn-secondary"
            onClick={() => onNavigate("main")}
            disabled={isAdding}
          >
            {t('recording.reRecord')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RecordingAnalysisPage;
