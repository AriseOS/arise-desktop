import React, { useState } from 'react'
import { Handle, Position } from 'reactflow'

function CustomNode({ data }) {
  const [showModal, setShowModal] = useState(false)

  const getNodeStyle = () => {
    if (data.type === 'start') {
      return { borderColor: '#52c41a', background: '#f6ffed' }
    } else if (data.type === 'end') {
      return { borderColor: '#ff4d4f', background: '#fff2f0' }
    }
    return { borderColor: '#3b82f6', background: '#eff6ff' }
  }

  return (
    <>
      <div
        className="custom-node"
        style={getNodeStyle()}
        onClick={() => setShowModal(true)}
      >
        <Handle type="target" position={Position.Top} />
        <div className="node-content">
          <div className="node-label">{data.label}</div>
          {data.type && <div className="node-type">{data.type}</div>}
        </div>
        <Handle type="source" position={Position.Bottom} />
      </div>

      {showModal && (
        <div className="node-detail-modal" onClick={() => setShowModal(false)}>
          <div className="node-detail-content" onClick={(e) => e.stopPropagation()}>
            <h3>{data.label}</h3>
            <div className="detail-item">
              <div className="detail-label">类型:</div>
              <div className="detail-value">{data.type || '无'}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">描述:</div>
              <div className="detail-value">{data.description || '无描述'}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">ID:</div>
              <div className="detail-value">{data.id || '无'}</div>
            </div>
            <button className="close-modal-btn" onClick={() => setShowModal(false)}>
              关闭
            </button>
          </div>
        </div>
      )}
    </>
  )
}

export default CustomNode
