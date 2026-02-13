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
import { WorkforceStatusPanel } from '../Workforce';
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
 *
 * State priority (Eigent pattern):
 * 1. splitting - Task is being decomposed (streamingDecomposeText active)
 * 2. running - Task is executing
 * 3. waiting/hasWaitConfirm - Waiting for user input after simple answer
 * 4. finished - Task completed, can continue conversation
 * 5. input - Default state
 */
function getBottomBoxState(task) {
  if (!task) return 'input';

  // If decomposing tasks (streaming text active) - highest priority
  if (task.streamingDecomposeText || task.status === 'decomposing') {
    return 'splitting';
  }

  // Task status mapping
  switch (task.status) {
    case 'failed':
    case 'cancelled':
      // Failed/cancelled tasks show finished state (no input allowed)
      return 'finished';
    case 'running':
      return 'running';
    case 'pause':
      return 'running'; // Keep running UI, just change pause button state
    case 'waiting':
      // Eigent pattern: waiting for user input after wait_confirm
      return 'input';
    case 'finished':
    case 'completed':
      // Eigent pattern: finished tasks can still accept input for multi-turn
      // Check if task was manually stopped (no natural 'end' message)
      const wasTaskStopped = !task.messages?.some(m => m.step === 'end');
      if (wasTaskStopped) {
        return 'finished';  // Manually stopped, no more input
      }
      // Natural completion - allow continued conversation
      return 'input';
  }

  // Eigent pattern: If hasWaitConfirm is true, allow input for multi-turn
  if (task.hasWaitConfirm) {
    return 'input';
  }

  return 'input';
}

/**
 * ChatBox Component
 *
 * @param {Object} props
 * @param {Array} props.messages - Chat messages
 * @param {Array} props.notices - Notice cards
 * @param {Object} props.task - Current task state from agentStore
 * @param {function} props.onSendMessage - Send message callback
 * @param {string} props.inputValue - Current input value
 * @param {function} props.onInputChange - Input change callback
 * @param {Array} props.files - File attachments
 * @param {function} props.onFilesChange - Files change callback
 * @param {function} props.onReplay - Replay task callback
 * @param {function} props.onPauseResume - Pause/resume callback
 * @param {function} props.onStop - Stop task callback
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
  onReplay,
  onPauseResume,
  onStop,
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
  const [stopLoading, setStopLoading] = useState(false);
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

  // Handle stop task
  const handleStop = useCallback(async () => {
    if (!onStop) return;
    setStopLoading(true);
    try {
      await onStop();
    } finally {
      setStopLoading(false);
    }
  }, [onStop]);

  // Calculate subtitle for confirm state
  const confirmSubtitle = useMemo(() => {
    if (!task?.taskInfo?.length) return '';
    return `${task.taskInfo.length} subtask${task.taskInfo.length > 1 ? 's' : ''} ready`;
  }, [task?.taskInfo]);

  // Determine if input should be disabled
  // Eigent pattern: Allow input during 'running' state for multi-turn conversation
  // Only disable during 'splitting' (task decomposition in progress)
  const isInputDisabled = disabled || isLoading ||
    bottomBoxState === 'splitting';

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
      {/* Workforce Status Panel - shows when workforce is active */}
      <WorkforceStatusPanel
        workforce={task?.workforce}
        subtaskAssignments={task?.subtaskAssignments}
      />

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
        onStop={handleStop}
        stopLoading={stopLoading}
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
