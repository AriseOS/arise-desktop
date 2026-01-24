/**
 * BrowserTab - Browser view with screenshot display
 *
 * Ported from Eigent's BrowserAgentWorkSpace/index.tsx:
 * - Lines 255-286: Single webview mode with large screenshot
 * - Lines 287-336: Multi-webview grid mode
 * - Lines 160-183: Take control mode with live webview
 * - Lines 337-400: Scroll and mode toggle controls
 *
 * Key features:
 * - Display browser screenshot
 * - Show current URL
 * - Take Control button (placeholder for future)
 * - Refresh capability
 */

import React, { useState, useEffect, useRef } from 'react';
import './BrowserTab.css';

/**
 * BrowserTab Component
 */
function BrowserTab({ taskId, screenshot, url }) {
  const [isLoading, setIsLoading] = useState(false);
  const [imageError, setImageError] = useState(false);
  const containerRef = useRef(null);

  /**
   * Handle image load
   */
  const handleImageLoad = () => {
    setIsLoading(false);
    setImageError(false);
  };

  /**
   * Handle image error
   */
  const handleImageError = () => {
    setIsLoading(false);
    setImageError(true);
  };

  /**
   * Reset error state when screenshot changes
   */
  useEffect(() => {
    if (screenshot) {
      setIsLoading(true);
      setImageError(false);
    }
  }, [screenshot]);

  /**
   * Handle take control (placeholder)
   * Similar to Eigent's handleTakeControl in BrowserAgentWorkSpace
   */
  const handleTakeControl = () => {
    // TODO: Implement take control functionality
    // This would pause the agent and show live webview
    console.log('Take control clicked - not yet implemented');
  };

  /**
   * Handle refresh
   */
  const handleRefresh = () => {
    // TODO: Trigger screenshot refresh from backend
    console.log('Refresh clicked - not yet implemented');
  };

  // Empty state
  if (!screenshot && !url) {
    return (
      <div className="browser-tab empty">
        <div className="empty-state">
          <span className="empty-icon">🌐</span>
          <span className="empty-text">No browser activity yet</span>
          <span className="empty-hint">
            The browser view will appear when the agent starts browsing
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="browser-tab" ref={containerRef}>
      {/* Header with URL */}
      <div className="browser-header">
        <div className="browser-url-bar">
          <span className="browser-url-icon">🔒</span>
          <span className="browser-url" title={url}>
            {url || 'about:blank'}
          </span>
        </div>
        <div className="browser-controls">
          <button
            className="browser-control-btn"
            onClick={handleRefresh}
            title="Refresh screenshot"
          >
            🔄
          </button>
        </div>
      </div>

      {/* Screenshot Display */}
      <div className="browser-content">
        {screenshot ? (
          <div className="browser-screenshot-container">
            {isLoading && (
              <div className="browser-loading">
                <span className="loading-spinner">⟳</span>
                <span>Loading...</span>
              </div>
            )}
            {imageError ? (
              <div className="browser-error">
                <span className="error-icon">⚠️</span>
                <span>Failed to load screenshot</span>
              </div>
            ) : (
              <img
                src={screenshot}
                alt="Browser screenshot"
                className="browser-screenshot"
                onLoad={handleImageLoad}
                onError={handleImageError}
              />
            )}
            {/* Take Control Overlay - Similar to Eigent's hover overlay */}
            <div className="browser-overlay">
              <button className="take-control-btn" onClick={handleTakeControl}>
                <span className="take-control-icon">✋</span>
                <span>Take Control</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="browser-placeholder">
            <span className="placeholder-icon">🖼️</span>
            <span className="placeholder-text">Waiting for screenshot...</span>
          </div>
        )}
      </div>

      {/* Status Footer */}
      <div className="browser-footer">
        <span className="browser-status">
          {screenshot ? 'Screenshot available' : 'No screenshot'}
        </span>
      </div>
    </div>
  );
}

export default BrowserTab;
