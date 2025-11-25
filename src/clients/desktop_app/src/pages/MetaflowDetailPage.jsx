import React, { useState, useEffect } from 'react';
import '../styles/MetaflowDetailPage.css';
import FlowVisualization from '../components/FlowVisualization';
import yaml from 'js-yaml';

const API_BASE = "http://127.0.0.1:8765";

function MetaflowDetailPage({ onNavigate, showStatus, metaflowId }) {
  const [metaflow, setMetaflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('preview'); // 'preview' or 'yaml'
  const [isGeneratingWorkflow, setIsGeneratingWorkflow] = useState(false);

  // Fetch MetaFlow details
  useEffect(() => {
    const fetchMetaflowDetails = async () => {
      if (!metaflowId) {
        showStatus('No MetaFlow ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/metaflows/${metaflowId}?user_id=default_user`);

        if (!response.ok) {
          throw new Error(`Failed to fetch MetaFlow: ${response.status}`);
        }

        const data = await response.json();
        setMetaflow(data);
      } catch (error) {
        console.error('Error fetching MetaFlow:', error);
        showStatus(`Failed to load MetaFlow: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchMetaflowDetails();
  }, [metaflowId]);

  const handleGenerateWorkflow = async () => {
    if (isGeneratingWorkflow) return;

    setIsGeneratingWorkflow(true);
    showStatus('Generating Workflow from MetaFlow...', 'info');

    try {
      const response = await fetch(`${API_BASE}/api/workflows/from-metaflow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metaflow_id: metaflowId,
          user_id: "default_user"
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to generate Workflow: ${response.status}`);
      }

      const data = await response.json();

      showStatus('Workflow generated successfully!', 'success');

      // Navigate to Workflow detail page
      setTimeout(() => {
        onNavigate('workflow-detail', {
          workflowId: data.workflow_id
        });
      }, 500);
    } catch (error) {
      console.error('Error generating Workflow:', error);
      showStatus(`Failed to generate Workflow: ${error.message}`, 'error');
    } finally {
      setIsGeneratingWorkflow(false);
    }
  };

  const handleModifyMetaflow = () => {
    // Navigate to MetaFlow preview page for modification
    onNavigate('metaflow-preview', {
      metaflowId: metaflowId,
      metaflowYaml: metaflow.metaflow_yaml
    });
  };

  const handleViewWorkflow = () => {
    if (metaflow.workflow_id) {
      onNavigate('workflow-detail', {
        workflowId: metaflow.workflow_id
      });
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const parseMetaflowYaml = (yamlContent) => {
    try {
      // Simple YAML parsing for display purposes
      const lines = yamlContent.split('\n');
      const result = {
        task: '',
        context: '',
        steps: []
      };

      let currentSection = null;
      let currentStep = null;

      for (const line of lines) {
        const trimmed = line.trim();

        if (trimmed.startsWith('task:')) {
          result.task = trimmed.substring(5).trim().replace(/^["']|["']$/g, '');
        } else if (trimmed.startsWith('context:')) {
          result.context = trimmed.substring(8).trim().replace(/^["']|["']$/g, '');
        } else if (trimmed === 'steps:') {
          currentSection = 'steps';
        } else if (currentSection === 'steps' && trimmed.startsWith('- id:')) {
          currentStep = {
            id: trimmed.substring(5).trim(),
            action: '',
            params: {}
          };
          result.steps.push(currentStep);
        } else if (currentStep && trimmed.startsWith('action:')) {
          currentStep.action = trimmed.substring(7).trim();
        } else if (currentStep && trimmed.startsWith('target:')) {
          currentStep.params.target = trimmed.substring(7).trim().replace(/^["']|["']$/g, '');
        } else if (currentStep && trimmed.startsWith('value:')) {
          currentStep.params.value = trimmed.substring(6).trim().replace(/^["']|["']$/g, '');
        } else if (currentStep && trimmed.startsWith('description:')) {
          currentStep.description = trimmed.substring(12).trim().replace(/^["']|["']$/g, '');
        }
      }

      return result;
    } catch (error) {
      console.error('Error parsing MetaFlow YAML:', error);
      return null;
    }
  };

  if (loading) {
    return (
      <div className="metaflow-detail-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading MetaFlow details...</p>
        </div>
      </div>
    );
  }

  if (!metaflow) {
    return (
      <div className="metaflow-detail-page">
        <div className="error-container">
          <div className="error-icon">Not found</div>
          <h2>MetaFlow not found</h2>
          <p>The requested MetaFlow could not be loaded.</p>
          <button className="btn-back" onClick={() => onNavigate('recordings-library')}>
            Back to Recordings
          </button>
        </div>
      </div>
    );
  }

  const parsedMetaflow = parseMetaflowYaml(metaflow.metaflow_yaml || '');

  return (
    <div className="metaflow-detail-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('recordings-library')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="page-title">
          MetaFlow Details
        </h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="detail-content">
        {/* MetaFlow Info Section */}
        <div className="info-section">
          <h2 className="section-title">MetaFlow Information</h2>

          <div className="metadata-section">
            <div className="metadata-item">
              <span className="metadata-label">User Query:</span>
              <span className="metadata-value">{metaflow.user_query || 'N/A'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">MetaFlow ID:</span>
              <span className="metadata-value code">{metaflowId}</span>
            </div>
          </div>

          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Created:</span>
              <span className="info-value">{formatTimestamp(metaflow.created_at)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Updated:</span>
              <span className="info-value">{formatTimestamp(metaflow.updated_at)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Workflow:</span>
              {metaflow.workflow_id ? (
                <span className="info-value link" onClick={handleViewWorkflow}>
                  {metaflow.workflow_id}
                </span>
              ) : (
                <span className="info-value">Not generated</span>
              )}
            </div>
          </div>
        </div>

        {/* Tab Section */}
        <div className="tab-section">
          <div className="tab-header">
            <button
              className={`tab-button ${activeTab === 'preview' ? 'active' : ''}`}
              onClick={() => setActiveTab('preview')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span>Preview</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'visual' ? 'active' : ''}`}
              onClick={() => setActiveTab('visual')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
              <span>Visual</span>
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

          <div className="tab-content">
            {activeTab === 'preview' && parsedMetaflow ? (
              <div className="preview-section">
                {/* Task Overview */}
                <div className="task-overview">
                  <h3>Task</h3>
                  <p className="task-description">{parsedMetaflow.task || 'No task defined'}</p>
                  {parsedMetaflow.context && (
                    <>
                      <h3>Context</h3>
                      <p className="task-context">{parsedMetaflow.context}</p>
                    </>
                  )}
                </div>

                {/* Steps */}
                {parsedMetaflow.steps && parsedMetaflow.steps.length > 0 && (
                  <div className="steps-section">
                    <h3>Steps ({parsedMetaflow.steps.length})</h3>
                    <div className="steps-list">
                      {parsedMetaflow.steps.map((step, index) => (
                        <div key={step.id || index} className="step-item">
                          <div className="step-marker">
                            <span className="step-number">{index + 1}</span>
                          </div>
                          <div className="step-content">
                            <div className="step-header">
                              <span className="step-action">{step.action}</span>
                              <span className="step-id">{step.id}</span>
                            </div>
                            {step.description && (
                              <p className="step-description">{step.description}</p>
                            )}
                            {Object.keys(step.params).length > 0 && (
                              <div className="step-params">
                                {Object.entries(step.params).map(([key, value]) => (
                                  <div key={key} className="param-item">
                                    <span className="param-key">{key}:</span>
                                    <span className="param-value">{value}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : activeTab === 'visual' ? (
              <div className="visual-section" style={{ height: '600px', background: '#fff', borderRadius: '8px', overflow: 'hidden' }}>
                <FlowVisualization
                  data={(() => {
                    try {
                      return yaml.load(metaflow.metaflow_yaml);
                    } catch (e) {
                      console.error("Failed to parse YAML for visual", e);
                      return null;
                    }
                  })()}
                  type="metaflow"
                />
              </div>
            ) : activeTab === 'yaml' ? (
              <div className="yaml-section">
                <div className="yaml-container">
                  <pre className="yaml-content">
                    <code>{metaflow.metaflow_yaml || 'No YAML content'}</code>
                  </pre>
                </div>
              </div>
            ) : (
              <div className="empty-section">
                <p>Unable to parse MetaFlow content</p>
              </div>
            )}
          </div>
        </div>

        {/* Action Section */}
        <div className="action-section">
          <div className="action-buttons">
            <button
              className="btn-primary"
              onClick={handleGenerateWorkflow}
              disabled={isGeneratingWorkflow || metaflow.workflow_id}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              {metaflow.workflow_id ? 'Workflow Generated' : isGeneratingWorkflow ? 'Generating...' : 'Generate Workflow'}
            </button>
            <button className="btn-secondary" onClick={handleModifyMetaflow}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              Modify MetaFlow
            </button>
          </div>
          {metaflow.workflow_id && (
            <p className="action-hint">
              Workflow already generated. Click to view or modify the MetaFlow.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default MetaflowDetailPage;
