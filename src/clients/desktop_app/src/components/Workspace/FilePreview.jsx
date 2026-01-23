/**
 * FilePreview Component
 *
 * Displays file content with syntax highlighting support.
 * Handles text files, JSON, and basic file types.
 */

import React, { useState, useEffect } from 'react';
import { api } from '../../utils/api';

function FilePreview({ taskId, filePath, onClose }) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load file content
  useEffect(() => {
    if (taskId && filePath) {
      loadContent();
    } else {
      setContent(null);
    }
  }, [taskId, filePath]);

  const loadContent = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.callAppBackend(
        `/api/v1/quick-task/workspace/${taskId}/file/${encodeURIComponent(filePath)}`
      );
      setContent(response.content);
    } catch (e) {
      console.error('Failed to load file content:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Get file extension
  const getExtension = (path) => {
    return path.split('.').pop()?.toLowerCase() || '';
  };

  // Check if file is an image
  const isImage = (path) => {
    const ext = getExtension(path);
    return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext);
  };

  // Get language for syntax highlighting
  const getLanguage = (path) => {
    const ext = getExtension(path);
    const langMap = {
      js: 'javascript',
      jsx: 'javascript',
      ts: 'typescript',
      tsx: 'typescript',
      py: 'python',
      json: 'json',
      md: 'markdown',
      html: 'html',
      css: 'css',
      yml: 'yaml',
      yaml: 'yaml',
      sh: 'bash',
      bash: 'bash',
    };
    return langMap[ext] || 'text';
  };

  // Format JSON content
  const formatContent = (text, path) => {
    if (getExtension(path) === 'json') {
      try {
        const parsed = JSON.parse(text);
        return JSON.stringify(parsed, null, 2);
      } catch {
        return text;
      }
    }
    return text;
  };

  if (!filePath) {
    return (
      <div className="file-preview empty">
        <div className="preview-placeholder">
          <span className="placeholder-icon">📄</span>
          <span className="placeholder-text">Select a file to preview</span>
        </div>
      </div>
    );
  }

  const fileName = filePath.split('/').pop() || filePath;

  return (
    <div className="file-preview">
      {/* Header */}
      <div className="preview-header">
        <div className="preview-title">
          <span className="preview-icon">📄</span>
          <span className="preview-filename">{fileName}</span>
        </div>
        <div className="preview-actions">
          <button
            className="preview-btn"
            onClick={loadContent}
            disabled={loading}
            title="Refresh"
          >
            🔄
          </button>
          {onClose && (
            <button
              className="preview-btn close"
              onClick={onClose}
              title="Close preview"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="preview-content">
        {loading ? (
          <div className="preview-loading">
            <span className="spinner small"></span>
            <span>Loading...</span>
          </div>
        ) : error ? (
          <div className="preview-error">
            <span>❌</span>
            <span>{error}</span>
          </div>
        ) : content !== null ? (
          isImage(filePath) ? (
            <div className="preview-image">
              <img
                src={`data:image/${getExtension(filePath)};base64,${content}`}
                alt={fileName}
              />
            </div>
          ) : (
            <pre className={`preview-code language-${getLanguage(filePath)}`}>
              <code>{formatContent(content, filePath)}</code>
            </pre>
          )
        ) : (
          <div className="preview-empty">
            <span>No content to display</span>
          </div>
        )}
      </div>

      {/* Footer */}
      {content && !isImage(filePath) && (
        <div className="preview-footer">
          <span className="preview-path">{filePath}</span>
          <span className="preview-lang">{getLanguage(filePath)}</span>
        </div>
      )}
    </div>
  );
}

export default FilePreview;
