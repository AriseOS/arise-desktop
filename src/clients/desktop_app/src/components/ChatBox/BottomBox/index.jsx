/**
 * BottomBox Component
 *
 * Multi-state input component for the chat interface.
 * Manages different states: input, splitting, confirm, running, finished.
 *
 * Features:
 * - State-based UI changes (background color, header variants)
 * - Queued messages display
 * - File attachments
 * - Action buttons (stop, replay, pause/resume)
 * - Token count and task time display
 *
 * Ported from Eigent's BottomBox component.
 *
 * States:
 * - input: Default state, user can type and send messages
 * - splitting: System is splitting tasks, shows loading indicator
 * - confirm: Waiting for user confirmation, shows Start Task button
 * - running: Task is running, shows stop and pause buttons
 * - finished: Task completed, shows replay button
 */

import React from 'react';
import InputBox from './InputBox';
import { BoxHeaderSplitting, BoxHeaderConfirm } from './BoxHeader';
import BoxAction from './BoxAction';
import QueuedBox from './QueuedBox';

/**
 * BottomBox State Types
 * @typedef {'input'|'splitting'|'confirm'|'running'|'finished'} BottomBoxState
 */

/**
 * BottomBox Component
 *
 * @param {Object} props
 * @param {BottomBoxState} props.state - Current state
 * @param {Array} props.queuedMessages - Queued messages
 * @param {function} props.onRemoveQueuedMessage - Remove queued message callback
 * @param {string} props.subtitle - Subtitle for confirm state
 * @param {function} props.onStartTask - Start task callback
 * @param {function} props.onEdit - Edit/back callback
 * @param {number} props.tokens - Token count
 * @param {string} props.taskTime - Task time display
 * @param {'running'|'finished'|'pending'|'pause'} props.taskStatus - Task status
 * @param {function} props.onReplay - Replay callback
 * @param {boolean} props.replayDisabled - Disable replay button
 * @param {boolean} props.replayLoading - Replay loading state
 * @param {function} props.onPauseResume - Pause/resume callback
 * @param {boolean} props.pauseResumeLoading - Pause/resume loading state
 * @param {function} props.onStop - Stop task callback
 * @param {boolean} props.stopLoading - Stop loading state
 * @param {Object} props.inputProps - Props for InputBox component
 * @param {boolean} props.loading - General loading state
 * @param {boolean} props.enableQueuedBox - Enable queued box display
 */
function BottomBox({
  state = 'input',
  queuedMessages = [],
  onRemoveQueuedMessage,
  subtitle = '',
  onStartTask,
  onEdit,
  tokens = 0,
  taskTime = '',
  taskStatus = 'pending',
  onReplay,
  replayDisabled = false,
  replayLoading = false,
  onPauseResume,
  pauseResumeLoading = false,
  onStop,
  stopLoading = false,
  inputProps = {},
  loading = false,
  enableQueuedBox = false,
  className = '',
}) {
  // Determine background class based on state
  let stateClass = 'state-input';
  if (state === 'splitting') stateClass = 'state-splitting';
  else if (state === 'confirm') stateClass = 'state-confirm';
  else if (state === 'running') stateClass = 'state-running';
  else if (state === 'finished') stateClass = 'state-finished';

  return (
    <div className={`bottom-box ${className}`}>
      {/* QueuedBox overlay */}
      {enableQueuedBox && queuedMessages.length > 0 && (
        <div className="bottom-box-queued">
          <QueuedBox
            queuedMessages={queuedMessages}
            onRemoveQueuedMessage={onRemoveQueuedMessage}
          />
        </div>
      )}

      {/* Main Box */}
      <div className={`bottom-box-main ${stateClass}`}>
        {/* BoxHeader variants */}
        {state === 'splitting' && (
          <BoxHeaderSplitting />
        )}

        {state === 'confirm' && (
          <BoxHeaderConfirm
            subtitle={subtitle}
            onStartTask={onStartTask}
            onEdit={onEdit}
          />
        )}

        {/* InputBox (always visible) */}
        <InputBox
          {...inputProps}
          disabled={inputProps.disabled || loading || state === 'splitting'}
        />

        {/* BoxAction (visible after initial input, when task has started) */}
        {state !== 'input' && (
          <BoxAction
            tokens={tokens}
            taskTime={taskTime}
            status={taskStatus}
            disabled={replayDisabled}
            loading={replayLoading}
            onReplay={onReplay}
            onPauseResume={onPauseResume}
            pauseResumeLoading={pauseResumeLoading}
            onStop={onStop}
            stopLoading={stopLoading}
          />
        )}
      </div>
    </div>
  );
}

// Export types and sub-components
export { default as InputBox } from './InputBox';
export { BoxHeaderSplitting, BoxHeaderConfirm } from './BoxHeader';
export { default as BoxAction } from './BoxAction';
export { default as QueuedBox } from './QueuedBox';

export default BottomBox;
