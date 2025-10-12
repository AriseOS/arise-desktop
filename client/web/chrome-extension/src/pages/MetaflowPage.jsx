import React, { useState, useEffect } from 'react'

function MetaflowPage({ onNavigate, showStatus, recordingData }) {
  const [metaflows, setMetaflows] = useState([])
  const [isEditing, setIsEditing] = useState(false)
  const [editingNode, setEditingNode] = useState(null)

  useEffect(() => {
    // Always generate hardcoded metaflows (not dependent on actual recording data)
    const generatedMetaflows = generateMetaflows()
    setMetaflows(generatedMetaflows)
  }, [])

  const generateMetaflows = () => {
    // Generate hardcoded metaflows with more details based on real workflow
    const metaflows = [
      {
        id: 'start',
        type: 'start',
        name: 'Start',
        description: 'Workflow initialization'
      },
      {
        id: 'step-1',
        type: 'navigate',
        name: 'Collect Wiki Activity Data',
        description: 'Use browser_use tool to navigate to user Wiki page and extract daily activity data. Input: Wiki URL, Output: Activity data in text format',
        properties: {
          agent_type: 'tool_agent',
          tool: 'browser_use',
          instruction: 'Navigate to provided Wiki URL and extract daily activity data'
        }
      },
      {
        id: 'step-2',
        type: 'process',
        name: 'Generate Work Report',
        description: 'Use llm_extract tool to summarize and reorganize collected activity data into a formatted work report',
        properties: {
          agent_type: 'text_agent',
          tool: 'llm_extract',
          instruction: 'Process input activity data using llm_extract tool to generate formatted work report'
        }
      },
      {
        id: 'step-3',
        type: 'interact',
        name: 'Send Report to WeChat',
        description: 'Use browser_use tool to simulate web operations and send the generated report to specified leader via WeChat. Input: Report text, Output: Send confirmation',
        properties: {
          agent_type: 'tool_agent',
          tool: 'browser_use',
          instruction: 'Use browser_use tool to send report to specified WeChat contact'
        }
      },
      {
        id: 'end',
        type: 'end',
        name: 'End',
        description: 'Workflow completed successfully'
      }
    ]

    return metaflows
  }

  const getMetaflowIcon = (type) => {
    switch (type) {
      case 'start':
        return '🚀'
      case 'navigate':
        return '🌐'
      case 'interact':
        return '👆'
      case 'extract':
        return '📊'
      case 'process':
        return '⚙️'
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
      case 'navigate':
        return '#8b5cf6'
      case 'interact':
        return '#f59e0b'
      case 'extract':
        return '#3b82f6'
      case 'process':
        return '#06b6d4'
      case 'end':
        return '#10b981'
      default:
        return '#6b7280'
    }
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
    onNavigate('workflow-generation', { recordingData })
  }

  return (
    <div className="page metaflow-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('intention')}
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
          {metaflows.map((metaflow, index) => (
            <React.Fragment key={metaflow.id}>
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

              {/* Arrow connector */}
              {index < metaflows.length - 1 && (
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
        <p>AgentCrafter v1.0.0</p>
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
