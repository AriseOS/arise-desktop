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

    // Workflow data from tests/test_data/coffee_allegro/output/workflow.yaml
    setTimeout(() => {
      const workflowYaml = {
        apiVersion: "agentcrafter.io/v1",
        kind: "Workflow",
        metadata: {
          name: "allegro-coffee-collection-workflow",
          description: "Collect coffee product information from Allegro including product name, price, and sales count",
          version: "1.0.0",
          tags: ["scraper", "allegro", "coffee", "price-collection"]
        },
        steps: [
          {
            id: "init-vars",
            name: "Initialize variables",
            agent_type: "variable",
            description: "Initialize data collection variables",
            agent_instruction: "Initialize product collection variables"
          },
          {
            id: "extract-product-urls",
            name: "Extract coffee product URLs",
            agent_type: "scraper_agent",
            description: "Navigate to coffee category and extract all product URLs from first page",
            agent_instruction: "Visit Allegro coffee category page and extract all product URLs"
          },
          {
            id: "save-urls",
            name: "Save product URLs",
            agent_type: "variable",
            description: "Save extracted URLs to variable",
            agent_instruction: "Save product URLs to collection variable"
          },
          {
            id: "collect-product-details",
            name: "Collect product details",
            agent_type: "foreach",
            description: "Iterate through all coffee products and extract detailed information",
            source: "{{all_product_urls}}",
            item_var: "current_product",
            steps: [
              {
                id: "scrape-product-info",
                name: "Scrape product information",
                agent_type: "scraper_agent",
                description: "Extract product name, price, and sales count",
                agent_instruction: "Visit product detail page and extract name, price, and sales count"
              },
              {
                id: "append-product",
                name: "Add product to collection",
                agent_type: "variable",
                description: "Append product information to collection list",
                agent_instruction: "Add product to collection list"
              },
              {
                id: "store-product",
                name: "Store product to database",
                agent_type: "storage_agent",
                description: "Persist product information to database",
                agent_instruction: "Store coffee product information to database"
              }
            ]
          },
          {
            id: "prepare-output",
            name: "Prepare final output",
            agent_type: "variable",
            description: "Organize collection results and prepare final response",
            agent_instruction: "Prepare final output with collection summary"
          }
        ]
      };

      // Transform to workflow visualization format
      const steps = [
        {
          id: 'step-start',
          type: 'start',
          name: 'Start',
          description: workflowYaml.metadata.description,
          agent_type: 'start'
        }
      ];

      // Convert workflow steps
      workflowYaml.steps.forEach(step => {
        if (step.agent_type === 'foreach') {
          // Add foreach loop node
          steps.push({
            id: step.id,
            type: 'foreach',
            name: step.name,
            description: step.description,
            agent_type: step.agent_type,
            source: step.source,
            item_var: step.item_var
          });

          // Add child steps
          if (step.steps) {
            step.steps.forEach(childStep => {
              steps.push({
                id: childStep.id,
                type: childStep.agent_type,
                name: childStep.name,
                description: childStep.description,
                agent_type: childStep.agent_type,
                parent: step.id
              });
            });
          }
        } else {
          steps.push({
            id: step.id,
            type: step.agent_type,
            name: step.name,
            description: step.description,
            agent_type: step.agent_type
          });
        }
      });

      steps.push({
        id: 'step-end',
        type: 'end',
        name: 'End',
        description: 'Workflow completed successfully',
        agent_type: 'end'
      });

      // Generate connections
      const connections = [];
      for (let i = 0; i < steps.length - 1; i++) {
        connections.push({
          from: steps[i].id,
          to: steps[i + 1].id
        });
      }

      const workflow = {
        name: workflowYaml.metadata.name,
        description: workflowYaml.metadata.description,
        steps: steps,
        connections: connections
      };

      setWorkflowData(workflow)
      setLoading(false)
    }, 500)
  }

  const pollTaskStatus = async (taskId, startTime) => {
    const pollInterval = 2000 // Poll every 2 seconds
    const maxAttempts = 300 // Max 10 minutes (300 * 2s)
    let attempts = 0

    const poll = async () => {
      if (attempts >= maxAttempts) {
        showStatus('❌ 执行超时', 'error')
        setIsRunning(false)
        return
      }

      try {
        const response = await fetch(`http://localhost:8000/api/agents/workflow/task/${taskId}/status`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${currentUser.token}`
          }
        })

        if (!response.ok) {
          throw new Error(`Failed to get task status: ${response.status}`)
        }

        const taskInfo = await response.json()
        console.log('Task status:', taskInfo)

        if (taskInfo.status === 'completed') {
          setIsRunning(false)

          // Record end time in local timezone to match database format
          const endNow = new Date()
          const endTime = new Date(endNow.getTime() - endNow.getTimezoneOffset() * 60000).toISOString().replace('Z', '')

          if (taskInfo.result && taskInfo.result.success) {
            showStatus('✅ 执行成功', 'success')
            // Navigate to result page with time range
            setTimeout(() => {
              onNavigate('workflow-result', {
                workflowName: 'allegro-coffee-collection-workflow',
                startTime: startTime,
                endTime: endTime
              })
            }, 1000)
          } else {
            showStatus('⚠️ 执行完成但有错误', 'warning')
          }
          return
        } else if (taskInfo.status === 'failed') {
          setIsRunning(false)
          showStatus(`❌ 执行失败: ${taskInfo.error || '未知错误'}`, 'error')
          return
        } else if (taskInfo.status === 'running') {
          // Continue polling
          attempts++
          setTimeout(poll, pollInterval)
        }
      } catch (err) {
        console.error('Poll task status error:', err)
        showStatus('❌ 获取状态失败', 'error')
        setIsRunning(false)
      }
    }

    poll()
  }

  const handleRunWorkflow = async () => {
    if (isRunning) return

    setIsRunning(true)
    showStatus('🚀 开始执行...', 'info')

    // Record start time in local timezone to match database format
    const now = new Date()
    const startTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().replace('Z', '')

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
      console.log('Workflow execution started:', result)

      if (result.success && result.task_id) {
        // Start polling for task status, pass startTime
        pollTaskStatus(result.task_id, startTime)
      } else {
        showStatus('❌ 启动失败', 'error')
        setIsRunning(false)
      }
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus('❌ 启动失败', 'error')
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
    case 'foreach':
      return '#ec4899'
    case 'variable':
      return '#06b6d4'
    case 'scraper_agent':
      return '#8b5cf6'
    case 'storage_agent':
      return '#f59e0b'
    case 'tool_agent':
      return '#3b82f6'
    case 'text_agent':
      return '#10b981'
    default:
      return '#6b7280'
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
