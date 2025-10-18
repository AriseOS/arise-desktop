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
      // Hardcoded demo data - 30 rows of Allegro coffee products
      const demoData = {
        workflow_name: "allegro-coffee-collection-workflow",
        total_items: 30,
        fields: ["Product Title", "Price (PLN)"],
        data: [
          ["Lavazza Qualita Oro Coffee Beans 1kg", "89.99"],
          ["Tchibo Exclusive Coffee Ground 250g", "24.50"],
          ["Starbucks Pike Place Roast Whole Bean 200g", "32.90"],
          ["Illy Classico Medium Roast Ground Coffee 250g", "42.00"],
          ["Jacobs Kronung Coffee Ground 500g", "28.75"],
          ["Nescafe Gold Blend Instant Coffee 200g", "34.99"],
          ["Davidoff Cafe Rich Aroma Instant Coffee 100g", "45.50"],
          ["Carte Noire Original Ground Coffee 250g", "36.80"],
          ["Pellini Top Arabica 100% Coffee Beans 500g", "52.00"],
          ["Julius Meinl Jubileum Coffee Beans 500g", "48.90"],
          ["Segafredo Zanetti Intermezzo Coffee Beans 1kg", "78.50"],
          ["Dallmayr Prodomo Ground Coffee 500g", "44.20"],
          ["Paulig Presidentti Original Coffee Beans 400g", "38.60"],
          ["Melitta Auslese Coffee Ground 500g", "31.90"],
          ["Tchibo Familia Ground Coffee 250g", "22.40"],
          ["Lavazza Crema e Gusto Ground Coffee 250g", "26.50"],
          ["Illy Intenso Bold Roast Ground Coffee 250g", "43.80"],
          ["Kimbo Espresso Napoletano Coffee Beans 1kg", "72.00"],
          ["Hausbrandt Trieste Coffee Beans 1kg", "84.50"],
          ["Danesi Caffe Doppio Coffee Beans 1kg", "91.00"],
          ["Carraro Globo Coffee Beans 1kg", "68.90"],
          ["Bristot Classico Coffee Beans 1kg", "75.50"],
          ["Torrie Superior Coffee Ground 250g", "29.90"],
          ["Mokate Gold 3in1 Instant Coffee Box 20x18g", "18.50"],
          ["Woseba Strong Coffee Ground 500g", "33.00"],
          ["Jacobs Velvet Aroma Coffee Ground 250g", "25.80"],
          ["Nescafe Classic Instant Coffee 200g", "28.90"],
          ["Maxwell House Original Ground Coffee 750g", "41.50"],
          ["Folgers Classic Roast Ground Coffee 320g", "35.20"],
          ["Tim Hortons Original Blend Ground Coffee 300g", "37.80"]
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
                <span className="table-subtitle">显示前 15 条数据</span>
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
                    {resultData.data.slice(0, 15).map((row, rowIdx) => (
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

              {resultData.total_items > 15 && (
                <div className="table-footer">
                  还有 {resultData.total_items - 15} 条数据未显示，请下载完整CSV查看
                </div>
              )}
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
