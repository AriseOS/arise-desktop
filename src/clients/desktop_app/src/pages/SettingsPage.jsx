import { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import { auth } from '../utils/auth';
import { api } from '../utils/api';
import Icon from '../components/Icons';
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
