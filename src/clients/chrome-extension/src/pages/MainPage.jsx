import React from 'react'

function MainPage({ currentUser, onNavigate, onLogout, showStatus }) {
  const menuItems = [
    {
      section: 'Workflow',
      items: [
        { id: 'record', title: '录制', icon: 'record', onClick: () => onNavigate('record') },
        { id: 'chat', title: '对话', icon: 'chat', onClick: () => onNavigate('chat') },
        { id: 'my', title: '我的', icon: 'my', onClick: () => onNavigate('my-workflows') },
      ]
    },
    {
      section: '其他',
      items: [
        { id: 'account', title: '账户', icon: 'account', onClick: () => showStatus('👤 账户设置功能开发中...', 'info') },
        { id: 'about', title: '关于', icon: 'about', onClick: () => onNavigate('about') },
        { id: 'logout', title: '退出登录', icon: 'logout', onClick: onLogout },
      ]
    }
  ]

  const getIcon = (type) => {
    const icons = {
      record: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <circle cx="12" cy="12" r="10"></circle>
          <circle cx="12" cy="12" r="3" fill="#667eea"></circle>
        </svg>
      ),
      chat: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      ),
      my: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
      ),
      account: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
      ),
      about: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
      ),
      logout: (
        <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
          <polyline points="16 17 21 12 16 7"></polyline>
          <line x1="21" y1="12" x2="9" y2="12"></line>
        </svg>
      ),
    }
    return icons[type]
  }

  return (
    <div className="page main-page">
      <div className="app-header">
        <div className="app-icon">🤖</div>
        <div className="app-info">
          <div className="app-name">Ami</div>
          <div className="app-description">Workflow Automation Extension</div>
        </div>
      </div>

      {menuItems.map((section, idx) => (
        <div key={idx}>
          <div className="settings-section-title">{section.section}</div>
          <div className="settings-section">
            {section.items.map((item) => (
              <div
                key={item.id}
                className="settings-item"
                onClick={item.onClick}
              >
                <div className="settings-item-left">
                  <div className="settings-item-icon">
                    {getIcon(item.icon)}
                  </div>
                  <div className="settings-item-text">
                    <div className="settings-item-title">{item.title}</div>
                  </div>
                </div>
                <div className="settings-item-arrow">›</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  )
}

export default MainPage
