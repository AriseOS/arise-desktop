import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/QuickStartPage.css';

function QuickStartPage({ session, onNavigate, showStatus }) {
  const userId = session?.username;
  const [step, setStep] = useState('tutorial'); // 'tutorial', 'input', 'recording', 'analyzing'
  const [tutorialPage, setTutorialPage] = useState(0);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [operationsCount, setOperationsCount] = useState(0);
  const [capturedOperations, setCapturedOperations] = useState([]);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [browserOpening, setBrowserOpening] = useState(false);
  const operationsListRef = useRef(null);

  // Check if user has seen tutorial before
  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem('hasSeenTutorial');
    if (hasSeenTutorial === 'true') {
      setStep('input');
    }
  }, []);

  // Poll for operations while recording
  useEffect(() => {
    if (step !== 'recording') {
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
  }, [step]);

  // Auto-scroll to bottom when new operations are added
  useEffect(() => {
    if (operationsListRef.current) {
      operationsListRef.current.scrollTop = operationsListRef.current.scrollHeight;
    }
  }, [capturedOperations]);

  // Get operation type label with icon
  const getOperationTypeLabel = (type) => {
    const typeLabels = {
      'click': { text: '点击', icon: 'mousePointer' },
      'input': { text: '输入', icon: 'keyboard' },
      'navigate': { text: '导航', icon: 'globe' },
      'scroll': { text: '滚动', icon: 'arrowDown' },
      'select': { text: '选择', icon: 'list' },
      'submit': { text: '提交', icon: 'checkCircle' },
      'hover': { text: '悬停', icon: 'mousePointer' },
      'keydown': { text: '按键', icon: 'keyboard' },
      'change': { text: '修改', icon: 'edit' },
      'newtab': { text: '新标签', icon: 'plus' },
      'closetab': { text: '关闭标签', icon: 'x' },
      'copy_action': { text: '复制', icon: 'clipboard' },
      'paste_action': { text: '粘贴', icon: 'clipboard' }
    };
    const label = typeLabels[type] || { text: type || '操作', icon: 'mapPin' };
    return (
      <>
        <Icon icon={label.icon} size={14} />
        <span>{label.text}</span>
      </>
    );
  };

  const tutorialSteps = [
    {
      title: "How Recording Works",
      description: "AI watches and learns from your browser actions",
      content: "We capture: Clicks, Text Input, Page Navigation, Copy/Paste\n\nThe AI uses this to build an automated workflow that replays your exact actions.",
      icon: "video"
    },
    {
      title: "Key Tip: Select + Copy",
      description: "This is how you tell AI what data to extract",
      content: "When you see data you want:\n1. Select the text with your mouse\n2. Press Ctrl+C (Cmd+C on Mac)\n\nAI knows: 'User wants to extract this field'",
      icon: "clipboard"
    },
    {
      title: "Complete Your Path",
      description: "Start from the beginning, click through each step",
      content: "Why? The workflow runs on a fresh browser.\n\nIt needs your full click path to:\n• Navigate to the right page\n• Find the same elements\n• Extract the same data",
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

  const handleOpenBrowserOnly = async () => {
    if (browserOpening) return;

    setBrowserOpening(true);
    showStatus("Opening browser...", "info");

    try {
      const result = await api.startBrowser(false);

      if (result.status === "already_running") {
        showStatus("Browser is already running. You can login to your accounts now.", "success");
      } else {
        showStatus("Browser opened! Login to your accounts, then click 'Start Recording' when ready.", "success");
      }
    } catch (error) {
      console.error("Open browser error:", error);
      showStatus(`Failed to open browser: ${error.message}`, "error");
    } finally {
      setBrowserOpening(false);
    }
  };

  const handleStartRecording = async () => {
    try {
      showStatus("Starting recording...", "info");

      // Use about:blank as default URL - user can navigate anywhere in browser
      const result = await api.callAppBackend('/api/v1/recordings/start', {
        method: "POST",
        body: JSON.stringify({
          url: "about:blank",
          user_id: userId,
          title: "Quick Start Recording",
          description: "Recording from Quick Start",
          task_metadata: {
            quick_start: true
          }
        })
      });
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

      const result = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });
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

      // Use api.analyzeRecording() which auto-injects X-Ami-API-Key header
      const analysisResult = await api.analyzeRecording(sessionId, userId);

      clearInterval(progressInterval);
      setAnalysisProgress(100);

      showStatus(`Analysis complete!`, "success");

      // Save metadata immediately after analysis
      try {
        await api.callAppBackend(`/api/v1/recordings/${sessionId}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: analysisResult.name,
            task_description: analysisResult.task_description,
            user_query: analysisResult.user_query,
            user_id: userId
          })
        });
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
    <div className="quick-start-container split-layout">
      {/* HEADER */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title">
          <Icon icon="zap" /> Quick Start
        </div>
      </div>

      <div className="content-wrapper">
        {/* LEFT COLUMN: START BUTTON card */}
        <div className="input-card">
          <div className="card-header">
            <h2>Start Recording</h2>
            <p>Click below to open the browser. We'll capture your actions to build the workflow.</p>
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

          <div className="browser-only-section">
            <div className="browser-only-divider">
              <span>or</span>
            </div>
            <button
              className="open-browser-btn"
              onClick={handleOpenBrowserOnly}
              disabled={browserOpening}
            >
              <Icon icon="globe" size={16} />
              <span>{browserOpening ? "Opening..." : "Open Browser Only"}</span>
            </button>
            <div className="browser-only-hint">
              <Icon icon="info" size={14} />
              <span>Need to login first? Open browser to login, then start recording.</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: TIPS & RULES */}
        <div className="tips-panel">
          <div className="tips-section">
            <h3><Icon icon="zap" size={18} /> Recording Best Practices</h3>
            <ul className="tips-list">
              <li>
                <strong>Select + Copy = Extract:</strong> To extract data, select text with mouse then press Ctrl+C. AI recognizes this as data to extract.
              </li>
              <li>
                <strong>Complete Path:</strong> Start from the beginning. Every click is recorded. AI needs the full path to automate replay.
              </li>
              <li>
                <strong>Wait for Load:</strong> Ensure pages fully load before clicking. This helps AI identify the correct elements.
              </li>
            </ul>
          </div>

          <div className="tips-section">
            <h3><Icon icon="clipboard" size={18} /> What Gets Recorded</h3>
            <ul className="tips-list info">
              <li><strong>Clicks:</strong> Buttons, links, menu items</li>
              <li><strong>Inputs:</strong> Text fields, search boxes</li>
              <li><strong>Select+Copy:</strong> Selected and copied text (key for data extraction)</li>
              <li><strong>Navigation:</strong> URL changes and page transitions</li>
            </ul>
          </div>

          <div className="tips-section warning-section">
            <h3><Icon icon="alertTriangle" size={18} /> Note</h3>
            <ul className="tips-list warning">
              <li>Do not close the browser directly. Return here and click "Stop Recording".</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );

  // Render Recording Step (Full Page Layout)
  const renderRecording = () => (
    <div className="recording-page-container">
      {/* Top header section */}
      <div className="recording-top-section">
        <div className="recording-status-bar">
          <div className="recording-indicator">
            <span className="recording-dot"></span>
            <span>Recording...</span>
          </div>
          <div className="recording-stats">
            <span className="operations-badge">{operationsCount} operations</span>
            <span className="session-id">Session: {currentSessionId}</span>
          </div>
        </div>

        <div className="recording-actions">
          <button className="stop-recording-btn" onClick={handleStopRecording}>
            <Icon icon="square" />
            <span>Stop Recording</span>
          </button>
        </div>

        <div className="recording-warning">
          <Icon icon="alertTriangle" />
          <span>Do not close the browser directly. Come back here and click "Stop Recording" when done.</span>
        </div>
      </div>

      {/* Operations list - main content area */}
      <div className="recording-operations-container">
        <div className="operations-header">
          <span className="operations-title">
            <Icon icon="list" /> Captured Operations
          </span>
          <span className="operations-count">{capturedOperations.length}</span>
        </div>
        <div className="operations-list-full" ref={operationsListRef}>
          {capturedOperations.length === 0 ? (
            <div className="empty-operations-full">
              <Icon icon="clipboard" size={64} />
              <h3>Waiting for operations...</h3>
              <p>Perform actions in the browser window. Your clicks, inputs, and navigation will appear here.</p>
            </div>
          ) : (
            capturedOperations.map((op, index) => (
              <div key={index} className="operation-item-full">
                <div className="operation-index">{index + 1}</div>
                <div className="operation-details">
                  <div className="operation-type">{getOperationTypeLabel(op.type)}</div>
                  <div className="operation-info">
                    {op.element?.textContent && (
                      <div className="operation-text">
                        {op.element.textContent.slice(0, 80)}
                        {op.element.textContent.length > 80 ? '...' : ''}
                      </div>
                    )}
                    {op.data?.actualValue && (
                      <div className="operation-value">
                        Input: {op.data.actualValue.slice(0, 50)}
                        {op.data.actualValue.length > 50 ? '...' : ''}
                      </div>
                    )}
                  </div>
                </div>
                {op.url && (
                  <div className="operation-url-badge">
                    {(() => {
                      try {
                        return new URL(op.url).hostname;
                      } catch {
                        return op.url.slice(0, 30);
                      }
                    })()}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
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
