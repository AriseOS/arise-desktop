import { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import { useStore } from 'zustand';
import { auth } from '../utils/auth';
import { api } from '../utils/api';
import Icon from '../components/Icons';
import IntegrationList from '../components/IntegrationList';
import settingsStore from '../store/settingsStore';
import '../styles/SettingsPage.css';

/**
 * Settings Page Component
 * Displays user account info, quota status, language selector, and logout option
 */
function SettingsPage({ navigate, showStatus, onLogout, language, onLanguageChange }) {
  const { t } = useTranslation();
  const [session, setSession] = useState(null);
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  // Theme/appearance settings from store
  const appearance = useStore(settingsStore, (state) => state.appearance);
  const setAppearance = useStore(settingsStore, (state) => state.setAppearance);
  const autoConfirmDelay = useStore(settingsStore, (state) => state.autoConfirmDelay);
  const setAutoConfirmDelay = useStore(settingsStore, (state) => state.setAutoConfirmDelay);
  const showTokenUsage = useStore(settingsStore, (state) => state.showTokenUsage);
  const setShowTokenUsage = useStore(settingsStore, (state) => state.setShowTokenUsage);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      // Load session data
      const sessionData = await auth.getSession();
      setSession(sessionData);

      // Load quota status
      try {
        const quotaData = await api.getQuotaStatus();
        setQuota(quotaData);
      } catch (quotaError) {
        console.error('[SettingsPage] Failed to load quota:', quotaError);
        // Don't fail the whole page if quota fails
      }
    } catch (error) {
      console.error('[SettingsPage] Failed to load data:', error);
      showStatus(`${t('settings.loadFailed')}: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshQuota = async () => {
    setRefreshing(true);
    try {
      const quotaData = await api.getQuotaStatus();
      setQuota(quotaData);
      showStatus(t('settings.quotaRefreshed'), 'success');
    } catch (error) {
      console.error('[SettingsPage] Failed to refresh quota:', error);
      showStatus(`${t('settings.refreshFailed')}: ${error.message}`, 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const handleLogoutClick = () => {
    setShowLogoutConfirm(true);
  };

  const handleLogoutConfirm = async () => {
    setShowLogoutConfirm(false);

    try {
      await auth.clearSession();
      showStatus(t('settings.logoutSuccess'), 'success');

      // Call parent logout handler to clear App state
      if (onLogout) {
        await onLogout();
      } else {
        // Fallback if onLogout not provided
        navigate('login');
      }
    } catch (error) {
      console.error('[SettingsPage] Logout error:', error);
      showStatus(`${t('settings.logoutFailed')}: ${error.message}`, 'error');
    }
  };

  const handleLogoutCancel = () => {
    setShowLogoutConfirm(false);
  };

  const handleLanguageChange = (lang) => {
    if (onLanguageChange) {
      onLanguageChange(lang);
    }
  };

  if (loading) {
    return (
      <div className="page settings-page">
        <div className="loading-container">
          <div className="btn-spinner"></div>
          <p>{t('settings.loading')}</p>
        </div>
      </div>
    );
  }

  const quotaInfo = quota?.quota;
  const workflowQuota = quotaInfo?.workflow_executions;
  const trialInfo = quotaInfo?.trial_info;
  const tokenUsage = quota?.token_usage?.current_month;

  // Calculate quota percentage and status
  const quotaPercentage = workflowQuota?.percentage || 0;
  const quotaStatus = quotaPercentage >= 100 ? 'danger' : quotaPercentage >= 80 ? 'warning' : 'success';

  return (
    <div className="page settings-page">
      <div className="settings-container">
        {/* Header */}
        <div className="settings-header">
          <button className="back-button" onClick={() => navigate('main')}>
            <Icon icon="arrowLeft" size={16} /> {t('settings.back')}
          </button>
          <h1 className="settings-title">{t('settings.title')}</h1>
        </div>

        {/* Account Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.account')}</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">{t('settings.username')}:</span>
              <span className="info-value">{session?.username || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{t('settings.email')}:</span>
              <span className="info-value">{session?.email || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{t('settings.apiKey')}:</span>
              <span className="info-value api-key" style={{ wordBreak: 'break-all', fontFamily: 'monospace', fontSize: '12px' }}>
                {session?.apiKey || 'N/A'}
              </span>
            </div>
            {session?.loginTimestamp && (
              <div className="info-row">
                <span className="info-label">{t('settings.lastLogin')}:</span>
                <span className="info-value">
                  {new Date(session.loginTimestamp).toLocaleString()}
                </span>
              </div>
            )}
          </div>
          <button className="btn btn-danger" onClick={handleLogoutClick}>
            <Icon icon="logOut" size={16} /> {t('settings.logout')}
          </button>
        </section>

        {/* Language Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.language')}</h2>
          <div className="info-card">
            <p style={{ marginBottom: '12px' }}>{t('settings.languageDesc')}</p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className={`btn ${language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => handleLanguageChange('en')}
              >
                English
              </button>
              <button
                type="button"
                className={`btn ${language === 'zh' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => handleLanguageChange('zh')}
              >
                简体中文
              </button>
            </div>
          </div>
        </section>

        {/* Appearance Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.appearance') || 'Appearance'}</h2>
          <div className="info-card">
            <p style={{ marginBottom: '12px' }}>{t('settings.appearanceDesc') || 'Choose your preferred theme'}</p>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className={`btn ${appearance === 'light' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setAppearance('light')}
              >
                <Icon name="sun" size={16} />
                {t('settings.themeLight') || 'Light'}
              </button>
              <button
                type="button"
                className={`btn ${appearance === 'dark' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setAppearance('dark')}
              >
                <Icon name="moon" size={16} />
                {t('settings.themeDark') || 'Dark'}
              </button>
              <button
                type="button"
                className={`btn ${appearance === 'system' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setAppearance('system')}
              >
                <Icon name="monitor" size={16} />
                {t('settings.themeSystem') || 'System'}
              </button>
              <button
                type="button"
                className={`btn ${appearance === 'transparent' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setAppearance('transparent')}
              >
                <Icon name="layers" size={16} />
                {t('settings.themeTransparent') || 'Transparent'}
              </button>
            </div>
          </div>
        </section>

        {/* Agent Settings Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.agentSettings') || 'Agent Settings'}</h2>
          <div className="info-card">
            {/* Auto-confirm delay */}
            <div className="info-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
              <span className="info-label">{t('settings.autoConfirmDelay') || 'Auto-confirm Delay'}</span>
              <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)' }}>
                {t('settings.autoConfirmDelayDesc') || 'Automatically confirm task decomposition after this delay (0 to disable)'}
              </p>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                <input
                  type="number"
                  min="0"
                  max="300"
                  value={autoConfirmDelay}
                  onChange={(e) => setAutoConfirmDelay(Math.max(0, Math.min(300, parseInt(e.target.value) || 0)))}
                  style={{
                    width: '80px',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                  }}
                />
                <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                  {t('settings.seconds') || 'seconds'}
                </span>
              </div>
            </div>

            {/* Show token usage toggle */}
            <div className="info-row" style={{ alignItems: 'center' }}>
              <div>
                <span className="info-label">{t('settings.showTokenUsage') || 'Show Token Usage'}</span>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: 'var(--text-tertiary)' }}>
                  {t('settings.showTokenUsageDesc') || 'Display token consumption during task execution'}
                </p>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={showTokenUsage}
                  onChange={(e) => setShowTokenUsage(e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
          </div>
        </section>

        {/* Integrations Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.integrations') || 'Integrations'}</h2>
          <div className="info-card integrations-card">
            <p style={{ marginBottom: '16px', color: 'var(--text-secondary)' }}>
              {t('settings.integrationsDesc') || 'Connect cloud services to enhance automation capabilities'}
            </p>
            <IntegrationList showTitle={false} />
          </div>
        </section>

        {/* Data & Storage Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.dataStorage') || 'Data & Storage'}</h2>
          <div className="info-card">
            <div
              className="info-row clickable-row"
              onClick={() => navigate('recordings-library')}
              style={{ cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Icon name="video" size={20} />
                <div>
                  <span className="info-label" style={{ display: 'block', marginBottom: '4px' }}>
                    {t('settings.recordingsLibrary') || 'Recordings Library'}
                  </span>
                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)' }}>
                    {t('settings.recordingsLibraryDesc') || 'View and manage your recorded sessions'}
                  </p>
                </div>
              </div>
              <Icon name="chevronRight" size={20} style={{ color: 'var(--text-tertiary)' }} />
            </div>
          </div>
        </section>

        {/* Developer Tools Section */}
        <section className="settings-section">
          <h2 className="section-title">{t('settings.developerTools') || 'Developer Tools'}</h2>
          <div className="info-card">
            <div
              className="info-row clickable-row"
              onClick={() => navigate('agent')}
              style={{ cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Icon name="terminal" size={20} />
                <div>
                  <span className="info-label" style={{ display: 'block', marginBottom: '4px' }}>
                    {t('settings.agentDebugView') || 'Agent Debug View'}
                  </span>
                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)' }}>
                    {t('settings.agentDebugViewDesc') || 'View detailed agent execution logs, browser states, and debug info'}
                  </p>
                </div>
              </div>
              <Icon name="chevronRight" size={20} style={{ color: 'var(--text-tertiary)' }} />
            </div>
          </div>
        </section>

        {/* Quota Section */}
        <section className="settings-section">
          <div className="section-header">
            <h2 className="section-title">{t('settings.quotaStatus')}</h2>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleRefreshQuota}
              disabled={refreshing}
            >
              <Icon icon="refreshCw" size={14} className={refreshing ? 'spinning' : ''} />
              {refreshing ? t('settings.refreshing') : t('settings.refresh')}
            </button>
          </div>

          {quota && workflowQuota ? (
            <div className="info-card">
              {/* Workflow Executions */}
              <div className="quota-section">
                <h3 className="quota-title">{t('settings.workflowExecutions')}</h3>
                <div className="quota-stats">
                  <div className="stat-item">
                    <span className="stat-label">{t('settings.used')}:</span>
                    <span className="stat-value">{workflowQuota.used}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">{t('settings.limit')}:</span>
                    <span className="stat-value">{workflowQuota.limit}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">{t('settings.remaining')}:</span>
                    <span className="stat-value">{workflowQuota.remaining}</span>
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="progress-container">
                  <div
                    className={`progress-bar progress-${quotaStatus}`}
                    style={{ width: `${Math.min(quotaPercentage, 100)}%` }}
                  ></div>
                </div>
                <div className="progress-text">
                  {t('settings.usedPercentage', { percent: quotaPercentage.toFixed(1) })}
                </div>

                {/* Warnings */}
                {quotaPercentage >= 100 && (
                  <div className="alert alert-danger">
                    <Icon icon="alertTriangle" size={16} /> {t('settings.quotaLimitReached')}
                  </div>
                )}
                {quotaPercentage >= 80 && quotaPercentage < 100 && (
                  <div className="alert alert-warning">
                    <Icon icon="alertTriangle" size={16} /> {t('settings.quotaLimitApproaching')}
                  </div>
                )}
              </div>

              {/* Trial Info */}
              {trialInfo && trialInfo.is_trial && (
                <div className="quota-section">
                  <h3 className="quota-title">{t('settings.trialPeriod')}</h3>
                  <div className="info-row">
                    <span className="info-label">{t('settings.daysRemaining')}:</span>
                    <span className="info-value">{trialInfo.days_remaining} {t('settings.days')}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">{t('settings.startDate')}:</span>
                    <span className="info-value">
                      {new Date(trialInfo.start_date).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">{t('settings.endDate')}:</span>
                    <span className="info-value">
                      {new Date(trialInfo.end_date).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              )}

              {/* Token Usage */}
              {tokenUsage && (
                <div className="quota-section">
                  <h3 className="quota-title">{t('settings.tokenUsage')}</h3>
                  <div className="quota-stats">
                    <div className="stat-item">
                      <span className="stat-label">{t('settings.inputTokens')}:</span>
                      <span className="stat-value">{tokenUsage.input_tokens.toLocaleString()}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">{t('settings.outputTokens')}:</span>
                      <span className="stat-value">{tokenUsage.output_tokens.toLocaleString()}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">{t('settings.totalTokens')}:</span>
                      <span className="stat-value">{tokenUsage.total_tokens.toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="info-card">
              <p className="no-data">{t('settings.noQuotaData')}</p>
            </div>
          )}
        </section>
      </div>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="modal-overlay" onClick={handleLogoutCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('settings.confirmLogout')}</h3>
            </div>
            <div className="modal-body">
              <p>{t('settings.logoutMessage')}</p>
              <p className="warning-text">{t('settings.logoutWarning')}</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleLogoutCancel}>
                {t('common.cancel')}
              </button>
              <button className="btn-confirm-delete" onClick={handleLogoutConfirm}>
                {t('settings.logout')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
