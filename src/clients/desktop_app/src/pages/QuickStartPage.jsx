import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from "react-i18next";
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/QuickStartPage.css';

function QuickStartPage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [step, setStep] = useState('tutorial'); // 'tutorial', 'input', 'recording', 'analyzing'
  const [tutorialPage, setTutorialPage] = useState(0);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [operationsCount, setOperationsCount] = useState(0);
  const [capturedOperations, setCapturedOperations] = useState([]);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [browserOpening, setBrowserOpening] = useState(false);
  const [recordingWebviewId, setRecordingWebviewId] = useState(null);
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
      'click': { text: t('quickStart.operations.click'), icon: 'mousePointer' },
      'input': { text: t('quickStart.operations.input'), icon: 'keyboard' },
      'navigate': { text: t('quickStart.operations.navigate'), icon: 'globe' },
      'scroll': { text: t('quickStart.operations.scroll'), icon: 'arrowDown' },
      'select': { text: t('quickStart.operations.select'), icon: 'list' },
      'submit': { text: t('quickStart.operations.submit'), icon: 'checkCircle' },
      'hover': { text: t('quickStart.operations.hover'), icon: 'mousePointer' },
      'keydown': { text: t('quickStart.operations.keydown'), icon: 'keyboard' },
      'change': { text: t('quickStart.operations.change'), icon: 'edit' },
      'newtab': { text: t('quickStart.operations.newtab'), icon: 'plus' },
      'closetab': { text: t('quickStart.operations.closetab'), icon: 'x' },
      'copy_action': { text: t('quickStart.operations.copy_action'), icon: 'clipboard' },
      'paste_action': { text: t('quickStart.operations.paste_action'), icon: 'clipboard' }
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
      title: t('quickStart.tutorial.step1Title'),
      description: t('quickStart.tutorial.step1Desc'),
      content: t('quickStart.tutorial.step1Content'),
      icon: "video"
    },
    {
      title: t('quickStart.tutorial.step2Title'),
      description: t('quickStart.tutorial.step2Desc'),
      content: t('quickStart.tutorial.step2Content'),
      icon: "clipboard"
    },
    {
      title: t('quickStart.tutorial.step3Title'),
      description: t('quickStart.tutorial.step3Desc'),
      content: t('quickStart.tutorial.step3Content'),
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

  // In Electron mode, the browser is always running as part of the app.
  // This will be expanded in Phase 5 to show the embedded browser view.
  const handleOpenBrowserOnly = async () => {
    showStatus(t('quickStart.status.browserAlreadyRunning'), "success");
  };

  const handleStartRecording = async () => {
    try {
      showStatus(t('quickStart.status.startingRecording'), "info");

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

      // Navigate to full-page recording browser
      onNavigate('browser', {
        mode: 'recording',
        sessionId: result.session_id,
        viewId: result.webview_id,
        source: 'quick_start',
      });

    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`${t('quickStart.status.startRecordingFailed')}: ${error.message}`, "error");
    }
  };

  const handleStopRecording = async () => {
    try {
      showStatus(t('quickStart.status.stoppingRecording'), "info");

      // Hide webview before stopping
      if (recordingWebviewId) {
        window.electronAPI?.hideWebview(recordingWebviewId);
        setRecordingWebviewId(null);
      }

      const result = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });
      setOperationsCount(result.operations_count);
      showStatus(t('quickStart.status.recordingCompleted', { count: result.operations_count }), "success");

      // Analyze recording with AI
      setStep('analyzing');
      await handleAnalyzeRecording(result.session_id);

    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`${t('quickStart.status.stopRecordingFailed')}: ${error.message}`, "error");
      setStep('input');
    }
  };

  const handleAnalyzeRecording = async (sessionId) => {
    try {
      setAnalysisProgress(0);
      showStatus(t('quickStart.status.analyzing'), "info");

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

      showStatus(t('quickStart.analysisComplete'), "success");

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
          taskDescription: analysisResult.task_description
        });
      }, 500);

    } catch (error) {
      console.error("Analysis error:", error);
      showStatus(`${t('quickStart.status.analyzeFailed')}: ${error.message}`, "error");
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
            <Icon icon="x" /> {t('quickStart.tutorial.skip')}
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
                  {t('quickStart.tutorial.previous')}
                </button>
              )}
              <button className="tutorial-btn primary" onClick={handleNextTutorialPage}>
                {tutorialPage === tutorialSteps.length - 1 ? t('quickStart.tutorial.getStarted') : t('quickStart.tutorial.next')}
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
          <Icon icon="zap" /> {t('quickStart.title')}
        </div>
      </div>

      <div className="content-wrapper">
        {/* LEFT COLUMN: START BUTTON card */}
        <div className="input-card">
          <div className="card-header">
            <h2>{t('quickStart.startRecordingTitle')}</h2>
            <p>{t('quickStart.startRecordingDesc')}</p>
          </div>

          <button
            className="start-recording-btn"
            onClick={handleStartRecording}
          >
            <span className="btn-icon">
              <Icon icon="video" />
            </span>
            <span>{t('quickStart.openBrowserAndRecord')}</span>
          </button>

          <div className="browser-only-section">
            <div className="browser-only-divider">
              <span>{t('quickStart.or')}</span>
            </div>
            <button
              className="open-browser-btn"
              onClick={handleOpenBrowserOnly}
              disabled={browserOpening}
            >
              <Icon icon="globe" size={16} />
              <span>{browserOpening ? t('quickStart.opening') : t('quickStart.openBrowserOnly')}</span>
            </button>
            <div className="browser-only-hint">
              <Icon icon="info" size={14} />
              <span>{t('quickStart.needLoginHint')}</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: TIPS & RULES */}
        <div className="tips-panel">
          <div className="tips-section">
            <h3><Icon icon="zap" size={18} /> {t('quickStart.recordingBestPractices')}</h3>
            <ul className="tips-list">
              <li>
                <strong>{t('quickStart.tipSelectCopy')}</strong> {t('quickStart.tipSelectCopyDesc')}
              </li>
              <li>
                <strong>{t('quickStart.tipCompletePath')}</strong> {t('quickStart.tipCompletePathDesc')}
              </li>
              <li>
                <strong>{t('quickStart.tipWaitForLoad')}</strong> {t('quickStart.tipWaitForLoadDesc')}
              </li>
            </ul>
          </div>

          <div className="tips-section">
            <h3><Icon icon="clipboard" size={18} /> {t('quickStart.whatGetsRecorded')}</h3>
            <ul className="tips-list info">
              <li><strong>{t('quickStart.clicks')}</strong> {t('quickStart.clicksDesc')}</li>
              <li><strong>{t('quickStart.inputs')}</strong> {t('quickStart.inputsDesc')}</li>
              <li><strong>{t('quickStart.selectCopy')}</strong> {t('quickStart.selectCopyDesc')}</li>
              <li><strong>{t('quickStart.navigation')}</strong> {t('quickStart.navigationDesc')}</li>
            </ul>
          </div>

          <div className="tips-section warning-section">
            <h3><Icon icon="alertTriangle" size={18} /> {t('quickStart.note')}</h3>
            <ul className="tips-list warning">
              <li>{t('quickStart.doNotCloseBrowser')}</li>
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
            <span>{t('quickStart.recordingStatus')}</span>
          </div>
          <div className="recording-stats">
            <span className="operations-badge">{operationsCount} {t('recordingsLibrary.operations')}</span>
            <span className="session-id">{t('recordingsLibrary.sessionId')}: {currentSessionId}</span>
          </div>
        </div>

        <div className="recording-actions">
          <button className="stop-recording-btn" onClick={handleStopRecording}>
            <Icon icon="square" />
            <span>{t('quickStart.stopRecording')}</span>
          </button>
        </div>

        <div className="recording-warning">
          <Icon icon="alertTriangle" />
          <span>{t('quickStart.doNotCloseWarning')}</span>
        </div>
      </div>

      {/* Operations list - main content area */}
      <div className="recording-operations-container">
        <div className="operations-header">
          <span className="operations-title">
            <Icon icon="list" /> {t('quickStart.capturedOperations')}
          </span>
          <span className="operations-count">{capturedOperations.length}</span>
        </div>
        <div className="operations-list-full" ref={operationsListRef}>
          {capturedOperations.length === 0 ? (
            <div className="empty-operations-full">
              <Icon icon="clipboard" size={64} />
              <h3>{t('quickStart.waitingForOperations')}</h3>
              <p>{t('quickStart.waitingDesc')}</p>
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
          <h2><Icon icon="cpu" /> {t('quickStart.aiAnalyzing')}</h2>
        </div>

        <p className="generating-status">{t('quickStart.understandingOperations')}</p>

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
            <span>{t('quickStart.stepAnalyzing')}</span>
          </div>
          <div className={`step-item ${analysisProgress > 60 ? 'completed' : analysisProgress > 30 ? 'active' : ''}`}>
            <span className="step-icon">
              {analysisProgress > 60 ? <Icon icon="check" /> : <Icon icon="clock" />}
            </span>
            <span>{t('quickStart.stepDetecting')}</span>
          </div>
          <div className={`step-item ${analysisProgress > 90 ? 'completed' : analysisProgress > 60 ? 'active' : ''}`}>
            <span className="step-icon">
              {analysisProgress > 90 ? <Icon icon="check" /> : <Icon icon="clock" />}
            </span>
            <span>{t('quickStart.stepGenerating')}</span>
          </div>
        </div>

        {analysisProgress < 100 && (
          <p className="estimated-time">{t('quickStart.estimatedTime', { seconds: Math.max(1, Math.ceil((100 - analysisProgress) / 20)) })}</p>
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
        <p>Ami v{version || '1.0.0'} • {session?.username && t('settings.loggedInAs', { username: session.username })}</p>
      </div>
    </div>
  );
}

export default QuickStartPage;
