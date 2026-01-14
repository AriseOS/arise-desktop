import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../utils/api';
import { auth } from '../utils/auth';
import Icon from '../components/Icons';
import '../styles/LoginPage.css';

/**
 * Login Page Component
 * Allows users to login with username and password
 */
function LoginPage({ navigate, showStatus, onLoginSuccess }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();

    // Validation
    if (!username.trim()) {
      showStatus(t('auth.validation.enterEmail'), 'error');
      return;
    }

    if (!password) {
      showStatus(t('auth.validation.enterPassword'), 'error');
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

      showStatus(t('auth.toasts.loginSuccess'), 'success');

      // Notify parent component
      if (onLoginSuccess) {
        await onLoginSuccess();
      }

      // Navigate to main page
      navigate('main');

    } catch (error) {
      console.error('[LoginPage] Login failed:', error);
      showStatus(t('auth.toasts.loginFailed', { error: error.message }), 'error');
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
          <p className="auth-subtitle">{t('auth.loginTitle')}</p>
        </div>

        {/* Login Form */}
        <form className="auth-form" onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="username">{t('auth.emailLabel')}</label>
            <input
              id="username"
              type="text"
              className="form-input"
              placeholder={t('auth.emailPlaceholder')}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <div className="form-hint">{t('auth.emailHint')}</div>
          </div>

          <div className="form-group">
            <label htmlFor="password">{t('auth.passwordLabel')}</label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder={t('auth.passwordPlaceholder')}
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
                <span>{t('auth.loggingIn')}</span>
              </>
            ) : (
              <>
                <Icon icon="logIn" size={20} />
                <span>{t('auth.loginBtn')}</span>
              </>
            )}
          </button>
        </form>

        {/* Register Link */}
        <div className="auth-footer">
          <p className="auth-link-text">
            {t('auth.noAccount')}{' '}
            <a
              className="auth-link"
              onClick={() => !loading && navigate('register')}
              style={{ cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              {t('auth.registerLink')}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
