import React, { useState, useEffect } from 'react'
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

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowGenerationPage({ currentUser, onNavigate, showStatus, recordingData }) {
  const [workflowData, setWorkflowData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    // Always generate hardcoded workflow (not dependent on actual recording data)
    generateWorkflowData()
  }, [])

  const generateWorkflowData = () => {
    setLoading(true)

    // Generate workflow based on real workflow data structure
    // In a real implementation, this would call an API
    setTimeout(() => {
      const workflow = {
        name: 'Wiki Activity Report Workflow',
        description: 'Automatically collect Wiki activity data, generate work report, and send to WeChat',
        steps: [
          {
            id: 'step-start',
            type: 'start',
            name: 'Start',
            description: 'Initialize workflow',
            agent_type: 'start'
          },
          {
            id: 'step-collect',
            type: 'tool_agent',
            name: 'Collect Wiki Activity Data',
            description: 'Use browser_use tool to navigate to user Wiki page and extract daily activity data',
            agent_type: 'tool_agent',
            tool: 'browser_use',
            instruction: 'Navigate to provided Wiki URL and extract daily activity data'
          },
          {
            id: 'step-generate',
            type: 'text_agent',
            name: 'Generate Work Report',
            description: 'Use llm_extract to process collected data and generate formatted work report',
            agent_type: 'text_agent',
            tool: 'llm_extract',
            instruction: 'Process input activity data using llm_extract tool to generate formatted work report'
          },
          {
            id: 'step-send',
            type: 'tool_agent',
            name: 'Send Report to WeChat',
            description: 'Use browser_use to send generated report to specified leader via WeChat',
            agent_type: 'tool_agent',
            tool: 'browser_use',
            instruction: 'Use browser_use tool to send report to specified WeChat contact'
          },
          {
            id: 'step-end',
            type: 'end',
            name: 'End',
            description: 'Workflow completed successfully',
            agent_type: 'end'
          }
        ],
        connections: [
          { from: 'step-start', to: 'step-collect' },
          { from: 'step-collect', to: 'step-generate' },
          { from: 'step-generate', to: 'step-send' },
          { from: 'step-send', to: 'step-end' }
        ]
      }

      setWorkflowData(workflow)
      setLoading(false)
    }, 500)
  }

  const handleRunWorkflow = async () => {
    if (isRunning) return

    setIsRunning(true)
    showStatus('🚀 运行中...', 'info')

    try {
      const response = await fetch(`http://localhost:8000/api/agents/workflow/allegro-coffee-collection-workflow/execute`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        }
      })

      if (!response.ok) {
        throw new Error(`Workflow execution failed: ${response.status}`)
      }

      const result = await response.json()
      console.log('Workflow execution completed:', result)

      if (result.success) {
        showStatus('✅ 执行成功', 'success')
      } else {
        showStatus('❌ 执行失败', 'error')
      }
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus('❌ 执行失败', 'error')
    } finally {
      setIsRunning(false)
    }
  }

  const handleSave = async () => {
    showStatus('💾 保存中...', 'info')

    try {
      // TODO: Call actual save workflow API
      await new Promise(resolve => setTimeout(resolve, 1000))

      showStatus('✅ 保存成功', 'success')

      // Navigate back to main page after save
      setTimeout(() => {
        onNavigate('main')
      }, 1000)
    } catch (err) {
      console.error('Save workflow error:', err)
      showStatus('❌ 保存失败', 'error')
    }
  }

  return (
    <div className="page workflow-generation-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('metaflow')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">Workflow</div>
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

      <div className="workflow-generation-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon">⏳</div>
            <div className="empty-state-title">生成中...</div>
          </div>
        )}

        {!loading && workflowData && (
          <WorkflowVisualization workflowData={workflowData} />
        )}
      </div>

      {/* Save Button at Bottom */}
      {!loading && workflowData && (
        <div className="workflow-save-actions">
          <button
            className="start-record-button"
            onClick={handleSave}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              <polyline points="17 21 17 13 7 13 7 21"/>
              <polyline points="7 3 7 8 15 8"/>
            </svg>
            <span>保存 Workflow</span>
          </button>
        </div>
      )}

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

export default WorkflowGenerationPage
