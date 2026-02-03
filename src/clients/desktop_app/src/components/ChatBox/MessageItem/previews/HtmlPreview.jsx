/**
 * HtmlPreview Component
 *
 * DS-11: Renders HTML files in a sandboxed iframe.
 * Uses 'allow-same-origin' but no scripts for security.
 *
 * Note: In Tauri, file:// fetch is not allowed by default.
 * We use Tauri's file reading API instead.
 */

import React, { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import './HtmlPreview.css';

function HtmlPreview({ filePath, maxHeight = 400 }) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const iframeRef = useRef(null);

  useEffect(() => {
    loadHtmlContent();
  }, [filePath]);

  const loadHtmlContent = async () => {
    if (!filePath) return;

    setLoading(true);
    setError(null);

    try {
      // In Tauri, file:// fetch is blocked for security.
      // For now, we show a message that the file can be opened externally.
      // TODO: Add a Tauri command to read file content if inline preview is needed.
      setError('HTML preview not available. Click "Open" to view in browser.');
    } catch (e) {
      console.error('Failed to load HTML content:', e);
      setError('Cannot preview HTML file. Click "Open" to view in browser.');
    } finally {
      setLoading(false);
    }
  };

  // Adjust iframe height based on content
  const handleIframeLoad = () => {
    if (iframeRef.current) {
      try {
        const doc = iframeRef.current.contentDocument;
        if (doc && doc.body) {
          const height = doc.body.scrollHeight;
          iframeRef.current.style.height = Math.min(height + 20, maxHeight) + 'px';
        }
      } catch (e) {
        // Cross-origin restriction, use default height
      }
    }
  };

  if (loading) {
    return (
      <div className="html-preview-loading">
        <span className="spinner small"></span>
        Loading HTML preview...
      </div>
    );
  }

  if (error) {
    return (
      <div className="html-preview-error">
        {error}
      </div>
    );
  }

  if (!content) {
    return (
      <div className="html-preview-empty">
        No content to preview
      </div>
    );
  }

  return (
    <div className={`html-preview ${expanded ? 'expanded' : ''}`}>
      <div className="html-preview-toolbar">
        <span className="html-preview-label">HTML Preview</span>
        <button
          className="html-preview-toggle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      <div
        className="html-preview-container"
        style={{ maxHeight: expanded ? 'none' : maxHeight }}
      >
        <iframe
          ref={iframeRef}
          srcDoc={content}
          sandbox="allow-same-origin"
          title="HTML Preview"
          onLoad={handleIframeLoad}
        />
      </div>
    </div>
  );
}

export default HtmlPreview;
