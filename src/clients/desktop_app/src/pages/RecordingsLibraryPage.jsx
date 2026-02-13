import React, { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingsLibraryPage.css';

function RecordingsLibraryPage({ session, onNavigate, showStatus }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [recordings, setRecordings] = useState([]);
  const [filteredRecordings, setFilteredRecordings] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }
  const [workflowIds, setWorkflowIds] = useState({}); // { sessionId: workflowId }
  const [addingToMemory, setAddingToMemory] = useState({}); // { sessionId: boolean }

  // Fetch recordings from API
  useEffect(() => {
    if (!userId) return;

    const fetchRecordings = async () => {
      try {
        const data = await api.callAppBackend(`/api/v1/recordings?user_id=${userId}`);
        setRecordings(data.recordings || []);
        setFilteredRecordings(data.recordings || []);

        // Asynchronously fetch workflow_id for each recording (if any)
        (data.recordings || []).forEach(async (recording) => {
          try {
            const detail = await api.callAppBackend(`/api/v1/recordings/${recording.session_id}?user_id=${userId}`);
            if (detail.workflow_id) {
              setWorkflowIds(prev => ({
                ...prev,
                [recording.session_id]: detail.workflow_id
              }));
            }
          } catch (err) {
            // Silently ignore errors for individual recordings
            console.debug(`Could not fetch workflow_id for ${recording.session_id}`);
          }
        });
      } catch (error) {
        console.error('Error fetching recordings:', error);
        showStatus(`${t('recordingsLibrary.loadFailed')}: ${error.message}`, 'error');
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

  const handleReplay = (sessionId, recordingName) => {
    onNavigate('replay', {
      sessionId: sessionId,
      userId: userId,
      recordingName: recordingName || sessionId
    });
  };

  const handleViewWorkflow = async (workflowId, sessionId) => {
    try {
      // Verify workflow still exists before navigating
      await api.callAppBackend(`/api/v1/workflows/${workflowId}?user_id=${userId}`);
      onNavigate('workflow-detail', { workflowId });
    } catch (error) {
      // Workflow was deleted, clear the cached workflow_id
      setWorkflowIds(prev => {
        const updated = { ...prev };
        delete updated[sessionId];
        return updated;
      });

      // Clear workflow_id from local recording via daemon API
      try {
        await api.callAppBackend(`/api/v1/recordings/${sessionId}/workflow?user_id=${userId}`, {
          method: 'DELETE'
        });
      } catch (updateError) {
        console.error('Failed to clear workflow_id from recording:', updateError);
      }

      showStatus(t('recordingsLibrary.workflowDeleted'), 'info');
    }
  };

  const handleGenerateWorkflow = (sessionId) => {
    // Get recording info for the generation page
    const recording = recordings.find(r => r.session_id === sessionId);
    const recordingName = recording?.task_metadata?.name || `${t('recordingsLibrary.recordingTitlePrefix')} ${sessionId}`;

    // Navigate to the dedicated generation page with recording info
    onNavigate('generation', {
      recordingId: sessionId,
      recordingName: recordingName,
      taskDescription: recording?.task_metadata?.task_description || '',
      userQuery: recording?.task_metadata?.user_query || ''
    });
  };

  const handleDeleteClick = (sessionId) => {
    const recording = recordings.find(r => r.session_id === sessionId);
    const recordingName = recording?.task_metadata?.name || `${t('recordingsLibrary.recordingTitlePrefix')} ${sessionId}`;

    setDeleteConfirm({ sessionId, recordingName });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { sessionId } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus(t('recordingsLibrary.deleting'), 'info');

      await api.callAppBackend(`/api/v1/recordings/${sessionId}?user_id=${userId}`, {
        method: 'DELETE'
      });

      // Remove from local state
      setRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      setFilteredRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      setWorkflowIds(prev => {
        const updated = { ...prev };
        delete updated[sessionId];
        return updated;
      });

      showStatus(t('recordingsLibrary.deleteSuccess'), 'success');
    } catch (error) {
      console.error('Error deleting recording:', error);
      showStatus(`${t('recordingsLibrary.deleteFailed')}: ${error.message}`, 'error');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(null);
  };

  const handleAddToMemory = async (sessionId) => {
    if (addingToMemory[sessionId]) return;

    setAddingToMemory(prev => ({ ...prev, [sessionId]: true }));
    try {
      const result = await api.addToMemory(userId, {
        recordingId: sessionId,
        generateEmbeddings: true
      });

      if (result.success) {
        const message = t('recordingDetail.addedToMemory', {
          states: result.states_added,
          merged: result.states_merged,
          sequences: result.intent_sequences_added
        }) || `Added to memory: ${result.states_added} states, ${result.states_merged} merged, ${result.intent_sequences_added} sequences`;
        showStatus(message, 'success');
      } else {
        showStatus(t('recordingDetail.addToMemoryFailed') || 'Failed to add to memory', 'error');
      }
    } catch (error) {
      console.error('Error adding to memory:', error);
      showStatus(`${t('recordingDetail.addToMemoryFailed') || 'Failed to add to memory'}: ${error.message}`, 'error');
    } finally {
      setAddingToMemory(prev => ({ ...prev, [sessionId]: false }));
    }
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return 'Unknown';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return t('recordingsLibrary.time.justNow');
    if (diffMins < 60) return t('recordingsLibrary.time.minutesAgo', { count: diffMins });
    if (diffHours < 24) return t('recordingsLibrary.time.hoursAgo', { count: diffHours });
    if (diffDays < 7) return t('recordingsLibrary.time.daysAgo', { count: diffDays });

    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="recordings-library-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>{t('common.loading')}</p>
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
        <h1 className="page-title"><Icon name="book" /> {t('recordingsLibrary.title')}</h1>
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
            placeholder={t('recordingsLibrary.searchPlaceholder')}
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
            ? t('recordingsLibrary.noRecordingsFound')
            : `${filteredRecordings.length} ${filteredRecordings.length === 1 ? t('recordingsLibrary.recordingUnit') : t('recordingsLibrary.recordingsUnit')}`}
        </p>
      </div>

      {/* Recordings List */}
      <div className="recordings-list">
        {filteredRecordings.length === 0 ? (
          <div className="empty-state">
            {recordings.length === 0 ? (
              <>
                <div className="empty-icon"><Icon name="video" /></div>
                <h3>{t('recordingsLibrary.noRecordingsYet')}</h3>
                <p>{t('recordingsLibrary.startRecordingDesc')}</p>
                <button className="btn-start-recording" onClick={() => onNavigate('quick-start')}>
                  <span className="button-icon"><Icon name="video" /></span>
                  <span>{t('recordingsLibrary.startRecording')}</span>
                </button>
              </>
            ) : (
              <>
                <div className="empty-icon"><Icon name="search" /></div>
                <h3>{t('recordingsLibrary.noResultsFound')}</h3>
                <p>{t('recordingsLibrary.adjustQuery')}</p>
                <button className="btn-clear-search" onClick={() => setSearchQuery('')}>
                  {t('recordingsLibrary.clearSearch')}
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
                    {recording.task_metadata?.name || `${t('recordingsLibrary.recordingTitlePrefix')} ${recording.session_id}`}
                  </h3>
                  <div className="recording-meta">
                    <span className="meta-item">
                      <Icon name="clock" />
                      {formatDate(recording.created_at)}
                    </span>
                    <span className="meta-item">
                      <Icon name="activity" />
                      {recording.action_count || 0} {t('recordingsLibrary.operations')}
                    </span>
                    <span className="meta-item">
                      <Icon name="code" />
                      {recording.dom_count || 0} {t('recordingsLibrary.doms')}
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
                  {t('recordingsLibrary.viewDetails')}
                </button>
                <button
                  className="btn btn-success"
                  onClick={() => handleReplay(recording.session_id, recording.task_metadata?.name)}
                >
                  <Icon name="play" />
                  Replay
                </button>
                {workflowIds[recording.session_id] ? (
                  <button
                    className="btn btn-primary"
                    onClick={() => handleViewWorkflow(workflowIds[recording.session_id], recording.session_id)}
                  >
                    <Icon name="fileText" />
                    {t('recordingsLibrary.viewWorkflow')}
                  </button>
                ) : (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleGenerateWorkflow(recording.session_id)}
                  >
                    <Icon name="zap" />
                    {t('recordingsLibrary.generateWorkflow')}
                  </button>
                )}
                <button
                  className="btn btn-secondary"
                  onClick={() => handleAddToMemory(recording.session_id)}
                  disabled={addingToMemory[recording.session_id]}
                >
                  <Icon name={addingToMemory[recording.session_id] ? 'loader' : 'database'} />
                  {addingToMemory[recording.session_id]
                    ? (t('recordingDetail.addingToMemory') || 'Adding...')
                    : (t('recordingDetail.addToMemory') || 'Add to Memory')}
                </button>
                <button
                  className="btn-icon-danger"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteClick(recording.session_id);
                  }}
                  title={t('recordingsLibrary.deleteRecording')}
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
              <h3>{t('recordingsLibrary.confirmDelete')}</h3>
            </div>
            <div className="modal-body">
              <p dangerouslySetInnerHTML={{ __html: t('recordingsLibrary.deleteMessage', { name: `<strong>${deleteConfirm.recordingName}</strong>` }) }}></p>
              <p className="warning-text">{t('recordingsLibrary.undoneWarning')}</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                {t('recordingsLibrary.cancel')}
              </button>
              <button className="btn btn-danger-solid" onClick={handleDeleteConfirm}>
                {t('recordingsLibrary.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default RecordingsLibraryPage;
