import React, { useState, useEffect } from 'react';
import '../styles/ExecutionResultPage.css';

const API_BASE = "http://127.0.0.1:8765";

function ExecutionResultPage({
  session,
  onNavigate,
  showStatus,
  workflowId,
  executionId
}) {
  const userId = session?.username || 'default_user';
  const [workflowName, setWorkflowName] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [executionStats, setExecutionStats] = useState(null);
  const [scrapedData, setScrapedData] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch execution results from API
  useEffect(() => {
    const fetchResults = async () => {
      if (!executionId) {
        showStatus('❌ No execution ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/execution/${executionId}/results`);
        if (!response.ok) {
          throw new Error(`Failed to fetch results: ${response.status}`);
        }

        const data = await response.json();
        setExecutionStats(data.stats);
        setScrapedData(data.results || []);
        setWorkflowName(data.workflow_name || 'Workflow');
      } catch (error) {
        console.error('Error fetching results:', error);
        showStatus(`❌ Failed to load results: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchResults();
  }, [executionId]);

  const handleDownload = (format) => {
    showStatus(`📥 Downloading data as ${format.toUpperCase()}...`, 'info');
    // Mock download
    setTimeout(() => {
      showStatus(`✅ Downloaded successfully as ${format.toUpperCase()}!`, 'success');
    }, 1000);
  };

  const handleRunAgain = () => {
    showStatus('▶️ Starting workflow execution...', 'info');
    setTimeout(() => {
      onNavigate('execution-monitor', { workflowId });
    }, 500);
  };

  const handleSaveWorkflow = () => {
    if (!workflowName.trim()) {
      showStatus('❌ Please enter a workflow name', 'error');
      return;
    }

    showStatus('💾 Saving workflow...', 'info');
    setTimeout(() => {
      showStatus(`✅ Workflow "${workflowName}" saved successfully!`, 'success');
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
          <p>Loading results...</p>
        </div>
      </div>
    );
  }

  if (!executionStats) {
    return (
      <div className="execution-result-page">
        <div className="error-container">
          <div className="error-icon">❌</div>
          <h2>Failed to load results</h2>
          <button className="btn-back" onClick={() => onNavigate('main')}>
            Back to Home
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
          <div className="success-icon">🎉</div>
          <h1 className="success-title">Execution Successful!</h1>
          <p className="success-subtitle">
            Scraped {executionStats.totalRecords || 0} records in {executionStats.duration || 'N/A'}
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="result-content">
        {/* Data Preview */}
        <div className="data-preview-section">
          <div className="section-header">
            <div className="header-left">
              <h2>📊 Data Preview</h2>
              <span className="data-count">
                {scrapedData.length > 0
                  ? `Showing first ${Math.min(10, scrapedData.length)} of ${executionStats.totalRecords || scrapedData.length} records`
                  : 'No data available'}
              </span>
            </div>
            <div className="header-right">
              <button className="btn-download" onClick={() => handleDownload('excel')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Download Excel
              </button>
              <button className="btn-download secondary" onClick={() => handleDownload('csv')}>
                Download CSV
              </button>
              <button className="btn-download secondary" onClick={() => handleDownload('json')}>
                Download JSON
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
                <p>Total {executionStats.totalRecords || scrapedData.length} records • Showing first {Math.min(10, scrapedData.length)} rows</p>
              </div>
            </>
          ) : (
            <div className="no-data-message">
              <p>No data was extracted from this execution.</p>
            </div>
          )}
        </div>

        {/* Save Workflow Section */}
        <div className="save-workflow-section">
          <div className="save-card">
            <div className="save-icon">💾</div>
            <h3>Want to use this workflow again?</h3>
            <p>Save it for easy access and reuse</p>

            <div className="workflow-name-input">
              <label>Workflow Name:</label>
              <input
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                placeholder="Enter workflow name..."
                onFocus={() => setIsEditingName(true)}
                onBlur={() => setIsEditingName(false)}
              />
            </div>

            <button className="btn-save-workflow" onClick={handleSaveWorkflow}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
              Save Workflow
            </button>
          </div>
        </div>

        {/* Next Actions */}
        <div className="next-actions-section">
          <h3>What's next?</h3>
          <div className="action-cards">
            <div className="action-card" onClick={handleRunAgain}>
              <div className="action-icon">▶️</div>
              <h4>Run Again</h4>
              <p>Execute this workflow again with the same settings</p>
            </div>

            <div className="action-card" onClick={handleCreateNew}>
              <div className="action-icon">🆕</div>
              <h4>Create New Workflow</h4>
              <p>Record a new workflow for a different task</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('main')}>
              <div className="action-icon">🏠</div>
              <h4>Back to Home</h4>
              <p>Return to the main dashboard</p>
            </div>
          </div>
        </div>

        {/* First-time User Celebration */}
        {localStorage.getItem('firstSuccessfulRun') !== 'true' && (
          <div className="first-time-celebration">
            <div className="celebration-content">
              <h3>🎉 Congratulations on your first automation!</h3>
              <p>You've just saved approximately <strong>30 minutes</strong> of manual work.</p>
              <button
                className="btn-got-it"
                onClick={() => {
                  localStorage.setItem('firstSuccessfulRun', 'true');
                  document.querySelector('.first-time-celebration').style.display = 'none';
                }}
              >
                Got it!
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Execution Info Footer */}
      <div className="execution-info-footer">
        <div className="info-item">
          <span className="info-label">Status:</span>
          <span className="info-value success">
            {executionStats.status === 'success' ? '✅ Success' : '❌ Failed'}
          </span>
        </div>
        <div className="info-item">
          <span className="info-label">Duration:</span>
          <span className="info-value">{executionStats.duration || 'N/A'}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Completed:</span>
          <span className="info-value">{executionStats.timestamp || 'N/A'}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Records:</span>
          <span className="info-value">{executionStats.totalRecords || 0}</span>
        </div>
      </div>
    </div>
  );
}

export default ExecutionResultPage;
