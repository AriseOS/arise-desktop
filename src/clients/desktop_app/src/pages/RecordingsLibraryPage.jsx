import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import '../styles/RecordingsLibraryPage.css';

const API_BASE = "http://127.0.0.1:8765";

function RecordingsLibraryPage({ session, onNavigate, showStatus }) {
  const userId = session?.username;
  const [recordings, setRecordings] = useState([]);
  const [filteredRecordings, setFilteredRecordings] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }
  const [metaflowIds, setMetaflowIds] = useState({}); // { sessionId: metaflowId }

  // Fetch recordings from API
  useEffect(() => {
    if (!userId) return;

    const fetchRecordings = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/recordings?user_id=${userId}`);

        if (!response.ok) {
          throw new Error(`Failed to fetch recordings: ${response.status}`);
        }

        const data = await response.json();
        setRecordings(data.recordings || []);
        setFilteredRecordings(data.recordings || []);

        // Asynchronously fetch metaflow_id for each recording
        (data.recordings || []).forEach(async (recording) => {
          try {
            const detailResponse = await fetch(`${API_BASE}/api/recordings/${recording.session_id}?user_id=${userId}`);
            if (detailResponse.ok) {
              const detail = await detailResponse.json();
              if (detail.metaflow_id) {
                setMetaflowIds(prev => ({
                  ...prev,
                  [recording.session_id]: detail.metaflow_id
                }));
              }
            }
          } catch (err) {
            // Silently ignore errors for individual recordings
            console.debug(`Could not fetch metaflow_id for ${recording.session_id}`);
          }
        });
      } catch (error) {
        console.error('Error fetching recordings:', error);
        showStatus(`Failed to load recordings: ${error.message}`, 'error');
        setRecordings([]);
        setFilteredRecordings([]);
      } finally {
        setLoading(false);
      }
    };

    fetchRecordings();
  }, [userId]);

  // Search filter
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredRecordings(recordings);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = recordings.filter(recording => {
      const nameMatch = recording.task_metadata?.name?.toLowerCase().includes(query);
      const sessionMatch = recording.session_id?.toLowerCase().includes(query);

      return nameMatch || sessionMatch;
    });

    setFilteredRecordings(filtered);
  }, [searchQuery, recordings]);

  const handleViewDetails = (sessionId) => {
    onNavigate('recording-detail', { sessionId });
  };

  const handleViewMetaflow = (metaflowId) => {
    onNavigate('metaflow-preview', { metaflowId });
  };

  const handleGenerateWorkflow = async (sessionId) => {
    showStatus('Generating MetaFlow from recording...', 'info');

    try {
      const response = await fetch(`${API_BASE}/api/metaflows/from-recording`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: "Auto-generated workflow from recording",
          user_id: userId
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to generate MetaFlow: ${response.status}`);
      }

      const data = await response.json();

      // Update metaflowIds state so the button appears immediately
      setMetaflowIds(prev => ({
        ...prev,
        [sessionId]: data.metaflow_id
      }));

      showStatus('MetaFlow generated! Please review.', 'success');

      // Navigate to MetaFlow preview page
      setTimeout(() => {
        onNavigate('metaflow-preview', {
          metaflowId: data.metaflow_id,
          metaflowYaml: data.metaflow_yaml
        });
      }, 500);
    } catch (error) {
      console.error('Error generating MetaFlow:', error);
      showStatus(`Failed to generate MetaFlow: ${error.message}`, 'error');
    }
  };

  const handleDeleteClick = (sessionId) => {
    const recording = recordings.find(r => r.session_id === sessionId);
    const recordingName = recording?.task_metadata?.name || `Recording ${sessionId}`;

    setDeleteConfirm({ sessionId, recordingName });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { sessionId } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus('Deleting recording...', 'info');

      const url = `${API_BASE}/api/recordings/${sessionId}?user_id=${userId}`;
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
      setMetaflowIds(prev => {
        const updated = { ...prev };
        delete updated[sessionId];
        return updated;
      });

      showStatus('Recording deleted successfully', 'success');
    } catch (error) {
      console.error('Error deleting recording:', error);
      showStatus(`Failed to delete recording: ${error.message}`, 'error');
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
        <button className="btn-icon" onClick={() => onNavigate('main')} aria-label="Go Back">
          <Icon name="arrowLeft" />
        </button>
        <h1 className="page-title"><Icon name="book" /> Recordings Library</h1>
        <div className="header-spacer"></div>
      </div>

      {/* Search Bar */}
      <div className="search-section">
        <div className="search-input-wrapper">
          <span className="search-icon">
            <Icon name="search" />
          </span>
          <input
            type="text"
            className="search-input"
            placeholder="Search by URL, field name, or session ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              <Icon name="x" />
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
                <div className="empty-icon"><Icon name="video" /></div>
                <h3>No recordings yet</h3>
                <p>Start recording a new workflow to see it here.</p>
                <button className="btn-start-recording" onClick={() => onNavigate('quick-start')}>
                  <span className="button-icon"><Icon name="video" /></span>
                  <span>Start Recording</span>
                </button>
              </>
            ) : (
              <>
                <div className="empty-icon"><Icon name="search" /></div>
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
                <div className="recording-icon"><Icon name="video" /></div>
                <div className="recording-info">
                  <h3 className="recording-title">
                    {recording.task_metadata?.name || `Recording ${recording.session_id}`}
                  </h3>
                  <div className="recording-meta">
                    <span className="meta-item">
                      <Icon name="clock" />
                      {formatDate(recording.created_at)}
                    </span>
                    <span className="meta-item">
                      <Icon name="activity" />
                      {recording.action_count || 0} operations
                    </span>
                  </div>
                </div>
              </div>

              <div className="recording-actions">
                <button
                  className="btn btn-primary"
                  onClick={() => handleViewDetails(recording.session_id)}
                >
                  <Icon name="eye" />
                  View Details
                </button>
                {metaflowIds[recording.session_id] ? (
                  <button
                    className="btn btn-primary"
                    onClick={() => handleViewMetaflow(metaflowIds[recording.session_id])}
                  >
                    <Icon name="fileText" />
                    View MetaFlow
                  </button>
                ) : (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleGenerateWorkflow(recording.session_id)}
                  >
                    <Icon name="zap" />
                    Generate Workflow
                  </button>
                )}
                <button
                  className="btn-icon-danger"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteClick(recording.session_id);
                  }}
                  title="Delete recording"
                >
                  <Icon name="trash" />
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
              <button className="btn btn-danger-solid" onClick={handleDeleteConfirm}>
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
