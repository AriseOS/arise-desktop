import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import '../styles/MetaflowDetailPage.css';
import FlowVisualization from '../components/FlowVisualization';
import yaml from 'js-yaml';
import { api } from '../utils/api';

const API_BASE = "http://127.0.0.1:8765";

function MetaflowDetailPage({ session, onNavigate, showStatus, metaflowId }) {
  const userId = session?.username;
  const [metaflow, setMetaflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('preview'); // 'preview', 'visual', 'yaml', 'chat'
  const [isGeneratingWorkflow, setIsGeneratingWorkflow] = useState(false);

  // Chat/Modification state
  const [chatInput, setChatInput] = useState('');
  const [isModifying, setIsModifying] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [modificationLog, setModificationLog] = useState([]);
  const [currentToolUse, setCurrentToolUse] = useState(null);
  const logEndRef = useRef(null);

  // Fetch MetaFlow details
  useEffect(() => {
    const fetchMetaflowDetails = async () => {
      if (!metaflowId) {
        showStatus('No MetaFlow ID provided', 'error');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/metaflows/${metaflowId}?user_id=${userId}`);

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
  }, [metaflowId, userId]);

  // Auto-scroll modification log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [modificationLog, currentToolUse]);

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
          user_id: userId
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
        const result = await api.callAppBackend('/api/intent-builder/start', {
          method: 'POST',
          body: JSON.stringify({
            user_id: userId,
            user_query: `Modify the following MetaFlow based on this request: ${userMessage}`,
            task_description: `Current MetaFlow ID: ${metaflowId}`,
            metaflow_id: metaflowId,  // Pass MetaFlow ID so Agent can save modifications
            // Pass current MetaFlow content so Agent has context
            current_metaflow_yaml: metaflow.metaflow_yaml,
            phase: 'metaflow'  // Tell Agent we're in MetaFlow phase
          })
        });

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
                    const updatedMetaflow = { ...metaflow, metaflow_yaml: event.result.updated_yaml };
                    setMetaflow(updatedMetaflow);

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
                  showStatus('Modification complete!', 'success');
                  break;
                case 'error':
                  showStatus(`Error: ${event.content}`, 'error');
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
      showStatus(`Modification failed: ${error.message}`, 'error');
      setModificationLog(prev => [...prev, { type: 'error', content: error.message }]);

      // If session not found (404), clear session ID to force recreation next time
      if (error.message.includes('404') || error.message.includes('Session not found')) {
        console.log('Session expired or not found, clearing session ID');
        setSessionId(null);
      }
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
          <div className="error-icon"><Icon icon="alertCircle" size={64} /></div>
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
          <Icon icon="arrowLeft" />
        </button>
        <h1 className="page-title">
          <Icon icon="fileText" /> MetaFlow 详情
        </h1>
        <button
          className="run-button"
          onClick={handleGenerateWorkflow}
          disabled={isGeneratingWorkflow || metaflow.workflow_id}
          title={metaflow.workflow_id ? 'Workflow 已生成' : '生成 Workflow'}
        >
          {isGeneratingWorkflow ? (
            <>
              <div className="btn-spinner"></div>
              <span>生成中...</span>
            </>
          ) : metaflow.workflow_id ? (
            <>
              <Icon icon="check" size={16} />
              <span>已生成</span>
            </>
          ) : (
            <>
              <Icon icon="zap" size={16} />
              <span>生成 Workflow</span>
            </>
          )}
        </button>
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
              <Icon icon="eye" />
              <span>Preview</span>
            </button>
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
            {/* <button
              className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <Icon icon="messageSquare" />
              <span>AI 对话</span>
            </button> */}
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
              <div className="visual-section" style={{ height: '100%', minHeight: '600px', background: '#fff', borderRadius: '8px', overflow: 'hidden' }}>
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
            ) : activeTab === 'chat' ? (
              <div className="metaflow-chat-container">
                <div className="chat-instructions">
                  <h3><Icon icon="bot" size={20} /> AI 助手</h3>
                  <p>使用自然语言描述你想要的修改，AI 会帮你调整 MetaFlow 配置</p>
                </div>

                {/* Modification Log */}
                {modificationLog.length > 0 && (
                  <div className="modification-log">
                    {modificationLog.map((msg, index) => (
                      <div key={index} className={`log-message ${msg.type}`}>
                        <span className="log-avatar">
                          {msg.type === 'user' ? <Icon icon="user" size={16} /> : msg.type === 'error' ? <Icon icon="alertCircle" size={16} /> : <Icon icon="bot" size={16} />}
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
                    placeholder="例如：在数据提取前添加一个过滤步骤..."
                    disabled={isModifying}
                    rows={3}
                  />
                  <button
                    onClick={handleModify}
                    disabled={!chatInput.trim() || isModifying}
                    className="modify-button"
                  >
                    {isModifying ? (
                      <div className="btn-spinner"></div>
                    ) : (
                      <Icon icon="send" size={16} />
                    )}
                  </button>
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

      </div>
    </div>
  );
}

export default MetaflowDetailPage;
