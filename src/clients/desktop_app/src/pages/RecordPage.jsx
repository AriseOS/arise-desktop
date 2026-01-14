import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { DEFAULT_CONFIG_KEY } from '../config/index'
import Icon from '../components/Icons'
import '../styles/RecordPage.css'

function RecordPage({ onNavigate, showStatus, currentUser, version }) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [capturedOperations, setCapturedOperations] = useState([])
  const operationsRef = useRef([])

  // Load recording state from storage on mount
  useEffect(() => {
    loadRecordingState()
  }, [])

  // Poll for operations from background while recording
  useEffect(() => {
    if (!isRecording) {
      return
    }

    // Poll every 500ms to get latest operations
    const pollInterval = setInterval(async () => {
      try {
        const response = await chrome.runtime.sendMessage({ action: 'getCapturedOperations' })
        if (response && response.success) {
          setCapturedOperations(response.operations)
        }
      } catch (error) {
        console.error('Failed to poll operations:', error)
      }
    }, 500)

    return () => {
      clearInterval(pollInterval)
    }
  }, [isRecording])

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

      // Get captured operations from background script
      const response = await chrome.runtime.sendMessage({ action: 'getCapturedOperations' })
      if (response && response.success) {
        setCapturedOperations(response.operations)
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
      showStatus(t('auth.validation.enterUsername'), 'error') // Reusing enterUsername or adding a new dedicated key
      return
    }

    try {
      showStatus(t('recording.hints.starting'), 'info')

      const response = await fetch('http://localhost:8000/api/recording/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        },
        body: JSON.stringify({
          url: "about:blank",  // Default URL for extension-based recording
          user_id: currentUser.username,  // User ID is username
          title: title,
          description: description || ''
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const result = await response.json()

      if (result.success) {
        // Only set recording state after API success
        setIsRecording(true)
        setCapturedOperations([])  // Clear previous operations
        // Clear from background script (non-blocking)
        chrome.runtime.sendMessage({ action: 'clearCapturedOperations' }).catch(err => {
          console.error('Failed to clear operations:', err)
        })

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

        showStatus(t('recording.hints.started'), 'success')

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
      showStatus(t('recording.hints.startFailed', { error: error.message }), 'error')
      setIsRecording(false)
    }
  }

  const getOperationTypeLabel = (type) => {
    const typeLabels = {
      'click': { text: t('recording.ops.click'), icon: 'mousePointer' },
      'input': { text: t('recording.ops.input'), icon: 'keyboard' },
      'navigate': { text: t('recording.ops.navigate'), icon: 'globe' },
      'scroll': { text: t('recording.ops.scroll'), icon: 'arrowDown' },
      'select': { text: t('recording.ops.select'), icon: 'list' },
      'submit': { text: t('recording.ops.submit'), icon: 'checkCircle' },
      'hover': { text: t('recording.ops.hover'), icon: 'mousePointer' }
    }
    const label = typeLabels[type] || { text: type, icon: 'mapPin' }
    return (
      <>
        <Icon icon={label.icon} size={14} />
        <span>{label.text}</span>
      </>
    )
  }

  const handleStopRecord = async () => {
    if (!sessionId) {
      showStatus(t('recording.hints.noRecording'), 'error')
      return
    }

    try {
      showStatus(t('recording.hints.stopping'), 'info')

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

        showStatus(t('recording.hints.stopped', { count: result.operation_count }), 'success')

        // Stop recording UI state
        setIsRecording(false)
        setIsGenerating(true)

        // Clear recording state and captured operations
        await clearRecordingState()
        chrome.runtime.sendMessage({ action: 'clearCapturedOperations' }).catch(err => {
          console.error('Failed to clear operations:', err)
        })

        // Navigate to appropriate page based on default config
        const targetPage = DEFAULT_CONFIG_KEY === 'cross-market-product-selection' ? 'workflow-analysis' : 'metaflow'
        console.log(`Preparing to navigate to ${targetPage} page with data:`, result)
        setTimeout(() => {
          console.log(`Calling onNavigate with ${targetPage} page`)
          setIsGenerating(false)
          onNavigate(targetPage, { recordingData: result, fromPage: 'record' })
        }, 2000)
      } else {
        throw new Error(result.error || 'Failed to stop recording')
      }
    } catch (error) {
      console.error('Stop recording error:', error)
      showStatus(t('recording.hints.stopFailed', { error: error.message }), 'error')
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
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="video" size={28} /> {t('recording.title')}</div>
      </div>

      <div className="record-content">
        <div className="record-container">
          {/* Left Panel: Form */}
          <div className="record-form">
            {!isRecording ? (
              <div className="form-section">
                <div className="input-group">
                  <label>
                    <span>
                      {t('recording.titleLabel')} <span className="required">*</span>
                    </span>
                    <span className="input-hint">{title.length}/50</span>
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={t('recording.namePlaceholder')}
                    disabled={isRecording}
                    maxLength={50}
                  />
                </div>

                <div className="input-group">
                  <label>
                    <span>{t('recording.descLabel')}</span>
                    <span className="input-hint">{description.length}/500</span>
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder={t('recording.descPlaceholder')}
                    disabled={isRecording}
                    maxLength={500}
                  />
                </div>
              </div>
            ) : (
              <div className="operations-display">
                <div className="operations-header">
                  <span className="operations-title">{t('recording.capturedOps')}</span>
                  <span className="operations-count">{t('recording.opsCount', { count: capturedOperations.length })}</span>
                </div>
                <div className="operations-list">
                  {capturedOperations.length === 0 ? (
                    <div className="empty-operations">
                      <div className="empty-icon"><Icon icon="clipboard" size={48} /></div>
                      <div className="empty-text">{t('recording.waitingOps')}</div>
                    </div>
                  ) : (
                    capturedOperations.map((op, index) => (
                      <div key={index} className="operation-item">
                        <div className="operation-index">{index + 1}</div>
                        <div className="operation-details">
                          <div className="operation-type">{getOperationTypeLabel(op.type)}</div>
                          <div className="operation-info">
                            {op.element?.textContent && (
                              <div className="operation-text">
                                {op.element.textContent.slice(0, 50)}
                                {op.element.textContent.length > 50 ? '...' : ''}
                              </div>
                            )}
                            <div className="operation-url">{new URL(op.url).hostname}</div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            <button
              className={`start-record-button ${isRecording ? 'recording' : ''} ${isGenerating ? 'generating' : ''}`}
              onClick={isRecording ? handleStopRecord : handleStartRecord}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <>
                  <div className="btn-spinner"></div>
                  <span>{t('recording.generating')}</span>
                </>
              ) : isRecording ? (
                <>
                  <Icon icon="square" size={20} />
                  <span>{t('recording.stopBtn')}</span>
                </>
              ) : (
                <>
                  <Icon icon="circle" size={20} fill="currentColor" />
                  <span>{t('recording.startBtn')}</span>
                </>
              )}
            </button>
          </div>

          {/* Right Panel: Tips & Rules */}
          {!isRecording && (
            <div className="record-tips-panel">
              <div className="tips-section">
                <h3><Icon icon="zap" size={18} /> {t('recording.hints.title')}</h3>
                <ul className="tips-list">
                  <li>
                    <strong>{t('recording.hints.selectCopy')}</strong> {t('recording.hints.selectCopyDesc')}
                  </li>
                  <li>
                    <strong>{t('recording.hints.completePath')}</strong> {t('recording.hints.completePathDesc')}
                  </li>
                  <li>
                    <strong>{t('recording.hints.waitForLoad')}</strong> {t('recording.hints.waitForLoadDesc')}
                  </li>
                </ul>
              </div>

              <div className="tips-section">
                <h3><Icon icon="clipboard" size={18} /> {t('recording.hints.whatRecorded')}</h3>
                <ul className="tips-list info">
                  <li><strong>{t('recording.hints.clicks')}</strong> {t('recording.hints.clicksDesc')}</li>
                  <li><strong>{t('recording.hints.inputs')}</strong> {t('recording.hints.inputsDesc')}</li>
                  <li><strong>{t('recording.hints.copyExtract')}</strong> {t('recording.hints.copyExtractDesc')}</li>
                  <li><strong>{t('recording.hints.navigation')}</strong> {t('recording.hints.navigationDesc')}</li>
                </ul>
              </div>

              <div className="tips-section">
                <h3><Icon icon="alertTriangle" size={18} /> {t('recording.hints.note')}</h3>
                <ul className="tips-list warning">
                  <li>{t('recording.hints.doNotClose')}</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'}</p>
      </div>
    </div>
  )
}

export default RecordPage
