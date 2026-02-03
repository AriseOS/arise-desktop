/**
 * ImagePreview Component
 *
 * DS-11: Displays image thumbnail with click-to-enlarge functionality.
 */

import React, { useState } from 'react';
import './ImagePreview.css';

function ImagePreview({ thumbnail, filePath, fileName, onEnlarge }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  // Use thumbnail if available, otherwise try file path
  const src = thumbnail || (filePath ? `file://${filePath}` : null);

  if (!src) return null;

  if (error) {
    return (
      <div className="image-preview-error">
        Failed to load image
      </div>
    );
  }

  return (
    <div className="image-preview" onClick={onEnlarge}>
      {!loaded && (
        <div className="image-preview-loading">
          <span className="spinner small"></span>
          Loading...
        </div>
      )}
      <img
        src={src}
        alt={fileName || 'Preview'}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        style={{ display: loaded ? 'block' : 'none' }}
      />
      {loaded && (
        <div className="image-preview-overlay">
          <span>Click to enlarge</span>
        </div>
      )}
    </div>
  );
}

export default ImagePreview;
