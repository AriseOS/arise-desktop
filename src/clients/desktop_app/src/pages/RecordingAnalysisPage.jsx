import React, { useState } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingAnalysisPage.css';

function RecordingAnalysisPage({ session, pageData, onNavigate, showStatus }) {
  const userId = session?.username;
  const [taskDescription, setTaskDescription] = useState(pageData?.taskDescription || '');
  const [userQuery, setUserQuery] = useState(pageData?.userQuery || '');
  const [isSaving, setIsSaving] = useState(false);

  const detectedPatterns = pageData?.detectedPatterns || {};
  const sessionId = pageData?.sessionId;
  const recordingName = pageData?.name || 'Unnamed Task';

  const handleConfirmAndGenerate = async () => {
    if (!taskDescription.trim() || !userQuery.trim()) {
      showStatus("Please fill in both task description and user query", "error");
      return;
    }

    try {
      setIsSaving(true);

      // Save metadata first
      showStatus("Saving metadata...", "info");
      await api.callAppBackend(`/api/v1/recordings/${sessionId}`, {
        method: "PATCH",
        body: JSON.stringify({
          task_description: taskDescription,
          user_query: userQuery,
          user_id: userId
        })
      });

      // Navigate to GenerationPage with all params - it will auto-start generation
      onNavigate('generation', {
        recordingId: sessionId,
        recordingName: recordingName,
        taskDescription: taskDescription,
        userQuery: userQuery
      });

    } catch (error) {
      console.error("Save metadata error:", error);
      setIsSaving(false);
      showStatus(`Failed to save metadata: ${error.message}`, "error");
    }
  };

  const renderPatternBadges = () => {
    const badges = [];

    if (detectedPatterns.loop_detected) {
      badges.push(
        <div key="loop" className="pattern-badge loop">
          <span className="badge-icon"><Icon icon="refreshCw" size={14} /></span>
          <span className="badge-text">Loop Pattern Detected</span>
          {detectedPatterns.loop_count && (
            <span className="badge-detail">Count: {detectedPatterns.loop_count}</span>
          )}
        </div>
      );
    }

    if (detectedPatterns.extracted_fields && detectedPatterns.extracted_fields.length > 0) {
      badges.push(
        <div key="extraction" className="pattern-badge extraction">
          <span className="badge-icon"><Icon icon="database" size={14} /></span>
          <span className="badge-text">Data Extraction</span>
          <span className="badge-detail">
            Fields: {detectedPatterns.extracted_fields.join(', ')}
          </span>
        </div>
      );
    }

    if (detectedPatterns.navigation_depth) {
      badges.push(
        <div key="navigation" className="pattern-badge navigation">
          <span className="badge-icon"><Icon icon="globe" size={14} /></span>
          <span className="badge-text">Navigation</span>
          <span className="badge-detail">Depth: {detectedPatterns.navigation_depth}</span>
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
        <div className="page-title"><Icon icon="checkCircle" /> AI Analysis Complete</div>
      </div>

      <div className="analysis-container">
        <div className="ai-badge">
          <span className="ai-icon"><Icon icon="cpu" size={16} /></span>
          <span className="ai-text">AI Generated Summary</span>
        </div>

        {/* Recording Name */}
        <div className="recording-name-section">
          <h2 className="recording-name">{recordingName}</h2>
        </div>

        {/* Detected Patterns */}
        {renderPatternBadges().length > 0 && (
          <div className="patterns-section">
            <h3><Icon icon="search" size={18} /> Detected Patterns</h3>
            <div className="patterns-grid">
              {renderPatternBadges()}
            </div>
          </div>
        )}

        {/* Task Description */}
        <div className="form-section">
          <label className="form-label">
            <span className="label-icon"><Icon icon="fileText" size={18} /></span>
            <span className="label-text">Task Description</span>
            <span className="label-hint">What operations did you perform?</span>
          </label>
          <textarea
            className="form-textarea"
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
            rows={4}
            placeholder="Describe the operations you performed..."
          />
        </div>

        {/* User Query */}
        <div className="form-section">
          <label className="form-label">
            <span className="label-icon"><Icon icon="target" size={18} /></span>
            <span className="label-text">User Query (Goal)</span>
            <span className="label-hint">What is your final goal?</span>
          </label>
          <textarea
            className="form-textarea"
            value={userQuery}
            onChange={(e) => setUserQuery(e.target.value)}
            rows={4}
            placeholder="Describe what you want to achieve..."
          />
        </div>

        {/* Action Buttons */}
        <div className="action-buttons">
          <button
            className="btn-secondary"
            onClick={() => onNavigate("main")}
          >
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={handleConfirmAndGenerate}
            disabled={isSaving || !taskDescription.trim() || !userQuery.trim()}
          >
            <span className="btn-icon"><Icon icon="zap" /></span>
            <span>{isSaving ? 'Saving...' : 'Confirm & Generate Workflow'}</span>
          </button>
        </div>

        {/* Info Box */}
        <div className="info-box">
          <p className="info-title"><Icon icon="info" size={16} /> Tips</p>
          <ul className="info-list">
            <li>AI analyzed your operations and suggested descriptions above</li>
            <li>You can edit them to better match your intent</li>
            <li>Keywords like "top 10", "all", "every" help AI detect loops</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default RecordingAnalysisPage;
