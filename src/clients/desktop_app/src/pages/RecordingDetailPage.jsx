import React, { useState, useEffect } from 'react';
import '../styles/RecordingDetailPage.css';

const API_BASE = "http://127.0.0.1:8765";

function RecordingDetailPage({ onNavigate, showStatus, sessionId }) {
  const [recording, setRecording] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch recording details from API
  useEffect(() => {
    const fetchRecordingDetails = async () => {
      if (!sessionId) {
        showStatus('❌ No session ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/recordings/${sessionId}`);

        if (!response.ok) {
          throw new Error(`Failed to fetch recording details: ${response.status}`);
        }

        const data = await response.json();
        setRecording(data);
      } catch (error) {
        console.error('Error fetching recording details:', error);
        showStatus(`❌ Failed to load recording: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchRecordingDetails();
  }, [sessionId]);

  const handleGenerateWorkflow = async () => {
    showStatus('✨ Generating workflow from recording...', 'info');

    try {
      const response = await fetch(`${API_BASE}/api/workflows/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: "Auto-generated workflow from recording",
          user_id: "default_user"
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to generate workflow: ${response.status}`);
      }

      const data = await response.json();

      showStatus('✅ Workflow generated successfully!', 'success');

      // Navigate to workflows page to see the generated workflow
      setTimeout(() => {
        onNavigate('workflows');
      }, 500);
    } catch (error) {
      console.error('Error generating workflow:', error);
      showStatus(`❌ Failed to generate workflow: ${error.message}`, 'error');
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getOperationTypeLabel = (type) => {
    const typeLabels = {
      'click': '🖱️ Click',
      'input': '⌨️ Input',
      'navigate': '🌐 Navigate',
      'scroll': '📜 Scroll',
      'select': '📋 Select',
      'submit': '✅ Submit',
      'hover': '👆 Hover',
      'copy_action': '📋 Copy Data',
      'test': '🧪 Test',
      'type': '⌨️ Type',
      'fill': '⌨️ Fill'
    };
    return typeLabels[type] || `📌 ${type.charAt(0).toUpperCase() + type.slice(1)}`;
  };

  const renderOperationDetails = (operation) => {
    if (!operation || !operation.details) return null;

    const details = [];
    const detailsObj = operation.details;
    const type = operation.type;

    // For navigate operations
    if (type === 'navigate') {
      if (detailsObj.url) {
        details.push(
          <div key="url" className="action-detail">
            <span className="detail-label">URL:</span>
            <span className="detail-value url-link">{detailsObj.url}</span>
          </div>
        );
      }
      if (detailsObj.page_title) {
        details.push(
          <div key="page_title" className="action-detail">
            <span className="detail-label">Page Title:</span>
            <span className="detail-value">"{detailsObj.page_title}"</span>
          </div>
        );
      }
    }

    // For click operations
    if (type === 'click') {
      if (detailsObj.element_text) {
        const displayText = detailsObj.element_text.trim();
        details.push(
          <div key="element_text" className="action-detail highlight-action">
            <span className="detail-label">👆 Clicked on:</span>
            <span className="detail-value clicked-text">"{displayText.substring(0, 100)}{displayText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (detailsObj.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{detailsObj.xpath}</span>
          </div>
        );
      }
      if (detailsObj.tag) {
        details.push(
          <div key="tag" className="action-detail">
            <span className="detail-label">Tag:</span>
            <span className="detail-value code">{detailsObj.tag}</span>
          </div>
        );
      }
    }

    // For input/type operations
    if (type === 'input' || type === 'type') {
      if (detailsObj.value) {
        details.push(
          <div key="value" className="action-detail">
            <span className="detail-label">Input Value:</span>
            <span className="detail-value">"{detailsObj.value}"</span>
          </div>
        );
      }
      if (detailsObj.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{detailsObj.xpath}</span>
          </div>
        );
      }
    }

    // For select operations
    if (type === 'select') {
      if (detailsObj.selected_text) {
        const selectedText = detailsObj.selected_text.trim();
        details.push(
          <div key="selected_text" className="action-detail highlight-action">
            <span className="detail-label">📋 Selected:</span>
            <span className="detail-value selected-text">"{selectedText.substring(0, 100)}{selectedText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (detailsObj.element_text && detailsObj.element_text !== detailsObj.selected_text) {
        const elementText = detailsObj.element_text.trim();
        details.push(
          <div key="element_text" className="action-detail">
            <span className="detail-label">From Element:</span>
            <span className="detail-value">"{elementText.substring(0, 100)}{elementText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (detailsObj.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{detailsObj.xpath}</span>
          </div>
        );
      }
    }

    // For copy_action operations
    if (type === 'copy_action') {
      if (detailsObj.copied_text) {
        details.push(
          <div key="copied_text" className="action-detail field-mapping">
            <span className="detail-label">📋 Copied Text:</span>
            <span className="detail-value field-value">"{detailsObj.copied_text}"</span>
          </div>
        );
      }
      if (detailsObj.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{detailsObj.xpath}</span>
          </div>
        );
      }
    }

    // For scroll operations
    if (type === 'scroll') {
      if (detailsObj.direction) {
        details.push(
          <div key="direction" className="action-detail">
            <span className="detail-label">Direction:</span>
            <span className="detail-value">{detailsObj.direction}</span>
          </div>
        );
      }
    }

    // For test operations
    if (type === 'test') {
      if (detailsObj.message) {
        details.push(
          <div key="message" className="action-detail">
            <span className="detail-label">Message:</span>
            <span className="detail-value">{detailsObj.message}</span>
          </div>
        );
      }
    }

    // Show URL for all operations (if available and not navigate)
    if (type !== 'navigate' && operation.url) {
      details.push(
        <div key="operation_url" className="action-detail url-context">
          <span className="detail-label">Page:</span>
          <span className="detail-value url-text">{operation.url}</span>
        </div>
      );
    }

    return details.length > 0 ? details : null;
  };

  if (loading) {
    return (
      <div className="recording-detail-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading recording details...</p>
        </div>
      </div>
    );
  }

  if (!recording) {
    return (
      <div className="recording-detail-page">
        <div className="error-container">
          <div className="error-icon">❌</div>
          <h2>Recording not found</h2>
          <p>The requested recording could not be loaded.</p>
          <button className="btn-back" onClick={() => onNavigate('recordings-library')}>
            Back to Recordings
          </button>
        </div>
      </div>
    );
  }

  const timeline = recording.timeline || [];
  const fields = recording.fields || [];

  return (
    <div className="recording-detail-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('recordings-library')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <h1 className="page-title">
          📹 {recording.name || recording.title || `Recording ${sessionId}`}
        </h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="detail-content">
        {/* Recording Info Section */}
        <div className="info-section">
          <h2 className="section-title">Recording Information</h2>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Created:</span>
              <span className="info-value">{formatTimestamp(recording.created_at)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Operations:</span>
              <span className="info-value">{timeline.length}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Extracted Fields:</span>
              <span className="info-value">{fields.length}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Session ID:</span>
              <span className="info-value code">{sessionId}</span>
            </div>
          </div>
        </div>

        {/* Operations Timeline Section */}
        <div className="timeline-section">
          <h2 className="section-title">Operations Timeline</h2>

          {timeline.length === 0 ? (
            <div className="empty-message">
              <p>No operations recorded.</p>
            </div>
          ) : (
            <div className="timeline-list">
              {timeline.map((operation, index) => {
                const isCopyAction = operation.type === 'copy_action';

                return (
                  <div
                    key={index}
                    className={`timeline-item ${isCopyAction ? 'copy-action' : ''}`}
                  >
                    <div className="timeline-marker">
                      <span className="step-number">{operation.step || index + 1}</span>
                    </div>

                    <div className="timeline-content">
                      <div className="action-header">
                        <span className="action-timestamp">
                          {operation.timestamp}
                        </span>
                        <span className="action-label">
                          {getOperationTypeLabel(operation.type)}
                        </span>
                        {isCopyAction && <span className="copy-badge">⭐ Data Extract</span>}
                      </div>

                      <div className="action-details">
                        {renderOperationDetails(operation)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Extracted Fields Section */}
        {fields.length > 0 && (
          <div className="fields-section">
            <h2 className="section-title">Extracted Fields ({fields.length})</h2>
            <div className="fields-table-container">
              <table className="fields-table">
                <thead>
                  <tr>
                    <th>Field Name</th>
                    <th>XPath</th>
                    <th>Sample Value</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((field, index) => (
                    <tr key={index}>
                      <td className="field-name">{field.name || `field_${index + 1}`}</td>
                      <td className="field-selector code">{field.xpath || 'N/A'}</td>
                      <td className="field-value">{field.sample_value ? `"${field.sample_value.substring(0, 80)}${field.sample_value.length > 80 ? '...' : ''}"` : 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Generate Workflow Button */}
        <div className="action-section">
          <button className="btn-generate-workflow" onClick={handleGenerateWorkflow}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Generate Workflow
          </button>
          <p className="action-hint">
            AI will analyze this recording and create an executable workflow
          </p>
        </div>
      </div>
    </div>
  );
}

export default RecordingDetailPage;
