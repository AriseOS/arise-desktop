import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import '../styles/QuickStartPage.css';

const API_BASE = "http://127.0.0.1:8765";

function QuickStartPage({ session, onNavigate, showStatus }) {
  const userId = session?.username;
  const [step, setStep] = useState('tutorial'); // 'tutorial', 'input', 'recording', 'analyzing'
  const [tutorialPage, setTutorialPage] = useState(0);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [operationsCount, setOperationsCount] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);

  // Check if user has seen tutorial before
  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem('hasSeenTutorial');
    if (hasSeenTutorial === 'true') {
      setStep('input');
    }
  }, []);

  const tutorialSteps = [
    {
      title: "Recording Tutorial",
      description: "Learn how to record your workflow in 3 simple steps",
      content: "1. Operate normally in the browser\n2. Select and copy the data you want\n3. Stop recording, AI generates workflow automatically",
      icon: "video"
    },
    {
      title: "Copy Data Fields",
      description: "Mark the data you want to extract",
      content: "When you see important data:\n1. Select the text with your mouse\n2. Press Ctrl+C (or Cmd+C) to copy\n3. System will automatically record this field",
      icon: "clipboard"
    },
    {
      title: "AI Automation",
      description: "Let AI handle the repetitive work",
      content: "After recording:\n• AI analyzes your operations\n• Generates executable workflow\n• Run anytime with one click",
      icon: "cpu"
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
    try {
      showStatus("Starting recording...", "info");

      // Use about:blank as default URL - user can navigate anywhere in browser
      const response = await fetch(`${API_BASE}/api/recording/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: "about:blank",
          title: "Quick Start Recording",
          description: "Recording from Quick Start",
          task_metadata: {
            quick_start: true,
            user_id: userId
          }
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to start recording: ${response.status}`);
      }

      const result = await response.json();
      setCurrentSessionId(result.session_id);
      setStep('recording');
      showStatus("Recording started! Navigate to any website in the browser", "success");

    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`Failed to start recording: ${error.message}`, "error");
    }
  };

  const handleStopRecording = async () => {
    try {
      showStatus("Stopping recording...", "info");

      const response = await fetch(`${API_BASE}/api/recording/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      if (!response.ok) {
        throw new Error(`Failed to stop recording: ${response.status}`);
      }

      const result = await response.json();
      setOperationsCount(result.operations_count);
      showStatus(`Recording completed! Captured ${result.operations_count} operations`, "success");

      // Analyze recording with AI
      setStep('analyzing');
      await handleAnalyzeRecording(result.session_id);

    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`Failed to stop recording: ${error.message}`, "error");
      setStep('input');
    }
  };

  const handleAnalyzeRecording = async (sessionId) => {
    try {
      setAnalysisProgress(0);
      showStatus("AI is analyzing your operations...", "info");

      const progressInterval = setInterval(() => {
        setAnalysisProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 15;
        });
      }, 300);

      const analyzeResponse = await fetch(`${API_BASE}/api/recording/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: userId
        })
      });

      clearInterval(progressInterval);
      setAnalysisProgress(100);

      if (!analyzeResponse.ok) {
        throw new Error(`Analysis failed: ${analyzeResponse.status}`);
      }

      const analysisResult = await analyzeResponse.json();

      showStatus(`Analysis complete!`, "success");

      // Save metadata immediately after analysis
      try {
        const updateResponse = await fetch(`${API_BASE}/api/recording/update-metadata`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            name: analysisResult.name,
            task_description: analysisResult.task_description,
            user_query: analysisResult.user_query,
            user_id: userId
          })
        });

        if (!updateResponse.ok) {
          throw new Error(`Failed to save metadata: ${updateResponse.status}`);
        }
      } catch (error) {
        console.error("Failed to save metadata:", error);
        // Continue anyway - metadata save is not critical
      }

      // Navigate to analysis review page
      setTimeout(() => {
        onNavigate('recording-analysis', {
          sessionId: sessionId,
          name: analysisResult.name,
          taskDescription: analysisResult.task_description,
          userQuery: analysisResult.user_query,
          detectedPatterns: analysisResult.detected_patterns
        });
      }, 500);

    } catch (error) {
      console.error("Analysis error:", error);
      showStatus(`Failed to analyze recording: ${error.message}`, "error");
      setStep('input');
    }
  };


  // Render Tutorial
  const renderTutorial = () => {
    const currentTutorial = tutorialSteps[tutorialPage];

    return (
      <div className="tutorial-overlay">
        <div className="tutorial-modal">
          <button className="tutorial-skip" onClick={handleSkipTutorial}>
            <Icon icon="x" /> Skip Tutorial
          </button>

          <div className="tutorial-content">
            <div className="tutorial-icon">
              <Icon icon={currentTutorial.icon} />
            </div>
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
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title">
          <Icon icon="zap" /> Quick Start
        </div>
      </div>

      <div className="input-card">
        <div className="card-header">
          <h2>Start Recording</h2>
          <p>Click to open browser and navigate to any website you want!</p>
        </div>

        <button
          className="start-recording-btn"
          onClick={handleStartRecording}
        >
          <span className="btn-icon">
            <Icon icon="video" />
          </span>
          <span>Open Browser & Start Recording</span>
        </button>
      </div>

      <div className="tips-section">
        <h3><Icon icon="info" /> Tips</h3>
        <ul>
          <li>Browser will open - navigate to any website in the address bar</li>
          <li>Perform your task naturally - AI will analyze it automatically</li>
          <li>Copy important data with Ctrl+C to mark what you want to extract</li>
          <li>AI will suggest task description and goal after recording</li>
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
          <p className="recording-hint"><Icon icon="info" /> Tip: Select data and copy</p>
        </div>

        <button className="stop-recording-btn" onClick={handleStopRecording}>
          <span><Icon icon="square" /></span>
          <span>Stop Recording</span>
        </button>

        <button className="minimize-btn">
          <Icon icon="minus" /> Minimize
        </button>
      </div>

      {/* Background instruction */}
      <div className="recording-background-instruction">
        <h3>Recording in progress...</h3>
        <p>Perform your task in the browser window</p>
        <p className="session-id">Session ID: {currentSessionId}</p>
      </div>
    </div>
  );

  // Render Analyzing Step
  const renderAnalyzing = () => (
    <div className="generating-container">
      <div className="generating-content">
        <div className="generating-animation">
          <div className="spinner-large"></div>
          <h2><Icon icon="cpu" /> AI is analyzing...</h2>
        </div>

        <p className="generating-status">Understanding your operations</p>

        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${analysisProgress}%` }}
          />
        </div>
        <p className="progress-text">{analysisProgress}%</p>

        <div className="generation-steps">
          <div className={`step-item ${analysisProgress > 30 ? 'completed' : 'active'}`}>
            <span className="step-icon">
              {analysisProgress > 30 ? <Icon icon="check" /> : <Icon icon="clock" />}
            </span>
            <span>Analyzing operation sequence</span>
          </div>
          <div className={`step-item ${analysisProgress > 60 ? 'completed' : analysisProgress > 30 ? 'active' : ''}`}>
            <span className="step-icon">
              {analysisProgress > 60 ? <Icon icon="check" /> : <Icon icon="clock" />}
            </span>
            <span>Detecting patterns</span>
          </div>
          <div className={`step-item ${analysisProgress > 90 ? 'completed' : analysisProgress > 60 ? 'active' : ''}`}>
            <span className="step-icon">
              {analysisProgress > 90 ? <Icon icon="check" /> : <Icon icon="clock" />}
            </span>
            <span>Generating description</span>
          </div>
        </div>

        {analysisProgress < 100 && (
          <p className="estimated-time">Estimated time remaining: ~{Math.max(1, Math.ceil((100 - analysisProgress) / 20))}s</p>
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
      {step === 'analyzing' && renderAnalyzing()}

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );
}

export default QuickStartPage;
