/**
 * InputBox Component
 *
 * A multi-state input component with two visual states:
 * - Default: Empty state with placeholder text and disabled send button
 * - Focus/Input: Active state with content, file attachments, and active send button
 *
 * Features:
 * - Auto-expanding textarea (up to 200px height)
 * - File attachment display (shows up to 5 files + count indicator)
 * - Action buttons (add file on left, send on right)
 * - Send button changes color based on content
 * - Supports Enter to send, Shift+Enter for new line
 * - Drag and drop file support
 * - Native HTML5 file selection (Tauri compatible)
 *
 * Ported from Eigent's InputBox component.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import Icon from '../../Icons';

/**
 * @typedef {Object} FileAttachment
 * @property {string} fileName - Name of the file
 * @property {string} filePath - Path to the file
 */

/**
 * InputBox Component
 *
 * @param {Object} props
 * @param {string} props.value - Current text value
 * @param {function} props.onChange - Callback when text changes
 * @param {function} props.onSend - Callback when send button is clicked
 * @param {FileAttachment[]} props.files - Array of file attachments
 * @param {function} props.onFilesChange - Callback when files are modified
 * @param {function} props.onAddFile - Callback when add file button is clicked (optional, uses native picker if not provided)
 * @param {string} props.placeholder - Placeholder text
 * @param {boolean} props.disabled - Disable all interactions
 * @param {boolean} props.allowDragDrop - Allow drag and drop files
 * @param {string} props.className - Additional CSS classes
 */
