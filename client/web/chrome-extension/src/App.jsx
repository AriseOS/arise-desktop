import React, { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import MainPage from './pages/MainPage'
import MyWorkflowsPage from './pages/MyWorkflowsPage'
import WorkflowDetailPage from './pages/WorkflowDetailPage'
import AboutPage from './pages/AboutPage'
import StatusMessage from './components/StatusMessage'

function App() {
  const [currentPage, setCurrentPage] = useState('login')
  const [currentUser, setCurrentUser] = useState(null)
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(null)
  const [statusMessage, setStatusMessage] = useState({ text: '', type: 'info' })

  useEffect(() => {
    checkLoginStatus()
  }, [])

  const checkLoginStatus = async () => {
    try {
      const result = await chrome.storage.local.get(['userToken', 'userId', 'username'])

      if (result.userToken && result.userId) {
        setCurrentUser({
          token: result.userToken,
          userId: result.userId,
          username: result.username
        })
        setCurrentPage('main')
      } else {
        setCurrentPage('login')
      }
    } catch (error) {
      console.error('Check login status error:', error)
      setCurrentPage('login')
    }
  }

  const handleLogin = async (token, userId, username) => {
    setCurrentUser({ token, userId, username })
    setCurrentPage('main')
  }

  const handleLogout = async () => {
    await chrome.storage.local.clear()
    setCurrentUser(null)
    setCurrentPage('login')
  }

  const navigateTo = (page, data = {}) => {
    if (data.workflowId) {
      setSelectedWorkflowId(data.workflowId)
    }
    setCurrentPage(page)
  }

  const showStatus = (text, type = 'info') => {
    setStatusMessage({ text, type })
  }

  const hideStatus = () => {
    setStatusMessage({ text: '', type: 'info' })
  }

  return (
    <div className="app">
      <StatusMessage
        message={statusMessage.text}
        type={statusMessage.type}
        onClose={hideStatus}
      />

      {currentPage === 'login' && (
        <LoginPage onLogin={handleLogin} />
      )}
      {currentPage === 'main' && (
        <MainPage
          currentUser={currentUser}
          onNavigate={navigateTo}
          onLogout={handleLogout}
          showStatus={showStatus}
        />
      )}
      {currentPage === 'my-workflows' && (
        <MyWorkflowsPage
          currentUser={currentUser}
          onNavigate={navigateTo}
          onLogout={handleLogout}
        />
      )}
      {currentPage === 'workflow-detail' && (
        <WorkflowDetailPage
          currentUser={currentUser}
          workflowId={selectedWorkflowId}
          onNavigate={navigateTo}
          showStatus={showStatus}
          onLogout={handleLogout}
        />
      )}
      {currentPage === 'about' && (
        <AboutPage onNavigate={navigateTo} />
      )}
    </div>
  )
}

export default App
