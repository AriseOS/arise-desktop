import React, { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingDetailPage.css';

function RecordingDetailPage({ session, onNavigate, showStatus, sessionId }) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [recording, setRecording] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('timeline'); // 'timeline', 'doms', or 'yaml'
  const [isEditingQuery, setIsEditingQuery] = useState(false);
  const [editedQuery, setEditedQuery] = useState('');

  const handleSaveQuery = async () => {
    if (!editedQuery.trim()) {
      showStatus(t('recordingDetail.queryEmpty'), 'warning');
      return;
    }

    try {
      await api.callAppBackend(`/api/v1/recordings/${sessionId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          task_description: recording.task_metadata?.task_description || "",
          user_query: editedQuery,
          user_id: userId
        })
      });

      // Update local state
      setRecording(prev => ({
        ...prev,
        task_metadata: {
          ...prev.task_metadata,
          user_query: editedQuery
        }
      }));

      setIsEditingQuery(false);
      showStatus(t('recordingDetail.queryUpdated'), 'success');
    } catch (error) {
      console.error('Error updating query:', error);
      showStatus(`${t('recordingDetail.queryUpdateFailed')}: ${error.message}`, 'error');
    }
  };

  // Fetch recording details from API
  useEffect(() => {
    const fetchRecordingDetails = async () => {
      if (!sessionId) {
        showStatus('No session ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const data = await api.callAppBackend(`/api/v1/recordings/${sessionId}?user_id=${userId}`);
        setRecording(data);
      } catch (error) {
        console.error('Error fetching recording details:', error);
        showStatus(`Failed to load recording: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchRecordingDetails();
  }, [sessionId]);

  const handleGenerateWorkflow = () => {
    // Navigate to generation page with recording info
    onNavigate('generation', {
      recordingId: sessionId,
      recordingName: recording?.task_metadata?.task_description || recording?.session_id,
      taskDescription: recording?.task_metadata?.task_description || '',
      userQuery: recording?.task_metadata?.user_query || ''
    });
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
      'click': t('recordingDetail.click'),
      'input': t('recordingDetail.input'),
      'navigate': t('recordingDetail.navigate'),
      'scroll': t('recordingDetail.scroll'),
      'select': t('recordingDetail.select'),
      'submit': t('recordingDetail.submit'),
      'hover': t('recordingDetail.hover'),
      'copy_action': t('recordingDetail.copyAction'),
      'test': t('recordingDetail.test'),
      'type': t('recordingDetail.type'),
      'fill': t('recordingDetail.fill')
    };
    return typeLabels[type] || `${type.charAt(0).toUpperCase() + type.slice(1)}`;
  };

  const getOperationIcon = (type) => {
    const typeIcons = {
      'click': 'mousePointer',
      'input': 'keyboard',
      'navigate': 'globe',
      'scroll': 'scroll',
      'select': 'list',
      'submit': 'checkCircle',
      'hover': 'hand',
      'copy_action': 'clipboard',
      'test': 'flask',
      'type': 'keyboard',
      'fill': 'edit'
    };
    return typeIcons[type] || 'activity';
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
            <span className="detail-label">{t('recordingDetail.url')}:</span>
            <span className="detail-value url-link">{operation.url}</span>
          </div>
        );
      }
      if (operation.page_title) {
        details.push(
          <div key="page_title" className="action-detail">
            <span className="detail-label">{t('recordingDetail.pageTitle')}:</span>
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
            <span className="detail-label"><Icon icon="mousePointer" size={14} /> {t('recordingDetail.clickedOn')}:</span>
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
            <span className="detail-label">{t('recordingDetail.tag')}:</span>
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
            <span className="detail-label">{t('recordingDetail.inputValue')}:</span>
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
            <span className="detail-label"><Icon icon="checkSquare" size={14} /> {t('recordingDetail.selected')}:</span>
            <span className="detail-value selected-text">"{selectedText.substring(0, 100)}{selectedText.length > 100 ? '...' : ''}"</span>
          </div>
        );
      }
      if (element.textContent && element.textContent !== data.selectedText) {
        const elementText = element.textContent.trim();
        details.push(
          <div key="element_text" className="action-detail">
            <span className="detail-label">{t('recordingDetail.fromElement')}:</span>
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
            <span className="detail-label"><Icon icon="clipboard" size={14} /> {t('recordingDetail.copiedText')}:</span>
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
            <span className="detail-label">{t('recordingDetail.direction')}:</span>
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
            <span className="detail-label">{t('recordingDetail.message')}:</span>
            <span className="detail-value">{data.message}</span>
          </div>
        );
      }
    }

    // Show URL for all operations (if available and not navigate)
    if (type !== 'navigate' && operation.url) {
      details.push(
        <div key="operation_url" className="action-detail url-context">
          <span className="detail-label">{t('recordingDetail.page')}:</span>
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
          <p>{t('recordingDetail.loading')}</p>
        </div>
      </div>
    );
  }

  if (!recording) {
    return (
      <div className="recording-detail-page">
        <div className="error-container">
          <div className="error-icon"><Icon icon="alertCircle" size={64} /></div>
          <h2>{t('recordingDetail.notFound')}</h2>
          <p>{t('recordingDetail.loadFailed')}</p>
          <button className="btn-back" onClick={() => onNavigate('recordings-library')}>
            {t('recordingDetail.backToLibrary')}
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
          <Icon icon="arrowLeft" />
        </button>
        <h1 className="page-title">
          <Icon icon="video" /> {recording.task_metadata?.name || `Recording ${sessionId}`}
        </h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="detail-content">
        {/* Recording Info Section */}
        <div className="info-section">
          <h2 className="section-title">{t('recordingDetail.infoTitle')}</h2>

          {/* Task Metadata */}
          {recording.task_metadata && Object.keys(recording.task_metadata).length > 0 && (
            <div className="task-metadata-section">
              {recording.task_metadata.task_description && (
                <div className="metadata-item">
                  <span className="metadata-label"><Icon icon="fileText" size={16} /> {t('recordingDetail.taskDescription')}:</span>
                  <span className="metadata-value">{recording.task_metadata.task_description}</span>
                </div>
              )}
              <div className="metadata-item">
                <span className="metadata-label"><Icon icon="target" size={16} /> {t('recordingDetail.userQuery')}:</span>
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
                      <button className="btn-save-mini" onClick={handleSaveQuery}><Icon icon="check" size={14} /></button>
                      <button className="btn-cancel-mini" onClick={() => setIsEditingQuery(false)}><Icon icon="x" size={14} /></button>
                    </div>
                  </div>
                ) : (
                  <div className="metadata-value-container">
                    <span className="metadata-value">
                      {recording.task_metadata.user_query || t('recordingDetail.noQuery')}
                    </span>
                    <button
                      className="btn-edit-icon"
                      onClick={() => {
                        setEditedQuery(recording.task_metadata.user_query || "");
                        setIsEditingQuery(true);
                      }}
                      title={t('recordingDetail.editQuery')}
                    >
                      <Icon icon="edit" size={14} />
                    </button>
                  </div>
                )}
              </div>
              {recording.task_metadata.session_id && (
                <div className="metadata-item">
                  <span className="metadata-label"><Icon icon="tag" size={16} /> {t('recordingDetail.sessionId')}:</span>
                  <span className="metadata-value">{recording.task_metadata.session_id}</span>
                </div>
              )}
            </div>
          )}

          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">{t('recordingDetail.created')}:</span>
              <span className="info-value">{formatTimestamp(recording.created_at)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('recordingDetail.operationsCount')}:</span>
              <span className="info-value">{operations.length}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('recordingDetail.fieldsCount')}:</span>
              <span className="info-value">{fields.length}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('recordingDetail.sessionId')}:</span>
              <span className="info-value code">{sessionId}</span>
            </div>
          </div>

          {/* Linked Workflow */}
          {recording.workflow_id && (
            <div className="linked-entity-section">
              <div className="linked-entity-item">
                <span className="linked-label">{t('recordingDetail.linkedWorkflow')}:</span>
                <button
                  className="linked-value-button"
                  onClick={() => onNavigate('workflow-detail', { workflowId: recording.workflow_id })}
                >
                  {recording.workflow_id}
                  <Icon icon="externalLink" size={14} />
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
              <Icon icon="list" />
              <span>{t('recordingDetail.timeline')}</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'doms' ? 'active' : ''}`}
              onClick={() => setActiveTab('doms')}
            >
              <Icon icon="code" />
              <span>{t('recordingDetail.doms')}</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
              onClick={() => setActiveTab('yaml')}
            >
              <Icon icon="fileText" />
              <span>{t('recordingDetail.yaml')}</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'timeline' && (
              <div className="timeline-section">
                <h2 className="section-title">{t('recordingDetail.operationsTimeline')}</h2>

                {operations.length === 0 ? (
                  <div className="empty-message">
                    <p>{t('recordingDetail.noOperations')}</p>
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
                                <Icon icon={getOperationIcon(operation.type)} size={16} />
                                {getOperationTypeLabel(operation.type)}
                              </span>
                              {isCopyAction && <span className="copy-badge"><Icon icon="star" size={12} /> Data Extract</span>}
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
            )}

            {activeTab === 'doms' && (
              <div className="doms-section">
                <h2 className="section-title">{t('recordingDetail.domSnapshots')} ({recording.dom_snapshots ? Object.keys(recording.dom_snapshots).length : 0})</h2>
                {!recording.dom_snapshots || Object.keys(recording.dom_snapshots).length === 0 ? (
                  <div className="empty-message">
                    <p>{t('recordingDetail.noDoms')}</p>
                  </div>
                ) : (
                  <div className="dom-list">
                    {Object.keys(recording.dom_snapshots).map((url, index) => (
                      <div key={index} className="dom-item">
                        <div className="dom-header">
                          <span className="dom-index">#{index + 1}</span>
                          <span className="dom-url">{url}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === 'yaml' && (
              <div className="yaml-section">
                <h2 className="section-title">{t('recordingDetail.recordingData')}</h2>
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
            <h2 className="section-title">{t('recordingDetail.fieldsTitle')} ({fields.length})</h2>
            <div className="fields-table-container">
              <table className="fields-table">
                <thead>
                  <tr>
                    <th>{t('recordingDetail.fieldName')}</th>
                    <th>{t('recordingDetail.xpath')}</th>
                    <th>{t('recordingDetail.sampleValue')}</th>
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
            <Icon icon="zap" />
            {t('recordingDetail.generateWorkflow')}
          </button>
          <p className="action-hint">
            {t('recordingDetail.generateHint')}
          </p>
        </div>
      </div>
    </div>
  );
}

export default RecordingDetailPage;
