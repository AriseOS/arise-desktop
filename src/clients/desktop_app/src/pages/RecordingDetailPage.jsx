import React, { useState, useEffect } from 'react';
import '../styles/RecordingDetailPage.css';

const API_BASE = "http://127.0.0.1:8765";

function RecordingDetailPage({ session, onNavigate, showStatus, sessionId }) {
  const userId = session?.username || 'userId';
  const [recording, setRecording] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('timeline'); // 'timeline' or 'yaml'
  const [isEditingQuery, setIsEditingQuery] = useState(false);
  const [editedQuery, setEditedQuery] = useState('');

  const handleSaveQuery = async () => {
    if (!editedQuery.trim()) {
      showStatus('⚠️ Query cannot be empty', 'warning');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/recording/update-metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: recording.task_metadata?.task_description || "",
          user_query: editedQuery,
          user_id: "userId"
        })
      });

      if (!response.ok) {
        throw new Error('Failed to update query');
      }

      // Update local state
      setRecording(prev => ({
        ...prev,
        task_metadata: {
          ...prev.task_metadata,
          user_query: editedQuery
        }
      }));

      setIsEditingQuery(false);
      showStatus('✅ User query updated!', 'success');
    } catch (error) {
      console.error('Error updating query:', error);
      showStatus(`❌ Failed to update query: ${error.message}`, 'error');
    }
  };

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
    showStatus('✨ Generating MetaFlow from recording...', 'info');

    try {
      // Extract task_description and user_query from recording metadata
      const task_description = recording.task_metadata?.task_description || "Auto-generated workflow from recording";
      const user_query = recording.task_metadata?.user_query;

      const response = await fetch(`${API_BASE}/api/metaflows/from-recording`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: task_description,
          user_query: user_query,  // Pass user_query to backend
          user_id: "userId"
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to generate MetaFlow: ${response.status}`);
      }

      const data = await response.json();

      showStatus('✅ MetaFlow generated! Please review.', 'success');

      // Navigate to MetaFlow preview page
      setTimeout(() => {
        onNavigate('metaflow-preview', {
          metaflowId: data.metaflow_id,
          metaflowYaml: data.metaflow_yaml
        });
      }, 500);
    } catch (error) {
      console.error('Error generating MetaFlow:', error);
      showStatus(`❌ Failed to generate MetaFlow: ${error.message}`, 'error');
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
    if (!operation) return null;

    const details = [];
    const type = operation.type;
    const element = operation.element || {};
    const data = operation.data || {};

    // For navigate operations
    if (type === 'navigate') {
      if (operation.url) {
        details.push(
          <div key="url" className="action-detail">
            <span className="detail-label">URL:</span>
            <span className="detail-value url-link">{operation.url}</span>
          </div>
        );
      }
      if (operation.page_title) {
        details.push(
          <div key="page_title" className="action-detail">
            <span className="detail-label">Page Title:</span>
            <span className="detail-value">"{operation.page_title}"</span>
          </div>
        );
      }
    }

    // For click operations
    if (type === 'click') {
      if (element.textContent) {
        const displayText = element.textContent.trim();
        details.push(
          <div key="element_text" className="action-detail highlight-action">
            <span className="detail-label">👆 Clicked on:</span>
            <span className="detail-value clicked-text">"{displayText.substring(0, 100)}{displayText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (element.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{element.xpath}</span>
          </div>
        );
      }
      if (element.tagName) {
        details.push(
          <div key="tag" className="action-detail">
            <span className="detail-label">Tag:</span>
            <span className="detail-value code">{element.tagName}</span>
          </div>
        );
      }
    }

    // For input/type operations
    if (type === 'input' || type === 'type') {
      if (data.value) {
        details.push(
          <div key="value" className="action-detail">
            <span className="detail-label">Input Value:</span>
            <span className="detail-value">"{data.value}"</span>
          </div>
        );
      }
      if (element.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{element.xpath}</span>
          </div>
        );
      }
    }

    // For select operations
    if (type === 'select') {
      if (data.selectedText) {
        const selectedText = data.selectedText.trim();
        details.push(
          <div key="selected_text" className="action-detail highlight-action">
            <span className="detail-label">📋 Selected:</span>
            <span className="detail-value selected-text">"{selectedText.substring(0, 100)}{selectedText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (element.textContent && element.textContent !== data.selectedText) {
        const elementText = element.textContent.trim();
        details.push(
          <div key="element_text" className="action-detail">
            <span className="detail-label">From Element:</span>
            <span className="detail-value">"{elementText.substring(0, 100)}{elementText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (element.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{element.xpath}</span>
          </div>
        );
      }
    }

    // For copy_action operations
    if (type === 'copy_action') {
      if (data.copiedText) {
        details.push(
          <div key="copied_text" className="action-detail field-mapping">
            <span className="detail-label">📋 Copied Text:</span>
            <span className="detail-value field-value">"{data.copiedText}"</span>
          </div>
        );
      }
      if (element.xpath) {
        details.push(
          <div key="xpath" className="action-detail">
            <span className="detail-label">XPath:</span>
            <span className="detail-value code">{element.xpath}</span>
          </div>
        );
      }
    }

    // For scroll operations
    if (type === 'scroll') {
      if (data.direction) {
        details.push(
          <div key="direction" className="action-detail">
            <span className="detail-label">Direction:</span>
            <span className="detail-value">{data.direction}</span>
          </div>
        );
      }
    }

    // For test operations
    if (type === 'test') {
      if (data.message) {
        details.push(
          <div key="message" className="action-detail">
            <span className="detail-label">Message:</span>
            <span className="detail-value">{data.message}</span>
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

  const operations = recording.operations || [];
  const fields = recording.fields || [];

  return (
    <div className="recording-detail-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('recordings-library')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="page-title">
          📹 {recording.task_metadata?.name || `Recording ${sessionId}`}
        </h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="detail-content">
        {/* Recording Info Section */}
        <div className="info-section">
          <h2 className="section-title">Recording Information</h2>

          {/* Task Metadata */}
          {recording.task_metadata && Object.keys(recording.task_metadata).length > 0 && (
            <div className="task-metadata-section">
              {recording.task_metadata.task_description && (
                <div className="metadata-item">
                  <span className="metadata-label">📝 Task Description:</span>
                  <span className="metadata-value">{recording.task_metadata.task_description}</span>
                </div>
              )}
              <div className="metadata-item">
                <span className="metadata-label">🎯 User Query:</span>
                {isEditingQuery ? (
                  <div className="edit-query-container">
                    <input
                      type="text"
                      className="edit-query-input"
                      value={editedQuery}
                      onChange={(e) => setEditedQuery(e.target.value)}
                      autoFocus
                    />
                    <div className="edit-actions">
                      <button className="btn-save-mini" onClick={handleSaveQuery}>✅</button>
                      <button className="btn-cancel-mini" onClick={() => setIsEditingQuery(false)}>❌</button>
                    </div>
                  </div>
                ) : (
                  <div className="metadata-value-container">
                    <span className="metadata-value">
                      {recording.task_metadata.user_query || "No query provided"}
                    </span>
                    <button
                      className="btn-edit-icon"
                      onClick={() => {
                        setEditedQuery(recording.task_metadata.user_query || "");
                        setIsEditingQuery(true);
                      }}
                      title="Edit User Query"
                    >
                      ✏️
                    </button>
                  </div>
                )}
              </div>
              {recording.task_metadata.session_id && (
                <div className="metadata-item">
                  <span className="metadata-label">🔖 Session ID:</span>
                  <span className="metadata-value">{recording.task_metadata.session_id}</span>
                </div>
              )}
            </div>
          )}

          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Created:</span>
              <span className="info-value">{formatTimestamp(recording.created_at)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Operations:</span>
              <span className="info-value">{operations.length}</span>
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

          {/* Linked MetaFlow */}
          {recording.metaflow_id && (
            <div className="linked-entity-section">
              <div className="linked-entity-item">
                <span className="linked-label">Linked MetaFlow:</span>
                <button
                  className="linked-value-button"
                  onClick={() => onNavigate('metaflow-preview', { metaflowId: recording.metaflow_id })}
                >
                  {recording.metaflow_id}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Tab Section */}
        <div className="tab-section">
          {/* Tab Header */}
          <div className="tab-header">
            <button
              className={`tab-button ${activeTab === 'timeline' ? 'active' : ''}`}
              onClick={() => setActiveTab('timeline')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="20" x2="12" y2="10" />
                <line x1="18" y1="20" x2="18" y2="4" />
                <line x1="6" y1="20" x2="6" y2="16" />
              </svg>
              <span>Timeline</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
              onClick={() => setActiveTab('yaml')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
              <span>YAML</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'timeline' ? (
              <div className="timeline-section">
                <h2 className="section-title">Operations Timeline</h2>

                {operations.length === 0 ? (
                  <div className="empty-message">
                    <p>No operations recorded.</p>
                  </div>
                ) : (
                  <div className="timeline-list">
                    {operations.map((operation, index) => {
                      const isCopyAction = operation.type === 'copy_action';

                      return (
                        <div
                          key={index}
                          className={`timeline-item ${isCopyAction ? 'copy-action' : ''}`}
                        >
                          <div className="timeline-marker">
                            <span className="step-number">{index + 1}</span>
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
            ) : (
              <div className="yaml-section">
                <h2 className="section-title">Recording Data (JSON)</h2>
                <div className="yaml-container">
                  <pre className="yaml-content">
                    <code>{JSON.stringify(recording, null, 2)}</code>
                  </pre>
                </div>
              </div>
            )}
          </div>
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
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
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
