import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/UserFlowsPage.css';

function UserFlowsPage({ session, onNavigate, showStatus, version }) {
  const { t, i18n } = useTranslation();
  const userId = session?.username;
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecording, setSelectedRecording] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }

  useEffect(() => {
    if (userId) {
      loadRecordings();
    }
  }, [userId]);

  const loadRecordings = async () => {
    try {
      setLoading(true);
      showStatus(t('userFlows.toasts.loadLoading'), "info");

      const data = await api.callAppBackend(`/api/v1/recordings?user_id=${userId}`);
      setRecordings(data.recordings || []);
      showStatus(t('userFlows.toasts.loadSuccess'), "success");

    } catch (error) {
      console.error("Load recordings error:", error);
      showStatus(t('userFlows.toasts.loadFailed'), "error");
      setRecordings([]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewRecording = () => {
    onNavigate("recording");
  };

  const handleQuickGenerate = (recording) => {
    // Navigate to generation page with recording info
    onNavigate('generation', {
      recordingId: recording.session_id,
      recordingName: recording.title || recording.description || recording.session_id,
      taskDescription: recording.description || '',
      userQuery: ''
    });
  };

  const handleDeleteClick = (recording) => {
    const recordingName = recording.title || `Recording ${recording.session_id}`;
    setDeleteConfirm({ sessionId: recording.session_id, recordingName });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { sessionId } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus(t('userFlows.toasts.deleteLoading'), "info");

      await api.callAppBackend(`/api/v1/recordings/${sessionId}?user_id=${userId}`, {
        method: 'DELETE'
      });

      setRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      showStatus(t('userFlows.toasts.deleteSuccess'), "success");

    } catch (error) {
      console.error("Delete recording error:", error);
      showStatus(t('userFlows.toasts.deleteFailed', { error: error.message }), "error");
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(null);
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const locale = i18n.language === 'zh' ? 'zh-CN' : 'en-US';
    return date.toLocaleString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return '#52c41a';
      case 'recording': return '#1890ff';
      case 'failed': return '#ff4d4f';
      default: return '#8c8c8c';
    }
  };

  return (
    <div className="page user-flows-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="video" size={28} /> {t('userFlows.title')}</div>
        <button className="primary-button" onClick={handleNewRecording}>
          <Icon icon="plusCircle" size={20} />
          <span>{t('userFlows.newRecording')}</span>
        </button>
      </div>

      <div className="user-flows-content">
        <div className="page-section">
          <div className="section-header">
            <h3>{t('userFlows.listTitle')}</h3>
            <div className="section-actions">
              <button className="secondary-button" onClick={loadRecordings}>
                <Icon icon="refreshCw" size={16} />
                <span>{t('userFlows.refresh')}</span>
              </button>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>{t('userFlows.loading')}</p>
            </div>
          ) : recordings.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Icon icon="video" size={48} /></div>
              <div className="empty-state-title">{t('userFlows.empty.title')}</div>
              <div className="empty-state-desc">
                {t('userFlows.empty.desc')}
              </div>
              <button className="primary-button" onClick={handleNewRecording}>
                <Icon icon="plusCircle" size={20} />
                <span>{t('userFlows.startRecording')}</span>
              </button>
            </div>
          ) : (
            <div className="recordings-list">
              {recordings.map((recording) => (
                <div key={recording.session_id} className="recording-item">
                  <div className="recording-main">
                    <div className="recording-info">
                      <div className="recording-title">
                        <h4>{recording.title}</h4>
                        <div
                          className="status-badge"
                          style={{ backgroundColor: getStatusColor(recording.status) }}
                        >
                          {recording.status === 'completed' ? t('userFlows.status.completed') :
                            recording.status === 'recording' ? t('userFlows.status.recording') : t('userFlows.status.failed')}
                        </div>
                      </div>

                      <div className="recording-description">
                        {recording.description}
                      </div>

                      <div className="recording-meta">
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="globe" size={14} /></span>
                          <span className="meta-label">{t('userFlows.meta.startUrl')}</span>
                          <span className="meta-value">{recording.url}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="zap" size={14} /></span>
                          <span className="meta-label">{t('userFlows.meta.actions')}</span>
                          <span className="meta-value">{recording.operations_count} {t('userFlows.meta.actionsUnit')}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="calendar" size={14} /></span>
                          <span className="meta-label">{t('userFlows.meta.time')}</span>
                          <span className="meta-value">{formatDate(recording.created_at)}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="hash" size={14} /></span>
                          <span className="meta-label">{t('userFlows.meta.sessionId')}</span>
                          <span className="meta-value">{recording.session_id}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="recording-actions">
                    <button
                      className="action-button primary"
                      onClick={() => handleQuickGenerate(recording)}
                      disabled={selectedRecording === recording.session_id}
                    >
                      {selectedRecording === recording.session_id ? (
                        <>
                          <span className="btn-spinner"></span>
                          <span>{t('userFlows.generating')}</span>
                        </>
                      ) : (
                        <>
                          <Icon icon="play" size={16} />
                          <span>{t('userFlows.generate')}</span>
                        </>
                      )}
                    </button>

                    <button className="action-button secondary">
                      <Icon icon="eye" size={16} />
                      <span>{t('userFlows.details')}</span>
                    </button>

                    <button
                      className="action-button danger"
                      onClick={() => handleDeleteClick(recording)}
                    >
                      <Icon icon="trash2" size={16} />
                      <span>{t('userFlows.delete')}</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="page-section">
          <div className="section-header">
            <h3><Icon icon="bookOpen" size={20} /> {t('userFlows.guide.title')}</h3>
          </div>
          <div className="guide-content">
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="video" size={24} /></div>
              <div className="guide-text">
                <h4>{t('userFlows.guide.recording.title')}</h4>
                <p>{t('userFlows.guide.recording.desc')}</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="zap" size={24} /></div>
              <div className="guide-text">
                <h4>{t('userFlows.guide.generate.title')}</h4>
                <p>{t('userFlows.guide.generate.desc')}</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="search" size={24} /></div>
              <div className="guide-text">
                <h4>{t('userFlows.guide.details.title')}</h4>
                <p>{t('userFlows.guide.details.desc')}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={handleDeleteCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('userFlows.deleteConfirm.title')}</h3>
            </div>
            <div className="modal-body">
              <p>{t('userFlows.deleteConfirm.desc', { name: deleteConfirm.recordingName })}</p>
              <p className="warning-text">{t('userFlows.deleteConfirm.warning')}</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                {t('userFlows.deleteConfirm.cancel')}
              </button>
              <button className="btn-confirm-delete" onClick={handleDeleteConfirm}>
                {t('userFlows.deleteConfirm.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserFlowsPage;