function InputBox({
  value = '',
  onChange,
  onSend,
  files = [],
  onFilesChange,
  onAddFile,
  placeholder = 'Ask Ami to automate your tasks',
  disabled = false,
  allowDragDrop = true,
  className = '',
}) {
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [hoveredFilePath, setHoveredFilePath] = useState(null);
  const dragCounter = useRef(0);

  // Auto-resize textarea on value changes
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  // Determine if we're in the "Input" state (has content or files)
  const hasContent = value.trim().length > 0 || files.length > 0;
  const isActive = isFocused || hasContent;

  const handleTextChange = useCallback((e) => {
    if (onChange) {
      onChange(e.target.value);
    }
  }, [onChange]);

  const handleSend = useCallback(() => {
    if (value.trim().length > 0 && !disabled && onSend) {
      onSend();
    }
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey && !disabled && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  }, [disabled, isComposing, handleSend]);

  const handleRemoveFile = useCallback((filePath) => {
    if (onFilesChange) {
      const newFiles = files.filter((f) => f.filePath !== filePath);
      onFilesChange(newFiles);
    }
  }, [files, onFilesChange]);

  // Native file selection handler (HTML5 fallback for Tauri)
  const handleNativeFileSelect = useCallback(() => {
    if (onAddFile) {
      // Use custom handler if provided (e.g., Tauri dialog plugin)
      onAddFile();
    } else if (fileInputRef.current) {
      // Fallback to native HTML5 file input
      fileInputRef.current.click();
    }
  }, [onAddFile]);

  // Handle files selected via native input
  const handleFileInputChange = useCallback((e) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0 || !onFilesChange) return;

    const mapped = selectedFiles.map((f) => ({
      fileName: f.name,
      filePath: f.path || f.name, // f.path available in Electron/Tauri
    }));

    // Merge without duplicates
    const newFiles = [
      ...files.filter((f) => !mapped.find((m) => m.filePath === f.filePath)),
      ...mapped,
    ];
    onFilesChange(newFiles);

    // Reset input so the same file can be selected again
    e.target.value = '';
  }, [files, onFilesChange]);

  // Get file icon based on extension
  const getFileIcon = useCallback((fileName) => {
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) {
      return '🖼️';
    }
    if (['pdf'].includes(ext)) {
      return '📕';
    }
    if (['doc', 'docx'].includes(ext)) {
      return '📘';
    }
    if (['xls', 'xlsx'].includes(ext)) {
      return '📗';
    }
    if (['ppt', 'pptx'].includes(ext)) {
      return '📙';
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
      return '📦';
    }
    return '📄';
  }, []);

  // Drag & drop handlers
  const isFileDrag = useCallback((e) => {
    try {
      return Array.from(e.dataTransfer?.types || []).includes('Files');
    } catch {
      return false;
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    if (!allowDragDrop || !isFileDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    setIsDragging(true);
  }, [allowDragDrop, isFileDrag]);

  const handleDragEnter = useCallback((e) => {
    if (!allowDragDrop || !isFileDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    setIsDragging(true);
  }, [allowDragDrop, isFileDrag]);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;

    if (!allowDragDrop || !onFilesChange) return;

    try {
      const dropped = Array.from(e.dataTransfer?.files || []);
      if (dropped.length === 0) return;

      const mapped = dropped.map((f) => ({
        fileName: f.name,
        filePath: f.path || f.name,
      }));

      // Merge without duplicates
      const newFiles = [
        ...files.filter((f) => !mapped.find((m) => m.filePath === f.filePath)),
        ...mapped.filter((m) => !files.find((f) => f.filePath === m.filePath)),
      ];
      onFilesChange(newFiles);
    } catch (error) {
      console.error('Drop File Error:', error);
    }
  }, [allowDragDrop, files, onFilesChange]);

  // File display limits
  const maxVisibleFiles = 5;
  const visibleFiles = files.slice(0, maxVisibleFiles);
  const remainingCount = files.length > maxVisibleFiles ? files.length - maxVisibleFiles : 0;

  return (
    <div
      className={`input-box ${isFocused ? 'focused' : ''} ${isDragging ? 'dragging' : ''} ${className}`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="input-box-drag-overlay">
          <Icon name="upload" size={32} />
          <span>Drop files to attach</span>
        </div>
      )}

      {/* Text Input Area */}
      <div className="input-box-text-area">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          disabled={disabled}
          placeholder={placeholder}
          className={`input-box-textarea ${isActive ? 'active' : ''}`}
          rows={1}
        />
      </div>

      {/* File Attachments */}
      {files.length > 0 && (
        <div className="input-box-files">
          {visibleFiles.map((file) => {
            const isHovered = hoveredFilePath === file.filePath;
            return (
              <div
                key={file.filePath}
                className="file-tag"
                onMouseEnter={() => setHoveredFilePath(file.filePath)}
                onMouseLeave={() => setHoveredFilePath(null)}
              >
                <button
                  className="file-tag-icon"
                  onClick={() => handleRemoveFile(file.filePath)}
                  title={isHovered ? 'Remove file' : file.fileName}
                >
                  {isHovered ? '×' : getFileIcon(file.fileName)}
                </button>
                <span className="file-tag-name" title={file.fileName}>
                  {file.fileName}
                </span>
              </div>
            );
          })}
          {remainingCount > 0 && (
            <div className="file-tag more">
              <span className="file-tag-name">+{remainingCount}</span>
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="input-box-actions">
        {/* Hidden file input for native selection */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileInputChange}
          style={{ display: 'none' }}
          accept="*/*"
        />

        {/* Left: Add File Button */}
        <button
          className="input-box-btn add-file"
          onClick={handleNativeFileSelect}
          disabled={disabled}
          title="Add file"
        >
          <Icon name="plus" size={16} />
        </button>

        {/* Right: Send Button */}
        <button
          className={`input-box-btn send ${value.trim().length > 0 ? 'active' : ''}`}
          onClick={handleSend}
          disabled={disabled || value.trim().length === 0}
          title="Send message"
        >
          <Icon
            name="arrowRight"
            size={16}
            className={`send-icon ${value.trim().length > 0 ? 'rotated' : ''}`}
          />
        </button>
      </div>
    </div>
  );
}

export default InputBox;
