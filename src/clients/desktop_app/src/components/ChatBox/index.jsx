/**
 * ChatBox Component
 *
 * Main chat interface component - displays ONLY conversation messages.
 * Following Eigent pattern: ChatBox = pure conversation, WorkspaceTabs = execution details.
 *
 * This component handles:
 * - User messages display
 * - Agent final responses (step: 'end' or regular replies)
 * - BottomBox state machine (input/splitting/confirm/running/finished)
 * - File attachments
 * - Task lifecycle control
 *
 * Execution details (thinking, toolkit events, browser view) are displayed
 * in WorkspaceTabs (AgentTab, BrowserTab, etc.), NOT here.
 *
 * Ported from Eigent's ChatBox component.
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
import MessageList from './MessageList';
import BottomBox from './BottomBox';
import './ChatBox.css';

/**
 * Calculate elapsed time display string
 */
function formatElapsedTime(elapsed, taskTime) {
  let totalMs = elapsed || 0;
  if (taskTime) {
    totalMs += Date.now() - taskTime;
  }

  const totalSeconds = Math.floor(totalMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

/**
 * Map task status to BottomBox state
 */
function getBottomBoxState(task) {
  if (!task) return 'input';

  // Task status mapping - check terminal states first
  switch (task.status) {
    case 'finished':
    case 'completed':
    case 'failed':
    case 'cancelled':
      return 'finished';
    case 'running':
      return 'running';
    case 'pause':
      return 'running'; // Keep running UI, just change pause button state
  }

  // If decomposing tasks
  if (task.streamingDecomposeText || task.status === 'decomposing') {
    return 'splitting';
  }

  // If waiting for confirmation (only in pending/waiting states)
  if (task.taskInfo?.length > 0 && task.status === 'waiting_confirmation') {
    return 'confirm';
  }

  return 'input';
}

/**
 * ChatBox Component
 *
 * @param {Object} props
 * @param {Array} props.messages - Chat messages
 * @param {Array} props.notices - Notice cards
 * @param {Object} props.task - Current task state from chatStore
 * @param {function} props.onSendMessage - Send message callback
 * @param {string} props.inputValue - Current input value
 * @param {function} props.onInputChange - Input change callback
 * @param {Array} props.files - File attachments
 * @param {function} props.onFilesChange - Files change callback
 * @param {function} props.onStartTask - Start task callback
 * @param {function} props.onEditTask - Edit/back callback
 * @param {function} props.onReplay - Replay task callback
 * @param {function} props.onPauseResume - Pause/resume callback
 * @param {Array} props.queuedMessages - Queued messages
 * @param {function} props.onRemoveQueuedMessage - Remove queued message callback
 * @param {boolean} props.isLoading - General loading state
 * @param {boolean} props.disabled - Disable input
 * @param {string} props.placeholder - Input placeholder
 * @param {boolean} props.showWelcome - Show welcome state
 */
function ChatBox({
  messages = [],
  notices = [],
  task = null,
  onSendMessage,
  inputValue = '',
  onInputChange,
  files = [],
  onFilesChange,
  onStartTask,
  onEditTask,
  onReplay,
  onPauseResume,
  queuedMessages = [],
  onRemoveQueuedMessage,
  isLoading = false,
  disabled = false,
  placeholder = 'Ask Ami to automate your tasks',
  showWelcome = false,
}) {
  // Local state for UI
  const [replayLoading, setReplayLoading] = useState(false);
  const [pauseResumeLoading, setPauseResumeLoading] = useState(false);
  const [taskTimeDisplay, setTaskTimeDisplay] = useState('');

  // Calculate BottomBox state from task
  const bottomBoxState = useMemo(() => getBottomBoxState(task), [task]);

  // Task status for action bar
  const taskStatus = task?.status || 'pending';

  // Update task time display
  useEffect(() => {
    if (!task || (task.status !== 'running' && task.status !== 'pause')) {
      if (task?.elapsed) {
        setTaskTimeDisplay(formatElapsedTime(task.elapsed, null));
      }
      return;
    }

    const interval = setInterval(() => {
      setTaskTimeDisplay(formatElapsedTime(task.elapsed, task.taskTime));
    }, 1000);

    return () => clearInterval(interval);
  }, [task?.status, task?.elapsed, task?.taskTime]);

  // Handle send
  const handleSend = useCallback(() => {
    if (inputValue.trim() && !disabled && onSendMessage) {
      onSendMessage(inputValue.trim());
    }
  }, [inputValue, disabled, onSendMessage]);

  // Handle replay
  const handleReplay = useCallback(async () => {
    if (!onReplay) return;
    setReplayLoading(true);
    try {
      await onReplay();
    } finally {
      setReplayLoading(false);
    }
  }, [onReplay]);

  // Handle pause/resume
  const handlePauseResume = useCallback(async () => {
    if (!onPauseResume) return;
    setPauseResumeLoading(true);
    try {
      await onPauseResume();
    } finally {
      setPauseResumeLoading(false);
    }
  }, [onPauseResume]);

  // Calculate subtitle for confirm state
  const confirmSubtitle = useMemo(() => {
    if (!task?.taskInfo?.length) return '';
    return `${task.taskInfo.length} subtask${task.taskInfo.length > 1 ? 's' : ''} ready`;
  }, [task?.taskInfo]);

  // Determine if input should be disabled
  const isInputDisabled = disabled || isLoading ||
    bottomBoxState === 'splitting' ||
    bottomBoxState === 'running';

  // Calculate token count
  const tokens = task?.tokens || 0;

  // Welcome state
  if (showWelcome && messages.length === 0) {
    return (
      <div className="chat-box chat-box-welcome">
        <div className="welcome-content">
          <h2 className="welcome-title">Welcome to Ami</h2>
          <p className="welcome-subtitle">How can I help you today?</p>
        </div>

        <BottomBox
          state="input"
          inputProps={{
            value: inputValue,
            onChange: onInputChange,
            onSend: handleSend,
            files: files,
            onFilesChange: onFilesChange,
            placeholder: placeholder,
            disabled: isInputDisabled,
            allowDragDrop: true,
          }}
          loading={isLoading}
        />
      </div>
    );
  }

  return (
    <div className="chat-box">
      {/* Message List with inline TaskCard (Eigent pattern) */}
      <MessageList
        messages={messages}
        notices={notices}
        task={task}
        onStartTask={onStartTask}
        onEditTask={onEditTask}
      />

      {/* BottomBox */}
      <BottomBox
        state={bottomBoxState}
        queuedMessages={queuedMessages}
        onRemoveQueuedMessage={onRemoveQueuedMessage}
        subtitle={confirmSubtitle}
        onStartTask={onStartTask}
        onEdit={onEditTask}
        tokens={tokens}
        taskTime={taskTimeDisplay}
        taskStatus={taskStatus}
        onReplay={handleReplay}
        replayDisabled={bottomBoxState === 'running'}
        replayLoading={replayLoading}
        onPauseResume={handlePauseResume}
        pauseResumeLoading={pauseResumeLoading}
        inputProps={{
          value: inputValue,
          onChange: onInputChange,
          onSend: handleSend,
          files: files,
          onFilesChange: onFilesChange,
          placeholder: placeholder,
          disabled: isInputDisabled,
          allowDragDrop: true,
        }}
        loading={isLoading}
        enableQueuedBox={queuedMessages.length > 0}
      />
    </div>
  );
}

export default ChatBox;

// Re-export sub-components
export { default as MessageList } from './MessageList';
export { default as BottomBox } from './BottomBox';
export { InputBox, BoxAction, QueuedBox } from './BottomBox';
