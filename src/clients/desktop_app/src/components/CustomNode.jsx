import React, { useState } from 'react'
import { Handle, Position } from 'reactflow'

function CustomNode({ data, onOptimizeScript }) {
  const [showModal, setShowModal] = useState(false)

  // Check if this is a scraper agent
  // Check multiple conditions: agent_type, tools array, or description/label containing 'scraper'
  const isScraperAgent = data.agent_type === 'scraper' || data.agent_type === 'scraper_agent' || (data.agent_type === 'tool' && data.tools?.includes('scraper')) ||
    data.label?.toLowerCase().includes('scraper') ||
    data.description?.toLowerCase().includes('scraper')

  const getNodeStyle = () => {
    const baseStyle = {
      padding: '12px 16px',
      borderRadius: '12px',
      border: '1px solid',
      minWidth: '200px',
      textAlign: 'left',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      transition: 'all 0.2s ease',
      background: '#fff',
      cursor: 'pointer',
      display: 'flex',
      flexDirection: 'column',
      gap: '4px'
    }

    if (data.type === 'start') {
      return { ...baseStyle, borderColor: '#52c41a', background: '#f6ffed' }
    } else if (data.type === 'end') {
      return { ...baseStyle, borderColor: '#ff4d4f', background: '#fff2f0' }
    } else if (data.type === 'branch_start' || data.type === 'branch_end') {
      return { ...baseStyle, borderColor: '#faad14', background: '#fffbe6' }
    } else if (data.type === 'loop' || data.type === 'loop_start') {
      return { ...baseStyle, borderColor: '#722ed1', background: '#f9f0ff' }
    }
    return { ...baseStyle, borderColor: '#e5e7eb', background: '#ffffff' }
  }

  const getNodeIcon = () => {
    if (data.type === 'branch_start') return '🔀'
    if (data.type === 'branch_end') return '🔗'
    if (data.type === 'loop' || data.type === 'loop_start') return '🔁'
    if (data.branch === 'allegro') return '🇵🇱'
    if (data.branch === 'amazon') return '🇺🇸'
    if (data.type === 'start') return '🚀'
    if (data.type === 'end') return '🏁'
    return '⚡'
  }

  const nodeIcon = getNodeIcon()

  return (
    <>
      <div
        className="custom-node"
        style={getNodeStyle()}
        onClick={() => setShowModal(true)}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-2px)'
          e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'none'
          e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)'
        }}
      >
        <Handle type="target" position={Position.Top} style={{ background: '#9ca3af' }} />
        <div className="node-header" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          {nodeIcon && <span className="node-icon" style={{ fontSize: '1.2em' }}>{nodeIcon}</span>}
          <div className="node-label" style={{ fontWeight: '600', fontSize: '14px', color: '#1f2937' }}>{data.label}</div>
        </div>
        {data.description && (
          <div className="node-desc" style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.4' }}>
            {data.description.length > 50 ? data.description.substring(0, 50) + '...' : data.description}
          </div>
        )}
        <Handle type="source" position={Position.Bottom} style={{ background: '#9ca3af' }} />
      </div>

      {showModal && (
        <div className="node-detail-modal-backdrop" onClick={() => setShowModal(false)} style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          zIndex: 1000,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="node-detail-modal-content" onClick={(e) => e.stopPropagation()} style={{
            background: 'white',
            borderRadius: '16px',
            width: '500px',
            maxWidth: '90vw',
            maxHeight: '85vh',
            overflowY: 'auto',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
            padding: '24px',
            position: 'relative'
          }}>
            <button
              onClick={() => setShowModal(false)}
              style={{
                position: 'absolute',
                top: '16px',
                right: '16px',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: '#6b7280',
                padding: '4px'
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>

            <div style={{ marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid #e5e7eb' }}>
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 12px',
                borderRadius: '9999px',
                background: '#f3f4f6',
                fontSize: '12px',
                fontWeight: '500',
                color: '#4b5563',
                marginBottom: '12px'
              }}>
                {data.type || 'Step'}
              </div>
              <h3 style={{
                fontSize: '20px',
                fontWeight: '700',
                color: '#111827',
                margin: 0,
                lineHeight: '1.4'
              }}>
                {data.label}
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {data.description && (
                <div>
                  <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>Description</h4>
                  <p style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6', margin: 0 }}>
                    {data.description}
                  </p>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>ID</h4>
                  <div style={{ fontSize: '13px', fontFamily: 'monospace', color: '#6b7280', background: '#f9fafb', padding: '8px', borderRadius: '6px' }}>
                    {data.id || 'N/A'}
                  </div>
                </div>
                {data.agent_type && (
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>Agent Type</h4>
                    <div style={{ fontSize: '13px', color: '#6b7280', background: '#f9fafb', padding: '8px', borderRadius: '6px' }}>
                      {data.agent_type}
                    </div>
                  </div>
                )}
              </div>

              {(data.inputs || data.outputs) && (
                <div style={{ background: '#f8fafc', borderRadius: '12px', padding: '16px', border: '1px solid #e2e8f0' }}>
                  {data.inputs && (
                    <div style={{ marginBottom: '16px' }}>
                      <h4 style={{ fontSize: '13px', fontWeight: '600', color: '#475569', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Inputs</h4>
                      <pre style={{ fontSize: '12px', background: 'white', padding: '12px', borderRadius: '8px', border: '1px solid #e2e8f0', overflowX: 'auto', margin: 0 }}>
                        {JSON.stringify(data.inputs, null, 2)}
                      </pre>
                    </div>
                  )}
                  {data.outputs && (
                    <div>
                      <h4 style={{ fontSize: '13px', fontWeight: '600', color: '#475569', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Outputs</h4>
                      <pre style={{ fontSize: '12px', background: 'white', padding: '12px', borderRadius: '8px', border: '1px solid #e2e8f0', overflowX: 'auto', margin: 0 }}>
                        {JSON.stringify(data.outputs, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Optimize Script Button for Scraper Agents */}
              {isScraperAgent && onOptimizeScript && (
                <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid #e5e7eb' }}>
                  <button
                    onClick={() => {
                      setShowModal(false)
                      onOptimizeScript(data)
                    }}
                    style={{
                      width: '100%',
                      padding: '12px 20px',
                      background: '#3b82f6',
                      color: 'white',
                      border: 'none',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: '600',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      transition: 'background 0.2s'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
                    onMouseLeave={(e) => e.currentTarget.style.background = '#3b82f6'}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                    优化脚本
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default CustomNode
