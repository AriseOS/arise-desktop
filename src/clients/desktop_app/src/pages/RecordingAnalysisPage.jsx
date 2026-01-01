import React, { useState } from 'react';
import Icon from '../components/Icons';
import WorkflowGenerationProgress from '../components/WorkflowGenerationProgress';
import { api } from '../utils/api';
import '../styles/RecordingAnalysisPage.css';

function RecordingAnalysisPage({ session, pageData, onNavigate, showStatus }) {
  const userId = session?.username;
  const [taskDescription, setTaskDescription] = useState(pageData?.taskDescription || '');
  const [userQuery, setUserQuery] = useState(pageData?.userQuery || '');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationStage, setGenerationStage] = useState('preparing');
  const [generationMessage, setGenerationMessage] = useState('');
  const [generationError, setGenerationError] = useState(null);

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
      setGenerationStage('preparing');
      setGenerationMessage('Saving metadata...');
      setGenerationError(null);

      // Step 1: Save metadata first
      showStatus("Saving metadata...", "info");
      await api.callAppBackend(`/api/v1/recordings/${sessionId}`, {
        method: "PATCH",
        body: JSON.stringify({
          task_description: taskDescription,
          user_query: userQuery,
          user_id: userId
        })
      });

      setGenerationProgress(15);
      setGenerationStage('analyzing');
      setGenerationMessage('Analyzing recording operations...');

      // Step 2: Generate Workflow directly (NEW v2 API - bypasses MetaFlow)
      showStatus("Generating Workflow...", "info");

      // Use streaming API for progress updates
      const workflowResult = await api.generateWorkflowStream(
        {
          userId: userId,
          taskDescription: taskDescription,
          recordingId: sessionId,
          userQuery: userQuery,
          enableSemanticValidation: true
        },
        (event) => {
          // Map backend status to frontend stage
          // Backend: pending, analyzing, understanding, generating, validating, completed, failed
          // Frontend: preparing, analyzing, generating, validating, complete, error
          const statusToStage = {
            'pending': 'preparing',
            'analyzing': 'analyzing',
            'understanding': 'analyzing',  // Merge into analyzing
            'generating': 'generating',
            'validating': 'validating',
            'completed': 'complete',
            'failed': 'error'
          };

          // Update stage from backend status
          if (event.status) {
            const mappedStage = statusToStage[event.status] || 'generating';
            setGenerationStage(mappedStage);

            if (event.status === 'failed') {
              setGenerationError(event.message || 'Generation failed');
            }
          }

          // Update progress from backend
          if (event.progress !== undefined) {
            setGenerationProgress(event.progress);
          }

          // Update message
          if (event.message) {
            setGenerationMessage(event.message);
            showStatus(event.message, "info");
          }
        }
      );

      setGenerationProgress(100);
      setGenerationStage('complete');
      setGenerationMessage('Workflow generated successfully!');

      if (workflowResult && workflowResult.workflow_id) {
        showStatus("Workflow generated! Redirecting to details...", "success");

        // Navigate to Workflow detail page directly after a short delay
        setTimeout(() => {
          onNavigate('workflow-detail', {
            workflowId: workflowResult.workflow_id,
            sessionId: workflowResult.session_id  // For dialogue support
          });
        }, 1000);
      } else {
        throw new Error("Workflow generation failed - no workflow_id returned");
      }

    } catch (error) {
      console.error("Generate Workflow error:", error);
      setGenerationStage('error');
      setGenerationError(error.message);
      showStatus(`Failed to generate Workflow: ${error.message}`, "error");
    }
  };

  const handleCancelGeneration = () => {
    setIsGenerating(false);
    setGenerationProgress(0);
    setGenerationStage('preparing');
    setGenerationMessage('');
    setGenerationError(null);
    showStatus("Generation cancelled", "info");
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
        <WorkflowGenerationProgress
          stage={generationStage}
          progress={generationProgress}
          message={generationMessage}
          error={generationError}
          onCancel={generationStage !== 'complete' && generationStage !== 'error' ? handleCancelGeneration : null}
        />
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
            <span>Confirm & Generate Workflow</span>
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
