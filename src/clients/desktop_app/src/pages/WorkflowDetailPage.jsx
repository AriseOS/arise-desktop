import React, { useState, useEffect, useRef } from 'react'
import 'reactflow/dist/style.css'
import CustomNode from '../components/CustomNode'
import yaml from 'js-yaml'
import Icon from '../components/Icons'
import FlowVisualization from '../components/FlowVisualization'
import { api } from '../utils/api'
import '../styles/WorkflowDetailPage.css'

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowDetailPage({ session, workflowId, autoRun, onNavigate, showStatus, onLogout }) {
  // Get user_id from session
  const userId = session?.username;
  const [workflowData, setWorkflowData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [activeTab, setActiveTab] = useState('visual') // 'visual', 'yaml', 'chat', or 'history'

  // Chat/Modification state
  const [chatInput, setChatInput] = useState('')
  const [isModifying, setIsModifying] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [modificationLog, setModificationLog] = useState([])
  const [currentToolUse, setCurrentToolUse] = useState(null)
  const logEndRef = useRef(null)

  // History state
  const [executions, setExecutions] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedExecution, setSelectedExecution] = useState(null)
  const [executionDetail, setExecutionDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    if (userId && workflowId) {
      loadWorkflowData()
    }
  }, [userId, workflowId])

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

  // Handle optimize script button click
  const handleOptimizeScript = (stepData) => {
    console.log('Optimize script clicked for step:', stepData)
    onNavigate('scraper-optimization', {
      userId: userId,
      workflowId: workflowId,
      stepId: stepData.id,
      workflowName: workflowData?.workflow_id || workflowId,
      stepName: stepData.label || stepData.id
    })
  }

  const loadWorkflowData = async () => {
    setLoading(true)
    setError(null)

    try {
      // Backend will auto-sync workflow resources before returning data
      const data = await api.callAppBackend(`/api/v1/workflows/${workflowId}?user_id=${userId}`)
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
      showStatus('启动 Workflow 执行...', 'info')

      // Use api.executeWorkflow to automatically include API key header
      const result = await api.executeWorkflow(workflowId, userId)
      const taskId = result.task_id

      showStatus('Workflow started! Redirecting to live execution page...', 'success')

      // Navigate to live execution page immediately
      setTimeout(() => {
        onNavigate('workflow-execution-live', {
          taskId: taskId,
          workflowName: workflowId
        })
      }, 500)
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus('执行失败', 'error')
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
        const result = await api.callAppBackend('/api/v1/intent-builder/sessions', {
          method: 'POST',
          body: JSON.stringify({
            user_id: userId,
            user_query: `Modify the following Workflow based on this request: ${userMessage}`,
            task_description: `Current Workflow ID: ${workflowId}`,
            workflow_id: workflowId,  // Pass Workflow ID so Agent can save modifications
            current_workflow_yaml: workflowData.workflow_yaml,
            phase: 'workflow'
          })
        })
        sid = result.session_id
        setSessionId(sid)
      }

      // Stream the modification response
      const response = await api.callAppBackendRaw(`/api/v1/intent-builder/sessions/${sid}/chat`, {
        method: 'POST',
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
                    api.callAppBackend(`/api/v1/workflows/${workflowId}`, {
                      method: 'PUT',
                      body: JSON.stringify({
                        user_id: userId,
                        workflow_yaml: event.result.updated_yaml
                      })
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
                      showStatus('Workflow modified but save failed. Changes may be lost on reload.', 'warning')
                    })
                  }
                  showStatus('Modification complete!', 'success')
                  break
                case 'error':
                  showStatus(`Error: ${event.content}`, 'error')
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
      showStatus(`Modification failed: ${error.message}`, 'error')
      setModificationLog(prev => [...prev, { type: 'error', content: error.message }])

      // If session not found (404), clear session ID to force recreation next time
      if (error.message.includes('404') || error.message.includes('Session not found')) {
        console.log('Session expired or not found, clearing session ID')
        setSessionId(null)
      }
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

  // History functions
  const fetchExecutionHistory = async () => {
    setHistoryLoading(true)
    try {
      const status = statusFilter === 'all' ? null : statusFilter
      const url = `/api/v1/workflows/${workflowId}/history?user_id=${userId}${status ? `&status=${status}` : ''}`
      const result = await api.callAppBackend(url)
      setExecutions(result.runs || [])
    } catch (error) {
      console.error('Error fetching executions:', error)
      showStatus(`Failed to load execution history: ${error.message}`, 'error')
    } finally {
      setHistoryLoading(false)
    }
  }

  const fetchExecutionDetail = async (runId) => {
    setDetailLoading(true)
    try {
      const url = `/api/v1/workflows/${workflowId}/history/${runId}?user_id=${userId}`
      const detail = await api.callAppBackend(url)
      setExecutionDetail(detail)
    } catch (error) {
      console.error('Error fetching execution detail:', error)
      showStatus(`Failed to load execution detail: ${error.message}`, 'error')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleViewExecution = (execution) => {
    setSelectedExecution(execution)
    fetchExecutionDetail(execution.run_id)
  }

  const handleCloseDetail = () => {
    setSelectedExecution(null)
    setExecutionDetail(null)
  }

  // Load history when tab changes to history
  useEffect(() => {
    if (activeTab === 'history' && userId && workflowId) {
      fetchExecutionHistory()
    }
  }, [activeTab, statusFilter, userId, workflowId])

  const formatDuration = (startedAt, finishedAt) => {
    if (!startedAt || !finishedAt) return 'N/A'
    const start = new Date(startedAt)
    const end = new Date(finishedAt)
    const durationMs = end - start

    if (durationMs < 1000) return `${durationMs}ms`
    if (durationMs < 60000) return `${(durationMs / 1000).toFixed(1)}s`

    const minutes = Math.floor(durationMs / 60000)
    const seconds = Math.floor((durationMs % 60000) / 1000)
    return `${minutes}m ${seconds}s`
  }

  const formatTime = (isoString) => {
    if (!isoString) return 'N/A'
    const date = new Date(isoString)
    return date.toLocaleString()
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <Icon icon="checkCircle" size={16} className="status-icon success" />
      case 'failed':
        return <Icon icon="xCircle" size={16} className="status-icon error" />
      case 'running':
        return <Icon icon="loader" size={16} className="status-icon running" />
      case 'cancelled':
        return <Icon icon="slash" size={16} className="status-icon cancelled" />
      default:
        return <Icon icon="circle" size={16} className="status-icon" />
    }
  }

  const getStatusClass = (status) => {
    switch (status) {
      case 'completed': return 'success'
      case 'failed': return 'error'
      case 'running': return 'running'
      case 'cancelled': return 'cancelled'
      default: return ''
    }
  }

  return (
    <div className="page workflow-detail-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('my-workflows')}
        >
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title">Workflow 详情</div>
        <button
          className="run-button"
          onClick={handleRunWorkflow}
          disabled={isRunning || loading}
        >
          {isRunning ? (
            <>
              <div className="btn-spinner"></div>
              <span>运行中</span>
            </>
          ) : (
            <>
              <Icon icon="play" size={16} />
              <span>运行</span>
            </>
          )}
        </button>
      </div>

      <div className="workflow-detail-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="clock" size={48} /></div>
            <div className="empty-state-title">加载中...</div>
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="alertTriangle" size={48} /></div>
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
                  <Icon icon="gitBranch" size={16} />
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
                        <Icon icon="externalLink" size={14} />
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
                        <Icon icon="externalLink" size={14} />
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
                <Icon icon="layout" size={16} />
                <span>Visual</span>
              </button>
              <button
                className={`workflow-tab-button ${activeTab === 'yaml' ? 'active' : ''}`}
                onClick={() => setActiveTab('yaml')}
              >
                <Icon icon="code" size={16} />
                <span>YAML</span>
              </button>
              <button
                className={`workflow-tab-button ${activeTab === 'chat' ? 'active' : ''}`}
                onClick={() => setActiveTab('chat')}
              >
                <Icon icon="messageSquare" size={16} />
                <span>AI 对话</span>
              </button>
              <button
                className={`workflow-tab-button ${activeTab === 'history' ? 'active' : ''}`}
                onClick={() => setActiveTab('history')}
              >
                <Icon icon="clock" size={16} />
                <span>执行历史</span>
              </button>
            </div>

            {/* Tabs Content */}
            <div className="workflow-tabs-content">
              {activeTab === 'visual' ? (
                <FlowVisualization
                  data={workflowData}
                  type="workflow"
                  onOptimizeScript={handleOptimizeScript}
                />
              ) : activeTab === 'yaml' ? (
                <div className="workflow-yaml-container">
                  <pre className="workflow-yaml-content">
                    <code>{workflowData.workflow_yaml || 'No YAML data available'}</code>
                  </pre>
                </div>
              ) : activeTab === 'chat' ? (
                <div className="workflow-chat-container">
                  <div className="chat-instructions">
                    <h3><Icon icon="bot" size={20} /> AI 助手</h3>
                    <p>使用自然语言描述你想要的修改，AI 会帮你调整 workflow 配置</p>
                  </div>

                  {/* Modification Log */}
                  {modificationLog.length > 0 && (
                    <div className="modification-log">
                      {modificationLog.map((msg, index) => (
                        <div key={index} className={`log-message ${msg.type}`}>
                          <span className="log-avatar">
                            {msg.type === 'user' ? <Icon icon="user" size={16} /> : msg.type === 'error' ? <Icon icon="xCircle" size={16} /> : <Icon icon="bot" size={16} />}
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
                        <Icon icon="send" size={16} />
                      )}
                    </button>
                  </div>
                </div>
              ) : activeTab === 'history' ? (
                <div className="workflow-history-container">
                  <div className="history-header">
                    <select
                      className="status-filter"
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                    >
                      <option value="all">全部状态</option>
                      <option value="completed">成功</option>
                      <option value="failed">失败</option>
                      <option value="running">运行中</option>
                    </select>
                    <button className="btn-refresh" onClick={fetchExecutionHistory}>
                      <Icon icon="refresh" size={16} />
                    </button>
                  </div>

                  {historyLoading ? (
                    <div className="history-loading">
                      <div className="spinner"></div>
                      <p>加载执行历史...</p>
                    </div>
                  ) : executions.length === 0 ? (
                    <div className="history-empty">
                      <Icon icon="inbox" size={48} />
                      <p>暂无执行记录</p>
                    </div>
                  ) : (
                    <div className="execution-list">
                      {executions.map((execution) => (
                        <div
                          key={execution.run_id}
                          className={`execution-item ${getStatusClass(execution.status)}`}
                          onClick={() => handleViewExecution(execution)}
                        >
                          <div className="execution-status">
                            {getStatusIcon(execution.status)}
                          </div>
                          <div className="execution-info">
                            <div className="execution-time">{formatTime(execution.started_at)}</div>
                            <div className="execution-meta">
                              <span className={`status-text ${getStatusClass(execution.status)}`}>
                                {execution.status}
                              </span>
                              {execution.error_summary && (
                                <span className="error-hint" title={execution.error_summary}>
                                  {execution.error_summary.substring(0, 50)}...
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="execution-arrow">
                            <Icon icon="chevronRight" size={16} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {/* Execution Detail Modal */}
            {selectedExecution && (
              <div className="modal-overlay" onClick={handleCloseDetail}>
                <div className="execution-detail-modal" onClick={e => e.stopPropagation()}>
                  <div className="modal-header">
                    <h2>执行详情</h2>
                    <button className="btn-close" onClick={handleCloseDetail}>
                      <Icon icon="x" size={20} />
                    </button>
                  </div>

                  {detailLoading ? (
                    <div className="modal-loading">
                      <div className="spinner"></div>
                      <p>加载中...</p>
                    </div>
                  ) : executionDetail ? (
                    <div className="modal-content">
                      {/* Header Stats */}
                      <div className="detail-header-stats">
                        <div className="stat-card">
                          <span className="stat-label">Status</span>
                          <div className={`stat-value-badge ${getStatusClass(executionDetail.meta?.status)}`}>
                            {getStatusIcon(executionDetail.meta?.status)}
                            <span>{executionDetail.meta?.status || 'Unknown'}</span>
                          </div>
                        </div>
                        <div className="stat-card">
                          <span className="stat-label">Duration</span>
                          <span className="stat-value">
                            {formatDuration(executionDetail.meta?.started_at, executionDetail.meta?.finished_at)}
                          </span>
                        </div>
                        <div className="stat-card">
                          <span className="stat-label">Steps Completed</span>
                          <span className="stat-value">
                            {executionDetail.meta?.steps_completed || 0}
                            <span className="stat-sub"> / {executionDetail.meta?.steps_total || 0}</span>
                          </span>
                        </div>
                        <div className="stat-card">
                          <span className="stat-label">Started At</span>
                          <span className="stat-value sm">{formatTime(executionDetail.meta?.started_at)}</span>
                        </div>
                      </div>

                      {executionDetail.meta?.error_summary && (
                        <div className="error-summary-banner">
                          <div className="error-icon-wrapper">
                            <Icon icon="alertTriangle" size={20} />
                          </div>
                          <div className="error-content">
                            <h4>Execution Failed</h4>
                            <pre>{executionDetail.meta.error_summary}</pre>
                          </div>
                        </div>
                      )}

                      <div className="detail-timeline-section">
                        <h3>Execution Timeline</h3>
                        <div className="timeline-wrapper">
                          {executionDetail.logs && executionDetail.logs.length > 0 ? (
                            (() => {
                              // Group logs by step
                              const groupedLogs = executionDetail.logs.reduce((acc, log, idx) => {
                                const stepIdx = log.step !== undefined ? log.step : -1;
                                if (!acc[stepIdx]) {
                                  acc[stepIdx] = {
                                    step: stepIdx,
                                    logs: [],
                                    status: 'completed',
                                    hasError: false
                                  };
                                }
                                // Add original index to log for unique key/expanding
                                acc[stepIdx].logs.push({ ...log, originalIdx: idx });
                                if (log.status === 'failed') {
                                  acc[stepIdx].status = 'failed';
                                  acc[stepIdx].hasError = true;
                                }
                                return acc;
                              }, {});

                              const sortedGroups = Object.values(groupedLogs).sort((a, b) => a.step - b.step);

                              return sortedGroups.map((group, groupIdx) => (
                                <div key={groupIdx} className={`timeline-group ${group.status}`}>
                                  <div className="timeline-group-header">
                                    <div className={`step-badge ${group.status}`}>
                                      {group.status === 'failed' ? (
                                        <Icon icon="x" size={12} />
                                      ) : (
                                        <span className="step-num">{group.step + 1}</span>
                                      )}
                                    </div>
                                    <span className="step-title">Step {group.step + 1}</span>
                                    {group.hasError && <span className="step-error-tag">Failed</span>}
                                  </div>

                                  <div className="timeline-group-content">
                                    {group.logs.map((log) => {
                                      const hasMetadata = log.metadata && Object.keys(log.metadata).length > 0;

                                      return (
                                        <div key={log.originalIdx} className={`timeline-log-entry ${log.status}`}>
                                          <div className="log-row-primary">
                                            <div className="log-time-col">
                                              {formatTime(log.ts).split(' ')[1] || formatTime(log.ts)}
                                            </div>
                                            <div className="log-divider">
                                              <div className="log-dot"></div>
                                            </div>
                                            <div className="log-details">
                                              <div className="log-main-line">
                                                <span className="log-action">{log.action}</span>
                                                {log.target && (
                                                  <span className="log-target">
                                                    <Icon icon="arrowRight" size={10} /> {log.target}
                                                  </span>
                                                )}
                                              </div>
                                              {log.message && <div className="log-sub-message">{log.message}</div>}

                                              {/* Inline Metadata Preview (e.g. error message) */}
                                              {hasMetadata && log.metadata.error && (
                                                <div className="log-inline-error">
                                                  <Icon icon="alertCircle" size={12} />
                                                  {log.metadata.error}
                                                </div>
                                              )}
                                            </div>
                                            <div className="log-meta-right">
                                              {log.duration_ms && (
                                                <span className="log-duration-badge">{log.duration_ms}ms</span>
                                              )}
                                            </div>
                                          </div>

                                          {/* Full Metadata Block */}
                                          {hasMetadata && (
                                            <div className="log-metadata-block">
                                              <details>
                                                <summary>View Details</summary>
                                                <div className="metadata-content">
                                                  {log.metadata.content_type === 'code' ? (
                                                    <pre className="code-block">
                                                      <code>{log.metadata.script_content || JSON.stringify(log.metadata, null, 2)}</code>
                                                    </pre>
                                                  ) : (
                                                    <pre className="json-block">{JSON.stringify(log.metadata, null, 2)}</pre>
                                                  )}
                                                </div>
                                              </details>
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              ));
                            })()
                          ) : (
                            <div className="no-logs-state">
                              <Icon icon="list" size={32} />
                              <p>No execution logs available</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="modal-error">
                      <p>加载执行详情失败</p>
                    </div>
                  )}

                  <div className="modal-footer">
                    <button className="btn btn-primary" onClick={handleCloseDetail}>
                      关闭
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div >
  )
}

export default WorkflowDetailPage

