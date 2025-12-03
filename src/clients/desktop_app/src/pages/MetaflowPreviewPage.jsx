import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import '../styles/MetaflowPreviewPage.css';
import yaml from 'js-yaml';
import FlowVisualization from '../components/FlowVisualization';

const API_BASE = "http://127.0.0.1:8765";

function MetaflowPreviewPage({ session, onNavigate, showStatus, metaflowId, metaflowYaml }) {
  const userId = session?.username;
  const [isGenerating, setIsGenerating] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [metaflowData, setMetaflowData] = useState(null);
  const [activeTab, setActiveTab] = useState('visual'); // 'visual' or 'yaml'

  // Chat/Modification state
  const [chatInput, setChatInput] = useState('');
  const [isModifying, setIsModifying] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [modificationLog, setModificationLog] = useState([]);
  const [currentToolUse, setCurrentToolUse] = useState(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    const fetchMetaflowData = async () => {
      // If metaflowYaml is provided, use it directly
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
      // If only metaflowId is provided, fetch the metaflow data
      else if (metaflowId && !metaflowYaml) {
        try {
          const response = await fetch(`${API_BASE}/api/metaflows/${metaflowId}?user_id=${userId}`);

          if (!response.ok) {
            throw new Error(`Failed to fetch MetaFlow: ${response.status}`);
          }

          const data = await response.json();
          setYamlContent(data.metaflow_yaml);

          // Parse YAML to get structured data for visualization
          try {
            const parsed = yaml.load(data.metaflow_yaml);
            setMetaflowData(parsed);
          } catch (error) {
            console.error('Failed to parse MetaFlow YAML:', error);
            showStatus('⚠️ Failed to parse MetaFlow structure', 'warning');
          }
        } catch (error) {
          console.error('Error fetching MetaFlow:', error);
          showStatus(`Failed to load MetaFlow: ${error.message}`, 'error');
        }
      }
    };

    fetchMetaflowData();
  }, [metaflowYaml, metaflowId]);

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
          user_id: userId
        })
      });

      if (!response.ok) {
        throw new Error(`Workflow generation failed: ${response.status}`);
      }

      const data = await response.json();

      showStatus('✅ Workflow generated successfully!', 'success');

      // Navigate to workflow detail page directly
      // Use workflow_id for navigation (this is the storage ID)
      console.log('Workflow response:', data);
      console.log('Using workflow_id:', data.workflow_id, 'workflow_name:', data.workflow_name);
      const workflowId = data.workflow_id || data.workflow_name;
      setTimeout(() => {
        onNavigate('workflow-detail', { workflowId: workflowId });
      }, 500);
    } catch (error) {
      console.error('Error generating workflow:', error);
      showStatus(`❌ Failed to generate workflow: ${error.message}`, 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCancel = () => {
    // Cleanup session if exists
    if (sessionId) {
      fetch(`${API_BASE}/api/intent-builder/${sessionId}`, {
        method: 'DELETE'
      }).catch(console.error);
    }
    onNavigate('main');
  };

  // Auto-scroll modification log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [modificationLog, currentToolUse]);

  // Handle modification request
  const handleModify = async () => {
    if (!chatInput.trim() || isModifying) return;

    const userMessage = chatInput.trim();
    setChatInput('');
    setIsModifying(true);
    setModificationLog(prev => [...prev, { type: 'user', content: userMessage }]);

    try {
      // Create session if not exists
      let sid = sessionId;
      if (!sid) {
        const response = await fetch(`${API_BASE}/api/intent-builder/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            user_query: `Modify the following MetaFlow based on this request: ${userMessage}`,
            task_description: `Current MetaFlow ID: ${metaflowId}`,
            metaflow_id: metaflowId,  // Pass MetaFlow ID so Agent can save modifications
            // Pass current MetaFlow content so Agent has context
            current_metaflow_yaml: yamlContent,
            phase: 'metaflow'  // Tell Agent we're in MetaFlow phase
          })
        });

        if (!response.ok) throw new Error(`Failed to start session: ${response.statusText}`);

        const result = await response.json();
        sid = result.session_id;
        setSessionId(sid);
      }

      // Stream the modification response
      const response = await fetch(`${API_BASE}/api/intent-builder/${sid}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });

      if (!response.ok) throw new Error(`Request failed: ${response.statusText}`);

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));

              switch (event.type) {
                case 'text':
                  accumulatedText += event.content;
                  break;
                case 'tool_use':
                  setCurrentToolUse({ name: event.tool_name, input: event.tool_input });
                  break;
                case 'tool_result':
                  setCurrentToolUse(null);
                  break;
                case 'complete':
                  setCurrentToolUse(null);
                  if (accumulatedText) {
                    setModificationLog(prev => [...prev, { type: 'assistant', content: accumulatedText }]);
                  }
                  // Reload updated MetaFlow YAML from the response
                  if (event.result?.updated_yaml) {
                    setYamlContent(event.result.updated_yaml);
                    try {
                      const parsed = yaml.load(event.result.updated_yaml);
                      setMetaflowData(parsed);
                    } catch (e) {
                      console.error('Failed to parse updated YAML:', e);
                    }

                    // Sync to local cache (Cloud already saved by Agent)
                    fetch(`${API_BASE}/api/metaflows/${metaflowId}`, {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        user_id: userId,
                        metaflow_yaml: event.result.updated_yaml
                      })
                    }).then(response => {
                      if (response.ok) {
                        console.log('✓ MetaFlow synced to local cache');
                      } else {
                        console.warn('⚠ Failed to sync metaflow to local cache');
                      }
                    }).catch(err => {
                      console.error('Failed to sync metaflow:', err);
                    });
                  }
                  showStatus('✅ Modification complete!', 'success');
                  break;
                case 'error':
                  showStatus(`❌ Error: ${event.content}`, 'error');
                  break;
              }
            } catch (e) {
              console.error('Failed to parse event:', e);
            }
          }
        }
      }

    } catch (error) {
      console.error('Modification error:', error);
      showStatus(`❌ Modification failed: ${error.message}`, 'error');
      setModificationLog(prev => [...prev, { type: 'error', content: error.message }]);
    } finally {
      setIsModifying(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleModify();
    }
  };

  const renderVisualTab = () => {
    if (!metaflowData) {
      return (
        <div className="empty-state">
          <p>No MetaFlow structure available</p>
        </div>
      );
    }

    return (
      <div className="visual-section" style={{ height: '600px', background: '#fff', borderRadius: '8px', overflow: 'hidden' }}>
        <FlowVisualization
          data={metaflowData}
          type="metaflow"
        />
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
          <Icon icon="arrowLeft" />
        </button>
        <h1 className="page-title"><Icon icon="fileText" /> Review MetaFlow</h1>
        <div className="header-spacer"></div>
      </div>

      {/* Content */}
      <div className="preview-content">
        {/* Instructions */}
        <div className="instructions-section">
          <div className="instruction-icon"><Icon icon="eye" size={24} /></div>
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
              <Icon icon="layout" />
              <span>Visual</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
              onClick={() => setActiveTab('yaml')}
            >
              <Icon icon="code" />
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
            <Icon icon="x" />
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
                <Icon icon="check" />
                <span>Confirm & Generate Workflow</span>
              </>
            )}
          </button>
        </div>

        {/* Modification Section */}
        <div className="modification-section">
          <div className="modification-header">
            <h3><Icon icon="cpu" size={20} /> Need changes?</h3>
            <p>Describe what you'd like to modify in natural language</p>
          </div>

          {/* Modification Log */}
          {modificationLog.length > 0 && (
            <div className="modification-log">
              {modificationLog.map((msg, index) => (
                <div key={index} className={`log-message ${msg.type}`}>
                  <span className="log-avatar">
                    {msg.type === 'user' ? <Icon icon="user" size={16} /> : msg.type === 'error' ? <Icon icon="alertCircle" size={16} /> : <Icon icon="cpu" size={16} />}
                  </span>
                  <pre className="log-content">{msg.content}</pre>
                </div>
              ))}
              {currentToolUse && (
                <div className="tool-indicator">
                  <div className="tool-spinner"></div>
                  <span className="tool-name">{currentToolUse.name}</span>
                  <span className="tool-desc">
                    {currentToolUse.name === 'Edit' && `Editing ${currentToolUse.input?.file_path || 'file'}...`}
                    {currentToolUse.name === 'Read' && `Reading ${currentToolUse.input?.file_path || 'file'}...`}
                    {currentToolUse.name === 'Write' && `Writing to ${currentToolUse.input?.file_path || 'file'}...`}
                    {!['Edit', 'Read', 'Write'].includes(currentToolUse.name) && `Using ${currentToolUse.name}...`}
                  </span>
                </div>
              )}
              <div ref={logEndRef} />
            </div>
          )}

          {/* Modification Input */}
          <div className="modification-input">
            <textarea
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="e.g., Add a scroll step before data extraction, or change the output format..."
              disabled={isModifying || isGenerating}
              rows={2}
            />
            <button
              onClick={handleModify}
              disabled={!chatInput.trim() || isModifying || isGenerating}
              className="modify-button"
            >
              {isModifying ? (
                <div className="btn-spinner"></div>
              ) : (
                <Icon icon="send" size={18} />
              )}
            </button>
          </div>
        </div>

        {/* Help Text */}
        <div className="help-text">
          <p>
            <Icon icon="info" size={14} /> <strong>What is a MetaFlow?</strong> It's a high-level description of the workflow steps
            before they are converted into executable code. Review it to ensure the AI understood your task correctly.
          </p>
        </div>
      </div>
    </div>
  );
}

export default MetaflowPreviewPage;
