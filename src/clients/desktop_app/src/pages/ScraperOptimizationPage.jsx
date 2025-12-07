import React, { useState, useEffect, useRef } from 'react'
import Icon from '../components/Icons'
import '../styles/ScraperOptimizationPage.css'

const API_BASE = "http://127.0.0.1:8765"

function ScraperOptimizationPage({ session, pageParams, onNavigate, showStatus }) {
  const { userId, workflowId, stepId, workflowName, stepName } = pageParams || {}

  const [loading, setLoading] = useState(true)
  const [workspaceContext, setWorkspaceContext] = useState(null)
  const [error, setError] = useState(null)
  const [cachedUrls, setCachedUrls] = useState([])  // Cached DOM URLs

  // Conversation state
  const [conversation, setConversation] = useState([])
  const [userMessage, setUserMessage] = useState('')
  const [isSending, setIsSending] = useState(false)

  const messagesEndRef = useRef(null)

  // Auto-scroll to bottom when conversation updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation])

  // Load workspace context on mount
  useEffect(() => {
    if (userId && workflowId && stepId) {
      loadWorkspace()
    } else {
      setError('Missing required parameters: userId, workflowId, or stepId')
      setLoading(false)
    }
  }, [userId, workflowId, stepId])

  const loadWorkspace = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/api/scraper-optimization/load-workspace`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          workflow_id: workflowId,
          step_id: stepId
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to load workspace')
      }

      setWorkspaceContext(data)
      setCachedUrls(data.cached_urls || [])

      // Add welcome message (simplified - URLs are shown in left panel)
      setConversation([{
        role: 'assistant',
        content: `Hello! I'm ready to help optimize your scraper script.

I can help you:
- Analyze and fix extraction issues for a specific URL (check the left panel for cached DOM URLs)
- Explain what the script does
- Improve the script's reliability
- Debug why certain fields are not being extracted

Just mention the URL you want to optimize, and I'll use the cached DOM data to help you!`
      }])

    } catch (err) {
      console.error('Load workspace error:', err)
      setError(err.message)
      showStatus?.('Failed to load workspace', 'error')
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = async () => {
    if (!userMessage.trim() || isSending) return

    const newUserMessage = { role: 'user', content: userMessage }
    const updatedConversation = [...conversation, newUserMessage]
    setConversation(updatedConversation)
    setUserMessage('')
    setIsSending(true)

    try {
      const response = await fetch(`${API_BASE}/api/scraper-optimization/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Ami-API-Key': session?.apiKey  // Add user's API key
        },
        body: JSON.stringify({
          user_id: userId,
          workflow_id: workflowId,
          step_id: stepId,
          message: userMessage,
          conversation_history: updatedConversation
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Chat failed')
      }

      // Add Claude's response
      setConversation([...updatedConversation, {
        role: 'assistant',
        content: data.response
      }])

    } catch (err) {
      console.error('Chat error:', err)
      showStatus?.(`Chat failed: ${err.message}`, 'error')

      // Add error message to conversation
      setConversation([...updatedConversation, {
        role: 'assistant',
        content: `❌ Error: ${err.message}\n\nPlease try again.`
      }])
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="page scraper-optimization-page">
      {/* Header */}
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('workflow-detail', { workflowId })}
        >
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title-section">
          <div className="page-title">Scraper Script Optimization</div>
          <div className="page-subtitle">
            {workflowName} / {stepName}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="optimization-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="clock" size={48} /></div>
            <div className="empty-state-title">Loading workspace...</div>
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-icon"><Icon icon="alertTriangle" size={48} /></div>
            <div className="empty-state-title">Error</div>
            <div className="empty-state-desc">{error}</div>
          </div>
        )}

        {!loading && !error && workspaceContext && (
          <div className="optimization-layout">
            {/* Left Panel: Context Info */}
            <div className="context-panel">
              <div className="context-card">
                <div className="context-card-header">
                  <Icon icon="folder" size={16} />
                  <h3>Workspace Info</h3>
                </div>
                <div className="context-card-content">
                  <div className="context-item">
                    <span className="context-label">Workflow:</span>
                    <span className="context-value">{workflowId}</span>
                  </div>
                  <div className="context-item">
                    <span className="context-label">Step:</span>
                    <span className="context-value">{stepId}</span>
                  </div>
                  <div className="context-item">
                    <span className="context-label">Script:</span>
                    <span className={`context-badge ${workspaceContext.has_script ? 'success' : 'error'}`}>
                      {workspaceContext.has_script ? '✅ Found' : '❌ Not found'}
                    </span>
                  </div>
                  <div className="context-item">
                    <span className="context-label">Path:</span>
                    <code className="context-path">{workspaceContext.script_path}</code>
                  </div>
                </div>
              </div>

              {workspaceContext.requirement && (
                <div className="context-card">
                  <div className="context-card-header">
                    <Icon icon="list" size={16} />
                    <h3>Data Requirements</h3>
                  </div>
                  <div className="context-card-content">
                    <div className="requirement-desc">
                      {workspaceContext.requirement.user_description || 'No description'}
                    </div>
                    {workspaceContext.requirement.output_format && (
                      <div className="requirement-fields">
                        <h4>Fields:</h4>
                        <ul>
                          {Object.keys(workspaceContext.requirement.output_format).map(field => (
                            <li key={field}>
                              <code>{field}</code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Cached DOM URLs Panel */}
              <div className="context-card">
                <div className="context-card-header">
                  <Icon icon="database" size={16} />
                  <h3>Cached DOM URLs</h3>
                  <span className="badge">{cachedUrls.length}</span>
                </div>
                <div className="context-card-content">
                  {cachedUrls.length === 0 ? (
                    <div className="empty-urls">
                      <p>No cached DOM URLs yet.</p>
                      <p className="hint">Run a scrape first to cache DOM data.</p>
                    </div>
                  ) : (
                    <div className="cached-urls-list">
                      {cachedUrls.map((item, idx) => (
                        <div key={idx} className="cached-url-item">
                          <div className="url-icon">
                            <Icon icon="globe" size={14} />
                          </div>
                          <div className="url-info">
                            <div className="url-text" title={item.url}>
                              {item.url}
                            </div>
                            <div className="url-meta">
                              <span className="url-hash">Hash: {item.hash}</span>
                              <span className="url-timestamp">
                                {item.timestamp ? new Date(item.timestamp).toLocaleString() : 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="help-card">
                <div className="help-card-header">
                  <Icon icon="help" size={16} />
                  <h3>How to use</h3>
                </div>
                <div className="help-card-content">
                  <ol>
                    <li>Mention the URL you want to optimize</li>
                    <li>Claude will check if DOM data exists</li>
                    <li>If available, Claude will analyze and fix issues</li>
                    <li>Continue conversation until satisfied</li>
                  </ol>
                </div>
              </div>
            </div>

            {/* Right Panel: Conversation */}
            <div className="conversation-panel">
              <div className="messages-container">
                {conversation.map((msg, idx) => (
                  <div key={idx} className={`message message-${msg.role}`}>
                    <div className="message-avatar">
                      {msg.role === 'user' ? (
                        <Icon icon="user" size={20} />
                      ) : (
                        <Icon icon="bot" size={20} />
                      )}
                    </div>
                    <div className="message-content">
                      <div className="message-text">
                        {msg.content.split('\n').map((line, i) => (
                          <React.Fragment key={i}>
                            {line}
                            {i < msg.content.split('\n').length - 1 && <br />}
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                {isSending && (
                  <div className="message message-assistant">
                    <div className="message-avatar">
                      <Icon icon="bot" size={20} />
                    </div>
                    <div className="message-content">
                      <div className="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="input-container">
                <textarea
                  className="message-input"
                  placeholder="Describe the issue or mention a URL to optimize..."
                  value={userMessage}
                  onChange={(e) => setUserMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  rows={3}
                  disabled={isSending}
                />
                <button
                  className="send-button"
                  onClick={sendMessage}
                  disabled={!userMessage.trim() || isSending}
                >
                  {isSending ? (
                    <>
                      <div className="btn-spinner"></div>
                      <span>Sending...</span>
                    </>
                  ) : (
                    <>
                      <Icon icon="send" size={16} />
                      <span>Send</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default ScraperOptimizationPage
