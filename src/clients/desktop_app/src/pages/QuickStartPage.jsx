import React, { useState, useEffect } from 'react';
import '../styles/QuickStartPage.css';

const API_BASE = "http://127.0.0.1:8765";
const DEFAULT_USER = "default_user";

function QuickStartPage({ onNavigate, showStatus }) {
  const [step, setStep] = useState('tutorial'); // 'tutorial', 'input', 'recording', 'generating', 'preview'
  const [tutorialPage, setTutorialPage] = useState(0);
  const [taskDescription, setTaskDescription] = useState('');
  const [startUrl, setStartUrl] = useState('https://www.google.com');
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [operationsCount, setOperationsCount] = useState(0);
  const [generatedWorkflow, setGeneratedWorkflow] = useState(null);
  const [adjustmentText, setAdjustmentText] = useState('');
  const [generationProgress, setGenerationProgress] = useState(0);
  const [autoRunCountdown, setAutoRunCountdown] = useState(3);

  // Check if user has seen tutorial before
  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem('hasSeenTutorial');
    if (hasSeenTutorial === 'true') {
      setStep('input');
    }
  }, []);

  // Auto-run countdown in preview step
  useEffect(() => {
    if (step === 'preview' && autoRunCountdown > 0) {
      const timer = setTimeout(() => {
        setAutoRunCountdown(prev => prev - 1);
      }, 1000);
      return () => clearTimeout(timer);
    } else if (step === 'preview' && autoRunCountdown === 0) {
      // Auto execute (mock for now)
      handleExecuteWorkflow();
    }
  }, [step, autoRunCountdown]);

  const tutorialSteps = [
    {
      title: "Recording Tutorial",
      description: "Learn how to record your workflow in 3 simple steps",
      content: "1. Operate normally in the browser\n2. Select and copy the data you want\n3. Stop recording, AI generates workflow automatically",
      icon: "📹"
    },
    {
      title: "Copy Data Fields",
      description: "Mark the data you want to extract",
      content: "When you see important data:\n1. Select the text with your mouse\n2. Press Ctrl+C (or Cmd+C) to copy\n3. System will automatically record this field",
      icon: "📋"
    },
    {
      title: "AI Automation",
      description: "Let AI handle the repetitive work",
      content: "After recording:\n• AI analyzes your operations\n• Generates executable workflow\n• Run anytime with one click",
      icon: "🤖"
    }
  ];

  const handleSkipTutorial = () => {
    localStorage.setItem('hasSeenTutorial', 'true');
    setStep('input');
  };

  const handleNextTutorialPage = () => {
    if (tutorialPage < tutorialSteps.length - 1) {
      setTutorialPage(prev => prev + 1);
    } else {
      handleSkipTutorial();
    }
  };

  const handlePrevTutorialPage = () => {
    if (tutorialPage > 0) {
      setTutorialPage(prev => prev - 1);
    }
  };

  const handleStartRecording = async () => {
    if (!taskDescription.trim() || !startUrl.trim()) {
      showStatus("❌ Please fill in task description and start URL", "error");
      return;
    }

    try {
      showStatus("📹 Starting recording...", "info");

      const response = await fetch(`${API_BASE}/api/recording/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: startUrl,
          title: taskDescription.substring(0, 50),
          description: taskDescription,
          task_metadata: {
            quick_start: true,
            user_id: DEFAULT_USER
          }
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to start recording: ${response.status}`);
      }

      const result = await response.json();
      setCurrentSessionId(result.session_id);
      setStep('recording');
      showStatus("✅ Recording started! Please operate in the browser", "success");

    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`❌ Failed to start recording: ${error.message}`, "error");
    }
  };

  const handleStopRecording = async () => {
    try {
      showStatus("⏹️ Stopping recording...", "info");

      const response = await fetch(`${API_BASE}/api/recording/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      if (!response.ok) {
        throw new Error(`Failed to stop recording: ${response.status}`);
      }

      const result = await response.json();
      setOperationsCount(result.operations_count);
      showStatus(`✅ Recording completed! Captured ${result.operations_count} operations`, "success");

      // Auto generate workflow
      setStep('generating');
      await handleGenerateWorkflow(result.session_id);

    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`❌ Failed to stop recording: ${error.message}`, "error");
      setStep('input');
    }
  };

  const handleGenerateWorkflow = async (sessionId) => {
    try {
      // Step 1: Generate MetaFlow from recording
      setGenerationProgress(0);
      showStatus("⚡ Generating MetaFlow...", "info");

      const progressInterval = setInterval(() => {
        setGenerationProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 500);

      const metaflowResponse = await fetch(`${API_BASE}/api/metaflows/from-recording`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: taskDescription,
          user_id: DEFAULT_USER
        })
      });

      clearInterval(progressInterval);
      setGenerationProgress(100);

      if (!metaflowResponse.ok) {
        throw new Error(`MetaFlow generation failed: ${metaflowResponse.status}`);
      }

      const metaflowResult = await metaflowResponse.json();

      showStatus("✅ MetaFlow generated! Redirecting to preview...", "success");

      // Navigate to MetaFlow preview page (user will review and generate workflow from there)
      setTimeout(() => {
        onNavigate('metaflow-preview', {
          metaflowId: metaflowResult.metaflow_id,
          metaflowYaml: metaflowResult.metaflow_yaml
        });
      }, 500);

    } catch (error) {
      console.error("Generate MetaFlow error:", error);
      showStatus(`❌ Failed to generate MetaFlow: ${error.message}`, "error");
      setStep('input');
    }
  };

  const handleExecuteWorkflow = () => {
    // Navigate to workflow detail page
    if (generatedWorkflow && generatedWorkflow.workflow_id) {
      showStatus("📋 Opening workflow detail...", "info");
      setTimeout(() => {
        onNavigate("workflow-detail", {
          workflowId: generatedWorkflow.workflow_id
        });
      }, 500);
    } else {
      showStatus("⚠️ Workflow ID not found", "error");
    }
  };

  const handleSaveForLater = () => {
    // Navigate to workflow detail page
    if (generatedWorkflow && generatedWorkflow.workflow_id) {
      showStatus("💾 Workflow saved! Opening detail page...", "success");
      setTimeout(() => {
        onNavigate("workflow-detail", {
          workflowId: generatedWorkflow.workflow_id
        });
      }, 500);
    } else {
      showStatus("⚠️ Workflow ID not found", "error");
    }
  };

  const handleCancelAutoRun = () => {
    setAutoRunCountdown(-1); // Stop countdown
  };

  const handleAdjustWorkflow = async () => {
    if (!adjustmentText.trim()) return;

    showStatus("🤖 Adjusting workflow with AI...", "info");

    // Mock adjustment (in production, call LLM API)
    setTimeout(() => {
      showStatus("✅ Workflow adjusted!", "success");
      setAdjustmentText('');

      // Update workflow steps (mock)
      setGeneratedWorkflow(prev => ({
        ...prev,
        steps: [
          ...prev.steps,
          `Added: ${adjustmentText}`
        ]
      }));
    }, 1500);
  };

  // Render Tutorial
  const renderTutorial = () => {
    const currentTutorial = tutorialSteps[tutorialPage];

    return (
      <div className="tutorial-overlay">
        <div className="tutorial-modal">
          <button className="tutorial-skip" onClick={handleSkipTutorial}>
            ✕ Skip Tutorial
          </button>

          <div className="tutorial-content">
            <div className="tutorial-icon">{currentTutorial.icon}</div>
            <h2 className="tutorial-title">{currentTutorial.title}</h2>
            <p className="tutorial-description">{currentTutorial.description}</p>

            <div className="tutorial-details">
              {currentTutorial.content.split('\n').map((line, idx) => (
                <p key={idx}>{line}</p>
              ))}
            </div>
          </div>

          <div className="tutorial-navigation">
            <div className="tutorial-dots">
              {tutorialSteps.map((_, idx) => (
                <span
                  key={idx}
                  className={`tutorial-dot ${idx === tutorialPage ? 'active' : ''}`}
                />
              ))}
            </div>

            <div className="tutorial-buttons">
              {tutorialPage > 0 && (
                <button className="tutorial-btn secondary" onClick={handlePrevTutorialPage}>
                  Previous
                </button>
              )}
              <button className="tutorial-btn primary" onClick={handleNextTutorialPage}>
                {tutorialPage === tutorialSteps.length - 1 ? "Get Started" : "Next"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Render Input Step
  const renderInput = () => (
    <div className="quick-start-container">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">⚡ Quick Start</div>
      </div>

      <div className="input-card">
        <div className="card-header">
          <h2>Describe what you want to do</h2>
          <p>Tell us your task, we'll help you record and generate workflow</p>
        </div>

        <div className="form-group">
          <label>Task Description *</label>
          <textarea
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
            placeholder="Describe your task in detail, e.g., Open Google, search for coffee, view search results"
            rows={4}
          />
        </div>

        <div className="form-group">
          <label>Start URL *</label>
          <input
            type="url"
            value={startUrl}
            onChange={(e) => setStartUrl(e.target.value)}
            placeholder="https://www.google.com"
          />
        </div>

        <button
          className="start-recording-btn"
          onClick={handleStartRecording}
          disabled={!taskDescription.trim() || !startUrl.trim()}
        >
          <span className="btn-icon">🎬</span>
          <span>Start Recording</span>
        </button>
      </div>

      <div className="tips-section">
        <h3>💡 Tips</h3>
        <ul>
          <li>Clearly describe your task for better workflow generation</li>
          <li>Ensure each step is executed correctly during recording</li>
          <li>You can view and edit detailed steps after generation</li>
        </ul>
      </div>
    </div>
  );

  // Render Recording Step (Floating Window Style)
  const renderRecording = () => (
    <div className="recording-overlay">
      <div className="recording-float-window">
        <div className="recording-indicator">
          <span className="recording-dot"></span>
          <span>Recording...</span>
        </div>

        <div className="recording-info">
          <p className="recording-count">Recorded {operationsCount} operations</p>
          <p className="recording-hint">💡 Tip: Select data and copy</p>
        </div>

        <button className="stop-recording-btn" onClick={handleStopRecording}>
          <span>⏹</span>
          <span>Stop Recording</span>
        </button>

        <button className="minimize-btn">− Minimize</button>
      </div>

      {/* Background instruction */}
      <div className="recording-background-instruction">
        <h3>Recording in progress...</h3>
        <p>Perform your task in the browser window</p>
        <p className="session-id">Session ID: {currentSessionId}</p>
      </div>
    </div>
  );

  // Render Generating Step
  const renderGenerating = () => (
    <div className="generating-container">
      <div className="generating-content">
        <div className="generating-animation">
          <div className="spinner-large"></div>
          <h2>⚙️ AI is analyzing...</h2>
        </div>

        <p className="generating-status">Understanding your workflow</p>

        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${generationProgress}%` }}
          />
        </div>
        <p className="progress-text">{generationProgress}%</p>

        <div className="generation-steps">
          <div className={`step-item ${generationProgress > 20 ? 'completed' : 'active'}`}>
            <span className="step-icon">✅</span>
            <span>Uploaded recording data</span>
          </div>
          <div className={`step-item ${generationProgress > 60 ? 'completed' : generationProgress > 20 ? 'active' : ''}`}>
            <span className="step-icon">{generationProgress > 60 ? '✅' : '⏳'}</span>
            <span>Analyzed intent</span>
          </div>
          <div className={`step-item ${generationProgress > 90 ? 'completed' : generationProgress > 60 ? 'active' : ''}`}>
            <span className="step-icon">{generationProgress > 90 ? '✅' : '⏳'}</span>
            <span>Generating workflow...</span>
          </div>
        </div>

        {generationProgress < 100 && (
          <p className="estimated-time">Estimated time remaining: {Math.max(1, Math.floor((100 - generationProgress) / 10))}s</p>
        )}
      </div>
    </div>
  );

  // Render Preview Step
  const renderPreview = () => (
    <div className="preview-container">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">✨ Workflow Generated!</div>
      </div>

      <div className="preview-card">
        <h2 className="workflow-title">📋 {generatedWorkflow?.name || "Workflow"}</h2>

        <div className="workflow-description">
          <h3>This workflow will:</h3>
          <ol className="workflow-steps-list">
            {generatedWorkflow?.steps.map((step, idx) => (
              <li key={idx}>{step}</li>
            ))}
          </ol>
        </div>

        <div className="adjustment-section">
          <h3>💬 Need adjustments?</h3>
          <div className="adjustment-input-group">
            <input
              type="text"
              value={adjustmentText}
              onChange={(e) => setAdjustmentText(e.target.value)}
              placeholder='E.g., "Add stock field" or "Only scrape first 10 products"'
            />
            <button
              className="btn-adjust"
              onClick={handleAdjustWorkflow}
              disabled={!adjustmentText.trim()}
            >
              Send
            </button>
          </div>
        </div>

        <div className="action-buttons">
          <button className="btn-run-now" onClick={handleExecuteWorkflow}>
            ▶️ Run Now
          </button>
          <button className="btn-save-later" onClick={handleSaveForLater}>
            Save for Later
          </button>
        </div>

        {autoRunCountdown > 0 && (
          <div className="auto-run-notice">
            <p>Auto-running in {autoRunCountdown}s...</p>
            <button className="btn-cancel-auto" onClick={handleCancelAutoRun}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // Main render
  return (
    <div className="quick-start-page">
      {step === 'tutorial' && renderTutorial()}
      {step === 'input' && renderInput()}
      {step === 'recording' && renderRecording()}
      {step === 'generating' && renderGenerating()}
      {step === 'preview' && renderPreview()}

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );
}

export default QuickStartPage;
