/**
 * FileAttachmentCard Component
 *
 * DS-11: Displays file attachments in task summary messages.
 * Supports different file types with expandable previews.
 *
 * File types and rendering:
 * - image: Thumbnail with click-to-enlarge
 * - html: Sandboxed iframe preview
 * - csv/excel: Table preview (first N rows)
 * - code: Syntax highlighted preview
 * - pdf: Page count info
 * - folder: File list summary
 * - other: File card only
 */

import React, { useState } from 'react';
import Icon from '../../Icons';
import ImagePreview from './previews/ImagePreview';
import HtmlPreview from './previews/HtmlPreview';
import TablePreview from './previews/TablePreview';
import CodePreview from './previews/CodePreview';
import './FileAttachmentCard.css';

// File type to icon mapping
const FILE_TYPE_ICONS = {
  image: 'image',
  html: 'code',
  csv: 'table',
  excel: 'table',
  code: 'file-code',
  pdf: 'file-pdf',
  office: 'file-text',
  folder: 'folder',
  other: 'file',
};

// Format file size for display
function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(unitIndex > 0 ? 1 : 0)} ${units[unitIndex]}`;
}

// Get language from file extension for code preview
function getLanguageFromExt(filename) {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const langMap = {
    py: 'python',
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    md: 'markdown',
    html: 'html',
    css: 'css',
    sql: 'sql',
    sh: 'bash',
    bash: 'bash',
  };
  return langMap[ext] || 'text';
}

function FileAttachmentCard({ file }) {
  const [expanded, setExpanded] = useState(false);
  const [enlargedImage, setEnlargedImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const {
    file_name,
    file_path,
    file_type: rawFileType,
    file_size,
    mime_type,
    preview,
  } = file;

  // Normalize: old format used "type" key, new format uses "file_type"
  const file_type = rawFileType || file.type || 'other';

  // Determine if this file type has a preview
  const hasPreview = ['image', 'html', 'csv', 'excel', 'code'].includes(file_type);

  // Images are always expanded (show thumbnail)
  const isAlwaysExpanded = file_type === 'image';

  // Open file with system default application
  const handleOpen = async () => {
    console.log('[FileAttachmentCard] Opening file:', file_path);
    setLoading(true);
    setError(null);
    try {
      const result = await window.electronAPI.openPath(file_path);
      console.log('[FileAttachmentCard] open_path result:', result);
      if (!result.success) {
        setError(result.error);
      }
    } catch (e) {
      console.error('[FileAttachmentCard] Failed to open file:', e);
      setError(e.message || 'Failed to open file');
    } finally {
      setLoading(false);
    }
  };

  // Reveal file in system file explorer
  const handleReveal = async () => {
    console.log('[FileAttachmentCard] Revealing file:', file_path);
    setLoading(true);
    setError(null);
    try {
      const result = await window.electronAPI.revealInFolder(file_path);
      console.log('[FileAttachmentCard] reveal_in_folder result:', result);
      if (!result.success) {
        setError(result.error);
      }
    } catch (e) {
      console.error('[FileAttachmentCard] Failed to reveal in folder:', e);
      setError(e.message || 'Failed to reveal in folder');
    } finally {
      setLoading(false);
    }
  };

  // Render preview based on file type
  const renderPreview = () => {
    if (!expanded && !isAlwaysExpanded) return null;
    if (!preview && file_type !== 'html') return null;

    switch (file_type) {
      case 'image':
        return (
          <ImagePreview
            thumbnail={preview?.thumbnail}
            filePath={file_path}
            fileName={file_name}
            onEnlarge={() => setEnlargedImage(preview?.thumbnail || `file://${file_path}`)}
          />
        );

      case 'html':
        return (
          <HtmlPreview filePath={file_path} />
        );

      case 'csv':
      case 'excel':
        return (
          <TablePreview
            headers={preview?.table_headers}
            rows={preview?.table_preview}
            totalRows={preview?.table_total_rows}
          />
        );

      case 'code':
        return (
          <CodePreview
            content={preview?.text_preview}
            totalLines={preview?.text_total_lines}
            language={getLanguageFromExt(file_name)}
          />
        );

      case 'pdf':
        return preview?.pdf_page_count ? (
          <div className="file-preview-info">
            <Icon name="file-pdf" size={16} />
            <span>{preview.pdf_page_count} pages</span>
          </div>
        ) : null;

      case 'folder':
        return preview?.folder_files ? (
          <div className="folder-preview">
            <div className="folder-preview-header">
              <span>{preview.folder_file_count || preview.folder_files.length} files</span>
              {preview.folder_total_size && (
                <span className="folder-size">{formatFileSize(preview.folder_total_size)}</span>
              )}
            </div>
            <ul className="folder-file-list">
              {preview.folder_files.slice(0, 5).map((name, i) => (
                <li key={i}>{name}</li>
              ))}
              {preview.folder_files.length > 5 && (
                <li className="more">... and {preview.folder_files.length - 5} more</li>
              )}
            </ul>
          </div>
        ) : null;

      default:
        return null;
    }
  };

  // Get icon name for file type
  const iconName = FILE_TYPE_ICONS[file_type] || 'file';

  return (
    <div className={`file-attachment-card file-type-${file_type}`}>
      {/* Header */}
      <div className="file-card-header">
        <div className="file-card-icon">
          <Icon name={iconName} size={20} />
        </div>

        <div className="file-card-info">
          <span className="file-card-name" title={file_name}>
            {file_name}
          </span>
          <span className="file-card-meta">
            {file_size ? formatFileSize(file_size) : ''}
            {file_type !== 'other' && (
              <span className="file-type-badge">{file_type.toUpperCase()}</span>
            )}
          </span>
        </div>

        <div className="file-card-actions">
          {hasPreview && !isAlwaysExpanded && (
            <button
              className="file-action-btn preview-btn"
              onClick={() => setExpanded(!expanded)}
              title={expanded ? 'Hide preview' : 'Show preview'}
            >
              {expanded ? 'Hide' : 'Preview'}
            </button>
          )}
          <button
            className="file-action-btn open-btn"
            onClick={handleOpen}
            disabled={loading}
            title="Open with default app"
          >
            Open
          </button>
          <button
            className="file-action-btn reveal-btn"
            onClick={handleReveal}
            disabled={loading}
            title="Reveal in folder"
          >
            <Icon name="folder-open" size={14} />
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="file-card-error">
          {error}
        </div>
      )}

      {/* Preview content */}
      {renderPreview()}

      {/* Image enlargement modal */}
      {enlargedImage && (
        <div className="image-modal-overlay" onClick={() => setEnlargedImage(null)}>
          <div className="image-modal-content" onClick={(e) => e.stopPropagation()}>
            <img src={enlargedImage} alt={file_name} />
            <button
              className="image-modal-close"
              onClick={() => setEnlargedImage(null)}
            >
              <Icon name="close" size={24} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default FileAttachmentCard;
