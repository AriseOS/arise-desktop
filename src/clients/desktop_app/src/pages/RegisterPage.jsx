import { useState } from 'react';
import { api } from '../utils/api';
import { auth } from '../utils/auth';
import Icon from '../components/Icons';
import '../styles/RegisterPage.css';

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
      showStatus('Please enter username', 'error');
      return false;
    }

    if (username.length < 3) {
      showStatus('Username must be at least 3 characters', 'error');
      return false;
    }

    // Email validation
    if (!email.trim()) {
      showStatus('Please enter email', 'error');
      return false;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      showStatus('Please enter a valid email address', 'error');
      return false;
    }

    // Password validation
    if (!password) {
      showStatus('Please enter password', 'error');
      return false;
    }

    if (password.length < 8) {
      showStatus('Password must be at least 8 characters', 'error');
      return false;
    }

    // Password confirmation
    if (password !== confirmPassword) {
      showStatus('Passwords do not match', 'error');
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

      showStatus('Registration successful! Welcome to Ami!', 'success');

      // Notify parent component
      if (onRegisterSuccess) {
        await onRegisterSuccess();
      }

      // Navigate to main page
      navigate('main');

    } catch (error) {
      console.error('[RegisterPage] Registration failed:', error);
      showStatus(`Registration failed: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page register-page">
      <div className="auth-container">
        {/* Logo and Title */}
        <div className="auth-header">
          <div className="auth-logo"><Icon icon="cpu" size={64} /></div>
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
            {loading ? (
              <>
                <div className="btn-spinner"></div>
                <span>Creating Account...</span>
              </>
            ) : (
              <>
                <Icon icon="userPlus" size={20} />
                <span>Register</span>
              </>
            )}
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
    </div>
  );
}

export default RegisterPage;
