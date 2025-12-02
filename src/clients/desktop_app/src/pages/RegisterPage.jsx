import { useState } from 'react';
import { api } from '../utils/api';
import { auth } from '../utils/auth';

/**
 * Register Page Component
 * Allows new users to create an account
 */
function RegisterPage({ navigate, showStatus, onRegisterSuccess }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const validateForm = () => {
    // Username validation
    if (!username.trim()) {
      showStatus('❌ Please enter username', 'error');
      return false;
    }

    if (username.length < 3) {
      showStatus('❌ Username must be at least 3 characters', 'error');
      return false;
    }

    // Email validation
    if (!email.trim()) {
      showStatus('❌ Please enter email', 'error');
      return false;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      showStatus('❌ Please enter a valid email address', 'error');
      return false;
    }

    // Password validation
    if (!password) {
      showStatus('❌ Please enter password', 'error');
      return false;
    }

    if (password.length < 8) {
      showStatus('❌ Password must be at least 8 characters', 'error');
      return false;
    }

    // Password confirmation
    if (password !== confirmPassword) {
      showStatus('❌ Passwords do not match', 'error');
      return false;
    }

    return true;
  };

  const handleRegister = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    try {
      console.log('[RegisterPage] Attempting registration for:', username);

      // Call API Proxy register endpoint
      const result = await api.register(username, email, password);

      if (!result.success || !result.api_key) {
        throw new Error('Invalid response from server');
      }

      console.log('[RegisterPage] Registration successful, saving session');

      // Save session with API key
      await auth.saveSession(
        result.api_key,
        result.user.username,
        result.user.email,
        result.user
      );

      showStatus('✅ Registration successful! Welcome to Ami!', 'success');

      // Notify parent component
      if (onRegisterSuccess) {
        await onRegisterSuccess();
      }

      // Navigate to main page
      navigate('main');

    } catch (error) {
      console.error('[RegisterPage] Registration failed:', error);
      showStatus(`❌ Registration failed: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page register-page">
      <div className="auth-container">
        {/* Logo and Title */}
        <div className="auth-header">
          <div className="auth-logo">🤖</div>
          <h1 className="auth-title">Ami</h1>
          <p className="auth-subtitle">Create your account</p>
        </div>

        {/* Registration Form */}
        <form className="auth-form" onSubmit={handleRegister}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              className="form-input"
              placeholder="Choose a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <div className="form-hint">Minimum 3 characters</div>
          </div>

          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              className="form-input"
              placeholder="your.email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder="Create a strong password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
            <div className="form-hint">Minimum 8 characters</div>
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              className="form-input"
              placeholder="Re-enter your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={loading}
          >
            {loading ? 'Creating Account...' : 'Register'}
          </button>
        </form>

        {/* Login Link */}
        <div className="auth-footer">
          <p className="auth-link-text">
            Already have an account?{' '}
            <a
              className="auth-link"
              onClick={() => !loading && navigate('login')}
              style={{ cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              Login
            </a>
          </p>
        </div>
      </div>

      <style jsx>{`
        .register-page {
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          padding: 20px;
        }

        .auth-container {
          background: white;
          border-radius: 12px;
          padding: 40px;
          width: 100%;
          max-width: 400px;
          box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }

        .auth-header {
          text-align: center;
          margin-bottom: 30px;
        }

        .auth-logo {
          font-size: 64px;
          margin-bottom: 10px;
        }

        .auth-title {
          font-size: 32px;
          font-weight: 700;
          color: #2d3748;
          margin: 0 0 8px 0;
        }

        .auth-subtitle {
          font-size: 16px;
          color: #718096;
          margin: 0;
        }

        .auth-form {
          margin-bottom: 20px;
        }

        .form-group {
          margin-bottom: 20px;
        }

        .form-group label {
          display: block;
          font-size: 14px;
          font-weight: 600;
          color: #4a5568;
          margin-bottom: 8px;
        }

        .form-input {
          width: 100%;
          padding: 12px 16px;
          font-size: 14px;
          border: 2px solid #e2e8f0;
          border-radius: 8px;
          transition: all 0.2s;
          box-sizing: border-box;
        }

        .form-input:focus {
          outline: none;
          border-color: #667eea;
          box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .form-input:disabled {
          background-color: #f7fafc;
          cursor: not-allowed;
        }

        .form-hint {
          font-size: 12px;
          color: #a0aec0;
          margin-top: 4px;
        }

        .btn {
          padding: 12px 24px;
          font-size: 16px;
          font-weight: 600;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-primary {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        .btn-primary:disabled {
          opacity: 0.6;
          cursor: not-allowed;
          transform: none;
        }

        .btn-block {
          width: 100%;
        }

        .auth-footer {
          text-align: center;
        }

        .auth-link-text {
          font-size: 14px;
          color: #718096;
          margin: 0;
        }

        .auth-link {
          color: #667eea;
          text-decoration: none;
          font-weight: 600;
        }

        .auth-link:hover {
          text-decoration: underline;
        }
      `}</style>
    </div>
  );
}

export default RegisterPage;
