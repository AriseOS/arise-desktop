import React, { useState, useEffect } from 'react'

function RecordPage({ onNavigate, showStatus, currentUser }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [sessionId, setSessionId] = useState(null)

  // Load recording state from storage on mount
  useEffect(() => {
    loadRecordingState()
  }, [])

  const loadRecordingState = async () => {
    try {
      const result = await chrome.storage.local.get(['recordingState'])
      if (result.recordingState) {
        const { title, description, sessionId, isRecording } = result.recordingState
        setTitle(title || '')
        setDescription(description || '')
        setSessionId(sessionId || null)
        setIsRecording(isRecording || false)
      }
    } catch (error) {
      console.error('Failed to load recording state:', error)
    }
  }

  const saveRecordingState = async (state) => {
    try {
      await chrome.storage.local.set({ recordingState: state })
    } catch (error) {
      console.error('Failed to save recording state:', error)
    }
  }

  const clearRecordingState = async () => {
    try {
      await chrome.storage.local.remove(['recordingState'])
    } catch (error) {
      console.error('Failed to clear recording state:', error)
    }
  }

  const handleStartRecord = async () => {
    if (!title.trim()) {
      showStatus('⚠️ 请输入标题', 'error')
      return
    }

    try {
      setIsRecording(true)
      showStatus('🎬 开始录制...', 'info')

      const response = await fetch('http://localhost:8000/api/recording/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        },
        body: JSON.stringify({
          title: title,
          description: description || ''
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const result = await response.json()

      if (result.success) {
        setSessionId(result.session_id)
        console.log('Recording started:', result)

        // Send message to all tabs to start recording
        const tabs = await chrome.tabs.query({})
        for (const tab of tabs) {
          try {
            await chrome.tabs.sendMessage(tab.id, {
              action: 'startRecording',
              sessionId: result.session_id,
              token: currentUser.token
            })
          } catch (e) {
            // Ignore errors for tabs where content script isn't loaded
            console.debug('Could not send to tab:', tab.id)
          }
        }

        showStatus('✅ 录制已开始，请在浏览器中操作', 'success')

        // Save recording state
        await saveRecordingState({
          title,
          description,
          sessionId: result.session_id,
          isRecording: true
        })
      } else {
        throw new Error(result.error || 'Failed to start recording')
      }
    } catch (error) {
      console.error('Start recording error:', error)
      showStatus('❌ 启动录制失败', 'error')
      setIsRecording(false)
    }
  }

  const handleStopRecord = async () => {
    if (!sessionId) {
      showStatus('⚠️ 无录制会话', 'error')
      return
    }

    try {
      showStatus('⏹️ 正在停止录制...', 'info')

      const response = await fetch('http://localhost:8000/api/recording/stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        },
        body: JSON.stringify({
          session_id: sessionId
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const result = await response.json()

      if (result.success) {
        // Send message to all tabs to stop recording
        const tabs = await chrome.tabs.query({})
        for (const tab of tabs) {
          try {
            await chrome.tabs.sendMessage(tab.id, {
              action: 'stopRecording'
            })
          } catch (e) {
            console.debug('Could not send to tab:', tab.id)
          }
        }

        console.log('Recording stopped:', result)
        console.log(`Captured ${result.operation_count} operations:`)

        // Print each operation in detail
        result.operations.forEach((op, index) => {
          console.log(`\n📋 Operation ${index + 1}:`)
          console.log('  Type:', op.type)
          console.log('  URL:', op.url)
          console.log('  Page Title:', op.page_title)
          console.log('  Timestamp:', new Date(op.timestamp).toLocaleString())

          if (op.element && op.element.xpath) {
            console.log('  Element XPath:', op.element.xpath)
            console.log('  Element Tag:', op.element.tagName)
            console.log('  Element ID:', op.element.id || '(none)')
            console.log('  Element Class:', op.element.className || '(none)')
            console.log('  Element Text:', op.element.textContent?.slice(0, 50) || '(none)')
          }

          if (op.data) {
            console.log('  Additional Data:', op.data)
          }
        })

        showStatus(`✅ 录制完成，捕获 ${result.operation_count} 个操作`, 'success')
        setIsRecording(false)
        setSessionId(null)

        // Clear recording state from storage
        await clearRecordingState()

        // Reset form
        setTitle('')
        setDescription('')
      } else {
        throw new Error(result.error || 'Failed to stop recording')
      }
    } catch (error) {
      console.error('Stop recording error:', error)
      showStatus('❌ 停止录制失败', 'error')
    }
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
