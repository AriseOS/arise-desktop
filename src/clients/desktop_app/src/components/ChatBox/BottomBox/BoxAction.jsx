/**
 * BoxAction Component
 *
 * Action bar displayed at the bottom of BottomBox.
 * Shows token count, task time, and action buttons (stop, pause/resume, replay).
 *
 * Ported from Eigent's BoxAction component.
 */

import React from 'react';
import Icon from '../../Icons';

/**
 * BoxAction Component
 *
 * @param {Object} props
 * @param {number} props.tokens - Token count to display
 * @param {string} props.taskTime - Task time display (e.g., "2m 30s")
 * @param {'running'|'finished'|'pending'|'pause'} props.status - Task status
 * @param {boolean} props.disabled - Whether replay is disabled
 * @param {boolean} props.loading - Loading state for replay action
 * @param {function} props.onReplay - Callback when replay button is clicked
 * @param {function} props.onPauseResume - Callback for pause/resume
 * @param {boolean} props.pauseResumeLoading - Loading state for pause/resume
 * @param {function} props.onStop - Callback when stop button is clicked
 * @param {boolean} props.stopLoading - Loading state for stop action
 */
function BoxAction({
  tokens = 0,
  taskTime = '',
  status = 'pending',
  disabled = false,
  loading = false,
  onReplay,
  onPauseResume,
  pauseResumeLoading = false,
  onStop,
  stopLoading = false,
  className = '',
}) {
  // Determine if stop/pause/resume should be shown
  const showStopButton = status === 'running' || status === 'pause';
  const showPauseResume = status === 'running' || status === 'pause';
  const isPaused = status === 'pause';

  return (
    <div className={`box-action ${className}`}>
      {/* Left: Token Count */}
      <div className="box-action-left">
        <span className="token-count">
          # Token {tokens.toLocaleString()}
        </span>
        {taskTime && (
          <span className="task-time">
            <Icon name="clock" size={12} />
            {taskTime}
          </span>
        )}
      </div>

      {/* Right: Action Buttons */}
      <div className="box-action-right">
        {/* Stop Button */}
        {showStopButton && onStop && (
          <button
            className="box-action-btn stop"
            onClick={onStop}
            disabled={stopLoading}
            title="Stop task"
          >
            {stopLoading ? (
              <span className="spinner small"></span>
            ) : (
              <>
                <Icon name="x" size={14} />
                <span>Stop</span>
              </>
            )}
          </button>
        )}

        {/* Pause/Resume Button */}
        {showPauseResume && onPauseResume && (
          <button
            className={`box-action-btn pause-resume ${isPaused ? 'paused' : ''}`}
            onClick={onPauseResume}
            disabled={pauseResumeLoading}
            title={isPaused ? 'Resume' : 'Pause'}
          >
            {pauseResumeLoading ? (
              <span className="spinner small"></span>
            ) : isPaused ? (
              <>
                <Icon name="play" size={14} />
                <span>Resume</span>
              </>
            ) : (
              <>
                <Icon name="square" size={14} />
                <span>Pause</span>
              </>
            )}
          </button>
        )}

        {/* Replay Button */}
        <button
          className="box-action-btn replay"
          onClick={onReplay}
          disabled={disabled || loading}
          title="Replay task"
        >
          {loading ? (
            <span className="spinner small"></span>
          ) : (
            <>
              <Icon name="refresh" size={14} />
              <span>Replay</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

export default BoxAction;
