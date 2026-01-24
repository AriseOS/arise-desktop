/**
 * TerminalTab - Terminal output display
 *
 * Wraps existing TerminalOutput component.
 *
 * Ported from Eigent's TerminalAgentWrokSpace/index.tsx:
 * - Terminal display with xterm styling
 * - Auto-scroll to bottom
 * - Support for multiple terminal instances
 */

import React from 'react';
import TerminalOutput from '../TerminalOutput';
import './TerminalTab.css';

/**
 * TerminalTab Component
 */
function TerminalTab({ taskId, output = [] }) {
  // Empty state
  if (!output || output.length === 0) {
    return (
      <div className="terminal-tab empty">
        <div className="empty-state">
          <span className="empty-icon">💻</span>
          <span className="empty-text">No terminal output yet</span>
          <span className="empty-hint">
            Terminal commands will appear here when executed
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="terminal-tab">
      <TerminalOutput lines={output} />
    </div>
  );
}

export default TerminalTab;
