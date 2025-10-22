import React, { useState, useEffect, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  ReactFlowProvider,
} from 'reactflow'
import 'reactflow/dist/style.css'
import CustomNode from '../components/CustomNode'
import { DEFAULT_CONFIG_KEY, getConfig } from '../config/index'

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowDetailPage({ currentUser, workflowId, onNavigate, showStatus, onLogout }) {
  const [workflowData, setWorkflowData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    loadWorkflowData()
  }, [workflowId])

  const loadWorkflowData = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`http://localhost:8000/api/agents/${workflowId}/workflow`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        }
      })

      if (!response.ok) {
        if (response.status === 401) {
          // 登录过期，清除登录信息并跳转到登录页
          await chrome.storage.local.clear()
          onLogout()
          return
        }
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()
      console.log('Workflow data received:', data)
      console.log('Steps:', data.steps)
      console.log('Connections:', data.connections)
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

    // 记录开始时间（本地时间格式以匹配数据库）
    const now = new Date()
    const startTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().replace('Z', '')

    try {
      // Get current workflow configuration
      const config = getConfig(DEFAULT_CONFIG_KEY)
      const workflowName = config.workflow.metadata.name

      // Run the configured workflow
      const response = await fetch(`http://localhost:8000/api/agents/workflow/${workflowName}/execute`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        }
      })

      if (!response.ok) {
        if (response.status === 401) {
          // 登录过期，清除登录信息并跳转到登录页
          await chrome.storage.local.clear()
          onLogout()
          return
        }
        throw new Error(`API error: ${response.status}`)
      }

      const result = await response.json()
      console.log('Workflow execution started:', result)

      // Poll task status until completion
      const taskId = result.task_id
      let completed = false
      let pollCount = 0
      const maxPolls = 60 // 最多轮询60次（5分钟）

      while (!completed && pollCount < maxPolls) {
        await new Promise(resolve => setTimeout(resolve, 5000)) // 等待5秒

        const statusResponse = await fetch(`http://localhost:8000/api/agents/workflow/task/${taskId}/status`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${currentUser.token}`
          }
        })

        if (statusResponse.ok) {
          const statusData = await statusResponse.json()
          console.log('Task status:', statusData.status, `(${statusData.progress}%)`)

          if (statusData.status === 'completed' || statusData.status === 'failed') {
            completed = true

            // 记录结束时间（本地时间格式以匹配数据库）
            const endNow = new Date()
            const endTime = new Date(endNow.getTime() - endNow.getTimezoneOffset() * 60000).toISOString().replace('Z', '')

            if (statusData.status === 'completed') {
              showStatus('✅ 执行成功', 'success')
              // 导航到结果页面，传递时间范围
              const config = getConfig(DEFAULT_CONFIG_KEY)
              const workflowName = config.workflow.metadata.name
              onNavigate('workflow-result', {
                workflowName: workflowName,
                startTime: startTime,
                endTime: endTime
              })
            } else {
              showStatus('❌ 执行失败', 'error')
            }
          }
        }

        pollCount++
      }

      if (!completed) {
        showStatus('⚠️ 执行超时', 'warning')
      }
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus('❌ 执行失败', 'error')
    } finally {
      setIsRunning(false)
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
            <path d="M19 12H5M12 19l-7-7 7-7"/>
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
          <WorkflowVisualization workflowData={workflowData} />
        )}
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

function WorkflowVisualization({ workflowData }) {
  const { nodes: initialNodes, edges: initialEdges } = transformWorkflowData(workflowData)

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const edgesWithMarkers = edges.map(edge => ({
    ...edge,
    markerEnd: { type: MarkerType.ArrowClosed }
  }))

  if (!workflowData || !workflowData.steps || workflowData.steps.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📋</div>
        <div className="empty-state-title">无流程数据</div>
      </div>
    )
  }

  return (
    <>
      <div className="workflow-canvas">
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edgesWithMarkers}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            fitView
            nodeTypes={nodeTypes}
            fitViewOptions={{ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 }}
            minZoom={0.3}
            maxZoom={2}
            defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
          >
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={nodeColor}
              nodeStrokeWidth={3}
              zoomable
              pannable
              style={{ width: 80, height: 60 }}
            />
            <Background variant="dots" gap={12} size={1} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </>
  )
}

const nodeColor = (node) => {
  switch (node.data?.type) {
    case 'start':
      return '#52c41a'
    case 'end':
      return '#ff4d4f'
    default:
      return '#3b82f6'
  }
}

const transformWorkflowData = (workflowData) => {
  console.log('transformWorkflowData called with:', workflowData)

  if (!workflowData || !workflowData.steps) {
    console.warn('No workflow data or steps found')
    return { nodes: [], edges: [] }
  }

  const nodes = []
  const edges = []

  // Compact layout for small screen - vertical flow
  const nodeWidth = 140
  const nodeHeight = 60
  const verticalGap = 80

  workflowData.steps.forEach((step, index) => {
    let className = ''
    if (step.type === 'start') {
      className = 'start-node'
    } else if (step.type === 'end') {
      className = 'end-node'
    }

    nodes.push({
      id: step.id || `step-${index}`,
      type: 'custom',
      data: {
        label: step.name || step.type || `Step ${index + 1}`,
        description: step.description || '',
        type: step.type || '',
        ...step
      },
      position: { x: 50, y: index * verticalGap },
      className: className,
    })
  })

  if (workflowData.connections) {
    workflowData.connections.forEach((connection, index) => {
      edges.push({
        id: `e-${index}`,
        source: connection.from,
        target: connection.to,
        type: 'smoothstep',
      })
    })
  } else {
    for (let i = 0; i < nodes.length - 1; i++) {
      edges.push({
        id: `e${i}-${i + 1}`,
        source: nodes[i].id,
        target: nodes[i + 1].id,
        type: 'smoothstep',
      })
    }
  }

  console.log('Generated nodes:', nodes)
  console.log('Generated edges:', edges)
  return { nodes, edges }
}

export default WorkflowDetailPage
