import React, { useState } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingAnalysisPage.css';

const API_BASE = "http://127.0.0.1:8765";

function RecordingAnalysisPage({ session, pageData, onNavigate, showStatus }) {
  const userId = session?.username;
  const [taskDescription, setTaskDescription] = useState(pageData?.taskDescription || '');
  const [userQuery, setUserQuery] = useState(pageData?.userQuery || '');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);

  const detectedPatterns = pageData?.detectedPatterns || {};
  const sessionId = pageData?.sessionId;
  const recordingName = pageData?.name || 'Unnamed Task';

  const handleConfirmAndGenerate = async () => {
    if (!taskDescription.trim() || !userQuery.trim()) {
      showStatus("Please fill in both task description and user query", "error");
      return;
    }

    try {
      setIsGenerating(true);
      setGenerationProgress(0);

      // Step 1: Save metadata first
      showStatus("Saving metadata...", "info");
      const updateResponse = await fetch(`${API_BASE}/api/recording/update-metadata`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: taskDescription,
          user_query: userQuery,
          user_id: userId
        })
      });

      if (!updateResponse.ok) {
        throw new Error(`Failed to save metadata: ${updateResponse.status}`);
      }

      setGenerationProgress(20);

      // Step 2: Generate MetaFlow
      showStatus("Generating MetaFlow...", "info");

      const progressInterval = setInterval(() => {
        setGenerationProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 500);

      const metaflowResult = await api.generateMetaflowFromRecording(
        sessionId,
        taskDescription,
        userQuery,
        userId
      );

      clearInterval(progressInterval);
      setGenerationProgress(100);

      showStatus("MetaFlow generated! Redirecting to preview...", "success");

      // Navigate to MetaFlow preview page
      setTimeout(() => {
        onNavigate('metaflow-preview', {
          metaflowId: metaflowResult.metaflow_id,
          metaflowYaml: metaflowResult.metaflow_yaml
        });
      }, 500);

    } catch (error) {
      console.error("Generate MetaFlow error:", error);
      showStatus(`Failed to generate MetaFlow: ${error.message}`, "error");
      setIsGenerating(false);
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

  if (isGenerating) {
    return (
      <div className="recording-analysis-page">
        <div className="generating-overlay">
          <div className="generating-content">
            <div className="generating-animation">
              <div className="spinner-large"></div>
              <h2><Icon icon="cpu" size={24} /> Generating MetaFlow...</h2>
            </div>

            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${generationProgress}%` }}
              />
            </div>
            <p className="progress-text">{generationProgress}%</p>

            {generationProgress < 100 && (
              <p className="estimated-time">
                Estimated time remaining: {Math.max(1, Math.floor((100 - generationProgress) / 10))}s
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

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
            disabled={!taskDescription.trim() || !userQuery.trim()}
          >
            <span className="btn-icon"><Icon icon="zap" /></span>
            <span>Confirm & Generate MetaFlow</span>
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
