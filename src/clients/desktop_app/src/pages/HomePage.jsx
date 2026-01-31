import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/HomePage.css';

/**
 * HomePage - Main dashboard with chat-style interface
 *
 * Features:
 * - Welcome card with Ami branding
 * - Chat history area
 * - Bottom input area with text/voice/record actions
 * - Optional recording sandbox panel
 */
function HomePage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();

  // State
  const [inputText, setInputText] = useState('');
  const [isRecordingSandboxOpen, setIsRecordingSandboxOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [messages, setMessages] = useState([]);
  const [recordingSteps, setRecordingSteps] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [isStartingRecording, setIsStartingRecording] = useState(false);

  const userId = session?.username;

  const chatHistoryRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [messages]);

  // Poll for operations while recording
  useEffect(() => {
    if (!isRecording) return;

    const pollInterval = setInterval(async () => {
      try {
        const result = await api.callAppBackend('/api/v1/recordings/current/operations', {
          method: "GET"
        });
        if (result.is_recording && result.operations) {
          // Convert operations to steps format
          const steps = result.operations.map((op, idx) => ({
            action: op.description || op.type || 'Action',
            timestamp: new Date(op.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }));
          setRecordingSteps(steps);
        }
      } catch (error) {
        console.error('Failed to poll operations:', error);
      }
    }, 500);

    return () => clearInterval(pollInterval);
  }, [isRecording]);

  // Handle text input submit
  const handleSubmit = () => {
    if (!inputText.trim()) return;

    // Add user message
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputText.trim(),
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Navigate to agent page with task
    onNavigate('agent', { initialTask: inputText.trim() });
    setInputText('');
  };

  // Handle key press
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Toggle recording - start/stop recording directly
  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Start recording - directly open browser and start recording
  const startRecording = async () => {
    if (isStartingRecording || isRecording) return;

    setIsStartingRecording(true);
    showStatus('Starting recording...', 'info');

    try {
      // Call API to start recording with browser
      const result = await api.callAppBackend('/api/v1/recordings/start', {
        method: "POST",
        body: JSON.stringify({
          url: "about:blank",
          user_id: userId,
          title: "Quick Recording",
          metadata: {
            source: "home_page",
            quick_start: true
          }
        })
      });

      setCurrentSessionId(result.session_id);
      setIsRecording(true);
      setRecordingSteps([]);
      setIsRecordingSandboxOpen(true);
      showStatus('Recording started! Browser is ready.', 'success');

    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`Failed to start recording: ${error.message}`, 'error');
    } finally {
      setIsStartingRecording(false);
    }
  };

  // Stop recording, run AI analysis, and navigate to analysis page
  const stopRecording = async () => {
    if (!isRecording) return;

    showStatus('Stopping recording...', 'info');

    try {
      // 1. Stop recording
      const stopResult = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });

      setIsRecording(false);
      setIsRecordingSandboxOpen(false);

      const sessionId = currentSessionId;
      const operationsCount = stopResult.operations_count || recordingSteps.length;

      if (!sessionId) {
        showStatus('Recording stopped', 'success');
        return;
      }

      // 2. Run AI analysis
      showStatus('Analyzing recording with AI...', 'info');

      try {
        const analysisResult = await api.callAppBackend(`/api/v1/recordings/${sessionId}/analyze`, {
          method: "POST",
          body: JSON.stringify({
            user_id: userId
          })
        });

        showStatus('Analysis complete!', 'success');

        // 3. Navigate to analysis page with results
        onNavigate('recording-analysis', {
          sessionId: sessionId,
          operationsCount: operationsCount,
          name: `Recording ${new Date().toLocaleDateString()}`,
          detectedPatterns: analysisResult.detected_patterns || {},
          taskDescription: analysisResult.task_description || '',
          userQuery: analysisResult.user_query || ''
        });

      } catch (analysisError) {
        console.error("Analysis error:", analysisError);
        // Still navigate even if analysis fails
        showStatus('Recording saved. Analysis failed, please try manually.', 'warning');
        onNavigate('recording-analysis', {
          sessionId: sessionId,
          operationsCount: operationsCount,
          name: `Recording ${new Date().toLocaleDateString()}`
        });
      }

    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`Failed to stop recording: ${error.message}`, 'error');
      setIsRecording(false);
    }
  };

  // Handle voice input
  const handleVoiceInput = () => {
    setIsVoiceActive(prev => !prev);
    if (!isVoiceActive) {
      showStatus('Voice input started...', 'info');
      // TODO: Implement voice recognition
    } else {
      showStatus('Voice input stopped', 'info');
    }
  };

  // Render instructions box (shown when no messages)
  const renderInstructions = () => (
    <div className="instructions-box">
      <h3 className="instructions-title">How can Ami help you?</h3>

      <div className="instruction-item">
        <div className="instruction-icon">
          <Icon name="sparkle" size={14} />
        </div>
        <div className="instruction-text">
          <div className="instruction-action">Describe your task</div>
          <div className="instruction-desc">Tell Ami what you want to automate in natural language</div>
        </div>
      </div>

      <div className="instruction-item">
        <div className="instruction-icon">
          <Icon name="record" size={14} />
        </div>
        <div className="instruction-text">
          <div className="instruction-action">Record your actions</div>
          <div className="instruction-desc">Show Ami how to do it by recording your workflow</div>
        </div>
      </div>

      <div className="instruction-item">
        <div className="instruction-icon">
          <Icon name="play" size={14} />
        </div>
        <div className="instruction-text">
          <div className="instruction-action">Run automations</div>
          <div className="instruction-desc">Execute your saved workflows with one click</div>
        </div>
      </div>
    </div>
  );

  // Render message bubble
  const renderMessage = (message) => (
    <div key={message.id} className={`message ${message.type}`}>
      <div className="message-bubble">
        {message.content}
      </div>
      <div className="message-time">
        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );

  // Render recording panel (only shown when recording)
  const renderRecordingPanel = () => {
    if (!isRecording) return null;

    return (
      <div className="recording-panel active">
        <div className="recording-panel-header">
          <div className="recording-status">
            <div className="status-indicator"></div>
            <span className="status-text">Recording... ({recordingSteps.length} actions)</span>
          </div>
          <button className="stop-recording-btn" onClick={stopRecording}>
            <Icon name="stop" size={16} />
            Stop
          </button>
        </div>

        {recordingSteps.length > 0 && (
          <div className="recording-steps-mini">
            {recordingSteps.slice(-3).map((step, index) => (
              <div key={index} className="step-mini">
                <span className="step-dot"></span>
                <span className="step-text">{step.action}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="home-page-v2">
      {/* Header */}
      <div className="home-header">
        <h1 className="home-title">Ami</h1>
        <div className="header-actions">
          <button
            className="header-btn"
            onClick={() => onNavigate('settings')}
            title="Settings"
          >
            <Icon name="settings" size={20} />
          </button>
        </div>
      </div>

      {/* Welcome Card */}
      <div className="welcome-card">
        <div className="welcome-content">
          <div className="assistant-avatar">
            <Icon name="robot" size={22} />
          </div>
          <div className="welcome-text">
            <h2>Hi{session?.username ? `, ${session.username}` : ''}!</h2>
            <p>I'm Ami, your automation assistant</p>
          </div>
        </div>
      </div>

      {/* Recording Panel (shown when recording) */}
      {renderRecordingPanel()}

      {/* Chat Container */}
      <div className="chat-container">
        <div
          className="chat-history full-width"
          ref={chatHistoryRef}
        >
          {messages.length === 0 ? (
            renderInstructions()
          ) : (
            messages.map(renderMessage)
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="input-area">
        <div className="input-wrapper">
          <input
            ref={inputRef}
            type="text"
            className="text-input"
            placeholder="Describe what you want to automate..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
          />
          <div className="action-buttons">
            <button
              className={`action-btn voice-btn ${isVoiceActive ? 'active' : ''}`}
              onClick={handleVoiceInput}
              title="Voice Input"
            >
              <Icon name="mic" size={20} />
            </button>
            <button
              className={`action-btn record-icon-btn ${isRecording ? 'active' : ''}`}
              onClick={toggleRecording}
              disabled={isStartingRecording}
              title={isRecording ? "Stop Recording" : "Start Recording"}
            >
              <Icon name={isRecording ? "stop" : "record"} size={20} />
            </button>
            <button
              className="action-btn send-btn"
              onClick={handleSubmit}
              disabled={!inputText.trim()}
              title="Send"
            >
              <Icon name="send" size={20} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
