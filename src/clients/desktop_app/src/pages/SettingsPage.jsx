import { useState, useEffect } from 'react';
import { auth } from '../utils/auth';
import { api } from '../utils/api';
import Icon from '../components/Icons';
import '../styles/SettingsPage.css';

/**
 * Settings Page Component
 * Displays user account info, quota status, and logout option
 */
function SettingsPage({ navigate, showStatus, onLogout }) {
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
      showStatus(`Failed to load settings: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshQuota = async () => {
    setRefreshing(true);
    try {
      const quotaData = await api.getQuotaStatus();
      setQuota(quotaData);
      showStatus('Quota refreshed', 'success');
    } catch (error) {
      console.error('[SettingsPage] Failed to refresh quota:', error);
      showStatus(`Failed to refresh: ${error.message}`, 'error');
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
      showStatus('Logged out successfully', 'success');

      // Call parent logout handler to clear App state
      if (onLogout) {
        await onLogout();
      } else {
        // Fallback if onLogout not provided
        navigate('login');
      }
    } catch (error) {
      console.error('[SettingsPage] Logout error:', error);
      showStatus(`Failed to logout: ${error.message}`, 'error');
    }
  };

  const handleLogoutCancel = () => {
    setShowLogoutConfirm(false);
  };

  if (loading) {
    return (
      <div className="page settings-page">
        <div className="loading-container">
          <div className="btn-spinner"></div>
          <p>Loading settings...</p>
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
            <Icon icon="arrowLeft" size={16} /> Back
          </button>
          <h1 className="settings-title">Settings</h1>
        </div>

        {/* Account Section */}
        <section className="settings-section">
          <h2 className="section-title">Account</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">Username:</span>
              <span className="info-value">{session?.username || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Email:</span>
              <span className="info-value">{session?.email || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">API Key:</span>
              <span className="info-value api-key">
                {session?.apiKey ? `${session.apiKey.slice(0, 15)}...` : 'N/A'}
              </span>
            </div>
            {session?.loginTimestamp && (
              <div className="info-row">
                <span className="info-label">Last Login:</span>
                <span className="info-value">
                  {new Date(session.loginTimestamp).toLocaleString()}
                </span>
              </div>
            )}
          </div>
          <button className="btn btn-danger" onClick={handleLogoutClick}>
            <Icon icon="logOut" size={16} /> Logout
          </button>
        </section>

        {/* Quota Section */}
        <section className="settings-section">
          <div className="section-header">
            <h2 className="section-title">Quota Status</h2>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleRefreshQuota}
              disabled={refreshing}
            >
              <Icon icon="refreshCw" size={14} className={refreshing ? 'spinning' : ''} />
              {refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          {quota && workflowQuota ? (
            <div className="info-card">
              {/* Workflow Executions */}
              <div className="quota-section">
                <h3 className="quota-title">Workflow Executions</h3>
                <div className="quota-stats">
                  <div className="stat-item">
                    <span className="stat-label">Used:</span>
                    <span className="stat-value">{workflowQuota.used}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Limit:</span>
                    <span className="stat-value">{workflowQuota.limit}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Remaining:</span>
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
                  {quotaPercentage.toFixed(1)}% used
                </div>

                {/* Warnings */}
                {quotaPercentage >= 100 && (
                  <div className="alert alert-danger">
                    <Icon icon="alertTriangle" size={16} /> You have reached your monthly quota limit!
                  </div>
                )}
                {quotaPercentage >= 80 && quotaPercentage < 100 && (
                  <div className="alert alert-warning">
                    <Icon icon="alertTriangle" size={16} /> You are approaching your monthly quota limit
                  </div>
                )}
              </div>

              {/* Trial Info */}
              {trialInfo && trialInfo.is_trial && (
                <div className="quota-section">
                  <h3 className="quota-title">Trial Period</h3>
                  <div className="info-row">
                    <span className="info-label">Days Remaining:</span>
                    <span className="info-value">{trialInfo.days_remaining} days</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Start Date:</span>
                    <span className="info-value">
                      {new Date(trialInfo.start_date).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">End Date:</span>
                    <span className="info-value">
                      {new Date(trialInfo.end_date).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              )}

              {/* Token Usage */}
              {tokenUsage && (
                <div className="quota-section">
                  <h3 className="quota-title">Token Usage (Current Month)</h3>
                  <div className="quota-stats">
                    <div className="stat-item">
                      <span className="stat-label">Input Tokens:</span>
                      <span className="stat-value">{tokenUsage.input_tokens.toLocaleString()}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Output Tokens:</span>
                      <span className="stat-value">{tokenUsage.output_tokens.toLocaleString()}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Total Tokens:</span>
                      <span className="stat-value">{tokenUsage.total_tokens.toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="info-card">
              <p className="no-data">Unable to load quota information</p>
            </div>
          )}
        </section>
      </div>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="modal-overlay" onClick={handleLogoutCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Confirm Logout</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to logout?</p>
              <p className="warning-text">You will need to login again to use the app.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleLogoutCancel}>
                Cancel
              </button>
              <button className="btn-confirm-delete" onClick={handleLogoutConfirm}>
                Logout
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
