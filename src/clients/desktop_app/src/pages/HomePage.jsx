import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import Icon from '../components/Icons';
import { getAgentConfig } from '../components/AgentNode/AgentNode';

// Allow <details>/<summary> and list tags through sanitizer, block dangerous tags
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames || []),
    'details', 'summary',
  ],
};
import { api } from '../utils/api';
import { useAgentStore } from '../store';
import FileAttachmentCard from '../components/ChatBox/MessageItem/FileAttachmentCard';
import '../styles/HomePage.css';

/**
 * Format a date for display as a divider label.
 * Returns "Today", "Yesterday", or a locale date string.
 */
function formatDateDivider(date) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffMs = today - msgDay;
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

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
function HomePage({ session, onNavigate, showStatus, version, initialMessage }) {
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
  const [recordingWebviewId, setRecordingWebviewId] = useState(null);
  const [isStartingRecording, setIsStartingRecording] = useState(false);

  // Session messages (historical, loaded from backend)
  const [sessionMessages, setSessionMessages] = useState([]);
  // Track which message IDs we've already shown (to avoid duplicates)
  const [shownMessageIds, setShownMessageIds] = useState(new Set());

  // Infinite scroll history state
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const [oldestTimestamp, setOldestTimestamp] = useState(null);

  const userId = session?.username;

  const chatHistoryRef = useRef(null);
  const inputRef = useRef(null);
  const sentinelRef = useRef(null);
  const isNearBottomRef = useRef(true);

  // Combine session messages with current task messages for display
  // Session messages are history, task messages are current execution
  const displayMessages = React.useMemo(() => {
    // Start with session messages
    const messages = [...sessionMessages];

    // Add task messages that aren't already in session (ID-based dedup only)
    // NOTE: Do NOT use content-based dedup — short messages like "hi", "ok"
    // would be incorrectly filtered when user sends the same text again.
    taskMessages.forEach(msg => {
      if (shownMessageIds.has(msg.id)) return;
      messages.push(msg);
    });

    // Sort by timestamp to prevent ordering issues when mixing session + task messages
    messages.sort((a, b) => {
      const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return ta - tb;
    });

    return messages;
  }, [sessionMessages, taskMessages, shownMessageIds]);

  // Track whether user is near the bottom of chat
  useEffect(() => {
    const el = chatHistoryRef.current;
    if (!el) return;

    const handleScroll = () => {
      const threshold = 100;
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };

    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  // Scroll to bottom when new messages arrive (only if user is near bottom)
  useEffect(() => {
    if (chatHistoryRef.current && isNearBottomRef.current) {
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
            reportType: msg.metadata?.reportType,
            agentType: msg.metadata?.agentType,
            executorId: msg.metadata?.executorId,
            taskLabel: msg.metadata?.taskLabel,
          }));

          setSessionMessages(messages);
          setShownMessageIds(new Set(messages.map(m => m.id)));

          // Record oldest timestamp for history pagination cursor
          const oldest = messages.reduce((min, m) =>
            !min || (m.timestamp && m.timestamp < min) ? m.timestamp : min
          , null);
          setOldestTimestamp(oldest);

          console.log(`[HomePage] Loaded ${messages.length} messages from session`);
        } else {
          // No messages in current session — there may still be older sessions
          setOldestTimestamp(new Date().toISOString());
        }
      } catch (error) {
        console.warn('[HomePage] Failed to load session:', error.message);
      }
    };

    loadSession();

    // Scroll to bottom on initial load
    setTimeout(() => {
      if (chatHistoryRef.current) {
        chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
      }
    }, 100);
  }, []);

  // Guard ref to prevent concurrent history loads (avoids stale closure issues)
  const isLoadingHistoryRef = useRef(false);

  // Load more history when user scrolls to top
  const loadMoreHistory = useCallback(async () => {
    if (isLoadingHistoryRef.current || !hasMoreHistory || !oldestTimestamp) return;

    isLoadingHistoryRef.current = true;
    setIsLoadingHistory(true);
    try {
      const result = await api.getSessionHistory(oldestTimestamp, 30);

      if (result.messages && result.messages.length > 0) {
        const newMessages = result.messages.map(msg => ({
          id: msg.id,
          role: msg.role === 'assistant' ? 'assistant' : msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
          attachments: msg.attachments || [],
          isContext: msg.is_context,
          reportType: msg.metadata?.reportType,
          agentType: msg.metadata?.agentType,
          executorId: msg.metadata?.executorId,
          taskLabel: msg.metadata?.taskLabel,
        }));

        // Preserve scroll position: record scrollHeight before prepend
        const el = chatHistoryRef.current;
        const prevScrollHeight = el ? el.scrollHeight : 0;

        setSessionMessages(prev => {
          // Dedup by id
          const existingIds = new Set(prev.map(m => m.id));
          const unique = newMessages.filter(m => !existingIds.has(m.id));
          return [...unique, ...prev];
        });
        setShownMessageIds(prev => {
          const next = new Set(prev);
          newMessages.forEach(m => next.add(m.id));
          return next;
        });

        // Restore scroll position after DOM update
        // Double rAF ensures React has flushed the DOM changes
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (el) {
              const newScrollHeight = el.scrollHeight;
              el.scrollTop += newScrollHeight - prevScrollHeight;
            }
          });
        });

        setOldestTimestamp(result.oldest_timestamp);
        setHasMoreHistory(result.has_more);

        console.log(`[HomePage] Loaded ${newMessages.length} history messages, has_more=${result.has_more}`);
      } else {
        setHasMoreHistory(false);
      }
    } catch (error) {
      console.warn('[HomePage] Failed to load history:', error.message);
    } finally {
      isLoadingHistoryRef.current = false;
      setIsLoadingHistory(false);
    }
  }, [hasMoreHistory, oldestTimestamp]);

  // IntersectionObserver to trigger loading when sentinel is visible
  useEffect(() => {
    const sentinel = sentinelRef.current;
    const container = chatHistoryRef.current;
    if (!sentinel || !container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          loadMoreHistory();
        }
      },
      {
        root: container,
        rootMargin: '100px 0px 0px 0px',
        threshold: 0,
      }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMoreHistory]);

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

  // Auto-submit initial message (e.g. from Explore page "Run" button)
  useEffect(() => {
    if (!initialMessage) return;

    setInputText(initialMessage);
    // Use a short delay to ensure state is set before submitting
    const timer = setTimeout(() => {
      const text = initialMessage.trim();
      if (!text) return;
      setInputText('');
      const newTaskId = createTask(text);
      startTask(newTaskId, showStatus);
    }, 300);

    return () => clearTimeout(timer);
  }, [initialMessage]);

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

  // Start recording - call API then navigate to recording browser page
  const startRecording = async () => {
    if (isStartingRecording || isRecording) return;

    setIsStartingRecording(true);
    showStatus('Starting recording...', 'info');

    try {
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

      // Navigate to full-page recording browser
      onNavigate('browser', {
        mode: 'recording',
        sessionId: result.session_id,
        viewId: result.webview_id,
        source: 'home_page',
      });

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

    // Hide webview before stopping
    if (recordingWebviewId) {
      window.electronAPI?.hideWebview(recordingWebviewId);
      setRecordingWebviewId(null);
    }

    try {
      // 1. Stop recording
      const stopResult = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });

      setIsRecording(false);
      setIsRecordingSandboxOpen(false);

      const sessionId = currentSessionId;

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
          name: analysisResult.name || `Recording ${new Date().toLocaleDateString()}`,
          taskDescription: analysisResult.task_description || ''
        });

      } catch (analysisError) {
        console.error("Analysis error:", analysisError);
        // Still navigate even if analysis fails
        showStatus('Recording saved. Analysis failed, please try manually.', 'warning');
        onNavigate('recording-analysis', {
          sessionId: sessionId,
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

    // Get agent config for avatar
    const agentConfig = (isAgent || isAssistant) ? getAgentConfig(message.agentType) : null;

    // Format timestamp
    const timestamp = message.timestamp
      ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';

    // DS-11: Get file attachments
    const attachments = message.attachments || message.attaches || [];

    if (isUser) {
      // User messages: simple right-aligned bubble, no avatar
      return (
        <div key={message.id || index} className="message user">
          <div className="message-bubble">
            {message.content}
          </div>
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
          {timestamp && <div className="message-time">{timestamp}</div>}
        </div>
      );
    }

    // Agent/assistant messages: avatar on left + bubble
    const subtaskTag = message.taskLabel;

    return (
      <div key={message.id || index} className={`message agent ${isAgent ? `report-${reportType}` : ''}`}>
        <div className="sender-name-line">
          <span className="sender-name">Ami</span>
          {subtaskTag && <span className="subtask-badge">{subtaskTag}</span>}
        </div>
        <div className="message-row">
          <div className="msg-avatar agent-avatar" style={agentConfig ? { background: agentConfig.bgColor, color: agentConfig.color } : undefined}>
            {agentConfig ? (
              <span className="avatar-emoji">{agentConfig.icon}</span>
            ) : (
              <Icon name="bot" size={14} />
            )}
          </div>
          <div className="message-body">
            <div className="message-bubble markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}>{message.content}</ReactMarkdown>
            </div>
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
            {timestamp && <div className="message-time">{timestamp}</div>}
          </div>
        </div>
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
            <>
              {/* Sentinel for infinite scroll trigger */}
              <div ref={sentinelRef} className="scroll-sentinel" />

              {/* Loading indicator */}
              {isLoadingHistory && (
                <div className="history-loading">
                  <div className="history-loading-spinner" />
                  <span>Loading earlier messages...</span>
                </div>
              )}

              {/* Beginning of history */}
              {!hasMoreHistory && displayMessages.length > 0 && (
                <div className="history-end">Beginning of conversation history</div>
              )}

              {/* Messages with date dividers and session boundaries */}
              {displayMessages.map((message, index) => {
                const dividers = [];
                const prevMsg = index > 0 ? displayMessages[index - 1] : null;

                // Date divider — when the calendar day changes
                if (message.timestamp) {
                  const msgDate = new Date(message.timestamp);
                  const prevDate = prevMsg?.timestamp ? new Date(prevMsg.timestamp) : null;

                  if (!prevDate || msgDate.toDateString() !== prevDate.toDateString()) {
                    dividers.push(
                      <div key={`date-${message.id || index}`} className="date-divider">
                        <span className="date-divider-label">{formatDateDivider(msgDate)}</span>
                      </div>
                    );
                  }
                }

                // Session boundary — detect via:
                // 1. context→non-context transition (current session's carry-over boundary)
                // 2. Time gap > 30 min between consecutive messages (session timeout gap)
                if (prevMsg) {
                  const isContextBoundary = prevMsg.isContext && !message.isContext;
                  let isTimeGap = false;
                  if (prevMsg.timestamp && message.timestamp) {
                    const gap = new Date(message.timestamp) - new Date(prevMsg.timestamp);
                    isTimeGap = gap > 30 * 60 * 1000; // 30 minutes
                  }

                  if (isContextBoundary || isTimeGap) {
                    dividers.push(
                      <div key={`session-${message.id || index}`} className="session-divider">
                        <span className="session-divider-label">New conversation</span>
                      </div>
                    );
                  }
                }

                return (
                  <React.Fragment key={message.id || index}>
                    {dividers}
                    {renderMessage(message, index)}
                  </React.Fragment>
                );
              })}
            </>
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
