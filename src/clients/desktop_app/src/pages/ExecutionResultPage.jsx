import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/ExecutionResultPage.css';

function ExecutionResultPage({
  session,
  onNavigate,
  showStatus,
  workflowId,
  taskId
}) {
  const { t } = useTranslation();
  const userId = session?.username;
  const [workflowName, setWorkflowName] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [executionStats, setExecutionStats] = useState(null);
  const [scrapedData, setScrapedData] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch execution results from API
  useEffect(() => {
    const fetchResults = async () => {
      if (!taskId) {
        showStatus('No task ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const data = await api.callAppBackend(`/api/v1/executions/${taskId}/results`);
        setExecutionStats(data.stats);
        setScrapedData(data.results || []);
        setWorkflowName(data.workflow_name || 'Workflow');
      } catch (error) {
        console.error('Error fetching results:', error);
        showStatus(`${t('workflowResult.failedTitle')}: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchResults();
  }, [taskId]);

  const handleDownload = (format) => {
    showStatus(t('workflowResult.downloading', { format: format.toUpperCase() }), 'info');
    // Mock download
    setTimeout(() => {
      showStatus(t('workflowResult.downloadSuccess', { format: format.toUpperCase() }), 'success');
    }, 1000);
  };

  const handleRunAgain = async () => {
    showStatus(t('workflowResult.startExecution'), 'info');
    try {
      const result = await api.executeWorkflow(workflowId, userId);
      const newTaskId = result.task_id;
      showStatus(t('workflowResult.startedRedirecting'), 'success');
      setTimeout(() => {
        onNavigate('workflow-execution-live', {
          taskId: newTaskId,
          workflowName: workflowName
        });
      }, 500);
    } catch (error) {
      console.error('Failed to start workflow:', error);
      showStatus(t('workflowResult.startFailed', { error: error.message }), 'error');
    }
  };

  const handleSaveWorkflow = () => {
    if (!workflowName.trim()) {
      showStatus(t('workflowResult.enterName'), 'error');
      return;
    }

    showStatus(t('workflowResult.saving'), 'info');
    setTimeout(() => {
      showStatus(t('workflowResult.savedSuccess', { name: workflowName }), 'success');
      setTimeout(() => {
        onNavigate('workflows');
      }, 1500);
    }, 1000);
  };

  const handleCreateNew = () => {
    onNavigate('quick-start');
  };

  const getColumns = () => {
    if (scrapedData.length === 0) return [];
    return Object.keys(scrapedData[0]).filter(key => key !== 'id');
  };

  if (loading) {
    return (
      <div className="execution-result-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>{t('workflowResult.loading')}</p>
        </div>
      </div>
    );
  }

  if (!executionStats) {
    return (
      <div className="execution-result-page">
        <div className="error-container">
          <div className="error-icon"><Icon icon="alertCircle" size={64} /></div>
          <h2>{t('workflowResult.failedTitle')}</h2>
          <button className="btn-back" onClick={() => onNavigate('main')}>
            {t('workflowResult.backToHome')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="execution-result-page">
      {/* Success Header */}
      <div className="result-header">
        <div className="success-celebration">
          <div className="success-icon"><Icon icon="checkCircle" size={48} /></div>
          <h1 className="success-title">{t('workflowResult.successTitle')}</h1>
          <p className="success-subtitle">
            {t('workflowResult.scrapedSummary', {
              count: executionStats.totalRecords || 0,
              duration: executionStats.duration || 'N/A'
            })}
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="result-content">
        {/* Data Preview */}
        <div className="data-preview-section">
          <div className="section-header">
            <div className="header-left">
              <h2><Icon icon="barChart" size={20} /> {t('workflowResult.dataPreview')}</h2>
              <span className="data-count">
                {scrapedData.length > 0
                  ? t('workflowResult.showingRecords', {
                    count: Math.min(10, scrapedData.length),
                    total: executionStats.totalRecords || scrapedData.length
                  })
                  : t('workflowResult.noDataAvailable')}
              </span>
            </div>
            <div className="header-right">
              <button className="btn-download" onClick={() => handleDownload('excel')}>
                <Icon icon="download" />
                {t('workflowResult.downloadExcel')}
              </button>
              <button className="btn-download secondary" onClick={() => handleDownload('csv')}>
                {t('workflowResult.downloadCSV')}
              </button>
              <button className="btn-download secondary" onClick={() => handleDownload('json')}>
                {t('workflowResult.downloadJSON')}
              </button>
            </div>
          </div>

          {scrapedData.length > 0 ? (
            <>
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      {getColumns().map(column => (
                        <th key={column}>{column.replace(/_/g, ' ').toUpperCase()}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scrapedData.slice(0, 10).map((row, idx) => (
                      <tr key={idx}>
                        {getColumns().map(column => (
                          <td key={column}>{row[column]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="table-footer">
                <p>{t('workflowResult.rowsInfo', {
                  total: executionStats.totalRecords || scrapedData.length,
                  shown: Math.min(10, scrapedData.length)
                })}</p>
              </div>
            </>
          ) : (
            <div className="no-data-message">
              <p>{t('workflowResult.noDataMessage')}</p>
            </div>
          )}
        </div>

        {/* Save Workflow Section */}
        <div className="save-workflow-section">
          <div className="save-card">
            <div className="save-icon"><Icon icon="save" size={24} /></div>
            <h3>{t('workflowResult.saveWorkflowTitle')}</h3>
            <p>{t('workflowResult.saveWorkflowDesc')}</p>

            <div className="workflow-name-input">
              <label>{t('workflowResult.workflowNameLabel')}</label>
              <input
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                placeholder={t('workflowResult.workflowNamePlaceholder')}
                onFocus={() => setIsEditingName(true)}
                onBlur={() => setIsEditingName(false)}
              />
            </div>

            <button className="btn-save-workflow" onClick={handleSaveWorkflow}>
              <Icon icon="save" />
              {t('workflowResult.saveWorkflowBtn')}
            </button>
          </div>
        </div>

        {/* Next Actions */}
        <div className="next-actions-section">
          <h3>{t('workflowResult.whatsNext')}</h3>
          <div className="action-cards">
            <div className="action-card" onClick={handleRunAgain}>
              <div className="action-icon"><Icon icon="play" size={24} /></div>
              <h4>{t('workflowResult.runAgain')}</h4>
              <p>{t('workflowResult.runAgainDesc')}</p>
            </div>

            <div className="action-card" onClick={handleCreateNew}>
              <div className="action-icon"><Icon icon="plusCircle" size={24} /></div>
              <h4>{t('workflowResult.createNew')}</h4>
              <p>{t('workflowResult.createNewDesc')}</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('main')}>
              <div className="action-icon"><Icon icon="home" size={24} /></div>
              <h4>{t('workflowResult.backToDashboard')}</h4>
              <p>{t('workflowResult.backToDashboardDesc')}</p>
            </div>
          </div>
        </div>

        {/* First-time User Celebration */}
        {localStorage.getItem('firstSuccessfulRun') !== 'true' && (
          <div className="first-time-celebration">
            <div className="celebration-content">
              <h3><Icon icon="star" size={24} /> {t('workflowResult.firstTime.title')}</h3>
              <p dangerouslySetInnerHTML={{ __html: t('workflowResult.firstTime.content').replace('30 minutes', '<strong>30 minutes</strong>').replace('30 分钟', '<strong>30 分钟</strong>') }}></p>
              <button
                className="btn-got-it"
                onClick={() => {
                  localStorage.setItem('firstSuccessfulRun', 'true');
                  document.querySelector('.first-time-celebration').style.display = 'none';
                }}
              >
                {t('workflowResult.firstTime.gotIt')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Execution Info Footer */}
      <div className="execution-info-footer">
        <div className="info-item">
          <span className="info-label">{t('workflowResult.status')}:</span>
          <span className="info-value success">
            {executionStats.status === 'success' ? <><Icon icon="checkCircle" size={14} /> Success</> : <><Icon icon="x" size={14} /> Failed</>}
          </span>
        </div>
        <div className="info-item">
          <span className="info-label">{t('workflowResult.duration')}:</span>
          <span className="info-value">{executionStats.duration || 'N/A'}</span>
        </div>
        <div className="info-item">
          <span className="info-label">{t('workflowResult.completed')}:</span>
          <span className="info-value">{executionStats.timestamp || 'N/A'}</span>
        </div>
        <div className="info-item">
          <span className="info-label">{t('workflowResult.records')}:</span>
          <span className="info-value">{executionStats.totalRecords || 0}</span>
        </div>
      </div>
    </div>
  );
}

export default ExecutionResultPage;
