import { useState, useEffect, useRef } from 'react'

const ANALYSIS_TEXT = `复用已有 Workflow:
  ✓ 采集 Allegro 商品数据（完整复用）
  ✓ 采集 Amazon 商品数据（完整复用）

新增数据处理能力:
  + 合并数据集 - 标准化字段名（Allegro 和 Amazon 字段名不同）
  + 对比分析 - 计算价格差异、评分对比、识别最佳优惠
  + 生成报告 - 创建包含图表的 PDF 报告

🎯 复用价值:
  - 数据采集: 100% 复用 已有Workflow
  - 数据处理: 100% 新学习（新能力，未来可复用）

💡 数据采集部分完全复用，只需要学习"如何对比分析"！
   这些分析能力未来可以用于任何跨网站对比场景。`

function WorkflowAnalysisPage({ onNavigate, params }) {
  const [displayedText, setDisplayedText] = useState('')
  const [isComplete, setIsComplete] = useState(false)
  const textRef = useRef(null)

  useEffect(() => {
    let currentIndex = 0
    const textLength = ANALYSIS_TEXT.length
    const typingSpeed = (5000 / textLength) // 5 seconds total

    const typeInterval = setInterval(() => {
      if (currentIndex < textLength) {
        setDisplayedText(ANALYSIS_TEXT.substring(0, currentIndex + 1))
        currentIndex++

        // Auto-scroll to bottom
        if (textRef.current) {
          textRef.current.scrollTop = textRef.current.scrollHeight
        }
      } else {
        clearInterval(typeInterval)
        setIsComplete(true)

        // Auto-navigate to metaflow after completion
        setTimeout(() => {
          onNavigate('metaflow', params)
        }, 500)
      }
    }, typingSpeed)

    return () => clearInterval(typeInterval)
  }, [onNavigate, params])

  return (
    <div className="page workflow-analysis-page">
      <div className="page-header">
        <div className="page-title">🔍 智能分析中...</div>
      </div>

      <div className="analysis-content">
        <div className="analysis-text-container">
          <pre className="analysis-text" ref={textRef}>{displayedText}</pre>
          {!isComplete && <span className="typing-cursor">▋</span>}
        </div>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default WorkflowAnalysisPage
