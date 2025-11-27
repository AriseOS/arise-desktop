import React, { useState, useEffect } from 'react';
import '../styles/RecordingsLibraryPage.css';

const API_BASE = "http://127.0.0.1:8765";

function RecordingsLibraryPage({ onNavigate, showStatus }) {
  const [recordings, setRecordings] = useState([]);
  const [filteredRecordings, setFilteredRecordings] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }

  // Fetch recordings from API
  useEffect(() => {
    const fetchRecordings = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/recordings`);

        if (!response.ok) {
          throw new Error(`Failed to fetch recordings: ${response.status}`);
        }

        const data = await response.json();
        setRecordings(data.recordings || []);
        setFilteredRecordings(data.recordings || []);
      } catch (error) {
        console.error('Error fetching recordings:', error);
        showStatus(`❌ Failed to load recordings: ${error.message}`, 'error');
        setRecordings([]);
        setFilteredRecordings([]);
      } finally {
        setLoading(false);
      }
    };

    fetchRecordings();
  }, []);

  // Search filter
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredRecordings(recordings);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = recordings.filter(recording => {
      const urlMatch = recording.url?.toLowerCase().includes(query);
      const fieldsMatch = recording.fields?.some(field =>
        field.toLowerCase().includes(query)
      );
      const sessionMatch = recording.session_id?.toLowerCase().includes(query);

      return urlMatch || fieldsMatch || sessionMatch;
    });

    setFilteredRecordings(filtered);
  }, [searchQuery, recordings]);

  const handleViewDetails = (sessionId) => {
    onNavigate('recording-detail', { sessionId });
  };

  const handleGenerateWorkflow = async (sessionId) => {
    showStatus('✨ Generating MetaFlow from recording...', 'info');

    try {
      const response = await fetch(`${API_BASE}/api/metaflows/from-recording`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: "Auto-generated workflow from recording",
          user_id: "default_user"
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

  const handleDeleteClick = (sessionId) => {
    const recording = recordings.find(r => r.session_id === sessionId);
    const recordingName = (recording?.title && recording.title !== "Untitled Recording")
      ? recording.title
      : `Recording ${sessionId}`;

    setDeleteConfirm({ sessionId, recordingName });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { sessionId } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus('🗑️ Deleting recording...', 'info');

      const url = `${API_BASE}/api/recordings/${sessionId}?user_id=default_user`;
      const response = await fetch(url, {
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete recording: ${response.status}`);
      }

      // Remove from local state
      setRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      setFilteredRecordings(prev => prev.filter(r => r.session_id !== sessionId));

      showStatus('✅ Recording deleted successfully', 'success');
    } catch (error) {
      console.error('Error deleting recording:', error);
      showStatus(`❌ Failed to delete recording: ${error.message}`, 'error');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(null);
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return 'Unknown';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minutes ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    if (diffDays < 7) return `${diffDays} days ago`;

    return date.toLocaleDateString();
  };

  const getFieldsPreview = (fields) => {
    if (!fields || fields.length === 0) return 'No fields';

    const preview = fields.slice(0, 3).join(', ');
    if (fields.length > 3) {
      return `${preview}...`;
    }
    return preview;
  };

  if (loading) {
    return (
      <div className="recordings-library-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading recordings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="recordings-library-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <h1 className="page-title">📚 Recordings Library</h1>
        <div className="header-spacer"></div>
      </div>

      {/* Search Bar */}
      <div className="search-section">
        <div className="search-input-wrapper">
          <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Search by URL, field name, or session ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Results Count */}
      <div className="results-info">
        <p className="results-count">
          {filteredRecordings.length === 0
            ? 'No recordings found'
            : `${filteredRecordings.length} recording${filteredRecordings.length === 1 ? '' : 's'}`}
        </p>
      </div>

      {/* Recordings List */}
      <div className="recordings-list">
        {filteredRecordings.length === 0 ? (
          <div className="empty-state">
            {recordings.length === 0 ? (
              <>
                <div className="empty-icon">📹</div>
                <h3>No recordings yet</h3>
                <p>Start recording a new workflow to see it here.</p>
                <button className="btn-start-recording" onClick={() => onNavigate('quick-start')}>
                  <span className="button-icon">🎬</span>
                  <span>Start Recording</span>
                </button>
              </>
            ) : (
              <>
                <div className="empty-icon">🔍</div>
                <h3>No results found</h3>
                <p>Try adjusting your search query.</p>
                <button className="btn-clear-search" onClick={() => setSearchQuery('')}>
                  Clear Search
                </button>
              </>
            )}
          </div>
        ) : (
          filteredRecordings.map((recording) => (
            <div key={recording.session_id} className="recording-card">
              <div className="recording-header">
                <div className="recording-icon">📹</div>
                <div className="recording-info">
                  <h3 className="recording-title">
                    {(recording.title && recording.title !== "Untitled Recording")
                      ? recording.title
                      : `Recording ${recording.session_id}`}
                  </h3>
                  <div className="recording-meta">
                    <span className="meta-item">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                      </svg>
                      {formatDate(recording.created_at)}
                    </span>
                    <span className="meta-item">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                      </svg>
                      {recording.action_count || 0} operations
                    </span>
                    <span className="meta-item">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="3" y="3" width="7" height="7"/>
                        <rect x="14" y="3" width="7" height="7"/>
                        <rect x="14" y="14" width="7" height="7"/>
                        <rect x="3" y="14" width="7" height="7"/>
                      </svg>
                      {recording.field_count || 0} fields
                    </span>
                  </div>
                  {recording.fields && recording.fields.length > 0 && (
                    <div className="recording-fields">
                      <span className="fields-label">Fields:</span>
                      <span className="fields-value">{getFieldsPreview(recording.fields)}</span>
                    </div>
                  )}
                  {recording.url && (
                    <div className="recording-url">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="2" y1="12" x2="22" y2="12"/>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                      </svg>
                      <span className="url-text">{recording.url}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="recording-actions">
                <button
                  className="btn-action primary"
                  onClick={() => handleViewDetails(recording.session_id)}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                  View Details
                </button>
                <button
                  className="btn-action secondary"
                  onClick={() => handleGenerateWorkflow(recording.session_id)}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                  </svg>
                  Generate Workflow
                </button>
                <button
                  className="btn-delete"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteClick(recording.session_id);
                  }}
                  title="Delete recording"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={handleDeleteCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Confirm Delete</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete <strong>"{deleteConfirm.recordingName}"</strong>?</p>
              <p className="warning-text">This action cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                Cancel
              </button>
              <button className="btn-confirm-delete" onClick={handleDeleteConfirm}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default RecordingsLibraryPage;
