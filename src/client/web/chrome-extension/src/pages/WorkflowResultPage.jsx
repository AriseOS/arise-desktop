import React, { useState, useEffect } from 'react'

function WorkflowResultPage({ currentUser, onNavigate, showStatus, params }) {
  const [resultData, setResultData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Extract parameters passed from WorkflowDetailPage
  const workflowName = params?.workflowName || 'allegro-coffee-collection-workflow'
  const startTime = params?.startTime
  const endTime = params?.endTime

  useEffect(() => {
    loadResultData()
  }, [])

  const loadResultData = async () => {
    setLoading(true)

    try {
      // Build API URL with time range parameters
      let apiUrl = `http://localhost:8000/api/agents/workflow/${workflowName}/results?`
      const queryParams = []

      if (startTime) {
        queryParams.push(`begin=${encodeURIComponent(startTime)}`)
      }
      if (endTime) {
        queryParams.push(`end=${encodeURIComponent(endTime)}`)
      }

      apiUrl += queryParams.join('&')

      console.log('Fetching workflow results:', apiUrl)

      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.token}`
        }
      })

      if (!response.ok) {
        if (response.status === 401) {
          await chrome.storage.local.clear()
          onNavigate('login')
          return
        }
        throw new Error(`API error: ${response.status}`)
      }

      const apiData = await response.json()
      console.log('Workflow results received:', apiData)

      // Transform API response to display format
      const results = apiData.results || []

      // Extract field names from first result (excluding system fields)
      const systemFields = ['id', 'created_at']
      const dataFields = results.length > 0
        ? Object.keys(results[0]).filter(key => !systemFields.includes(key))
        : []

      // Transform results to table data
      const tableData = results.map(item =>
        dataFields.map(field => item[field] || '')
      )

      const displayData = {
        workflow_name: apiData.workflow_name,
        total_items: apiData.total_results,
        fields: dataFields.map(field =>
          field.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
        ),
        data: tableData,
        time_range: apiData.time_range
      }

      setResultData(displayData)
      setLoading(false)
    } catch (err) {
      console.error('Load result data error:', err)
      showStatus('❌ 加载结果失败', 'error')
      setLoading(false)
    }
  }

  const downloadCSV = () => {
    if (!resultData) return

    // Generate CSV content
    const headers = resultData.fields.join(',')
    const rows = resultData.data.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
    const csvContent = `${headers}\n${rows}`

    // Create download link
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)

    link.setAttribute('href', url)
    link.setAttribute('download', `${resultData.workflow_name}_results.csv`)
    link.style.visibility = 'hidden'

    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    showStatus('✅ CSV文件已下载', 'success')
  }

  return (
    <div className="page workflow-result-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('workflow-generation')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">运行结果</div>
        {!loading && resultData && (
          <button className="download-button" onClick={downloadCSV}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>下载</span>
          </button>
        )}
      </div>

      <div className="workflow-result-content">
        {loading && (
          <div className="empty-state">
            <div className="empty-state-icon">⏳</div>
            <div className="empty-state-title">加载中...</div>
          </div>
        )}

        {!loading && resultData && (
          <>
            <div className="result-summary">
              <div className="summary-item">
                <span className="summary-label">Workflow</span>
                <span className="summary-value">{resultData.workflow_name}</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">采集数量</span>
                <span className="summary-value">{resultData.total_items} 条</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">字段数量</span>
                <span className="summary-value">{resultData.fields.length} 个</span>
              </div>
            </div>

            <div className="result-table-container">
              <div className="result-table-header">
                <span className="table-title">数据预览</span>
                <span className="table-subtitle">共 {resultData.total_items} 条数据</span>
              </div>

              <div className="result-table-wrapper">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      {resultData.fields.map((field, idx) => (
                        <th key={idx}>{field}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {resultData.data.map((row, rowIdx) => (
                      <tr key={rowIdx}>
                        <td className="row-number">{rowIdx + 1}</td>
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default WorkflowResultPage
