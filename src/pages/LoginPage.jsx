import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../utils/api';
import { auth } from '../utils/auth';
import Icon from '../components/Icons';
import '../styles/LoginPage.css';

/**
 * Login Page Component
 * Allows users to login with username and password, or use their own API key
 */
function LoginPage({ navigate, showStatus, onLoginSuccess, onLocalModeStart }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  // Local mode (own API key) state
  const [showApiKeyForm, setShowApiKeyForm] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [localLoading, setLocalLoading] = useState(false);

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

      const result = await api.login(username, password);

      if (!result.success || !result.access_token) {
        throw new Error('Invalid response from server');
      }

      console.log('[LoginPage] Login successful, saving UI metadata');

      // Daemon already stored tokens + fetched LLM credentials (intercepted during login proxy)
      await auth.saveSession(
        result.user.username,
        result.user.email || '',
        result.user
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

  const handleLocalModeStart = async () => {
    if (!apiKey.trim()) {
      showStatus(t('auth.apiKeyRequired'), 'error');
      return;
    }

    setLocalLoading(true);

    try {
      // Save API key and optional base_url to daemon settings
      const credConfig = { api_key: apiKey.trim() };
      if (baseUrl.trim()) {
        credConfig.base_url = baseUrl.trim();
      }
      await api.setCredentials('anthropic', credConfig);

      // Save model if provided
      if (model.trim()) {
        await api.post('/api/v1/settings', { llm_model: model.trim() });
      }

      console.log('[LoginPage] Local mode credentials saved');

      // Notify parent to enter local mode
      if (onLocalModeStart) {
        await onLocalModeStart();
      }

      navigate('main');
    } catch (error) {
      console.error('[LoginPage] Failed to save local mode credentials:', error);
      showStatus(t('auth.toasts.loginFailed', { error: error.message }), 'error');
    } finally {
      setLocalLoading(false);
    }
  };

  const isAnyLoading = loading || localLoading;

  return (
    <div className="page login-page">
      <div className="auth-container">
        {/* Logo and Title */}
        <div className="auth-header">
          <div className="auth-logo"><Icon icon="cpu" size={64} /></div>
          <h1 className="auth-title">Arise</h1>
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
              disabled={isAnyLoading}
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
              disabled={isAnyLoading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={isAnyLoading}
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
              onClick={() => !isAnyLoading && navigate('register')}
              style={{ cursor: isAnyLoading ? 'not-allowed' : 'pointer' }}
            >
              {t('auth.registerLink')}
            </a>
          </p>
        </div>

        {/* Divider */}
        <div className="auth-divider">
          <span>{t('auth.orDivider')}</span>
        </div>

        {/* Use Own API Key */}
        <div className="auth-footer">
          <a
            className="auth-link"
            onClick={() => !isAnyLoading && setShowApiKeyForm(!showApiKeyForm)}
            style={{ cursor: isAnyLoading ? 'not-allowed' : 'pointer' }}
          >
            {t('auth.useOwnKey')}
          </a>
        </div>

        {/* Inline API Key Form */}
        {showApiKeyForm && (
          <div className="api-key-form" style={{ marginTop: '16px' }}>
            <div className="form-group">
              <label htmlFor="apiKey">{t('auth.apiKeyLabel')}</label>
              <input
                id="apiKey"
                type="password"
                className="form-input"
                placeholder={t('auth.apiKeyPlaceholder')}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={isAnyLoading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="baseUrl">{t('auth.baseUrlLabel')}</label>
              <input
                id="baseUrl"
                type="text"
                className="form-input"
                placeholder={t('auth.baseUrlPlaceholder')}
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                disabled={isAnyLoading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model">{t('auth.modelLabel')}</label>
              <input
                id="model"
                type="text"
                className="form-input"
                placeholder={t('auth.modelPlaceholder')}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={isAnyLoading}
              />
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-block"
              disabled={isAnyLoading || !apiKey.trim()}
              onClick={handleLocalModeStart}
            >
              {localLoading ? (
                <>
                  <div className="btn-spinner"></div>
                  <span>{t('common.loading')}</span>
                </>
              ) : (
                <span>{t('auth.startLocalMode')}</span>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default LoginPage;
