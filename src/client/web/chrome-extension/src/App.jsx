import React, { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import MainPage from './pages/MainPage'
import MyWorkflowsPage from './pages/MyWorkflowsPage'
import WorkflowDetailPage from './pages/WorkflowDetailPage'
import WorkflowGenerationPage from './pages/WorkflowGenerationPage'
import WorkflowResultPage from './pages/WorkflowResultPage'
import AboutPage from './pages/AboutPage'
import RecordPage from './pages/RecordPage'
import IntentionPage from './pages/IntentionPage'
import MetaflowPage from './pages/MetaflowPage'
import ChatPage from './pages/ChatPage'
import WorkflowAnalysisPage from './pages/WorkflowAnalysisPage'
import StatusMessage from './components/StatusMessage'

function App() {
  const [currentPage, setCurrentPage] = useState('login')
  const [currentUser, setCurrentUser] = useState(null)
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(null)
  const [recordingData, setRecordingData] = useState(null)
  const [currentTaskId, setCurrentTaskId] = useState(null)
  const [statusMessage, setStatusMessage] = useState({ text: '', type: 'info' })

  useEffect(() => {
    checkLoginStatus()

    // Listen for auth expiration from background script
    const handleMessage = (message, sender, sendResponse) => {
      if (message.action === 'authExpired') {
        console.log('⚠️ Auth expired, redirecting to login')
        handleLogout()
        showStatus('🔐 登录已过期，请重新登录', 'warning')
      }
    }

    chrome.runtime.onMessage.addListener(handleMessage)

    // Cleanup
    return () => {
      chrome.runtime.onMessage.removeListener(handleMessage)
    }
  }, [])

  const checkLoginStatus = async () => {
    try {
      const result = await chrome.storage.local.get(['userToken', 'userId', 'username', 'currentPage', 'selectedWorkflowId'])

      if (result.userToken && result.userId) {
        setCurrentUser({
          token: result.userToken,
          userId: result.userId,
          username: result.username
        })
        // Restore previous page state
        if (result.currentPage && result.currentPage !== 'login') {
          setCurrentPage(result.currentPage)
          if (result.selectedWorkflowId) {
            setSelectedWorkflowId(result.selectedWorkflowId)
          }
        } else {
          setCurrentPage('main')
        }
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

  const [navigationParams, setNavigationParams] = useState({})

  const navigateTo = async (page, data = {}) => {
    if (data.workflowId) {
      setSelectedWorkflowId(data.workflowId)
      await chrome.storage.local.set({
        currentPage: page,
        selectedWorkflowId: data.workflowId
      })
    } else {
      await chrome.storage.local.set({ currentPage: page })
    }

    // Handle recording data for intention page (in memory only, not persistent)
    if (data.recordingData) {
      setRecordingData(data.recordingData)
    }

    // Handle taskId for result page (in memory only)
    if (data.taskId) {
      setCurrentTaskId(data.taskId)
    }

    // Store all navigation params for pages that need them
    setNavigationParams(data)

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
      {currentPage === 'record' && (
        <RecordPage
          currentUser={currentUser}
          onNavigate={navigateTo}
          showStatus={showStatus}
        />
      )}
      {currentPage === 'intention' && (
        <IntentionPage
          onNavigate={navigateTo}
          showStatus={showStatus}
          recordingData={recordingData}
        />
      )}
      {currentPage === 'workflow-analysis' && (
        <WorkflowAnalysisPage
          onNavigate={navigateTo}
          params={navigationParams}
        />
      )}
      {currentPage === 'metaflow' && (
        <MetaflowPage
          onNavigate={navigateTo}
          showStatus={showStatus}
          recordingData={recordingData}
        />
      )}
      {currentPage === 'workflow-generation' && (
        <WorkflowGenerationPage
          currentUser={currentUser}
          onNavigate={navigateTo}
          showStatus={showStatus}
          recordingData={recordingData}
        />
      )}
      {currentPage === 'workflow-result' && (
        <WorkflowResultPage
          currentUser={currentUser}
          onNavigate={navigateTo}
          showStatus={showStatus}
          params={navigationParams}
        />
      )}
      {currentPage === 'chat' && (
        <ChatPage
          onNavigate={navigateTo}
          showStatus={showStatus}
        />
      )}
    </div>
  )
}

export default App
