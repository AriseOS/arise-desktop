import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../utils/api';
import { auth } from '../utils/auth';
import Icon from '../components/Icons';
import '../styles/RegisterPage.css';

/**
 * Register Page Component
 * Allows new users to create an account
 */
function RegisterPage({ navigate, showStatus, onRegisterSuccess }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const validateForm = () => {
    // Username validation
    if (!username.trim()) {
      showStatus(t('auth.validation.enterUsername'), 'error');
      return false;
    }

    if (username.length < 3) {
      showStatus(t('auth.validation.usernameLength'), 'error');
      return false;
    }

    // Email validation
    if (!email.trim()) {
      showStatus(t('auth.validation.enterEmail'), 'error');
      return false;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      showStatus(t('auth.validation.validEmail'), 'error');
      return false;
    }

    // Password validation
    if (!password) {
      showStatus(t('auth.validation.enterPassword'), 'error');
      return false;
    }

    if (password.length < 8) {
      showStatus(t('auth.validation.passwordLength'), 'error');
      return false;
    }

    // Check for uppercase letter
    if (!/[A-Z]/.test(password)) {
      showStatus(t('auth.validation.passwordUpper'), 'error');
      return false;
    }

    // Check for lowercase letter
    if (!/[a-z]/.test(password)) {
      showStatus(t('auth.validation.passwordLower'), 'error');
      return false;
    }

    // Password confirmation
    if (password !== confirmPassword) {
      showStatus(t('auth.validation.passwordMatch'), 'error');
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

      // Save session with API key and token (CRS provides token in registration response)
      await auth.saveSession(
        result.api_key,
        result.user.username,
        result.user.email,
        result.user,
        result.token // CRS JWT token (if provided)
      );

      showStatus(t('auth.toasts.registerSuccess'), 'success');

      // Notify parent component
      if (onRegisterSuccess) {
        await onRegisterSuccess();
      }

      // Navigate to main page
      navigate('main');

    } catch (error) {
      console.error('[RegisterPage] Registration failed:', error);
      showStatus(t('auth.toasts.registerFailed', { error: error.message }), 'error');
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
          <p className="auth-subtitle">{t('auth.createAccountTitle')}</p>
        </div>

        {/* Registration Form */}
        <form className="auth-form" onSubmit={handleRegister}>
          <div className="form-group">
            <label htmlFor="username">{t('auth.usernameLabel')}</label>
            <input
              id="username"
              type="text"
              className="form-input"
              placeholder={t('auth.usernamePlaceholder')}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <div className="form-hint">{t('auth.usernameHint')}</div>
          </div>

          <div className="form-group">
            <label htmlFor="email">{t('auth.emailLabel')}</label>
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
            <label htmlFor="password">{t('auth.passwordLabel')}</label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder={t('auth.passwordPlaceholderStrong')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
            <div className="form-hint">{t('auth.passwordHint')}</div>
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">{t('auth.confirmPasswordLabel')}</label>
            <input
              id="confirmPassword"
              type="password"
              className="form-input"
              placeholder={t('auth.confirmPasswordPlaceholder')}
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
                <span>{t('auth.creatingAccount')}</span>
              </>
            ) : (
              <>
                <Icon icon="userPlus" size={20} />
                <span>{t('auth.registerBtn')}</span>
              </>
            )}
          </button>
        </form>

        {/* Login Link */}
        <div className="auth-footer">
          <p className="auth-link-text">
            {t('auth.hasAccount')}{' '}
            <a
              className="auth-link"
              onClick={() => !loading && navigate('login')}
              style={{ cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              {t('auth.loginLink')}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
