import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
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
import { getWorkflow } from '../config/workflows'
import { DEFAULT_CONFIG_KEY } from '../config/index'
import { BACKEND_CONFIG } from '../config/backend'
import Icon from '../components/Icons'
import '../styles/WorkflowGenerationPage.css'

const nodeTypes = {
  custom: CustomNode,
}

function WorkflowGenerationPage({ session, onNavigate, showStatus, recordingData, version }) {
  const { t } = useTranslation()
  const userId = session?.username;
  const [workflowData, setWorkflowData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [currentWorkflowKey, setCurrentWorkflowKey] = useState(DEFAULT_CONFIG_KEY)

  useEffect(() => {
    // Check if this is a quick-generated workflow
    if (recordingData && recordingData.quickGenerated && recordingData.workflowName) {
      // Load the quick-generated workflow
      loadQuickGeneratedWorkflow(recordingData.workflowName);
    } else {
      // Default behavior: generate hardcoded workflow
      generateWorkflowData();
    }
  }, [recordingData])

  const loadQuickGeneratedWorkflow = async (workflowName) => {
    setLoading(true);
    try {
      showStatus(t('workflowGeneration.loading'), "info");

      // Fetch workflow detail from backend
      const response = await fetch(`${BACKEND_CONFIG.httpBase}/api/v1/workflows/${workflowName}?user_id=${userId}`);

      if (!response.ok) {
        throw new Error(`Failed to load workflow: ${response.status}`);
      }

      const workflowDetail = await response.json();

      // Version check: reject v1 format
      if (workflowDetail.apiVersion === 'ami.io/v1' || workflowDetail.kind === 'Workflow') {
        throw new Error(t('workflowGeneration.v1NotSupported'));
      }

      // Transform to workflow visualization format (v2 format)
      const steps = [
        {
          id: 'step-start',
          type: 'start',
          name: 'Start',
          description: workflowDetail.description,
          agent: 'start'
        }
      ];

      // Convert workflow steps (v2 format: 'agent' instead of 'agent_type', 'foreach' as key, 'do' for body, 'as' for variable)
      workflowDetail.steps.forEach(step => {
        if (step.type === 'branch_start') {
          // Add branch start node
          steps.push({
            id: step.id,
            type: 'branch_start',
            name: step.name,
            description: step.description,
            agent: 'branch_start',
            branches: step.branches
          });
        } else if (step.type === 'branch_end') {
          // Add branch end node
          steps.push({
            id: step.id,
            type: 'branch_end',
            name: step.name,
            description: step.description,
            agent: 'branch_end'
          });
        } else if ('foreach' in step) {
          // v2 format: foreach as a key
          steps.push({
            id: step.id,
            type: 'foreach',
            name: step.name || step.intent_name,
            description: step.description || step.intent_description,
            agent: 'foreach',
            branch: step.branch,
            foreach: step.foreach,
            as: step.as
          });

          // Add child steps (v2: 'do' instead of 'steps')
          if (step.do) {
            step.do.forEach(childStep => {
              steps.push({
                id: childStep.id,
                type: childStep.agent,
                name: childStep.name || childStep.intent_name,
                description: childStep.description || childStep.intent_description,
                agent: childStep.agent,
                branch: step.branch,
                parent: step.id
              });
            });
          }
        } else {
          steps.push({
            id: step.id,
            type: step.agent || step.type,
            name: step.name || step.intent_name,
            description: step.description || step.intent_description,
            agent: step.agent || step.type,
            branch: step.branch
          });
        }
      });

      steps.push({
        id: 'step-end',
        type: 'end',
        name: 'End',
        description: 'Workflow completed successfully',
        agent: 'end'
      });

      // Generate connections with parallel support
      const connections = [];

      for (let i = 0; i < steps.length - 1; i++) {
        const currentStep = steps[i];
        const nextStep = steps[i + 1];

        // Handle branch_start connections
        if (currentStep.type === 'branch_start') {
          // Connect to first step of each branch
          const branches = currentStep.branches || [];
          branches.forEach(branchName => {
            const firstBranchStep = steps.find(s => s.branch === branchName);
            if (firstBranchStep) {
              connections.push({
                from: currentStep.id,
                to: firstBranchStep.id
              });
            }
          });
          continue;
        }

        // Handle branch_end connections
        if (nextStep.type === 'branch_end') {
          // Only connect if current step is the last in its branch
          const sameBranchSteps = steps.filter(s => s.branch === currentStep.branch);
          const lastInBranch = sameBranchSteps[sameBranchSteps.length - 1];
          if (currentStep.id === lastInBranch.id) {
            connections.push({
              from: currentStep.id,
              to: nextStep.id
            });
          }
          continue;
        }

        // Regular sequential connections (same branch or no branch)
        if (!currentStep.branch || currentStep.branch === nextStep.branch) {
          connections.push({
            from: currentStep.id,
            to: nextStep.id
          });
        }
      }

      const workflow = {
        name: workflowDetail.name,
        description: workflowDetail.description,
        steps: steps,
        connections: connections
      };

      setWorkflowData(workflow);
      showStatus(t('workflowGeneration.loadSuccess'), "success");
    } catch (error) {
      console.error("Load quick generated workflow error:", error);
      showStatus(t('workflowGeneration.loadFailed', { error: error.message }), "error");
      // Fallback to default workflow
      generateWorkflowData();
    } finally {
      setLoading(false);
    }
  };

  const generateWorkflowData = () => {
    setLoading(true)

    // Load workflow from config (v2 format)
    setTimeout(() => {
      const workflowYaml = getWorkflow(currentWorkflowKey);

      // Version check: reject v1 format
      if (workflowYaml.apiVersion === 'ami.io/v1' || workflowYaml.kind === 'Workflow') {
        showStatus(t('workflowGeneration.v1NotSupported'), 'error');
        setLoading(false);
        return;
      }

      // Transform to workflow visualization format (v2 format)
      const steps = [
        {
          id: 'step-start',
          type: 'start',
          name: 'Start',
          description: workflowYaml.description,
          agent: 'start'
        }
      ];

      // Convert workflow steps (v2 format)
      workflowYaml.steps.forEach(step => {
        if (step.type === 'branch_start') {
          // Add branch start node
          steps.push({
            id: step.id,
            type: 'branch_start',
            name: step.name,
            description: step.description,
            agent: 'branch_start',
            branches: step.branches
          });
        } else if (step.type === 'branch_end') {
          // Add branch end node
          steps.push({
            id: step.id,
            type: 'branch_end',
            name: step.name,
            description: step.description,
            agent: 'branch_end'
          });
        } else if ('foreach' in step) {
          // v2 format: foreach as a key
          steps.push({
            id: step.id,
            type: 'foreach',
            name: step.name || step.intent_name,
            description: step.description || step.intent_description,
            agent: 'foreach',
            branch: step.branch,
            foreach: step.foreach,
            as: step.as
          });

          // Add child steps (v2: 'do' instead of 'steps')
          if (step.do) {
            step.do.forEach(childStep => {
              steps.push({
                id: childStep.id,
                type: childStep.agent,
                name: childStep.name || childStep.intent_name,
                description: childStep.description || childStep.intent_description,
                agent: childStep.agent,
                branch: step.branch,
                parent: step.id
              });
            });
          }
        } else {
          steps.push({
            id: step.id,
            type: step.agent || step.type,
            name: step.name || step.intent_name,
            description: step.description || step.intent_description,
            agent: step.agent || step.type,
            branch: step.branch
          });
        }
      });

      steps.push({
        id: 'step-end',
        type: 'end',
        name: 'End',
        description: 'Workflow completed successfully',
        agent: 'end'
      });

      // Generate connections with parallel support
      const connections = [];

      for (let i = 0; i < steps.length - 1; i++) {
        const currentStep = steps[i];
        const nextStep = steps[i + 1];

        // Handle branch_start connections
        if (currentStep.type === 'branch_start') {
          // Connect to first step of each branch
          const branches = currentStep.branches || [];
          branches.forEach(branchName => {
            const firstBranchStep = steps.find(s => s.branch === branchName);
            if (firstBranchStep) {
              connections.push({
                from: currentStep.id,
                to: firstBranchStep.id
              });
            }
          });
          continue;
        }

        // Handle branch_end connections
        if (nextStep.type === 'branch_end') {
          // Only connect if current step is the last in its branch
          const sameBranchSteps = steps.filter(s => s.branch === currentStep.branch);
          const lastInBranch = sameBranchSteps[sameBranchSteps.length - 1];
          if (currentStep.id === lastInBranch.id) {
            connections.push({
              from: currentStep.id,
              to: nextStep.id
            });
          }
          continue;
        }

        // Regular sequential connections (same branch or no branch)
        if (!currentStep.branch || currentStep.branch === nextStep.branch) {
          connections.push({
            from: currentStep.id,
            to: nextStep.id
          });
        }
      }

      const workflow = {
        name: workflowYaml.name,
        description: workflowYaml.description,
        steps: steps,
        connections: connections
      };

      setWorkflowData(workflow)
      setLoading(false)
    }, 500)
  }

  const pollTaskStatus = async (taskId, startTime, workflowName) => {
    const pollInterval = 2000 // Poll every 2 seconds
    const maxAttempts = 450 // Max 15 minutes (450 * 2s)
    let attempts = 0

    const poll = async () => {
      if (attempts >= maxAttempts) {
        showStatus(t('workflowGeneration.executeTimeout'), 'error')
        setIsRunning(false)
        return
      }

      try {
        const response = await fetch(`http://localhost:8000/api/agents/workflow/task/${taskId}/status`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session?.apiKey}`
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
            showStatus(t('workflowGeneration.executeSuccess'), 'success')
            // Navigate to result page with time range
            setTimeout(() => {
              onNavigate('workflow-result', {
                workflowName: workflowName,
                startTime: startTime,
                endTime: endTime
              })
            }, 1000)
          } else {
            showStatus(t('workflowGeneration.executeWarning'), 'warning')
          }
          return
        } else if (taskInfo.status === 'failed') {
          setIsRunning(false)
          showStatus(t('workflowGeneration.executeFailed', { error: taskInfo.error || t('workflowGeneration.unknownError') }), 'error')
          return
        } else if (taskInfo.status === 'running') {
          // Continue polling
          attempts++
          setTimeout(poll, pollInterval)
        }
      } catch (err) {
        console.error('Poll task status error:', err)
        showStatus(t('workflowGeneration.getStatusFailed'), 'error')
        setIsRunning(false)
      }
    }

    poll()
  }

  const handleRunWorkflow = async () => {
    if (isRunning) return

    setIsRunning(true)
    showStatus(t('workflowGeneration.startExecution'), 'info')

    // Record start time in local timezone to match database format
    const now = new Date()
    const startTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().replace('Z', '')

    // Get current workflow name from config
    const currentWorkflow = getWorkflow(currentWorkflowKey)
    const workflowName = currentWorkflow.metadata.name

    try {
      const response = await fetch(`http://localhost:8000/api/agents/workflow/${workflowName}/execute`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session?.apiKey}`
        }
      })

      if (!response.ok) {
        throw new Error(`Workflow execution failed: ${response.status}`)
      }

      const result = await response.json()
      console.log('Workflow execution started:', result)

      if (result.success && result.task_id) {
        // Start polling for task status, pass startTime and workflowName
        pollTaskStatus(result.task_id, startTime, workflowName)
      } else {
        showStatus(t('workflowGeneration.startFailed'), 'error')
        setIsRunning(false)
      }
    } catch (err) {
      console.error('Run workflow error:', err)
      showStatus(t('workflowGeneration.startFailed'), 'error')
      setIsRunning(false)
    }
  }

  const handleSave = async () => {
    showStatus(t('workflowGeneration.saving'), 'info')

    try {
      // TODO: Call actual save workflow API
      await new Promise(resolve => setTimeout(resolve, 1000))

      showStatus(t('workflowGeneration.saveSuccess'), 'success')

      // Navigate back to main page after save
      setTimeout(() => {
        onNavigate('main')
      }, 1000)
    } catch (err) {
      console.error('Save workflow error:', err)
      showStatus(t('workflowGeneration.saveFailed'), 'error')
    }
  }

  return (
    <div className="page workflow-generation-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('metaflow')}
        >
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title">Workflow</div>
        <button
          className="run-button"
          onClick={handleRunWorkflow}
          disabled={isRunning || loading}
        >
          {isRunning ? (
            <>
              <div className="btn-spinner"></div>
              <span>{t('workflowGeneration.statusRunning')}</span>
            </>
          ) : (
            <>
              <Icon icon="play" size={16} />
              <span>{t('workflowGeneration.statusRun')}</span>
            </>
          )}
        </button>
      </div>

      <div className="workflow-generation-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="clock" size={48} /></div>
            <div className="empty-state-title">{t('workflowGeneration.generating')}</div>
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
            <Icon icon="save" size={20} />
            <span>{t('workflowGeneration.saveWorkflow')}</span>
          </button>
        </div>
      )}

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
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
        <div className="empty-state-icon"><Icon icon="clipboard" size={48} /></div>
        <div className="empty-state-title">{t('workflowGeneration.noFlowData')}</div>
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
    case 'branch_start':
    case 'branch_end':
      return '#f59e0b'
    case 'foreach':
      return '#ec4899'
    case 'variable':
      return '#06b6d4'
    case 'scraper_agent':
      return '#8b5cf6'
    case 'storage_agent':
      return '#f59e0b'
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

  // Layout configuration
  const verticalGap = 80
  const amazonYOffset = 15  // Amazon branch slightly lower
  let currentY = 0
  let branchStartIndex = -1
  let branchEndIndex = -1
  let branchStartY = 0

  // Find branch start and end indices
  workflowData.steps.forEach((step, index) => {
    if (step.type === 'branch_start') {
      branchStartIndex = index
    } else if (step.type === 'branch_end') {
      branchEndIndex = index
    }
  })

  // Group branch steps by branch and calculate positions
  const branchStepIndices = { allegro: [], amazon: [] }
  if (branchStartIndex !== -1 && branchEndIndex !== -1) {
    workflowData.steps.forEach((step, index) => {
      if (index > branchStartIndex && index < branchEndIndex) {
        if (step.branch === 'allegro') {
          branchStepIndices.allegro.push(index)
        } else if (step.branch === 'amazon') {
          branchStepIndices.amazon.push(index)
        }
      }
    })
  }

  // Process steps
  workflowData.steps.forEach((step, index) => {
    let className = ''
    let position = { x: 50, y: currentY }

    if (step.type === 'start') {
      className = 'start-node'
      currentY += verticalGap
    } else if (step.type === 'end') {
      className = 'end-node'
      currentY += verticalGap
    } else if (step.type === 'branch_start') {
      className = 'branch-node'
      branchStartY = currentY + verticalGap  // Record Y after branch_start
      currentY += verticalGap
    } else if (step.type === 'branch_end') {
      className = 'branch-node'
      // Calculate Y after branch section based on max branch length
      const maxBranchLength = Math.max(branchStepIndices.allegro.length, branchStepIndices.amazon.length)
      const branchEndY = branchStartY + (maxBranchLength * verticalGap)
      position = { x: 50, y: branchEndY }
      currentY = branchEndY + verticalGap
    } else if (branchStartIndex !== -1 && branchEndIndex !== -1 &&
      index > branchStartIndex && index < branchEndIndex) {
      // This step is inside branch section
      if (step.branch === 'allegro') {
        // Left branch (Allegro) - calculate Y based on position in allegro array
        const allegroIndex = branchStepIndices.allegro.indexOf(index)
        const yPos = branchStartY + (allegroIndex * verticalGap)
        position = { x: -80, y: yPos }
      } else if (step.branch === 'amazon') {
        // Right branch (Amazon) - calculate Y based on position in amazon array, with slight offset
        const amazonIndex = branchStepIndices.amazon.indexOf(index)
        const yPos = branchStartY + (amazonIndex * verticalGap) + amazonYOffset
        position = { x: 180, y: yPos }
      }
      // Don't increment currentY for branch steps
    } else {
      // Regular steps outside parallel section
      currentY += verticalGap
    }

    nodes.push({
      id: step.id || `step-${index}`,
      type: 'custom',
      data: {
        label: step.name || step.type || `Step ${index + 1}`,
        description: step.description || '',
        type: step.type || '',
        branch: step.branch,
        ...step
      },
      position: position,
      className: className,
    })
  })

  // Use connections from workflowData
  if (workflowData.connections) {
    workflowData.connections.forEach((connection, index) => {
      edges.push({
        id: `e-${index}`,
        source: connection.from,
        target: connection.to,
        type: 'smoothstep',
      })
    })
  }

  console.log('Generated nodes:', nodes)
  console.log('Generated edges:', edges)
  return { nodes, edges }
}

export default WorkflowGenerationPage
