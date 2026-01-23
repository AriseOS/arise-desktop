/**
 * TerminalOutput Component
 *
 * Displays terminal/command output from task execution.
 * Simpler than eigent's xterm-based terminal - just displays output.
 */

import React, { useRef, useEffect } from 'react';

function TerminalOutput({ output = [], title = 'Terminal' }) {
  const containerRef = useRef(null);

  // Auto-scroll to bottom when new output arrives
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [output]);

  // Format output line (handle ANSI codes, etc.)
  const formatLine = (line) => {
    // Strip common ANSI escape codes for display
    return line
      .replace(/\x1b\[[0-9;]*m/g, '') // Strip color codes
      .replace(/\r/g, '') // Remove carriage returns
      .replace(/\t/g, '    '); // Convert tabs to spaces
  };

  // Detect line type for styling
  const getLineClass = (line) => {
    const lower = line.toLowerCase();
    if (lower.includes('error') || lower.includes('failed') || lower.includes('exception')) {
      return 'output-error';
    }
    if (lower.includes('warning') || lower.includes('warn')) {
      return 'output-warning';
    }
    if (lower.includes('success') || lower.includes('done') || lower.includes('completed')) {
      return 'output-success';
    }
    if (line.startsWith('$') || line.startsWith('>') || line.startsWith('#')) {
      return 'output-command';
    }
    return '';
  };

  return (
    <div className="terminal-output">
      {/* Header */}
      <div className="terminal-header">
        <div className="terminal-title">
          <span className="terminal-icon">💻</span>
          <span>{title}</span>
        </div>
        <div className="terminal-controls">
          <span className="control-dot red"></span>
          <span className="control-dot yellow"></span>
          <span className="control-dot green"></span>
        </div>
      </div>

      {/* Output */}
      <div className="terminal-content" ref={containerRef}>
        {output.length === 0 ? (
          <div className="terminal-empty">
            <span className="empty-prompt">$</span>
            <span className="empty-cursor"></span>
          </div>
        ) : (
          output.map((line, index) => (
            <div
              key={index}
              className={`terminal-line ${getLineClass(line)}`}
            >
              <span className="line-number">{index + 1}</span>
              <span className="line-content">{formatLine(line)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default TerminalOutput;
