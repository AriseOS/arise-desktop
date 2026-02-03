import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingAnalysisPage.css';

function RecordingAnalysisPage({ session, pageData, onNavigate, showStatus }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [taskDescription, setTaskDescription] = useState(pageData?.taskDescription || '');
  const [userQuery, setUserQuery] = useState(pageData?.userQuery || '');
  const [isAdding, setIsAdding] = useState(false);
  const [isAdded, setIsAdded] = useState(false);

  const detectedPatterns = pageData?.detectedPatterns || {};
  const sessionId = pageData?.sessionId;
  const recordingName = pageData?.name || t('analysis.unnamedTask');

  const handleAddToMemory = async () => {
    try {
      setIsAdding(true);

      // Call the memory add API with the recording ID
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
        <div className="ai-badge">
          <span className="ai-icon"><Icon icon="cpu" size={16} /></span>
          <span className="ai-text">{t('analysis.aiSummary')}</span>
        </div>

        {/* Recording Name */}
        <div className="recording-name-section">
          <h2 className="recording-name">{recordingName}</h2>
        </div>

        {/* Detected Patterns */}
        {renderPatternBadges().length > 0 && (
          <div className="patterns-section">
            <h3><Icon icon="search" size={18} /> {t('analysis.patternsTitle')}</h3>
            <div className="patterns-grid">
              {renderPatternBadges()}
            </div>
          </div>
        )}

        {/* Task Description */}
        <div className="form-section">
          <label className="form-label">
            <span className="label-icon"><Icon icon="fileText" size={18} /></span>
            <span className="label-text">{t('analysis.taskDesc')}</span>
            <span className="label-hint">{t('analysis.taskDescHint')}</span>
          </label>
          <textarea
            className="form-textarea"
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
            rows={4}
            placeholder={t('analysis.taskDescPlaceholder')}
          />
        </div>

        {/* User Query */}
        <div className="form-section">
          <label className="form-label">
            <span className="label-icon"><Icon icon="target" size={18} /></span>
            <span className="label-text">{t('analysis.userQuery')}</span>
            <span className="label-hint">{t('analysis.userQueryHint')}</span>
          </label>
          <textarea
            className="form-textarea"
            value={userQuery}
            onChange={(e) => setUserQuery(e.target.value)}
            rows={4}
            placeholder={t('analysis.userQueryPlaceholder')}
          />
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
            <span className="btn-icon"><Icon icon={isAdded ? "checkCircle" : "database"} /></span>
            <span>{isAdding ? t('analysis.addingToMemory') : (isAdded ? t('common.success') : t('analysis.addToMemoryBtn'))}</span>
          </button>
        </div>

        {/* Info Box */}
        <div className="info-box">
          <p className="info-title"><Icon icon="info" size={16} /> {t('analysis.tips.title')}</p>
          <ul className="info-list">
            <li>{t('analysis.tips.tip1')}</li>
            <li>{t('analysis.tips.tip2')}</li>
            <li>{t('analysis.tips.tip3')}</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default RecordingAnalysisPage;
