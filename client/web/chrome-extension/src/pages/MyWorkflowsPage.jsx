import React, { useState, useEffect } from 'react'

function MyWorkflowsPage({ currentUser, onNavigate }) {
  const [workflows, setWorkflows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadWorkflows()
  }, [])

  const loadWorkflows = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('http://localhost:8000/api/agents?default=true', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        }
      })

      if (!response.ok) {
        if (response.status === 401) {
          alert('Login expired, please login again')
          return
        }
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()
      setWorkflows(data)
    } catch (err) {
      console.error('Load workflows error:', err)
      setError('Failed to load workflows')
    } finally {
      setLoading(false)
    }
  }

  const handleWorkflowClick = (workflowId) => {
    onNavigate('workflow-detail', { workflowId })
  }

  return (
    <div className="page my-workflows-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">My Workflows</div>
      </div>

      <div className="workflow-list">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon">⏳</div>
            <div className="empty-state-title">Loading...</div>
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-icon">⚠️</div>
            <div className="empty-state-title">Error</div>
            <div className="empty-state-desc">{error}</div>
          </div>
        )}

        {!loading && !error && workflows.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <div className="empty-state-title">No Workflows</div>
            <div className="empty-state-desc">Create a workflow via recording or chat</div>
          </div>
        )}

        {!loading && !error && workflows.length > 0 && (
          <div>
            {workflows.map((workflow) => (
              <div
                key={workflow.agent_id}
                className="workflow-item"
                onClick={() => handleWorkflowClick(workflow.agent_id)}
              >
                <div className="workflow-item-info">
                  <div className="workflow-item-name">{workflow.name}</div>
                  {workflow.description && (
                    <div className="workflow-item-desc">{workflow.description}</div>
                  )}
                </div>
                <div className="workflow-item-arrow">›</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default MyWorkflowsPage
