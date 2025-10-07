import React, { useState } from 'react'

function RecordPage({ onNavigate, showStatus }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isRecording, setIsRecording] = useState(false)

  const handleStartRecord = () => {
    if (!title.trim()) {
      showStatus('⚠️ 请输入标题', 'error')
      return
    }

    // TODO: 开始录制
    setIsRecording(true)
    console.log('Start recording:', { title, description })
    showStatus('🎬 开始录制...', 'info')
  }

  const handleStopRecord = () => {
    // TODO: 停止录制
    setIsRecording(false)
    console.log('Stop recording')
    showStatus('⏹️ 已停止录制', 'info')
  }

  return (
    <div className="page record-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
          disabled={isRecording}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">录制 Workflow</div>
      </div>

      <div className="record-content">
        <div className="record-form">
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
                disabled={isRecording}
                maxLength={50}
              />
            </div>

            <div className="input-group">
              <label>
                <span>功能描述</span>
                <span className="input-hint">{description.length}/500</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="详细描述这个工作流要完成什么任务，包含哪些步骤...&#10;&#10;例如：打开某个网站，填写表单字段，提交数据&#10;&#10;留空则根据录制的操作自动生成描述"
                disabled={isRecording}
                maxLength={500}
              />
            </div>
          </div>

          <button
            className={`start-record-button ${isRecording ? 'recording' : ''}`}
            onClick={isRecording ? handleStopRecord : handleStartRecord}
          >
            {isRecording ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12"></rect>
                </svg>
                <span>停止录制</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="12" r="8"></circle>
                </svg>
                <span>开始录制</span>
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

export default RecordPage
