/**
 * CodePreview Component
 *
 * DS-11: Displays code/text file preview with line numbers.
 * Shows first N lines with a "more lines" indicator.
 */

import React from 'react';
import './CodePreview.css';

function CodePreview({ content, totalLines, language }) {
  if (!content) {
    return (
      <div className="code-preview-empty">
        No content to preview
      </div>
    );
  }

  const lines = content.split('\n');
  const displayedLines = lines.length;
  const remainingLines = totalLines ? totalLines - displayedLines : 0;

  return (
    <div className="code-preview">
      <div className="code-preview-header">
        <span className="code-preview-language">{language || 'text'}</span>
        {totalLines && (
          <span className="code-preview-info">{totalLines} lines total</span>
        )}
      </div>
      <div className="code-preview-content">
        <pre>
          <code className={`language-${language || 'text'}`}>
            {lines.map((line, i) => (
              <div key={i} className="code-line">
                <span className="line-number">{i + 1}</span>
                <span className="line-content">{line || ' '}</span>
              </div>
            ))}
          </code>
        </pre>
      </div>
      {remainingLines > 0 && (
        <div className="code-preview-footer">
          ... {remainingLines} more lines
        </div>
      )}
    </div>
  );
}

export default CodePreview;
