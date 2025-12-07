import { useState } from 'react';
import { api } from '../utils/api';
import { auth } from '../utils/auth';
import Icon from '../components/Icons';
import '../styles/LoginPage.css';

/**
 * Login Page Component
 * Allows users to login with username and password
 */
function LoginPage({ navigate, showStatus, onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();

    // Validation
    if (!username.trim()) {
      showStatus('Please enter username', 'error');
      return;
    }

    if (!password) {
      showStatus('Please enter password', 'error');
      return;
    }

    setLoading(true);

    try {
      console.log('[LoginPage] Attempting login for:', username);

      // Call API Proxy login endpoint
      const result = await api.login(username, password);

      if (!result.success || !result.api_key) {
        throw new Error('Invalid response from server');
      }

      console.log('[LoginPage] Login successful, saving session');

      // Save session with API key and token (CRS provides token in login response)
      await auth.saveSession(
        result.api_key,
        result.user.username,
        result.user.email,
        result.user,
        result.token // CRS JWT token
      );

      showStatus('Login successful!', 'success');

      // Notify parent component
      if (onLoginSuccess) {
        await onLoginSuccess();
      }

      // Navigate to main page
      navigate('main');

    } catch (error) {
      console.error('[LoginPage] Login failed:', error);
      showStatus(`Login failed: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page login-page">
      <div className="auth-container">
        {/* Logo and Title */}
        <div className="auth-header">
          <div className="auth-logo"><Icon icon="cpu" size={64} /></div>
          <h1 className="auth-title">Ami</h1>
          <p className="auth-subtitle">Login to your account</p>
        </div>

        {/* Login Form */}
        <form className="auth-form" onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="username">Email</label>
            <input
              id="username"
              type="text"
              className="form-input"
              placeholder="Enter your email address"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <div className="form-hint">CRS requires email for login</div>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={loading}
          >
            {loading ? (
              <>
                <div className="btn-spinner"></div>
                <span>Logging in...</span>
              </>
            ) : (
              <>
                <Icon icon="logIn" size={20} />
                <span>Login</span>
              </>
            )}
          </button>
        </form>

        {/* Register Link */}
        <div className="auth-footer">
          <p className="auth-link-text">
            Don't have an account?{' '}
            <a
              className="auth-link"
              onClick={() => !loading && navigate('register')}
              style={{ cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              Register
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
