import React, { useState, useEffect } from 'react';
import '../styles/MetaflowPreviewPage.css';
import yaml from 'js-yaml';

const API_BASE = "http://127.0.0.1:8765";

function MetaflowPreviewPage({ onNavigate, showStatus, metaflowId, metaflowYaml }) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [metaflowData, setMetaflowData] = useState(null);
  const [activeTab, setActiveTab] = useState('visual'); // 'visual' or 'yaml'

  useEffect(() => {
    if (metaflowYaml) {
      setYamlContent(metaflowYaml);

      // Parse YAML to get structured data for visualization
      try {
        const parsed = yaml.load(metaflowYaml);
        setMetaflowData(parsed);
      } catch (error) {
        console.error('Failed to parse MetaFlow YAML:', error);
        showStatus('⚠️ Failed to parse MetaFlow structure', 'warning');
      }
    }
  }, [metaflowYaml]);

  const handleConfirmAndGenerate = async () => {
    if (!metaflowId) {
      showStatus('❌ No MetaFlow ID provided', 'error');
      return;
    }

    setIsGenerating(true);
    showStatus('✨ Generating workflow from MetaFlow...', 'info');

    try {
      const response = await fetch(`${API_BASE}/api/workflows/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metaflow_id: metaflowId,
          user_id: "default_user"
        })
      });

      if (!response.ok) {
        throw new Error(`Workflow generation failed: ${response.status}`);
      }

      const data = await response.json();

      showStatus('✅ Workflow generated successfully!', 'success');

      // Navigate to workflow detail page directly
      const workflowName = data.workflow_name;
      setTimeout(() => {
        onNavigate('workflow-detail', { workflowId: workflowName });
      }, 500);
    } catch (error) {
      console.error('Error generating workflow:', error);
      showStatus(`❌ Failed to generate workflow: ${error.message}`, 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCancel = () => {
    onNavigate('main');
  };

  // Helper functions for visualization (similar to Chrome Extension)
  const getNodeIcon = (type) => {
    switch (type) {
      case 'start':
        return '🚀';
      case 'navigate':
        return '🌐';
      case 'click':
      case 'interact':
        return '👆';
      case 'extract':
      case 'copy_action':
        return '📊';
      case 'type':
      case 'input':
        return '⌨️';
      case 'loop':
        return '🔄';
      case 'branch':
        return '🔀';
      case 'end':
        return '✅';
      default:
        return '📌';
    }
  };

  const getNodeColor = (type) => {
    switch (type) {
      case 'start':
        return '#10b981';
      case 'navigate':
        return '#8b5cf6';
      case 'click':
      case 'interact':
        return '#f59e0b';
      case 'extract':
      case 'copy_action':
        return '#3b82f6';
      case 'type':
      case 'input':
        return '#06b6d4';
      case 'loop':
        return '#ec4899';
      case 'branch':
        return '#f59e0b';
      case 'end':
        return '#10b981';
      default:
        return '#6b7280';
    }
  };

  const renderNode = (node, index) => {
    const nodeType = node.type || 'process';
    const nodeName = node.name || node.intent_name || `Step ${index + 1}`;
    const nodeDescription = node.description || node.intent_description || '';

    return (
      <div key={index} className="metaflow-node-wrapper">
        <div
          className="metaflow-node"
          style={{ borderColor: getNodeColor(nodeType) }}
        >
          <div className="node-icon" style={{ backgroundColor: getNodeColor(nodeType) }}>
            {getNodeIcon(nodeType)}
          </div>
          <div className="node-content">
            <div className="node-name">{nodeName}</div>
            {nodeDescription && (
              <div className="node-description">{nodeDescription}</div>
            )}
            {node.operations && node.operations.length > 0 && (
              <div className="node-meta">
                {node.operations.length} operation{node.operations.length !== 1 ? 's' : ''}
              </div>
            )}
          </div>
        </div>
        {index < (metaflowData?.nodes?.length || 0) - 1 && (
          <div className="node-connector">
            <svg width="24" height="40" viewBox="0 0 24 40">
              <line x1="12" y1="0" x2="12" y2="32" stroke="#d1d5db" strokeWidth="2"/>
              <polygon points="12,40 8,32 16,32" fill="#d1d5db"/>
            </svg>
          </div>
        )}
      </div>
    );
  };

  const renderVisualTab = () => {
    if (!metaflowData || !metaflowData.nodes) {
      return (
        <div className="empty-state">
          <p>No MetaFlow structure available</p>
        </div>
      );
    }

    return (
      <div className="visual-container">
        <div className="metaflow-flow">
          {metaflowData.nodes.map((node, index) => renderNode(node, index))}
        </div>
      </div>
    );
  };

  const renderYamlTab = () => {
    return (
      <div className="yaml-container">
        <pre className="yaml-content">
          <code>{yamlContent || 'Loading MetaFlow...'}</code>
        </pre>
      </div>
    );
  };

  return (
    <div className="metaflow-preview-page">
      {/* Header */}
      <div className="page-header">
        <button className="back-button" onClick={handleCancel}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <h1 className="page-title">📋 Review MetaFlow</h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="preview-content">
        {/* Instructions */}
        <div className="instructions-section">
          <div className="instruction-icon">👀</div>
          <h2>Review Generated MetaFlow</h2>
          <p>
            The AI has analyzed your task and created a MetaFlow (intermediate workflow structure).
            Please review it below before generating the final executable workflow.
          </p>
        </div>

        {/* Tabs */}
        <div className="tabs-section">
          <div className="tabs-header">
            <button
              className={`tab-button ${activeTab === 'visual' ? 'active' : ''}`}
              onClick={() => setActiveTab('visual')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="7" height="7"/>
                <rect x="14" y="3" width="7" height="7"/>
                <rect x="14" y="14" width="7" height="7"/>
                <rect x="3" y="14" width="7" height="7"/>
              </svg>
              <span>Visual</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
              onClick={() => setActiveTab('yaml')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="16 18 22 12 16 6"/>
                <polyline points="8 6 2 12 8 18"/>
              </svg>
              <span>YAML</span>
            </button>
          </div>

          <div className="tabs-content">
            {activeTab === 'visual' ? renderVisualTab() : renderYamlTab()}
          </div>

          <div className="metaflow-info">
            <div className="info-badge">
              <span className="badge-label">ID:</span>
              <span className="badge-value">{metaflowId || 'N/A'}</span>
            </div>
            {metaflowData?.nodes && (
              <div className="info-badge">
                <span className="badge-label">Nodes:</span>
                <span className="badge-value">{metaflowData.nodes.length}</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="action-buttons-section">
          <button
            className="btn-cancel"
            onClick={handleCancel}
            disabled={isGenerating}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
            <span>Cancel</span>
          </button>

          <button
            className="btn-confirm"
            onClick={handleConfirmAndGenerate}
            disabled={!metaflowId || isGenerating}
          >
            {isGenerating ? (
              <>
                <div className="btn-spinner"></div>
                <span>Generating Workflow...</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span>Confirm & Generate Workflow</span>
              </>
            )}
          </button>
        </div>

        {/* Help Text */}
        <div className="help-text">
          <p>
            💡 <strong>What is a MetaFlow?</strong> It's a high-level description of the workflow steps
            before they are converted into executable code. Review it to ensure the AI understood your task correctly.
          </p>
        </div>
      </div>
    </div>
  );
}

export default MetaflowPreviewPage;
