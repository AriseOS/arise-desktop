import React, { useState, useEffect } from 'react'

function MetaflowPage({ onNavigate, showStatus, recordingData }) {
  const [metaflows, setMetaflows] = useState([])
  const [isEditing, setIsEditing] = useState(false)
  const [editingNode, setEditingNode] = useState(null)

  useEffect(() => {
    // Generate metaflows from actual metaflow.yaml data
    const generatedMetaflows = generateMetaflows()
    setMetaflows(generatedMetaflows)
  }, [])

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

  const generateMetaflows = () => {
    // Metaflow data from tests/test_data/coffee_allegro/output/metaflow.yaml
    const metaflowData = {
      version: '1.0',
      task_description: 'Collect coffee product information from Allegro including product name, price, and sales count',
      nodes: [
        {
          id: 'node_1',
          intent_id: 'intent_6c3e972a',
          intent_name: 'NavigateToAllegro',
          intent_description: 'Navigate to Allegro homepage to begin coffee product price collection',
          operations: [
            { type: 'test', timestamp: '2025-09-13 10:32:54', url: 'about:blank' },
            { type: 'navigate', timestamp: '2025-09-13 10:32:57', url: 'https://allegro.pl/' }
          ]
        },
        {
          id: 'node_2',
          intent_id: 'intent_69544a61',
          intent_name: 'NavigateToCoffeeCategory',
          intent_description: 'Navigate to the coffee category page to view coffee products',
          operations: [
            { type: 'click', timestamp: '2025-09-13 10:32:58', url: 'https://allegro.pl/' },
            { type: 'click', timestamp: '2025-09-13 10:33:00', url: 'https://allegro.pl/' },
            { type: 'navigate', timestamp: '2025-09-13 10:33:02', url: 'https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030' }
          ]
        },
        {
          id: 'node_3',
          intent_id: 'implicit_extract_list',
          intent_name: 'ExtractProductList',
          intent_description: 'Extract coffee product list from first page (inferred node)',
          operations: [
            { type: 'extract', element: { xpath: '<PLACEHOLDER>', tagName: 'A' }, target: 'product_urls', value: [] }
          ]
        },
        {
          id: 'node_4',
          type: 'loop',
          description: 'Iterate through all coffee products on first page, extract detailed information',
          source: '{{product_urls}}',
          item_var: 'current_product',
          children: [
            {
              id: 'node_4_1',
              intent_id: 'intent_7fe0c6bf',
              intent_name: 'NavigateToProductDetail',
              intent_description: 'Navigate to a specific coffee product detail page to view its information',
              operations: [
                { type: 'click', timestamp: '2025-09-13 10:33:04' },
                { type: 'navigate', timestamp: '2025-09-13 10:33:05' }
              ]
            },
            {
              id: 'node_4_2',
              intent_id: 'intent_b7f99df2',
              intent_name: 'ExtractProductDetails',
              intent_description: 'Extract coffee product details including name, price, and purchase statistics',
              operations: [
                { type: 'click', timestamp: '2025-09-13 10:33:08' },
                { type: 'select', timestamp: '2025-09-13 10:33:08' },
                { type: 'copy_action', timestamp: '2025-09-13 10:33:08' }
              ]
            }
          ]
        }
      ]
    };

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
      if (node.type === 'loop') {
        // Add loop node
        metaflows.push({
          id: node.id,
          type: 'loop',
          name: 'Loop: Extract Product Details',
          description: node.description,
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
          onClick={() => onNavigate('record')}
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
