import React, { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'

// Demo markdown content for coffee-market-analysis-workflow
const DEMO_MARKDOWN = `# 咖啡市场对比调研报告（ Allegro vs. Amazon ）
*——基于 2025 年 10 月公开商品数据*

---

## 一、调研目的
快速扫描波兰 Allegro 与美国 Amazon 两大平台「咖啡豆/whole bean」热销商品的价格、动销与评价特征，为后续选品、定价及卖点提炼提供参考。

---

## 二、样本说明
| 平台   | 抓取日期 | 样本量 | 筛选条件 |
|--------|----------|--------|----------|
| Allegro | 2025-10 | 10 条 | 关键词"kawa ziarnista 1kg"，按销量排序取 Top10 |
| Amazon  | 2025-10 | 10 条 | 关键词"whole bean coffee"，综合排序取 Top10 |

---

## 三、核心发现

### 1. 价格带分布
| 指标 | Allegro (PLN) | Amazon (USD 估算)* |
|------|---------------|--------------------|
| 最低 | 58.71 zł | ≈7.99 USD (Amazon Fresh 32 Oz) |
| 最高 | 143.99 zł | ≈22.99 USD (Peet's 18 Oz) |
| 中位 | 72.97 zł | ≈12.99 USD |

\\*按 1 USD≈4.2 zł 粗略换算，仅对比量级。

- Allegro 主流价 65-75 zł/kg（≈15-18 USD/kg），Amazon 因包装规格差异大，换算后 12-20 USD/kg，**二者中高端价位段高度重叠**。
- Allegro 出现 2 倍高价组合装（2kg+赠品），说明**捆绑销售可显著抬高客单价**。

### 2. 动销/互动指标
| 平台 | 可量化热度 | 平均值 | 备注 |
|------|------------|--------|------|
| Allegro | 近30天购买人数 | 2,440 人 | Top1 SKU 超 5,000 人 |
| Amazon | 累计评价数 | 21,052 条 | Top1 SKU 35,416 条 |

- Allegro 直接用「购买人数」展示，**转化透明度更高**；Amazon 用「评价数」间接反映累计销量，头部 SKU 评价积累远高于 Allegro。
- 以 Allegro 最高 5,058 人购买 vs Amazon 最高 35,416 条评价，**Amazon 头部 SKU 市场容量≈7×**（假设留评率 3-5%，则销量≈70-120 万袋）。

### 3. 产地与卖点关键词
| 平台 | 高频产地 | 高频卖点词 |
|------|----------|------------|
| Allegro | 巴西、哥伦比亚、越南 | **Świeżo Palona（新鲜烘焙）**、100% Arabica、+GRATIS（赠品） |
| Amazon | 哥伦比亚、意大利拼配 | **Medium Roast**、Crema、Barista、Non-GMO |

- **「新鲜烘焙」是波兰市场核心差异化卖点**，几乎所有 Allegro 热销款都标注；Amazon 更强调「稳定油脂/crema」与「barista 配方」，反映饮用场景偏向意式/浓缩。
- Allegro 赠品策略普遍（1kg 主售即送磨豆机、密封罐等），Amazon 几乎无赠品，**捆绑价值感在波兰市场更有效**。

### 4. 品牌格局
- Allegro：本土/小微烘焙品牌占 8/10（Blue Orca、Mott Gato 等），国际品牌仅 Melitta 进入 Top10。
- Amazon：Lavazza 独占 6/10，Peet's、Amazon自有品牌瓜分其余，**头部集中度高，进口大牌主导**。

---

## 四、机会点与建议
1. 进入波兰：
   - 主打「新鲜烘焙+巴西/哥伦比亚单一产地」+ **明确烘焙日期**；
   - 1kg 标准装标价 69-75 zł，搭配高感知价值赠品（如咖啡勺/密封夹），复制现有爆款公式。

2. 进入美国：
   - 避开 Lavazza 强势价格段（12-14 USD/2.2lb），可切入 **功能性细分**（低酸、高咖啡因、有机）或 **小批次单一庄园** 故事溢价 18-22 USD/12oz。
   - 重点积累早期评价：通过亚马逊 Vine、早期 reviewer 计划快速达到 500+ 评价，突破「评价门槛」。

3. 交叉学习：
   - Allegro 商家善用「购买人数」实时社交证明，Amazon 新品牌可尝试在独立站/Bing Ads 同步展示「XX 人本周购买」动态，强化转化。
   - Amazon 头部 SKU 图文详情页高度标准化（拼配比例、杯测分数、冲煮参数），Allegro 商家可引入同款信息模块，提升专业度与溢价空间。

---

## 五、数据局限
- 样本仅 Top10，未覆盖长尾；
- Allegro 购买人数为「近30天」，Amazon 评价数为「累计」，时间维度不一致；
- 汇率、运费、促销价未统一，价格对比为量级参考。

---

## 六、附录（原始样本）
详见抓取文件：
- \`allegro_top10_kawa_ziarnista_202510.csv\`
- \`amazon_top10_whole_bean_202510.csv\`
`

function WorkflowResultPage({ currentUser, onNavigate, showStatus, params }) {
  const reportRef = useRef(null)
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

      // Check if results is an object (multi-collection) or array (single collection)
      const isObjectFormat = apiData.results && typeof apiData.results === 'object' && !Array.isArray(apiData.results)

      // Determine if multi-collection based on number of collections
      // If only 1 collection, treat as single collection for better UX
      const isMultiCollection = isObjectFormat && apiData.collections && apiData.collections.length > 1

      let displayData

      if (isObjectFormat && isMultiCollection) {
        // Handle multi-collection results
        const collections = Object.keys(apiData.results)
        const systemFields = ['id', 'created_at']

        // Process each collection
        const collectionsData = collections.map(collectionName => {
          const results = apiData.results[collectionName] || []

          // Extract field names from first result
          const dataFields = results.length > 0
            ? Object.keys(results[0]).filter(key => !systemFields.includes(key))
            : []

          // Transform results to table data
          const tableData = results.map(item =>
            dataFields.map(field => item[field] || '')
          )

          return {
            name: collectionName,
            displayName: collectionName.split('_').map(word =>
              word.charAt(0).toUpperCase() + word.slice(1)
            ).join(' '),
            count: results.length,
            fields: dataFields.map(field =>
              field.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
            ),
            data: tableData
          }
        })

        displayData = {
          workflow_name: apiData.workflow_name,
          total_items: apiData.total_results,
          collections: collectionsData,
          isMultiCollection: true,
          time_range: apiData.time_range
        }
      } else if (isObjectFormat && !isMultiCollection) {
        // Handle single collection in object format (new backend format)
        const collectionName = Object.keys(apiData.results)[0]
        const results = apiData.results[collectionName] || []
        const systemFields = ['id', 'created_at']
        const dataFields = results.length > 0
          ? Object.keys(results[0]).filter(key => !systemFields.includes(key))
          : []

        const tableData = results.map(item =>
          dataFields.map(field => item[field] || '')
        )

        displayData = {
          workflow_name: apiData.workflow_name,
          total_items: apiData.total_results,
          fields: dataFields.map(field =>
            field.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
          ),
          data: tableData,
          isMultiCollection: false,
          time_range: apiData.time_range
        }
      } else {
        // Handle old array format (backward compatibility)
        const results = Array.isArray(apiData.results) ? apiData.results : []
        const systemFields = ['id', 'created_at']
        const dataFields = results.length > 0
          ? Object.keys(results[0]).filter(key => !systemFields.includes(key))
          : []

        const tableData = results.map(item =>
          dataFields.map(field => item[field] || '')
        )

        displayData = {
          workflow_name: apiData.workflow_name,
          total_items: apiData.total_results,
          fields: dataFields.map(field =>
            field.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
          ),
          data: tableData,
          isMultiCollection: false,
          time_range: apiData.time_range
        }
      }

      setResultData(displayData)
      setLoading(false)
    } catch (err) {
      console.error('Load result data error:', err)
      showStatus('❌ 加载结果失败', 'error')
      setLoading(false)
    }
  }

  const downloadPDF = async () => {
    if (!reportRef.current) return

    showStatus('📄 正在生成PDF...', 'info')

    try {
      const canvas = await html2canvas(reportRef.current, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff'
      })

      const imgData = canvas.toDataURL('image/png')
      const pdf = new jsPDF('p', 'mm', 'a4')

      const pdfWidth = pdf.internal.pageSize.getWidth()
      const pdfHeight = pdf.internal.pageSize.getHeight()
      const imgWidth = pdfWidth - 20 // 10mm margins on each side
      const imgHeight = (canvas.height * imgWidth) / canvas.width

      let heightLeft = imgHeight
      let position = 10

      // Add first page
      pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight)
      heightLeft -= pdfHeight

      // Add additional pages if content is longer
      while (heightLeft > 0) {
        position = heightLeft - imgHeight + 10
        pdf.addPage()
        pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight)
        heightLeft -= pdfHeight
      }

      pdf.save('咖啡市场对比调研报告_Allegro_vs_Amazon.pdf')
      showStatus('✅ PDF已下载', 'success')
    } catch (error) {
      console.error('PDF generation error:', error)
      showStatus('❌ PDF生成失败', 'error')
    }
  }

  const downloadCSV = () => {
    if (!resultData) return

    if (resultData.isMultiCollection) {
      // Download separate CSV for each collection
      resultData.collections.forEach(collection => {
        const headers = collection.fields.join(',')
        const rows = collection.data.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
        const csvContent = `${headers}\n${rows}`

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const link = document.createElement('a')
        const url = URL.createObjectURL(blob)

        link.setAttribute('href', url)
        link.setAttribute('download', `${resultData.workflow_name}_${collection.name}.csv`)
        link.style.visibility = 'hidden'

        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      })
      showStatus(`✅ 已下载 ${resultData.collections.length} 个CSV文件`, 'success')
    } else {
      // Single collection CSV download
      const headers = resultData.fields.join(',')
      const rows = resultData.data.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
      const csvContent = `${headers}\n${rows}`

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
  }

  const handleDownload = () => {
    // Check if this is the demo workflow
    if (workflowName === 'coffee-market-analysis-workflow') {
      downloadPDF()
    } else {
      downloadCSV()
    }
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
        {!loading && (workflowName === 'coffee-market-analysis-workflow' || resultData) && (
          <button className="download-button" onClick={handleDownload}>
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

        {/* Demo mode: Display markdown report for coffee-market-analysis-workflow */}
        {!loading && workflowName === 'coffee-market-analysis-workflow' && (
          <div className="markdown-report-container" ref={reportRef}>
            <ReactMarkdown>{DEMO_MARKDOWN}</ReactMarkdown>
          </div>
        )}

        {/* Normal mode: Display data tables */}
        {!loading && workflowName !== 'coffee-market-analysis-workflow' && resultData && (
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
              {!resultData.isMultiCollection && (
                <div className="summary-item">
                  <span className="summary-label">字段数量</span>
                  <span className="summary-value">{resultData.fields.length} 个</span>
                </div>
              )}
              {resultData.isMultiCollection && (
                <div className="summary-item">
                  <span className="summary-label">数据源</span>
                  <span className="summary-value">{resultData.collections.length} 个</span>
                </div>
              )}
            </div>

            {resultData.isMultiCollection ? (
              // Multi-collection display
              resultData.collections.map((collection, collectionIdx) => (
                <div key={collectionIdx} className="result-table-container">
                  <div className="result-table-header">
                    <span className="table-title">{collection.displayName}</span>
                    <span className="table-subtitle">共 {collection.count} 条数据</span>
                  </div>

                  <div className="result-table-wrapper">
                    <table className="result-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          {collection.fields.map((field, idx) => (
                            <th key={idx}>{field}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {collection.data.map((row, rowIdx) => (
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
              ))
            ) : (
              // Single collection display
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
            )}
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
