import React, { useState, useEffect, useRef } from 'react'
import 'reactflow/dist/style.css'
import CustomNode from '../components/CustomNode'
import yaml from 'js-yaml'
import Icon from '../components/Icons'
import FlowVisualization from '../components/FlowVisualization'
import { api } from '../utils/api'
import { syncResources } from '../utils/workflowSync'
import '../styles/WorkflowDetailPage.css'

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowDetailPage({ session, workflowId, autoRun, onNavigate, showStatus, onLogout, pageData, version }) {
  // Get user_id from session
  const userId = session?.username;

  // Helper to get cached workflow data from localStorage
  const getCachedWorkflowData = () => {
    try {
      const key = `workflow_data_${workflowId}`
      const cached = localStorage.getItem(key)
      if (cached) {
        const data = JSON.parse(cached)
        // Check if cache is not too old (e.g., 1 hour)
        if (data.cachedAt && Date.now() - data.cachedAt < 3600000) {
          return data.workflowData
        }
      }
    } catch (e) {
      console.warn('Failed to load cached workflow data:', e)
    }
    return null
  }

  // Initialize workflowData from cache if available
  const cachedWorkflowData = getCachedWorkflowData()
  const [workflowData, setWorkflowData] = useState(cachedWorkflowData)
  const [loading, setLoading] = useState(!cachedWorkflowData) // Don't show loading if we have cached data
  const [error, setError] = useState(null)
  const [isRunning, setIsRunning] = useState(false)

  // Helper to get saved chat state from localStorage
  const getSavedChatState = () => {
    try {
      const key = `workflow_chat_${workflowId}`
      const saved = localStorage.getItem(key)
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (e) {
      console.warn('Failed to load saved chat state:', e)
    }
    return null
  }

  // Get initial state from pageData or localStorage
  const savedState = getSavedChatState()

  // Restore activeTab from pageData or localStorage, otherwise default to 'visual'
  const [activeTab, setActiveTab] = useState(
    pageData?.activeTab || savedState?.activeTab || 'visual'
  ) // 'visual', 'yaml', 'chat', 'data', or 'history'

  // Chat/Modification state
  const [chatInput, setChatInput] = useState('')
  const [isModifying, setIsModifying] = useState(false)
  // Use sessionId from pageData, localStorage, or null
  const [dialogueSessionId, setDialogueSessionId] = useState(
    pageData?.dialogueSessionId || pageData?.sessionId || savedState?.dialogueSessionId || null
  )
  // Restore modificationLog from pageData or localStorage
  const [modificationLog, setModificationLog] = useState(
    pageData?.modificationLog || savedState?.modificationLog || []
  )
  const [currentToolUse, setCurrentToolUse] = useState(null)
  // SSE progress events (similar to WorkflowExecutionLivePage skill-log)
  const [progressEvents, setProgressEvents] = useState([])
  // Chat instructions collapsed state (default: collapsed, saved to localStorage)
  const [chatInstructionsCollapsed, setChatInstructionsCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem('chat_instructions_collapsed')
      return saved !== null ? JSON.parse(saved) : true // Default collapsed
    } catch {
      return true
    }
  })
  const logEndRef = useRef(null)
  // Save chat instructions collapsed state
  useEffect(() => {
    try {
      localStorage.setItem('chat_instructions_collapsed', JSON.stringify(chatInstructionsCollapsed))
    } catch (e) {
      console.warn('Failed to save chat instructions state:', e)
    }
  }, [chatInstructionsCollapsed])

  // Save chat state to localStorage whenever it changes
  useEffect(() => {
    if (workflowId && (dialogueSessionId || modificationLog.length > 0)) {
      try {
        const key = `workflow_chat_${workflowId}`
        const state = {
          activeTab,
          dialogueSessionId,
          modificationLog,
          savedAt: Date.now()
        }
        localStorage.setItem(key, JSON.stringify(state))
      } catch (e) {
        console.warn('Failed to save chat state:', e)
      }
    }
  }, [workflowId, activeTab, dialogueSessionId, modificationLog])

  // Cleanup: close workflow session when page unmounts
  useEffect(() => {
    return () => {
      if (dialogueSessionId) {
        // Close the session on unmount - fire and forget
        api.closeWorkflowSession(dialogueSessionId).catch(err => {
          console.warn('Failed to close workflow session:', err)
        })
        // Clear session ID from localStorage to avoid using stale session
        try {
          const key = `workflow_chat_${workflowId}`
          const saved = localStorage.getItem(key)
          if (saved) {
            const state = JSON.parse(saved)
            delete state.dialogueSessionId
            localStorage.setItem(key, JSON.stringify(state))
          }
        } catch (e) {
          console.warn('Failed to clear session ID from localStorage:', e)
        }
      }
    }
  }, [dialogueSessionId, workflowId])

  // History state
  const [executions, setExecutions] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedExecution, setSelectedExecution] = useState(null)
  const [executionDetail, setExecutionDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Data tab state
  const [collections, setCollections] = useState([])
  const [dataLoading, setDataLoading] = useState(false)
  const [selectedCollection, setSelectedCollection] = useState(null)
  const [collectionData, setCollectionData] = useState(null)
  const [collectionLoading, setCollectionLoading] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(null) // { collectionName: string }

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

  const loadWorkflowData = async () => {
    // Only show loading spinner if we don't have cached data
    if (!workflowData) {
      setLoading(true)
    }
    setError(null)

    try {
      // Backend will auto-sync workflow resources before returning data
      const data = await api.callAppBackend(`/api/v1/workflows/${workflowId}?user_id=${userId}`)
      console.log('Workflow data received:', data)
      setWorkflowData(data)

      // Cache the workflow data to localStorage
      try {
        const key = `workflow_data_${workflowId}`
        localStorage.setItem(key, JSON.stringify({
          workflowData: data,
          cachedAt: Date.now()
        }))
      } catch (e) {
        console.warn('Failed to cache workflow data:', e)
      }
    } catch (err) {
      console.error('Load workflow error:', err)
      // Only show error if we don't have cached data to display
      if (!workflowData) {
        setError('加载工作流数据失败')
      } else {
        showStatus('刷新数据失败，显示缓存数据', 'warning')
      }
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

  // Handle modification request using new WorkflowService API
  const handleModify = async () => {
    if (!chatInput.trim() || isModifying) return

    const userMessage = chatInput.trim()
    setChatInput('')
    setIsModifying(true)
    setModificationLog(prev => [...prev, { type: 'user', content: userMessage }])

    try {
      let sessionId = dialogueSessionId

      // Create session if not exists
      if (!sessionId) {
        showStatus('Creating dialogue session...', 'info')
        const sessionResult = await api.createWorkflowSession(
          userId,
          workflowId,
          workflowData.workflow_yaml
        )
        sessionId = sessionResult.session_id
        setDialogueSessionId(sessionId)
      }

      // Use the WorkflowService chat API with streaming events
      // Clear previous progress events and start fresh
      setProgressEvents([])

      const response = await api.workflowChat(sessionId, userMessage, async (event) => {
        // Handle streaming events - add to progressEvents for display
        if (event.type === 'text') {
          // Accumulate text events
          setProgressEvents(prev => {
            // Find existing text event to update, or add new one
            const textIdx = prev.findIndex(e => e.type === 'text')
            if (textIdx >= 0) {
              const updated = [...prev]
              updated[textIdx] = { ...updated[textIdx], content: (updated[textIdx].content || '') + event.message }
              return updated
            }
            return [...prev, { type: 'text', content: event.message }]
          })
          setCurrentToolUse(null)
        } else if (event.type === 'tool_use') {
          // Add tool_use event
          setProgressEvents(prev => [...prev, { type: 'tool_use', content: event.message }])
          setCurrentToolUse(event.message)
        } else if (event.type === 'workflow_updated') {
          // Add workflow_updated event
          setProgressEvents(prev => [...prev, { type: 'workflow_updated', content: 'Workflow updated' }])
        } else if (event.type === 'sync_required') {
          // Handle sync_required event - sync modified files to local client
          setProgressEvents(prev => [...prev, { type: 'sync', content: `Syncing ${event.files?.length || 0} files to local...` }])
          try {
            await syncResources(workflowId, 'download')
            setProgressEvents(prev => [...prev, { type: 'sync_complete', content: 'Files synced to local' }])
            showStatus('Files synced to local', 'success')
          } catch (syncError) {
            console.error('Sync failed:', syncError)
            setProgressEvents(prev => [...prev, { type: 'sync_error', content: 'Sync failed' }])
          }
        } else if (event.type === 'error') {
          // Add error event
          setProgressEvents(prev => [...prev, { type: 'error', content: event.message }])
        }
      })

      setCurrentToolUse(null)
      // Clear progress events after completion
      setProgressEvents([])

      // Add assistant reply to log
      if (response.message) {
        setModificationLog(prev => [...prev, { type: 'assistant', content: response.message }])
      }

      // Update workflow if modified
      if (response.workflow_updated && response.workflow_yaml) {
        const updatedData = { ...workflowData, workflow_yaml: response.workflow_yaml }
        try {
          const parsed = yaml.load(response.workflow_yaml)
          updatedData.steps = parsed.steps || []
          updatedData.connections = parsed.connections || []
        } catch (e) {
          console.error('Failed to parse updated YAML:', e)
        }
        setWorkflowData(updatedData)

        // Sync to storage
        api.callAppBackend(`/api/v1/workflows/${workflowId}`, {
          method: 'PUT',
          body: JSON.stringify({
            user_id: userId,
            workflow_yaml: response.workflow_yaml
          })
        }).then(result => {
          console.log('Workflow saved:', result)
        }).catch(err => {
          console.error('Failed to save workflow:', err)
          showStatus('Workflow modified but save failed.', 'warning')
        })

        showStatus('Workflow updated!', 'success')
      } else {
        showStatus('Response received', 'success')
      }

    } catch (error) {
      console.error('Modification error:', error)
      showStatus(`Modification failed: ${error.message}`, 'error')
      setModificationLog(prev => [...prev, { type: 'error', content: error.message }])

      // If session not found (404), clear session ID to create new one on next try
      if (error.message.includes('404') || error.message.includes('Session not found')) {
        console.log('Session expired or not found, clearing session ID')
        setDialogueSessionId(null)
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

  // Data tab functions
  const fetchCollections = async () => {
    setDataLoading(true)
    try {
      const url = `/api/v1/workflows/${workflowId}/data/collections?user_id=${userId}`
      const result = await api.callAppBackend(url)
      setCollections(result.collections || [])
    } catch (error) {
      console.error('Error fetching collections:', error)
      showStatus(`Failed to load collections: ${error.message}`, 'error')
    } finally {
      setDataLoading(false)
    }
  }

  const fetchCollectionData = async (collectionName) => {
    setCollectionLoading(true)
    try {
      const url = `/api/v1/workflows/${workflowId}/data/collections/${collectionName}?user_id=${userId}`
      const result = await api.callAppBackend(url)
      setCollectionData(result)
    } catch (error) {
      console.error('Error fetching collection data:', error)
      showStatus(`Failed to load collection data: ${error.message}`, 'error')
    } finally {
      setCollectionLoading(false)
    }
  }

  const handleSelectCollection = (collection) => {
    // Always refresh data when clicking a collection, even if it's already selected
    setSelectedCollection(collection)
    fetchCollectionData(collection.collection_name)
  }

  const handleDeleteClick = (collectionName) => {
    setDeleteConfirm({ collectionName })
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return

    const { collectionName } = deleteConfirm
    setDeleteConfirm(null)

    try {
      showStatus('Deleting...', 'info')
      const url = `/api/v1/workflows/${workflowId}/data/collections/${collectionName}?user_id=${userId}`
      await api.callAppBackend(url, { method: 'DELETE' })
      showStatus(`Collection "${collectionName}" deleted`, 'success')
      setSelectedCollection(null)
      setCollectionData(null)
      fetchCollections()
    } catch (error) {
      console.error('Error deleting collection:', error)
      showStatus(`Failed to delete collection: ${error.message}`, 'error')
    }
  }

  const handleDeleteCancel = () => {
    setDeleteConfirm(null)
  }

  const handleExportCollection = async (collectionName) => {
    try {
      showStatus('Exporting...', 'info')
      const response = await api.callAppBackendRaw(
        `/api/v1/workflows/${workflowId}/data/collections/${collectionName}/export?user_id=${userId}`
      )

      if (!response.ok) {
        throw new Error(`Export failed: ${response.status}`)
      }

      // Get the CSV content
      const csvContent = await response.text()

      // Create blob and download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${collectionName}_${workflowId}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      showStatus('Export completed', 'success')
    } catch (error) {
      console.error('Export error:', error)
      showStatus(`Export failed: ${error.message}`, 'error')
    }
  }

  // Refresh all data: collections list and selected collection data
  const handleRefreshData = async () => {
    await fetchCollections()
    if (selectedCollection) {
      fetchCollectionData(selectedCollection.collection_name)
    }
  }

  // Load data when tab changes to data
  useEffect(() => {
    if (activeTab === 'data' && userId && workflowId) {
      fetchCollections()
      // Also refresh selected collection data if one is selected
      if (selectedCollection) {
        fetchCollectionData(selectedCollection.collection_name)
      }
    }
  }, [activeTab, userId, workflowId])

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
        <div className="page-title">{workflowData?.workflow_name || workflowData?.name || 'Workflow 详情'}</div>
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
        {/* Show loading only if we don't have any workflowData yet */}
        {loading && !workflowData && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="clock" size={48} /></div>
            <div className="empty-state-title">加载中...</div>
          </div>
        )}

        {/* Show error only if we don't have workflowData to fall back on */}
        {error && !workflowData && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="alertTriangle" size={48} /></div>
            <div className="empty-state-title">错误</div>
            <div className="empty-state-desc">{error}</div>
          </div>
        )}

        {/* Show tabs if we have workflowData (even during refresh/loading) */}
        {workflowData && (
          <>
            {/* Workflow Metadata Card */}
            {workflowData && (
              <div className="workflow-traceability-card">
                <div className="traceability-header">
                  <Icon icon="info" size={16} />
                  <h3>Metadata</h3>
                </div>
                <div className="traceability-content" style={{ flexDirection: 'column', gap: '8px', alignItems: 'flex-start' }}>
                  {/* Name from metadata.json workflow_name */}
                  <div className="trace-item">
                    <span className="trace-label">Name:</span>
                    <code className="trace-value" style={{ width: 'auto' }}>{workflowData.workflow_name || workflowData.name || workflowId}</code>
                  </div>
                  {/* ID from metadata.json workflow_id */}
                  <div className="trace-item">
                    <span className="trace-label">ID:</span>
                    <code className="trace-value" style={{ width: 'auto' }}>{workflowData.workflow_id || workflowId}</code>
                  </div>
                  {/* Source recording from metadata.json */}
                  {workflowData.source_recording_id && (
                    <div className="trace-item">
                      <span className="trace-label">Source:</span>
                      <code className="trace-value" style={{ width: 'auto' }}>{workflowData.source_recording_id}</code>
                      <button
                        className="trace-link-button"
                        onClick={() => onNavigate('recording-detail', { sessionId: workflowData.source_recording_id })}
                        title="View Recording"
                      >
                        <Icon icon="externalLink" size={14} />
                      </button>
                    </div>
                  )}
                  {/* Description from workflow.yaml */}
                  {workflowData.description && (
                    <div className="trace-item">
                      <span className="trace-label">Description:</span>
                      <code className="trace-value" style={{ width: 'auto' }}>{workflowData.description}</code>
                    </div>
                  )}
                  {/* Timestamps from metadata.json */}
                  {workflowData.created_at && (
                    <div className="trace-item">
                      <span className="trace-label">Created:</span>
                      <code className="trace-value" style={{ width: 'auto' }}>{new Date(workflowData.created_at).toLocaleString()}</code>
                    </div>
                  )}
                  {workflowData.updated_at && (
                    <div className="trace-item">
                      <span className="trace-label">Updated:</span>
                      <code className="trace-value" style={{ width: 'auto' }}>{new Date(workflowData.updated_at).toLocaleString()}</code>
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
                className={`workflow-tab-button ${activeTab === 'data' ? 'active' : ''}`}
                onClick={() => setActiveTab('data')}
              >
                <Icon icon="database" size={16} />
                <span>数据</span>
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
                />
              ) : activeTab === 'yaml' ? (
                <div className="workflow-yaml-container">
                  <pre className="workflow-yaml-content">
                    <code>{workflowData.workflow_yaml || 'No YAML data available'}</code>
                  </pre>
                </div>
              ) : activeTab === 'chat' ? (
                <div className="workflow-chat-container">
                  {/* Collapsible chat instructions - small badge when collapsed */}
                  {chatInstructionsCollapsed ? (
                    <div
                      className="chat-instructions-badge"
                      onClick={() => setChatInstructionsCollapsed(false)}
                      title="点击展开说明"
                    >
                      <Icon icon="bot" size={14} />
                      <span>AI 助手</span>
                      <Icon icon="chevronDown" size={12} />
                    </div>
                  ) : (
                    <div className="chat-instructions">
                      <div className="chat-instructions-header">
                        <h3><Icon icon="bot" size={20} /> AI 助手</h3>
                        <button
                          className="collapse-btn"
                          onClick={() => setChatInstructionsCollapsed(true)}
                          title="收起"
                        >
                          <Icon icon="x" size={14} />
                        </button>
                      </div>
                      <p>使用自然语言描述你想要的修改，AI 会帮你调整 workflow 配置</p>
                    </div>
                  )}

                  {/* Modification Log */}
                  {(modificationLog.length > 0 || progressEvents.length > 0) && (
                    <div className="modification-log">
                      {modificationLog.map((msg, index) => (
                        <div key={index} className={`log-message ${msg.type}`}>
                          <span className="log-avatar">
                            {msg.type === 'user' ? <Icon icon="user" size={16} /> : msg.type === 'error' ? <Icon icon="xCircle" size={16} /> : <Icon icon="bot" size={16} />}
                          </span>
                          <pre className="log-content">{msg.content}</pre>
                        </div>
                      ))}

                      {/* SSE Progress Events - similar to WorkflowExecutionLivePage skill-log */}
                      {progressEvents.length > 0 && (
                        <div className="sse-progress-log">
                          {progressEvents.map((event, idx) => (
                            <div key={idx} className={`progress-event ${event.type}`}>
                              {event.type === 'tool_use' && (
                                <>
                                  <Icon icon="tool" size={14} className="spinning-icon" />
                                  <span>{event.content}</span>
                                </>
                              )}
                              {event.type === 'text' && (
                                <>
                                  <Icon icon="messageSquare" size={14} />
                                  <span>{event.content}</span>
                                </>
                              )}
                              {event.type === 'workflow_updated' && (
                                <>
                                  <Icon icon="checkCircle" size={14} />
                                  <span>Workflow updated successfully</span>
                                </>
                              )}
                              {event.type === 'error' && (
                                <>
                                  <Icon icon="alertCircle" size={14} />
                                  <span>{event.content}</span>
                                </>
                              )}
                            </div>
                          ))}
                          {isModifying && (
                            <div className="progress-event thinking">
                              <Icon icon="loader" size={14} className="spinning-icon" />
                              <span>Processing...</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Show simple spinner if modifying but no events yet */}
                      {isModifying && progressEvents.length === 0 && (
                        <div className="sse-progress-log">
                          <div className="progress-event thinking">
                            <Icon icon="loader" size={14} className="spinning-icon" />
                            <span>Connecting to AI assistant...</span>
                          </div>
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
              ) : activeTab === 'data' ? (
                <div className="workflow-data-container">
                  {dataLoading ? (
                    <div className="data-loading">
                      <div className="spinner"></div>
                      <p>Loading collections...</p>
                    </div>
                  ) : collections.length === 0 ? (
                    <div className="data-empty">
                      <Icon icon="database" size={48} />
                      <p>No collections found</p>
                      <span className="data-empty-hint">
                        This workflow may not store data, or it hasn't been executed yet.
                      </span>
                    </div>
                  ) : (
                    <div className="data-layout-container">
                      {/* Left Sidebar */}
                      <div className="data-sidebar">
                        <div className="sidebar-header">
                          <span className="sidebar-title">Data Collections</span>
                          <button className="btn-icon-ghost" onClick={handleRefreshData} title="Refresh">
                            <Icon icon="refresh" size={14} />
                          </button>
                        </div>
                        <div className="sidebar-list">
                          {collections.map((col) => (
                            <div
                              key={col.collection_name}
                              className={`sidebar-item ${selectedCollection?.collection_name === col.collection_name ? 'active' : ''}`}
                              onClick={() => handleSelectCollection(col)}
                            >
                              <div className="item-icon">
                                <Icon icon="database" size={16} />
                              </div>
                              <div className="item-content">
                                <span className="item-name">{col.collection_name}</span>
                                <span className="item-meta">{col.records_count} records</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Main Content Area */}
                      <div className="data-main-view">
                        {!selectedCollection ? (
                          <div className="empty-selection-state">
                            <div className="empty-icon-circle">
                              <Icon icon="mousePointer" size={24} />
                            </div>
                            <h3>Select a Collection</h3>
                            <p>Choose a data collection from the left to view and manage its records.</p>
                          </div>
                        ) : collectionLoading ? (
                          <div className="main-loading-state">
                            <div className="spinner"></div>
                            <p>Loading records...</p>
                          </div>
                        ) : collectionData ? (
                          <>
                            {/* View Header */}
                            <div className="data-view-header">
                              <div className="header-title-group">
                                <h1>{selectedCollection.collection_name}</h1>
                                <div className="header-badges">
                                  <span className="badge-pill">
                                    <Icon icon="list" size={12} />
                                    {collectionData.total_records} Records
                                  </span>
                                  <span className="badge-pill">
                                    <Icon icon="columns" size={12} />
                                    {collectionData.fields?.length || 0} Fields
                                  </span>
                                </div>
                              </div>

                              <div className="header-actions">
                                <button
                                  className="btn-secondary"
                                  onClick={() => handleExportCollection(selectedCollection.collection_name)}
                                >
                                  <Icon icon="download" size={16} />
                                  <span>Export CSV</span>
                                </button>
                                <button
                                  className="btn-danger-secondary"
                                  onClick={() => handleDeleteClick(selectedCollection.collection_name)}
                                >
                                  <Icon icon="trash2" size={16} />
                                  <span>Delete</span>
                                </button>
                              </div>
                            </div>

                            {/* Data Table */}
                            <div className="data-table-card">
                              <div className="table-scroll-container">
                                <table className="modern-data-table">
                                  <thead>
                                    <tr>
                                      {collectionData.fields?.map((field) => (
                                        <th key={field}>{field}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {collectionData.data?.map((row, idx) => (
                                      <tr key={idx}>
                                        {collectionData.fields?.map((field) => (
                                          <td key={field}>
                                            <div className="cell-content">
                                              {typeof row[field] === 'object'
                                                ? JSON.stringify(row[field])
                                                : String(row[field] ?? '')}
                                            </div>
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              <div className="table-footer">
                                <span>Showing {collectionData.data?.length} of {collectionData.total_records} records</span>
                              </div>
                            </div>
                          </>
                        ) : null}
                      </div>
                    </div>
                  )}
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
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>

      {/* Delete Collection Confirmation Modal */}
      {
        deleteConfirm && (
          <div className="modal-overlay" onClick={handleDeleteCancel}>
            <div className="delete-confirm-modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Confirm Delete</h3>
              </div>
              <div className="modal-body">
                <p>Are you sure you want to delete collection <strong>"{deleteConfirm.collectionName}"</strong>?</p>
                <p className="warning-text">This action cannot be undone.</p>
              </div>
              <div className="modal-footer">
                <button className="btn-cancel" onClick={handleDeleteCancel}>
                  Cancel
                </button>
                <button className="btn-confirm-delete" onClick={handleDeleteConfirm}>
                  Delete
                </button>
              </div>
            </div>
          </div>
        )
      }


    </div >
  )
}

export default WorkflowDetailPage

