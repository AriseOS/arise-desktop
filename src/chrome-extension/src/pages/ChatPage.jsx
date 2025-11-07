import React, { useState } from 'react'
import { DEFAULT_CONFIG_KEY } from '../config/index'

function ChatPage({ onNavigate, showStatus }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  const handleGenerate = () => {
    if (!title.trim()) {
      showStatus('⚠️ 请输入标题', 'error')
      return
    }

    if (!description.trim()) {
      showStatus('⚠️ 请输入功能描述', 'error')
      return
    }

    setIsGenerating(true)

    // Only show generating status for non-analysis workflows
    if (DEFAULT_CONFIG_KEY !== 'cross-market-product-selection') {
      showStatus('🤖 开始生成 Workflow...', 'info')
    }

    // Simulate generation delay
    setTimeout(() => {
      setIsGenerating(false)

      // Only show success status for non-analysis workflows
      if (DEFAULT_CONFIG_KEY !== 'cross-market-product-selection') {
        showStatus('✅ Workflow 生成成功', 'success')
      }

      // Navigate to appropriate page based on default config
      const targetPage = DEFAULT_CONFIG_KEY === 'cross-market-product-selection' ? 'workflow-analysis' : 'metaflow'
      onNavigate(targetPage, { fromPage: 'chat' })
    }, 1000)
  }

  const handleStopGenerate = () => {
    setIsGenerating(false)
    showStatus('⏹️ 已停止生成', 'info')
  }

  return (
    <div className="page chat-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
          disabled={isGenerating}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">生成 Workflow</div>
      </div>

      <div className="chat-content">
        <div className="chat-form">
          <div className="form-section">
            <div className="input-group">
              <label>
                <span>
                  标题 <span className="required">*</span>
                </span>
                <span className="input-hint">{title.length}/50</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：自动填写表单"
                disabled={isGenerating}
                maxLength={50}
              />
            </div>

            <div className="input-group">
              <label>
                <span>
                  功能描述 <span className="required">*</span>
                </span>
                <span className="input-hint">{description.length}/500</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="详细描述这个工作流要完成什么任务，包含哪些步骤...&#10;&#10;例如：打开某个网站，填写表单字段，提交数据"
                disabled={isGenerating}
                maxLength={500}
              />
            </div>
          </div>

          <button
            className={`generate-button ${isGenerating ? 'generating' : ''}`}
            onClick={isGenerating ? handleStopGenerate : handleGenerate}
          >
            {isGenerating ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12"></rect>
                </svg>
                <span>停止生成</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
                <span>生成 Workflow</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default ChatPage
