/**
 * FilesTab - File browser and preview
 *
 * Wraps existing FileBrowser and FilePreview components.
 *
 * Ported from Eigent's Folder/index.tsx:
 * - Collapsible sidebar with file tree
 * - File preview with syntax highlighting
 * - Support for multiple file types
 */

import React, { useState } from 'react';
import FileBrowser from '../FileBrowser';
import FilePreview from '../FilePreview';
import './FilesTab.css';

/**
 * FilesTab Component
 */
function FilesTab({ taskId, files = [], workspacePath = '' }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewContent, setPreviewContent] = useState(null);

  /**
   * Handle file selection
   */
  const handleFileSelect = (file) => {
    setSelectedFile(file);
    // FilePreview will load content based on file path
  };

  /**
   * Close preview
   */
  const handleClosePreview = () => {
    setSelectedFile(null);
    setPreviewContent(null);
  };

  return (
    <div className="files-tab">
      {/* File Browser */}
      <div className={`files-browser-section ${selectedFile ? 'with-preview' : ''}`}>
        <FileBrowser
          taskId={taskId}
          onFileSelect={handleFileSelect}
          selectedFile={selectedFile}
        />
      </div>

      {/* File Preview */}
      {selectedFile && (
        <div className="files-preview-section">
          <div className="preview-header">
            <span className="preview-filename">{selectedFile}</span>
            <button className="preview-close-btn" onClick={handleClosePreview}>
              ✕
            </button>
          </div>
          <FilePreview taskId={taskId} filePath={selectedFile} />
        </div>
      )}
    </div>
  );
}

export default FilesTab;
