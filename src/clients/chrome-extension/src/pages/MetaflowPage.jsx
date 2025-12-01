import React, { useState, useEffect } from 'react'
import { getMetaflow } from '../config/metaflows'
import { DEFAULT_CONFIG_KEY, getConfig } from '../config/index'

function MetaflowPage({ onNavigate, showStatus, recordingData, params }) {
  const [metaflows, setMetaflows] = useState([])
  const [isEditing, setIsEditing] = useState(false)
  const [editingNode, setEditingNode] = useState(null)
  const [currentMetaflowKey, setCurrentMetaflowKey] = useState(DEFAULT_CONFIG_KEY)
  const [metaflowYaml, setMetaflowYaml] = useState(null)

  useEffect(() => {
    // Check if we have metaflow data from API (passed from RecordPage)
    if (params?.metaflowData?.metaflow_json) {
      console.log('Using MetaFlow JSON data from API:', params.metaflowData)
      setMetaflowYaml(params.metaflowData.metaflow_yaml)

      // Use the visualization JSON directly from backend
      const generatedMetaflows = generateMetaflowsFromJson(params.metaflowData.metaflow_json)
      setMetaflows(generatedMetaflows)
      showStatus(`✅ 已加载生成的 MetaFlow (${params.metaflowData.nodes_count} 个节点)`, 'success')
    } else {
      // Fallback to config file metaflow
      console.log('Using MetaFlow from config file')
      const generatedMetaflows = generateMetaflows()
      setMetaflows(generatedMetaflows)
    }
  }, [params])

  const inferNodeType = (node) => {
    if (node.type === 'loop') return 'loop';

    const operations = node.operations || [];
    const hasNavigate = operations.some(op => op.type === 'navigate');
    const hasClick = operations.some(op => op.type === 'click');
    const hasExtract = operations.some(op => op.type === 'extract');
    const hasSelect = operations.some(op => op.type === 'select' || op.type === 'copy_action');

    if (hasExtract) return 'extract';
    if (hasSelect) return 'extract';
    if (hasNavigate || hasClick) return 'navigate';

    return 'process';
  }

  const generateMetaflowsFromJson = (metaflowJson) => {
    try {
      console.log('Using MetaFlow JSON from backend:', metaflowJson)

      // Backend already provides the visualization structure
      // We just need to map it to our frontend format
      const metaflows = metaflowJson.nodes.map(node => ({
        id: node.id,
        type: node.type,
        name: node.name,
        description: node.description,
        properties: node.properties || {}
      }))

      // Add edges information if needed
      if (metaflowJson.edges) {
        // Store edges for later use if needed
        console.log('MetaFlow edges:', metaflowJson.edges)
      }

      console.log('Converted metaflows:', metaflows)
      return metaflows
    } catch (error) {
      console.error('Failed to process MetaFlow JSON:', error)
      showStatus('⚠️ MetaFlow 处理失败，使用默认配置', 'warning')
      return generateMetaflows()
    }
  }

  const generateMetaflows = () => {
    // Load metaflow from config
    const metaflowData = getMetaflow(currentMetaflowKey);

    const metaflows = [
      {
        id: 'start',
        type: 'start',
        name: 'Start',
        description: metaflowData.task_description
      }
    ];

    // Convert nodes to metaflow format
    metaflowData.nodes.forEach(node => {
      if (node.type === 'branch_start') {
        // Add branch start node
        metaflows.push({
          id: node.id,
          type: 'branch_start',
          name: node.intent_name,
          description: node.intent_description,
          properties: {
            branches: node.branches
          }
        });
      } else if (node.type === 'branch_end') {
        // Add branch end node
        metaflows.push({
          id: node.id,
          type: 'branch_end',
          name: node.intent_name,
          description: node.intent_description
        });
      } else if (node.type === 'loop') {
        // Add loop node
        metaflows.push({
          id: node.id,
          type: 'loop',
          name: 'Loop: Extract Product Details',
          description: node.description,
          branch: node.branch,
          properties: {
            source: node.source,
            item_var: node.item_var
          }
        });

        // Add children nodes
        if (node.children) {
          node.children.forEach(child => {
            const childType = inferNodeType(child);
            metaflows.push({
              id: child.id,
              type: childType,
              name: child.intent_name,
              description: child.intent_description,
              branch: node.branch,
              properties: {
                intent_id: child.intent_id,
                operations_count: child.operations ? child.operations.length : 0,
                parent: node.id
              }
            });
          });
        }
      } else {
        const nodeType = inferNodeType(node);
        metaflows.push({
          id: node.id,
          type: nodeType,
          name: node.intent_name,
          description: node.intent_description,
          branch: node.branch,
          properties: {
            intent_id: node.intent_id,
            operations_count: node.operations ? node.operations.length : 0
          }
        });
      }
    });

    metaflows.push({
      id: 'end',
      type: 'end',
      name: 'End',
      description: 'Workflow completed successfully'
    });

    return metaflows;
  }

  const getMetaflowIcon = (type) => {
    switch (type) {
      case 'start':
        return '🚀'
      case 'branch_start':
        return '🔀'
      case 'branch_end':
        return '🔗'
      case 'navigate':
        return '🌐'
      case 'interact':
        return '👆'
      case 'extract':
        return '📊'
      case 'process':
        return '⚙️'
      case 'loop':
        return '🔄'
      case 'end':
        return '✅'
      default:
        return '📌'
    }
  }

  const getMetaflowColor = (type) => {
    switch (type) {
      case 'start':
        return '#10b981'
      case 'branch_start':
        return '#f59e0b'
      case 'branch_end':
        return '#f59e0b'
      case 'navigate':
        return '#8b5cf6'
      case 'interact':
        return '#f59e0b'
      case 'extract':
        return '#3b82f6'
      case 'process':
        return '#06b6d4'
      case 'loop':
        return '#ec4899'
      case 'end':
        return '#10b981'
      default:
        return '#6b7280'
    }
  }

  const renderMetaflowNode = (metaflow) => {
    return (
      <div
        className={`metaflow-node ${isEditing ? 'editable' : ''}`}
        style={{ borderColor: getMetaflowColor(metaflow.type) }}
        onClick={() => handleNodeClick(metaflow)}
      >
        <div className="metaflow-icon" style={{ backgroundColor: getMetaflowColor(metaflow.type) }}>
          {getMetaflowIcon(metaflow.type)}
        </div>
        <div className="metaflow-details">
          <div className="metaflow-name">{metaflow.name}</div>
          <div className="metaflow-description">{metaflow.description}</div>
          {metaflow.properties && (
            <div className="metaflow-properties">
              {Object.entries(metaflow.properties).map(([key, value]) => (
                <div key={key} className="property-item">
                  <span className="property-key">{key}:</span>
                  <span className="property-value">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderMetaflowNodes = () => {
    const elements = []
    let i = 0

    while (i < metaflows.length) {
      const metaflow = metaflows[i]

      // Check if this is a branch_start node
      if (metaflow.type === 'branch_start') {
        // Render branch_start node
        elements.push(
          <React.Fragment key={metaflow.id}>
            {renderMetaflowNode(metaflow)}
            <div className="metaflow-arrow">
              <svg width="24" height="40" viewBox="0 0 24 40">
                <line x1="12" y1="0" x2="12" y2="32" stroke="#d1d5db" strokeWidth="2"/>
                <polygon points="12,40 8,32 16,32" fill="#d1d5db"/>
              </svg>
            </div>
          </React.Fragment>
        )

        // Find branch_end node
        let branchEndIndex = i + 1
        while (branchEndIndex < metaflows.length && metaflows[branchEndIndex].type !== 'branch_end') {
          branchEndIndex++
        }

        // Group nodes by branch
        const branchNodes = {}
        for (let j = i + 1; j < branchEndIndex; j++) {
          const node = metaflows[j]
          const branch = node.branch || 'default'
          if (!branchNodes[branch]) {
            branchNodes[branch] = []
          }
          branchNodes[branch].push(node)
        }

        // Render branches
        const branches = Object.keys(branchNodes)
        if (branches.length > 0) {
          elements.push(
            <div key={`parallel-${metaflow.id}`} className="parallel-branches">
              {branches.map((branchName, branchIndex) => (
                <div key={branchName} className="parallel-branch">
                  {branchNodes[branchName].map((node, nodeIndex) => (
                    <React.Fragment key={node.id}>
                      {renderMetaflowNode(node)}
                      {nodeIndex < branchNodes[branchName].length - 1 && (
                        <div className="metaflow-arrow">
                          <svg width="24" height="40" viewBox="0 0 24 40">
                            <line x1="12" y1="0" x2="12" y2="32" stroke="#d1d5db" strokeWidth="2"/>
                            <polygon points="12,40 8,32 16,32" fill="#d1d5db"/>
                          </svg>
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              ))}
            </div>
          )
        }

        // Skip to branch_end
        i = branchEndIndex

        // Render merge arrow before branch_end
        if (i < metaflows.length) {
          elements.push(
            <div key={`merge-arrow-${i}`} className="metaflow-arrow">
              <svg width="24" height="40" viewBox="0 0 24 40">
                <line x1="12" y1="0" x2="12" y2="32" stroke="#d1d5db" strokeWidth="2"/>
                <polygon points="12,40 8,32 16,32" fill="#d1d5db"/>
              </svg>
            </div>
          )
        }
      } else {
        // Regular node
        elements.push(
          <React.Fragment key={metaflow.id}>
            {renderMetaflowNode(metaflow)}
            {i < metaflows.length - 1 && (
              <div className="metaflow-arrow">
                <svg width="24" height="40" viewBox="0 0 24 40">
                  <line x1="12" y1="0" x2="12" y2="32" stroke="#d1d5db" strokeWidth="2"/>
                  <polygon points="12,40 8,32 16,32" fill="#d1d5db"/>
                </svg>
              </div>
            )}
          </React.Fragment>
        )
        i++
      }
    }

    return elements
  }

  const handleEdit = () => {
    setIsEditing(!isEditing)
    if (!isEditing) {
      showStatus('📝 进入编辑模式', 'info')
    } else {
      showStatus('✅ 保存成功', 'success')
      setEditingNode(null)
    }
  }

  const handleNodeClick = (metaflow) => {
    if (isEditing) {
      setEditingNode(metaflow)
    }
  }

  const handleSaveNode = (updatedNode) => {
    setMetaflows(metaflows.map(node =>
      node.id === updatedNode.id ? updatedNode : node
    ))
    setEditingNode(null)
    showStatus('✅ 节点已更新', 'success')
  }

  const handleDeleteNode = (nodeId) => {
    setMetaflows(metaflows.filter(node => node.id !== nodeId))
    setEditingNode(null)
    showStatus('✅ 节点已删除', 'success')
  }

  const handleNext = () => {
    // Pass all relevant data to workflow generation page
    const navigationData = {
      recordingData,
      metaflowYaml,
      sessionId: params?.sessionId,
      intentsData: params?.intentsData,
      metaflowData: params?.metaflowData,
      fromPage: 'metaflow'
    }
    console.log('Navigating to workflow-generation with data:', navigationData)
    onNavigate('workflow-generation', navigationData)
  }

  return (
    <div className="page metaflow-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate(params?.fromPage || 'record')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">Metaflow</div>
        <button
          className="run-button"
          onClick={handleEdit}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          <span>{isEditing ? '保存' : '编辑'}</span>
        </button>
      </div>

      <div className="metaflow-content">
        {/* Metaflow Visualization */}
        <div className="metaflow-visualization">
          {renderMetaflowNodes()}
        </div>

        {/* Action Bar */}
        <div className="metaflow-actions">
          <button
            className="start-record-button"
            onClick={handleNext}
          >
            <span>下一步：生成 Workflow</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>

      {/* Edit Modal */}
      {editingNode && (
        <EditNodeModal
          node={editingNode}
          onSave={handleSaveNode}
          onDelete={handleDeleteNode}
          onClose={() => setEditingNode(null)}
        />
      )}
    </div>
  )
}

function EditNodeModal({ node, onSave, onDelete, onClose }) {
  const [name, setName] = useState(node.name)
  const [description, setDescription] = useState(node.description)
  const [agentType, setAgentType] = useState(node.properties?.agent_type || '')
  const [tool, setTool] = useState(node.properties?.tool || '')
  const [instruction, setInstruction] = useState(node.properties?.instruction || '')

  const handleSave = () => {
    onSave({
      ...node,
      name,
      description,
      properties: {
        ...node.properties,
        agent_type: agentType,
        tool: tool,
        instruction: instruction
      }
    })
  }

  // Check if this is a start or end node (should not be fully editable)
  const isSystemNode = node.type === 'start' || node.type === 'end'

  return (
    <div className="node-detail-modal" onClick={onClose}>
      <div className="node-detail-content edit-modal-scrollable" onClick={(e) => e.stopPropagation()}>
        <h3>编辑节点</h3>

        <div className="detail-item">
          <div className="detail-label">名称</div>
          <input
            type="text"
            className="edit-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isSystemNode}
          />
        </div>

        <div className="detail-item">
          <div className="detail-label">描述</div>
          <textarea
            className="edit-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            disabled={isSystemNode}
          />
        </div>

        {!isSystemNode && (
          <>
            <div className="detail-item">
              <div className="detail-label">Agent类型</div>
              <select
                className="edit-input"
                value={agentType}
                onChange={(e) => setAgentType(e.target.value)}
              >
                <option value="">选择Agent类型</option>
                <option value="tool_agent">Tool Agent</option>
                <option value="text_agent">Text Agent</option>
                <option value="code_agent">Code Agent</option>
              </select>
            </div>

            <div className="detail-item">
              <div className="detail-label">工具</div>
              <input
                type="text"
                className="edit-input"
                value={tool}
                onChange={(e) => setTool(e.target.value)}
                placeholder="例如: browser_use, llm_extract"
              />
            </div>

            <div className="detail-item">
              <div className="detail-label">指令</div>
              <textarea
                className="edit-textarea"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                rows={4}
                placeholder="输入该步骤的具体执行指令"
              />
            </div>
          </>
        )}

        <div className="modal-actions">
          {!isSystemNode && (
            <button className="delete-btn" onClick={() => onDelete(node.id)}>
              删除节点
            </button>
          )}
          <div className="modal-actions-right">
            <button className="cancel-btn" onClick={onClose}>
              取消
            </button>
            <button className="save-btn" onClick={handleSave}>
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default MetaflowPage
