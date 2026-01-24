/**
 * BoxHeader Components
 *
 * Header variants for BottomBox component:
 * - BoxHeaderSplitting: Shows when task is being split
 * - BoxHeaderConfirm: Shows when waiting for user confirmation
 *
 * Ported from Eigent's BoxHeader component.
 * Enhanced with 30-second auto-confirm countdown display.
 */

import React, { useState, useEffect, useCallback } from 'react';
import Icon from '../../Icons';

/**
 * BoxHeaderSplitting Component
 *
 * Displayed when the system is splitting tasks.
 * Shows an animated loading indicator.
 */
export function BoxHeaderSplitting({ className = '' }) {
  return (
    <div className={`box-header splitting ${className}`}>
      <div className="box-header-content">
        <button className="box-header-icon-btn">
          <span className="orbit-icon">
            <span className="spinner small"></span>
          </span>
        </button>
        <div className="box-header-text">
          <span className="splitting-text">Splitting Tasks</span>
        </div>
      </div>
    </div>
  );
}

/**
 * BoxHeaderConfirm Component
 *
 * Displayed when waiting for user to confirm task decomposition.
 * Shows subtitle, back button, start task button, and auto-confirm countdown.
 *
 * @param {Object} props
 * @param {string} props.subtitle - Subtitle text to display
 * @param {function} props.onStartTask - Callback when Start Task is clicked
 * @param {function} props.onEdit - Callback when back/edit is clicked
 * @param {number} props.autoConfirmSeconds - Countdown seconds (default 30)
 * @param {boolean} props.showCountdown - Whether to show countdown (default true)
 */
export function BoxHeaderConfirm({
  subtitle = '',
  onStartTask,
  onEdit,
  autoConfirmSeconds = 30,
  showCountdown = true,
  className = '',
}) {
  const [countdown, setCountdown] = useState(autoConfirmSeconds);
  const [isPaused, setIsPaused] = useState(false);

  // Countdown timer effect
  useEffect(() => {
    if (!showCountdown || isPaused) return;

    // Reset countdown when component mounts or autoConfirmSeconds changes
    setCountdown(autoConfirmSeconds);

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          // Note: Actual auto-confirm is handled by agentStore's timer
          // This is just for UI display
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [autoConfirmSeconds, showCountdown, isPaused]);

  // Handle pause/resume countdown
  const handleTogglePause = useCallback(() => {
    setIsPaused((prev) => !prev);
  }, []);

  return (
    <div className={`box-header confirm ${className}`}>
      <div className="box-header-content">
        {/* Back/Edit Button */}
        <button
          className="box-header-icon-btn"
          onClick={onEdit}
          title="Edit tasks"
        >
          <Icon name="chevronLeft" size={16} />
        </button>

        {/* Subtitle and Countdown */}
        <div className="box-header-text">
          {subtitle && (
            <span className="subtitle-text">{subtitle}</span>
          )}
          {showCountdown && countdown > 0 && (
            <span
              className={`countdown-text ${isPaused ? 'paused' : ''}`}
              onClick={handleTogglePause}
              title={isPaused ? 'Click to resume countdown' : 'Click to pause countdown'}
            >
              {isPaused ? '(paused)' : `Auto-confirm in ${countdown}s`}
            </span>
          )}
        </div>

        {/* Start Task Button */}
        <button
          className="box-header-start-btn"
          onClick={onStartTask}
        >
          Start Task
        </button>
      </div>
    </div>
  );
}

export default { BoxHeaderSplitting, BoxHeaderConfirm };
