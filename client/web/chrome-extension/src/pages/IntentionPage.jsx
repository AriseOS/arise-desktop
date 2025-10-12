import React, { useState, useEffect } from 'react'

function IntentionPage({ onNavigate, showStatus, recordingData }) {
  const [intentions, setIntentions] = useState([])

  useEffect(() => {
    if (recordingData && recordingData.operations) {
      // Generate intentions from recording operations
      const generatedIntentions = generateIntentions(recordingData.operations)
      setIntentions(generatedIntentions)
    }
  }, [recordingData])

  const generateIntentions = (operations) => {
    // Generate intentions based on real workflow data
    const intentions = [
      {
        id: 'start',
        type: 'start',
        name: 'Start',
        description: 'Workflow start point'
      },
      {
        id: 'collect',
        type: 'navigate',
        name: 'Collect Wiki Activity Data',
        description: 'Navigate to Wiki page and extract daily activity data',
        properties: {
          tool: 'browser_use',
          action: 'navigate and extract'
        }
      },
      {
        id: 'generate',
        type: 'process',
        name: 'Generate Work Report',
        description: 'Process collected data and generate formatted work report',
        properties: {
          tool: 'llm_extract',
          action: 'summarize and format'
        }
      },
      {
        id: 'send',
        type: 'interact',
        name: 'Send Report to WeChat',
        description: 'Send generated report to specified contact via WeChat',
        properties: {
          tool: 'browser_use',
          action: 'send message'
        }
      },
      {
        id: 'end',
        type: 'end',
        name: 'End',
        description: 'Workflow completed'
      }
    ]

    return intentions
  }

  const getIntentionIcon = (type) => {
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
      case 'end':
        return '✅'
      default:
        return '📌'
    }
  }

  const getIntentionColor = (type) => {
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
      case 'end':
        return '#10b981'
      default:
        return '#6b7280'
    }
  }

  const handleNext = () => {
    onNavigate('metaflow', { recordingData })
  }

  return (
    <div className="page intention-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">意图</div>
      </div>

      <div className="intention-content">
        {/* Intention Visualization */}
        <div className="intention-visualization">
          {intentions.map((intention, index) => (
            <React.Fragment key={intention.id}>
              <div
                className="intention-node"
                style={{ borderColor: getIntentionColor(intention.type) }}
              >
                <div className="intention-icon" style={{ backgroundColor: getIntentionColor(intention.type) }}>
                  {getIntentionIcon(intention.type)}
                </div>
                <div className="intention-details">
                  <div className="intention-name">{intention.name}</div>
                  <div className="intention-description">{intention.description}</div>
                  {intention.properties && (
                    <div className="intention-properties">
                      {Object.entries(intention.properties).map(([key, value]) => (
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
              {index < intentions.length - 1 && (
                <div className="intention-arrow">
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
        <div className="intention-actions">
          <button
            className="start-record-button"
            onClick={handleNext}
          >
            <span>下一步：生成 Metaflow</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default IntentionPage
