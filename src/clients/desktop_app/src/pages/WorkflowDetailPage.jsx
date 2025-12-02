import React, { useState, useEffect, useRef } from 'react'
import 'reactflow/dist/style.css'
import CustomNode from '../components/CustomNode'
import yaml from 'js-yaml'

const API_BASE = "http://127.0.0.1:8765"

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowDetailPage({ session, workflowId, autoRun, onNavigate, showStatus, onLogout }) {
  // Get user_id from session
  const userId = session?.username || 'default_user';
  const [workflowData, setWorkflowData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [activeTab, setActiveTab] = useState('visual') // 'visual', 'yaml', or 'chat'

  // Chat/Modification state
  const [chatInput, setChatInput] = useState('')
  const [isModifying, setIsModifying] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [modificationLog, setModificationLog] = useState([])
  const [currentToolUse, setCurrentToolUse] = useState(null)
  const logEndRef = useRef(null)

  useEffect(() => {
    loadWorkflowData()
  }, [workflowId])

  // Auto-run workflow if autoRun is true
  useEffect(() => {
    if (autoRun && workflowData && !loading && !isRunning) {
      handleRunWorkflow()
    }
  }, [autoRun, workflowData, loading])

  // Auto-scroll modification log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [modificationLog, currentToolUse])

  const loadWorkflowData = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/api/workflows/${workflowId}/detail?user_id=${userId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()
      console.log('Workflow data received:', data)
      setWorkflowData(data)
    } catch (err) {
      console.error('Load workflow error:', err)
      setError('加载工作流数据失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRunWorkflow = async () => {
    if (isRunning) return

    setIsRunning(true)

    try {
      showStatus('🚀 启动 Workflow 执行...', 'info')

      const response = await fetch(`${API_BASE}/api/workflow/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          workflow_name: workflowId,
          user_id: userId
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const result = await response.json()
      const taskId = result.task_id

      showStatus(`🔄 执行中... (Task ID: ${taskId})`, 'info')

      // Poll task status
      let completed = false
      let pollCount = 0
      const maxPolls = 60

      while (!completed && pollCount < maxPolls) {
        await new Promise(resolve => setTimeout(resolve, 5000))

        const statusResponse = await fetch(`${API_BASE}/api/workflow/status/${taskId}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          }
        })

        if (statusResponse.ok) {
          const statusData = await statusResponse.json()

          showStatus(`🔄 执行中... ${statusData.progress}% (${statusData.current_step}/${statusData.total_steps})`, 'info')

          if (statusData.status === 'completed' || statusData.status === 'failed') {
            completed = true

            if (statusData.status === 'completed') {
              showStatus('✅ 执行成功！', 'success')
              setTimeout(() => {
                onNavigate('workflow-result', {
                  workflowName: workflowId,
                  taskId: taskId,
                  result: statusData.result
                })
              }, 1500)
            } else {
              showStatus(`❌ 执行失败: ${statusData.error || '未知错误'}`, 'error')
            }
          }
        }

        pollCount++
      }

      if (!completed) {
        showStatus('⚠️ 执行超时，请稍后查看结果', 'warning')
      }
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus('❌ 执行失败', 'error')
    } finally {
      setIsRunning(false)
    }
  }

  // Handle modification request
  const handleModify = async () => {
    if (!chatInput.trim() || isModifying) return

    const userMessage = chatInput.trim()
    setChatInput('')
    setIsModifying(true)
    setModificationLog(prev => [...prev, { type: 'user', content: userMessage }])

    try {
      // Create session if not exists
      let sid = sessionId
      if (!sid) {
        const response = await fetch(`${API_BASE}/api/intent-builder/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            user_query: `Modify the following Workflow based on this request: ${userMessage}`,
            task_description: `Current Workflow ID: ${workflowId}`,
            workflow_id: workflowId,  // Pass Workflow ID so Agent can save modifications
            current_workflow_yaml: workflowData.workflow_yaml,
            phase: 'workflow'
          })
        })

        if (!response.ok) throw new Error(`Failed to start session: ${response.statusText}`)

        const result = await response.json()
        sid = result.session_id
        setSessionId(sid)
      }

      // Stream the modification response
      const response = await fetch(`${API_BASE}/api/intent-builder/${sid}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      })

      if (!response.ok) throw new Error(`Request failed: ${response.statusText}`)

      // Read SSE stream
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulatedText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))

              switch (event.type) {
                case 'text':
                  accumulatedText += event.content
                  break
                case 'tool_use':
                  setCurrentToolUse({ name: event.tool_name, input: event.tool_input })
                  break
                case 'tool_result':
                  setCurrentToolUse(null)
                  break
                case 'complete':
                  setCurrentToolUse(null)
                  if (accumulatedText) {
                    setModificationLog(prev => [...prev, { type: 'assistant', content: accumulatedText }])
                  }
                  // Reload updated Workflow YAML
                  if (event.result?.updated_yaml) {
                    const updatedData = { ...workflowData, workflow_yaml: event.result.updated_yaml }
                    try {
                      const parsed = yaml.load(event.result.updated_yaml)
                      updatedData.steps = parsed.steps || []
                      updatedData.connections = parsed.connections || []
                    } catch (e) {
                      console.error('Failed to parse updated YAML:', e)
                    }
                    setWorkflowData(updatedData)

                    // Sync to both Cloud and Local storage
                    fetch(`${API_BASE}/api/workflows/${workflowId}`, {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        user_id: userId,
                        workflow_yaml: event.result.updated_yaml
                      })
                    }).then(response => {
                      if (response.ok) {
                        return response.json()
                      } else {
                        throw new Error('Failed to save workflow')
                      }
                    }).then(result => {
                      console.log('✓ Workflow saved:', result)
                      if (result.updated_in_cloud) {
                        console.log('  ✓ Cloud Backend updated')
                      } else {
                        console.warn('  ⚠ Cloud Backend update failed')
                      }
                      if (result.updated_in_local) {
                        console.log('  ✓ Local cache updated')
                      } else {
                        console.warn('  ⚠ Local cache update failed')
                      }
                    }).catch(err => {
                      console.error('❌ Failed to save workflow:', err)
                      showStatus('⚠️ Workflow modified but save failed. Changes may be lost on reload.', 'warning')
                    })
                  }
                  showStatus('✅ Modification complete!', 'success')
                  break
                case 'error':
                  showStatus(`❌ Error: ${event.content}`, 'error')
                  break
              }
            } catch (e) {
              console.error('Failed to parse event:', e)
            }
          }
        }
      }

    } catch (error) {
      console.error('Modification error:', error)
      showStatus(`❌ Modification failed: ${error.message}`, 'error')
      setModificationLog(prev => [...prev, { type: 'error', content: error.message }])
    } finally {
      setIsModifying(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleModify()
    }
  }

  return (
    <div className="page workflow-detail-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('my-workflows')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="page-title">Workflow 详情</div>
        <button
          className="run-button"
          onClick={handleRunWorkflow}
          disabled={isRunning || loading}
        >
          {isRunning ? (
            <>
              <span className="loading-spinner"></span>
              <span>运行中</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              <span>运行</span>
            </>
          )}
        </button>
      </div>

      <div className="workflow-detail-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon">⏳</div>
            <div className="empty-state-title">加载中...</div>
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-icon">⚠️</div>
            <div className="empty-state-title">错误</div>
            <div className="empty-state-desc">{error}</div>
          </div>
        )}

        {!loading && !error && workflowData && (
          <>
            {/* Workflow Traceability Info */}
            {(workflowData.source_metaflow_id || workflowData.source_recording_id) && (
              <div className="workflow-traceability-card">
                <div className="traceability-header">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" />
                    <path d="M2 17L12 22L22 17" />
                    <path d="M2 12L12 17L22 12" />
                  </svg>
                  <h3>来源信息</h3>
                </div>
                <div className="traceability-content">
                  {workflowData.source_metaflow_id && (
                    <div className="trace-item">
                      <span className="trace-label">MetaFlow:</span>
                      <code className="trace-value">{workflowData.source_metaflow_id}</code>
                      <button
                        className="trace-link-button"
                        onClick={() => onNavigate('metaflow-preview', { metaflowId: workflowData.source_metaflow_id })}
                        title="查看MetaFlow详情"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </button>
                    </div>
                  )}
                  {workflowData.source_recording_id && (
                    <div className="trace-item">
                      <span className="trace-label">Recording:</span>
                      <code className="trace-value">{workflowData.source_recording_id}</code>
                      <button
                        className="trace-link-button"
                        onClick={() => onNavigate('recording-detail', { sessionId: workflowData.source_recording_id })}
                        title="查看Recording详情"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </button>
                    </div>
                  )}
                  {!workflowData.source_metaflow_id && !workflowData.source_recording_id && (
                    <div className="trace-item no-trace">
                      <span>暂无来源信息</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tabs Header */}
            <div className="workflow-tabs-header">
              <button
                className={`workflow-tab-button ${activeTab === 'visual' ? 'active' : ''}`}
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
                className={`workflow-tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
                onClick={() => setActiveTab('yaml')}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="16 18 22 12 16 6" />
                  <polyline points="8 6 2 12 8 18" />
                </svg>
                <span>YAML</span>
              </button>
              <button
                className={`workflow-tab-button ${activeTab === 'chat' ? 'active' : ''}`}
                onClick={() => setActiveTab('chat')}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span>AI 修改</span>
              </button>
            </div>

            {/* Tabs Content */}
            <div className="workflow-tabs-content">
              {activeTab === 'visual' ? (
                <FlowVisualization data={workflowData} type="workflow" />
              ) : activeTab === 'yaml' ? (
                <div className="workflow-yaml-container">
                  <pre className="workflow-yaml-content">
                    <code>{workflowData.workflow_yaml || 'No YAML data available'}</code>
                  </pre>
                </div>
              ) : (
                <div className="workflow-chat-container">
                  <div className="chat-instructions">
                    <h3>🤖 AI 助手</h3>
                    <p>使用自然语言描述你想要的修改，AI 会帮你调整 workflow 配置</p>
                  </div>

                  {/* Modification Log */}
                  {modificationLog.length > 0 && (
                    <div className="modification-log">
                      {modificationLog.map((msg, index) => (
                        <div key={index} className={`log-message ${msg.type}`}>
                          <span className="log-avatar">
                            {msg.type === 'user' ? '👤' : msg.type === 'error' ? '❌' : '🤖'}
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
                      placeholder="例如：在 scraper 步骤前添加 2 秒延迟，或者修改超时时间为 30 秒..."
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
                        <svg viewBox="0 0 24 24" fill="currentColor">
                          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  )
}

// Workflow Visualization Component
// Replaced by shared FlowVisualization component
import FlowVisualization from '../components/FlowVisualization'

export default WorkflowDetailPage

