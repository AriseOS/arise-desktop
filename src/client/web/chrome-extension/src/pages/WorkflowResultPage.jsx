import React, { useState, useEffect } from 'react'

function WorkflowResultPage({ currentUser, onNavigate, showStatus, taskId }) {
  const [resultData, setResultData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadResultData()
  }, [])

  const loadResultData = async () => {
    setLoading(true)

    try {
      // Demo data from allegro_coffee_products_test_user.csv - 10 rows
      const demoData = {
        workflow_name: "allegro-coffee-collection-workflow",
        total_items: 10,
        fields: ["Product Name", "Price", "Sales Count"],
        data: [
          ["Kawa ziarnista mieszana Dallmayr Crema d Oro 1000 g", "64,99 zł", "3 272 osoby kupiły ostatnio"],
          ["SEGAFREDO INTERMEZZO 1 KG-Kawa ziarnista", "57,97 zł", "6 029 osób kupiło ostatnio"],
          ["Kawa ziarnista 1KG OLOMEGA ARABICA 100% Świeżo Palona Blue Orca + GRATIS", "74,99 zł", "1 696 osób kupiło ostatnio"],
          ["Kawa ziarnista Tchibo Eduscho Family 1 kg", "49,50 zł", "3 513 osób kupiło ostatnio"],
          ["COSTA PROFESSIONAL 1KG SIGNATURE MEDIUM ROAST KAWA ZIARNISTA", "69,29 zł", "2 683 osoby kupiły ostatnio"],
          ["Kawa ziarnista 1kg ITALIANA BELLAGIO ROAST -Świeżo palona BLUE ORCA +GRATIS", "72,99 zł", "3 511 osób kupiło tę ofertę"],
          ["Kawa Ziarnista Lavazza Mieszana Crema e Aroma 1kg Ziarno Do Ekspresu", "73,89 zł", "3 207 osób kupiło tę ofertę"],
          ["Kawa ziarnista 1kg TOPACIO - ŚWIEŻO PALONA BLUE ORCA 100% ARABICA +GRATIS", "67,99 zł", "5 620 osób kupiło ostatnio"],
          ["Kawa ziarnista Arabica Lavazza Qualita Oro 1000 g", "74,99 zł", "3 237 osób kupiło ostatnio"],
          ["Kawa ziarnista Brazylia 1kg Świeżo Palona - 100% Arabica - Monte Carmelo", "71,95 zł", "3 293 osoby kupiły ostatnio"]
        ]
      }

      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 500))

      setResultData(demoData)
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
