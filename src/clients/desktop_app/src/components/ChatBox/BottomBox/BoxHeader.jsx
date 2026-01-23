/**
 * BoxHeader Components
 *
 * Header variants for BottomBox component:
 * - BoxHeaderSplitting: Shows when task is being split
 * - BoxHeaderConfirm: Shows when waiting for user confirmation
 *
 * Ported from Eigent's BoxHeader component.
 */

import React from 'react';
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
 * Shows subtitle, back button, and start task button.
 *
 * @param {Object} props
 * @param {string} props.subtitle - Subtitle text to display
 * @param {function} props.onStartTask - Callback when Start Task is clicked
 * @param {function} props.onEdit - Callback when back/edit is clicked
 */
export function BoxHeaderConfirm({
  subtitle = '',
  onStartTask,
  onEdit,
  className = '',
}) {
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

        {/* Subtitle */}
        <div className="box-header-text">
          {subtitle && (
            <span className="subtitle-text">{subtitle}</span>
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
