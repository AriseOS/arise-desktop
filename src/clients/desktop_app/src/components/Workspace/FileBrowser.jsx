/**
 * FileBrowser Component
 *
 * Displays files created in the task's working directory.
 * Allows viewing file contents and basic file operations.
 */

import React, { useState, useEffect } from 'react';
import Icon from '../Icons';
import { api } from '../../utils/api';

function FileBrowser({ taskId, onFileSelect, selectedFile }) {
  const [files, setFiles] = useState([]);
  const [workspace, setWorkspace] = useState('');
  const [totalSize, setTotalSize] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedFolders, setExpandedFolders] = useState(new Set());

  // Load files when taskId changes
  useEffect(() => {
    if (taskId) {
      loadFiles();
    } else {
      setFiles([]);
      setWorkspace('');
      setError(null);
    }
  }, [taskId]);

  // Load files from API
  const loadFiles = async () => {
    if (!taskId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.callAppBackend(`/api/v1/quick-task/workspace/${taskId}/files`);
      setFiles(response.files || []);
      setWorkspace(response.workspace || '');
      setTotalSize(response.total_size_bytes || 0);
    } catch (e) {
      console.error('Failed to load workspace files:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Get file icon based on extension
  const getFileIcon = (filename) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'txt':
      case 'md':
        return '📄';
      case 'json':
        return '📋';
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
        return '🖼️';
      case 'pdf':
        return '📕';
      case 'log':
        return '📝';
      default:
        return '📄';
    }
  };

  // Build file tree from flat list
  const buildFileTree = (files) => {
    const tree = {};

    files.forEach(filePath => {
      const parts = filePath.split('/');
      let current = tree;

      parts.forEach((part, index) => {
        if (index === parts.length - 1) {
          // It's a file
          current[part] = { type: 'file', path: filePath };
        } else {
          // It's a folder
          if (!current[part]) {
            current[part] = { type: 'folder', children: {} };
          }
          current = current[part].children;
        }
      });
    });

    return tree;
  };

  // Toggle folder expansion
  const toggleFolder = (folderPath) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(folderPath)) {
      newExpanded.delete(folderPath);
    } else {
      newExpanded.add(folderPath);
    }
    setExpandedFolders(newExpanded);
  };

  // Render file tree recursively
  const renderTree = (tree, parentPath = '') => {
    const entries = Object.entries(tree).sort(([, a], [, b]) => {
      // Folders first, then files
      if (a.type === 'folder' && b.type === 'file') return -1;
      if (a.type === 'file' && b.type === 'folder') return 1;
      return 0;
    });

    return entries.map(([name, item]) => {
      const currentPath = parentPath ? `${parentPath}/${name}` : name;

      if (item.type === 'folder') {
        const isExpanded = expandedFolders.has(currentPath);
        return (
          <div key={currentPath} className="file-tree-folder">
            <div
              className="file-tree-item folder"
              onClick={() => toggleFolder(currentPath)}
            >
              <span className="item-icon">
                {isExpanded ? '📂' : '📁'}
              </span>
              <span className="item-name">{name}</span>
              <Icon
                name="chevron"
                size={12}
                className={`folder-chevron ${isExpanded ? 'expanded' : ''}`}
              />
            </div>
            {isExpanded && (
              <div className="folder-children">
                {renderTree(item.children, currentPath)}
              </div>
            )}
          </div>
        );
      }

      // File
      const isSelected = selectedFile === item.path;
      return (
        <div
          key={currentPath}
          className={`file-tree-item file ${isSelected ? 'selected' : ''}`}
          onClick={() => onFileSelect && onFileSelect(item.path)}
        >
          <span className="item-icon">{getFileIcon(name)}</span>
          <span className="item-name">{name}</span>
        </div>
      );
    });
  };

  // Format file size
  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const fileTree = buildFileTree(files);

  return (
    <div className="file-browser">
      {/* Header */}
      <div className="file-browser-header">
        <div className="header-title">
          <span className="header-icon">📁</span>
          <span>Workspace</span>
        </div>
        <button
          className="refresh-btn"
          onClick={loadFiles}
          disabled={loading}
          title="Refresh files"
        >
          <Icon name="refresh" size={14} className={loading ? 'spinning' : ''} />
        </button>
      </div>

      {/* Content */}
      <div className="file-browser-content">
        {loading && files.length === 0 ? (
          <div className="file-browser-loading">
            <span className="spinner small"></span>
            <span>Loading files...</span>
          </div>
        ) : error ? (
          <div className="file-browser-error">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        ) : files.length === 0 ? (
          <div className="file-browser-empty">
            <span className="empty-icon">📭</span>
            <span>No files yet</span>
          </div>
        ) : (
          <div className="file-tree">
            {renderTree(fileTree)}
          </div>
        )}
      </div>

      {/* Footer */}
      {files.length > 0 && (
        <div className="file-browser-footer">
          <span className="file-count">{files.length} files</span>
          <span className="file-size">{formatSize(totalSize)}</span>
        </div>
      )}
    </div>
  );
}

export default FileBrowser;
