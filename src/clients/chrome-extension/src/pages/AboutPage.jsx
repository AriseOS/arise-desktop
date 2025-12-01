import React from 'react'

function AboutPage({ onNavigate }) {
  return (
    <div className="page about-page">
      <div className="page-header">
        <button
          className="back-button"
          onClick={() => onNavigate('main')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">关于</div>
      </div>

      <div className="about-content">
        <h3>🤖 Ami</h3>
        <p>Ami 致力于通过智能工作流自动化技术，解放您的双手，让重复性劳动成为过去。我们的愿景是打造您的专属数字员工，让 AI 真正为您工作。</p>

        <h3>✨ 我们能做什么</h3>
        <ul>
          <li><strong>录制生成工作流</strong>：只需在浏览器中操作一遍，系统自动生成可复用的工作流</li>
          <li><strong>对话生成工作流</strong>：用自然语言描述需求，AI 为您智能创建工作流</li>
          <li><strong>一键执行任务</strong>：将复杂的多步骤操作简化为一次点击</li>
          <li><strong>跨平台协作</strong>：浏览器插件与 Web 平台无缝配合，随时随地管理您的自动化任务</li>
        </ul>

        <h3>💬 联系我们</h3>
        <p>如果您在使用过程中遇到任何问题，或有任何建议和想法，欢迎随时向我们反馈。您的每一条意见都将帮助我们做得更好。</p>

        <p style={{ textAlign: 'center', color: '#8e8e93', marginTop: '24px' }}>
          Ami v1.0.0<br/>
          让 AI 成为您的得力助手
        </p>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  )
}

export default AboutPage
