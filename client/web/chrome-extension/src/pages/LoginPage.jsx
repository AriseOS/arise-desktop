import React, { useState } from 'react'

function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', type: '' })

  const showMessage = (text, type = 'info') => {
    setMessage({ text, type })
    setTimeout(() => setMessage({ text: '', type: '' }), 3000)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!username || !password) {
      showMessage('Please enter username and password', 'error')
      return
    }

    setLoading(true)

    try {
      const response = await fetch('http://localhost:8000/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })

      if (response.ok) {
        const data = await response.json()

        await chrome.storage.local.set({
          userToken: data.access_token,
          userId: data.user.id,
          username: data.user.username
        })

        onLogin(data.access_token, data.user.id, data.user.username)
      } else {
        showMessage('Login failed', 'error')
      }
    } catch (error) {
      console.error('Login error:', error)
      showMessage('Network error', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page login-page">
      {message.text && (
        <div className={`status-message status-${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="header">
        <h1>🤖 AgentCrafter</h1>
        <p>Workflow Automation Extension</p>
      </div>

      <div className="card">
        <h3>Login</h3>
        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              disabled={loading}
            />
          </div>
          <div className="input-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={loading}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  )
}

export default LoginPage
