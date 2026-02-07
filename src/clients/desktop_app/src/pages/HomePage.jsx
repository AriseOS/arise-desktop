import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import { useAgentStore } from '../store';
import FileAttachmentCard from '../components/ChatBox/MessageItem/FileAttachmentCard';
import '../styles/HomePage.css';

/**
 * HomePage - Main dashboard with chat-style interface
 *
 * Features:
 * - Welcome card with Ami branding
 * - Chat history area with real-time agent reports
 * - Bottom input area with text/voice/record actions
 * - Optional recording sandbox panel
 * - Inline task execution (no page navigation)
 *
 * Message Display Architecture:
 * - sessionMessages: Historical messages loaded from session (JSONL)
 * - taskMessages: Current task's messages (for active execution)
 * - Display = sessionMessages + taskMessages (continuous conversation)
 * - Each new task has its own workspace, but messages appear continuous
 */
function HomePage({ session, onNavigate, showStatus, version }) {
  const { t } = useTranslation();

  // Agent Store
  const {
    tasks,
    activeTaskId,
    createTask,
    startTask,
    sendUserMessage,
  } = useAgentStore();

  // Get active task state
  const activeTask = activeTaskId ? tasks[activeTaskId] : null;
  const taskStatus = activeTask?.status || 'idle';
  const taskMessages = activeTask?.messages || [];

  // Local State
  const [inputText, setInputText] = useState('');
  const [isRecordingSandboxOpen, setIsRecordingSandboxOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [recordingSteps, setRecordingSteps] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [isStartingRecording, setIsStartingRecording] = useState(false);

  // Session messages (historical, loaded from backend)
  const [sessionMessages, setSessionMessages] = useState([]);
  // Track which message IDs we've already shown (to avoid duplicates)
  const [shownMessageIds, setShownMessageIds] = useState(new Set());

  const userId = session?.username;

  const chatHistoryRef = useRef(null);
  const inputRef = useRef(null);

  // Combine session messages with current task messages for display
  // Session messages are history, task messages are current execution
  const displayMessages = React.useMemo(() => {
    // Start with session messages
    const messages = [...sessionMessages];

    // Add task messages that aren't already in session (new messages from current execution)
    taskMessages.forEach(msg => {
      if (!shownMessageIds.has(msg.id)) {
        messages.push(msg);
      }
    });

    return messages;
  }, [sessionMessages, taskMessages, shownMessageIds]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [displayMessages]);

  // Load session messages on app start/reload
  useEffect(() => {
    const loadSession = async () => {
      try {
        // Get current session (handles timeout automatically)
        const result = await api.getSession(100);

        if (result.messages && result.messages.length > 0) {
          const messages = result.messages.map(msg => ({
            id: msg.id,
            role: msg.role === 'assistant' ? 'assistant' : msg.role,
            content: msg.content,
            timestamp: msg.timestamp,
            attachments: msg.attachments || [],
            isContext: msg.is_context,
          }));

          setSessionMessages(messages);
          setShownMessageIds(new Set(messages.map(m => m.id)));

          console.log(`[HomePage] Loaded ${messages.length} messages from session`);
        }
      } catch (error) {
        console.warn('[HomePage] Failed to load session:', error.message);
      }
    };

    loadSession();
  }, []);

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
  const handleSubmit = async () => {
    if (!inputText.trim()) return;

    const text = inputText.trim();
    setInputText('');

    // Check if we should continue conversation or start new task
    const shouldContinue = activeTask && (
      taskStatus === 'running' ||
      taskStatus === 'waiting' ||
      taskStatus === 'completed' ||
      activeTask.hasWaitConfirm
    );

    if (shouldContinue) {
      // Continue conversation with existing task
      const result = await sendUserMessage(activeTaskId, text);
      if (!result.success) {
        showStatus(`Failed to send message: ${result.error}`, 'error');
      }
    } else {
      // Start new task (each new request gets its own workspace)
      const newTaskId = createTask(text);
      const success = await startTask(newTaskId, showStatus);
      if (!success) {
        showStatus('Failed to start task', 'error');
      }
    }
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
  const renderMessage = (message, index) => {
    const isUser = message.role === 'user';
    const isAgent = message.role === 'agent';
    const isAssistant = message.role === 'assistant';

    // Determine message type for styling
    let messageType = 'system';
    if (isUser) messageType = 'user';
    else if (isAgent || isAssistant) messageType = 'agent';

    // Get report type for agent messages
    const reportType = message.reportType || 'info';

    // Format timestamp
    const timestamp = message.timestamp
      ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';

    // DS-11: Get file attachments
    const attachments = message.attachments || message.attaches || [];

    return (
      <div key={message.id || index} className={`message ${messageType} ${isAgent ? `report-${reportType}` : ''}`}>
        <div className="message-bubble markdown-content">
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          )}
        </div>
        {/* DS-11: Render file attachments */}
        {attachments.length > 0 && (
          <div className="message-attachments">
            {attachments.map((file, idx) => (
              file.file_path ? (
                <FileAttachmentCard key={`file-${idx}`} file={file} />
              ) : (
                <div key={`attach-${idx}`} className="attachment-item legacy">
                  <Icon name="file" size={14} />
                  <span>{file.fileName || file.name}</span>
                </div>
              )
            ))}
          </div>
        )}
        {timestamp && (
          <div className="message-time">
            {timestamp}
          </div>
        )}
      </div>
    );
  };

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

  // Render task status indicator
  const renderTaskStatus = () => {
    if (!activeTask || taskStatus === 'idle') return null;

    return (
      <div className={`task-status-indicator ${taskStatus}`}>
        {taskStatus === 'running' && (
          <>
            <div className="status-spinner"></div>
            <span>Processing...</span>
          </>
        )}
        {taskStatus === 'waiting' && (
          <>
            <Icon name="check" size={14} />
            <span>Ready for input</span>
          </>
        )}
        {taskStatus === 'completed' && (
          <>
            <Icon name="check" size={14} />
            <span>Completed</span>
          </>
        )}
        {taskStatus === 'failed' && (
          <>
            <Icon name="alert" size={14} />
            <span>Failed</span>
          </>
        )}
      </div>
    );
  };

  // Input is always enabled - messages are queued when agent is running
  // This follows the "queue instead of block" pattern
  const isInputDisabled = false;

  return (
    <div className="home-page-v2">
      {/* Header */}
      <div className="home-header">
        <h1 className="home-title">Ami</h1>
        <div className="header-actions">
          {renderTaskStatus()}
          <button
            className="header-btn"
            onClick={() => onNavigate('settings')}
            title="Settings"
          >
            <Icon name="settings" size={20} />
          </button>
        </div>
      </div>

      {/* Welcome Card - Hide when there are messages */}
      {displayMessages.length === 0 && (
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
      )}

      {/* Recording Panel (shown when recording) */}
      {renderRecordingPanel()}

      {/* Chat Container */}
      <div className="chat-container">
        <div
          className="chat-history full-width"
          ref={chatHistoryRef}
        >
          {displayMessages.length === 0 ? (
            renderInstructions()
          ) : (
            displayMessages.map(renderMessage)
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
            placeholder={taskStatus === 'running' ? "Type here (queued while agent works)..." : "Describe what you want to automate..."}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isInputDisabled}
          />
          <div className="action-buttons">
            <button
              className={`action-btn voice-btn ${isVoiceActive ? 'active' : ''}`}
              onClick={handleVoiceInput}
              title="Voice Input"
              disabled={isInputDisabled}
            >
              <Icon name="mic" size={20} />
            </button>
            <button
              className={`action-btn record-icon-btn ${isRecording ? 'active' : ''}`}
              onClick={toggleRecording}
              disabled={isStartingRecording || isInputDisabled}
              title={isRecording ? "Stop Recording" : "Start Recording"}
            >
              <Icon name={isRecording ? "stop" : "record"} size={20} />
            </button>
            <button
              className="action-btn send-btn"
              onClick={handleSubmit}
              disabled={!inputText.trim() || isInputDisabled}
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
