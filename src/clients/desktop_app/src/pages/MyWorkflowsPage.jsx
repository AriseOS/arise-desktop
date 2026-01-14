import React, { useState, useEffect } from 'react'
import { useTranslation } from "react-i18next";
import Icon from '../components/Icons'
import { api } from '../utils/api'
import '../styles/MyWorkflowsPage.css'

function MyWorkflowsPage({ session, onNavigate, onLogout, version }) {
  const { t, i18n } = useTranslation();
  // Get user_id from session
  const userId = session?.username;
  const [workflows, setWorkflows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null) // { workflowId, workflowName }

  useEffect(() => {
    if (userId) {
      loadWorkflows()
    }
  }, [userId])

  const loadWorkflows = async () => {
    setLoading(true)
    setError(null)

    try {
      const data = await api.callAppBackend(`/api/v1/workflows?user_id=${userId}`)
      setWorkflows(data.workflows || [])
    } catch (err) {
      console.error('Load workflows error:', err)

      // Show mock data for demo
      const mockWorkflows = [
        {
          agent_id: "workflow_demo_001",
          name: "Google搜索自动化",
          description: "自动打开Google，搜索指定关键词，获取搜索结果",
          created_at: "2025-01-13T10:30:00Z",
          is_downloaded: true,
          source: "local",
          status: "ready",
          last_run: "2025-01-13T11:00:00Z"
        },
        {
          agent_id: "workflow_demo_002",
          name: "表单填写助手",
          description: "自动填写网页表单，支持多种表单类型",
          created_at: "2025-01-12T16:45:00Z",
          is_downloaded: true,
          source: "local",
          status: "ready",
          last_run: "2025-01-12T17:30:00Z"
        }
      ];
      setWorkflows(mockWorkflows);
    } finally {
      setLoading(false)
    }
  }

  const handleWorkflowClick = (workflowId) => {
    onNavigate('workflow-detail', { workflowId })
  }

  const handleGenerateWorkflow = () => {
    onNavigate('generation')
  }

  const handleQuickGenerate = () => {
    onNavigate('quick-start')
  }

  const handleRunWorkflow = (workflowId) => {
    // Navigate to workflow detail page and trigger execution
    onNavigate('workflow-detail', { workflowId, autoRun: true })
  }

  const handleDeleteClick = (workflowId) => {
    const workflow = workflows.find(w => w.agent_id === workflowId)
    const workflowName = workflow?.name || `Workflow ${workflowId}`
    setDeleteConfirm({ workflowId, workflowName })
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return

    const { workflowId } = deleteConfirm
    setDeleteConfirm(null)

    try {
      await api.callAppBackend(`/api/v1/workflows/${workflowId}?user_id=${userId}`, {
        method: 'DELETE'
      })

      setWorkflows(prev => prev.filter(w => w.agent_id !== workflowId))
    } catch (err) {
      console.error('Delete workflow error:', err)
      setError(`${t('myWorkflows.deleteFailed')}: ${err.message}`)
    }
  }

  const handleDeleteCancel = () => {
    setDeleteConfirm(null)
  }

  const formatDate = (dateString) => {
    if (!dateString) return t('myWorkflows.never')
    const date = new Date(dateString)
    return date.toLocaleString(i18n.language === 'zh' ? 'zh-CN' : 'en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'ready': return '#52c41a'
      case 'running': return '#1890ff'
      case 'draft': return '#faad14'
      case 'failed': return '#ff4d4f'
      default: return '#8c8c8c'
    }
  }

  const getStatusText = (status) => {
    switch (status) {
      case 'ready': return t('myWorkflows.status.ready')
      case 'running': return t('myWorkflows.status.running')
      case 'draft': return t('myWorkflows.status.draft')
      case 'failed': return t('myWorkflows.status.failed')
      default: return t('myWorkflows.status.unknown')
    }
  }

  return (
    <div className="page my-workflows-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
        >
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="cpu" size={28} /> {t('myWorkflows.pageTitle')}</div>
        <div className="header-actions">
          <button className="secondary-button" onClick={handleQuickGenerate}>
            <Icon icon="zap" size={16} />
            <span>{t('myWorkflows.quickGenerate')}</span>
          </button>
          {/* <button className="primary-button" onClick={handleGenerateWorkflow}>
            <Icon icon="plusCircle" size={16} />
            <span>新建 Workflow</span>
          </button> */}
        </div>
      </div>

      <div className="workflows-content">
        <div className="page-section">
          <div className="section-header">
            <h3>{t('myWorkflows.myWorkflows')}</h3>
            <div className="section-stats">
              <span className="stat-item">
                <span className="stat-value">{workflows.length}</span>
                <span className="stat-label">{t('myWorkflows.workflowsCount')}</span>
              </span>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>{t('myWorkflows.loading')}</p>
            </div>
          ) : error ? (
            <div className="error-state">
              <div className="error-icon"><Icon icon="alertCircle" size={48} /></div>
              <div className="error-message">{error}</div>
              <button className="retry-button" onClick={loadWorkflows}>
                {t('myWorkflows.retry')}
              </button>
            </div>
          ) : workflows.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon"><Icon icon="cpu" size={48} /></div>
              <div className="empty-state-title">{t('myWorkflows.noWorkflows')}</div>
              <div className="empty-state-desc">
                {t('myWorkflows.noWorkflowsDesc')}
              </div>
              <div className="empty-actions">
                <button className="primary-button" onClick={handleQuickGenerate}>
                  <Icon icon="zap" size={16} />
                  <span>{t('myWorkflows.quickGenerateFromRecord')}</span>
                </button>
                {/* <button className="secondary-button" onClick={handleGenerateWorkflow}>
                  <Icon icon="plusCircle" size={16} />
                  <span>AI 智能生成</span>
                </button> */}
              </div>
            </div>
          ) : (
            <div className="workflows-grid">
              {workflows.map((workflow) => (
                <div key={workflow.agent_id} className="workflow-card">
                  <div className="workflow-header">
                    <div className="workflow-title">
                      <h4>{workflow.name}</h4>
                      <div
                        className="status-badge"
                        style={{ backgroundColor: getStatusColor(workflow.status) }}
                      >
                        {getStatusText(workflow.status)}
                      </div>
                    </div>
                    <div className="workflow-source">
                      {workflow.source === 'cloud' ? <Icon icon="cloud" size={12} /> : <Icon icon="monitor" size={12} />}
                      {workflow.source === 'cloud' ? t('myWorkflows.cloud') : t('myWorkflows.local')}
                    </div>
                  </div>

                  <div className="workflow-description">
                    {workflow.description}
                  </div>

                  <div className="workflow-meta">
                    <div className="meta-item">
                      <span className="meta-icon"><Icon icon="calendar" size={12} /></span>
                      <span className="meta-label">{t('myWorkflows.createdAt')}:</span>
                      <span className="meta-value">{formatDate(workflow.created_at)}</span>
                    </div>
                    <div className="meta-item">
                      <span className="meta-icon"><Icon icon="clock" size={12} /></span>
                      <span className="meta-label">{t('myWorkflows.lastRun')}:</span>
                      <span className="meta-value">{formatDate(workflow.last_run)}</span>
                    </div>
                    <div className="meta-item">
                      <span className="meta-icon"><Icon icon="hash" size={12} /></span>
                      <span className="meta-label">{t('workflowDetail.id')}:</span>
                      <span className="meta-value">{workflow.agent_id}</span>
                    </div>
                  </div>

                  <div className="workflow-actions">
                    <button
                      className="action-button primary"
                      onClick={() => handleWorkflowClick(workflow.agent_id)}
                    >
                      <Icon icon="eye" size={14} />
                      <span>{t('myWorkflows.viewDetails')}</span>
                    </button>

                    <button
                      className="action-button secondary"
                      onClick={() => handleRunWorkflow(workflow.agent_id)}
                    >
                      <Icon icon="play" size={14} />
                      <span>{t('common.run')}</span>
                    </button>

                    <button
                      className="action-button danger"
                      onClick={() => handleDeleteClick(workflow.agent_id)}
                    >
                      <Icon icon="trash" size={14} />
                      <span>{t('common.delete')}</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && t('settings.loggedInAs', { username: session.username })}</p>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={handleDeleteCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('myWorkflows.deleteConfirmTitle')}</h3>
            </div>
            <div className="modal-body">
              <p>{t('myWorkflows.deleteConfirmMessage', { name: deleteConfirm.workflowName })}</p>
              <p className="warning-text">{t('myWorkflows.undoneWarning')}</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                {t('common.cancel')}
              </button>
              <button className="btn-confirm-delete" onClick={handleDeleteConfirm}>
                {t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MyWorkflowsPage
