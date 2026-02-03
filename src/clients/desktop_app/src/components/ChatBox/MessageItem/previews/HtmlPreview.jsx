/**
 * HtmlPreview Component
 *
 * DS-11: Renders HTML files in a sandboxed iframe.
 * Uses 'allow-same-origin' but no scripts for security.
 */

import React, { useState, useEffect, useRef } from 'react';
import { api } from '../../../../utils/api';
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
      // Read file content via backend API
      // filePath is absolute, we need to extract task workspace info
      const response = await fetch(`file://${filePath}`);
      if (!response.ok) {
        throw new Error(`Failed to load: ${response.status}`);
      }
      const html = await response.text();
      setContent(html);
    } catch (e) {
      console.error('Failed to load HTML content:', e);
      // Try reading via file protocol directly
      try {
        // For Tauri, we might need to use a different approach
        setError('Cannot preview HTML file. Click "Open" to view in browser.');
      } catch (e2) {
        setError(e.message || 'Failed to load HTML content');
      }
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
