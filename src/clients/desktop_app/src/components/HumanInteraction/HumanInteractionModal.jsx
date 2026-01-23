/**
 * HumanInteractionModal Component
 *
 * Modal for handling human interaction requests from the agent.
 * Supports text input and predefined options.
 *
 * Props:
 * - isOpen: boolean - Controls modal visibility
 * - type: 'question' | 'confirmation' - Modal type for styling
 * - title: string - Custom title (optional)
 * - question: string - The question to display
 * - context: string - Additional context (optional)
 * - options: array - Predefined options for selection (optional)
 * - timeout: number - Auto-submit timeout in seconds (optional)
 * - placeholder: string - Placeholder for text input (optional)
 * - onSubmit / onRespond: function - Callback when user responds (supports both names)
 * - onClose: function - Callback to close modal
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

// Modal type icons
const TYPE_ICONS = {
  question: '💬',
  confirmation: '⚠️',
  choice: '🔀',
};

// Default titles by type
const DEFAULT_TITLES = {
  question: 'Human Input Required',
  confirmation: 'Confirmation Required',
  choice: 'Make a Choice',
};

function HumanInteractionModal({
  // Visibility control
  isOpen = true,
  // Type and title
  type = 'question',
  title = null,
  // Content
  question,
  context = null,
  options = null,
  // Timing
  timeout = null,
  // Input customization
  placeholder = 'Type your response...',
  // Callbacks - support both onSubmit and onRespond
  onSubmit,
  onRespond,
  onClose,
}) {
  const [response, setResponse] = useState('');
  const [selectedOption, setSelectedOption] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState(timeout);
  const textareaRef = useRef(null);
  const timerRef = useRef(null);

  // Normalize callback - support both onSubmit and onRespond
  const handleCallback = useCallback((value, isTimeout = false) => {
    const callback = onSubmit || onRespond;
    if (callback) {
      callback(value, isTimeout);
    }
  }, [onSubmit, onRespond]);

  // Reset state when modal opens/closes or question changes
  useEffect(() => {
    if (isOpen) {
      setResponse('');
      setSelectedOption(null);
      setTimeRemaining(timeout);
    }
  }, [isOpen, question, timeout]);

  // Auto-focus textarea when modal opens
  useEffect(() => {
    if (isOpen && textareaRef.current && (!options || options.length === 0)) {
      // Small delay to ensure modal is rendered
      const focusTimer = setTimeout(() => {
        textareaRef.current?.focus();
      }, 100);
      return () => clearTimeout(focusTimer);
    }
  }, [isOpen, options]);

  // Countdown timer
  useEffect(() => {
    // Clear existing timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (!isOpen || !timeout || timeout <= 0) {
      return;
    }

    timerRef.current = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          timerRef.current = null;
          // Auto-submit on timeout
          if (options && options.length > 0) {
            // Auto-select first option (usually "Yes" or default)
            handleCallback(options[0].value, true);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isOpen, timeout, options, handleCallback]);

  // Handle submit
  const handleSubmit = useCallback((value = null) => {
    const submitValue = value || (selectedOption !== null && options ? options[selectedOption].value : response);
    if (submitValue && (typeof submitValue === 'string' ? submitValue.trim() : true)) {
      handleCallback(submitValue, false);
    }
  }, [selectedOption, options, response, handleCallback]);

  // Handle option selection
  const handleOptionClick = useCallback((index) => {
    setSelectedOption(index);
    // Auto-submit on option click
    if (options && options[index]) {
      handleCallback(options[index].value, false);
    }
  }, [options, handleCallback]);

  // Handle key press
  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  // Don't render if not open
  if (!isOpen) {
    return null;
  }

  // Determine display values
  const displayIcon = TYPE_ICONS[type] || TYPE_ICONS.question;
  const displayTitle = title || DEFAULT_TITLES[type] || DEFAULT_TITLES.question;
  const hasOptions = options && options.length > 0;

  return (
    <div className="human-interaction-overlay" onClick={onClose}>
      <div
        className={`human-interaction-modal modal-type-${type}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <span className="modal-icon">{displayIcon}</span>
          <h3 className="modal-title">{displayTitle}</h3>
          {timeRemaining > 0 && (
            <div className={`timeout-badge ${timeRemaining <= 10 ? 'urgent' : ''}`}>
              <span>⏱️</span>
              <span>{timeRemaining}s</span>
            </div>
          )}
          <button className="close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {/* Question */}
          <p className="question-text">{question}</p>

          {/* Context */}
          {context && (
            <div className="context-box">
              <div className="context-label">Context</div>
              <pre className="context-content">{context}</pre>
            </div>
          )}

          {/* Options or Text Input */}
          {hasOptions ? (
            <div className="options-container">
              {options.map((option, index) => (
                <button
                  key={index}
                  className={`option-btn ${selectedOption === index ? 'selected' : ''} ${option.variant ? `variant-${option.variant}` : ''}`}
                  onClick={() => handleOptionClick(index)}
                >
                  {option.icon && <span className="option-icon">{option.icon}</span>}
                  <span className="option-label">{option.label}</span>
                  {option.description && (
                    <span className="option-description">{option.description}</span>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-input-container">
              <textarea
                ref={textareaRef}
                className="response-textarea"
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={placeholder}
                rows={3}
              />
            </div>
          )}
        </div>

        {/* Footer - only show for text input mode */}
        {!hasOptions && (
          <div className="modal-footer">
            <button className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleSubmit()}
              disabled={!response.trim()}
            >
              Submit
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default HumanInteractionModal;
