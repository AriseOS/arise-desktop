import { useState, useEffect } from 'react';
import { auth } from '../utils/auth';
import { api } from '../utils/api';

/**
 * Settings Page Component
 * Displays user account info, quota status, and logout option
 */
function SettingsPage({ navigate, showStatus }) {
  const [session, setSession] = useState(null);
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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
      showStatus('✅ Quota refreshed', 'success');
    } catch (error) {
      console.error('[SettingsPage] Failed to refresh quota:', error);
      showStatus(`Failed to refresh: ${error.message}`, 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const handleLogout = async () => {
    const confirmed = window.confirm('Are you sure you want to logout?');
    if (!confirmed) return;

    try {
      await auth.clearSession();
      showStatus('✅ Logged out successfully', 'success');
      navigate('login');
    } catch (error) {
      console.error('[SettingsPage] Logout error:', error);
      showStatus(`Failed to logout: ${error.message}`, 'error');
    }
  };

  if (loading) {
    return (
      <div className="page settings-page">
        <div className="loading-container">
          <div className="loading-spinner"></div>
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
            ← Back
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
          <button className="btn btn-danger" onClick={handleLogout}>
            Logout
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
              {refreshing ? '⟳ Refreshing...' : '⟳ Refresh'}
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
                    ⚠️ You have reached your monthly quota limit!
                  </div>
                )}
                {quotaPercentage >= 80 && quotaPercentage < 100 && (
                  <div className="alert alert-warning">
                    ⚠️ You are approaching your monthly quota limit
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

      <style jsx>{`
        .settings-page {
          padding: 20px;
          background-color: #f7fafc;
          min-height: 100vh;
        }

        .settings-container {
          max-width: 800px;
          margin: 0 auto;
        }

        .settings-header {
          display: flex;
          align-items: center;
          gap: 20px;
          margin-bottom: 30px;
        }

        .back-button {
          padding: 8px 16px;
          background: white;
          border: 2px solid #e2e8f0;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 600;
          color: #4a5568;
          transition: all 0.2s;
        }

        .back-button:hover {
          background-color: #f7fafc;
          border-color: #cbd5e0;
        }

        .settings-title {
          font-size: 32px;
          font-weight: 700;
          color: #2d3748;
          margin: 0;
        }

        .settings-section {
          margin-bottom: 30px;
        }

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 20px;
          font-weight: 600;
          color: #2d3748;
          margin: 0 0 16px 0;
        }

        .info-card {
          background: white;
          border-radius: 12px;
          padding: 24px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
          margin-bottom: 16px;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          padding: 12px 0;
          border-bottom: 1px solid #e2e8f0;
        }

        .info-row:last-child {
          border-bottom: none;
        }

        .info-label {
          font-weight: 600;
          color: #4a5568;
        }

        .info-value {
          color: #2d3748;
        }

        .api-key {
          font-family: monospace;
          font-size: 13px;
          background-color: #f7fafc;
          padding: 4px 8px;
          border-radius: 4px;
        }

        .quota-section {
          margin-bottom: 24px;
        }

        .quota-section:last-child {
          margin-bottom: 0;
        }

        .quota-title {
          font-size: 16px;
          font-weight: 600;
          color: #2d3748;
          margin: 0 0 12px 0;
        }

        .quota-stats {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          margin-bottom: 16px;
        }

        .stat-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .stat-label {
          font-size: 12px;
          color: #718096;
          font-weight: 600;
          text-transform: uppercase;
        }

        .stat-value {
          font-size: 24px;
          font-weight: 700;
          color: #2d3748;
        }

        .progress-container {
          width: 100%;
          height: 12px;
          background-color: #e2e8f0;
          border-radius: 6px;
          overflow: hidden;
          margin-bottom: 8px;
        }

        .progress-bar {
          height: 100%;
          transition: width 0.3s ease;
          border-radius: 6px;
        }

        .progress-success {
          background: linear-gradient(90deg, #48bb78 0%, #38a169 100%);
        }

        .progress-warning {
          background: linear-gradient(90deg, #ed8936 0%, #dd6b20 100%);
        }

        .progress-danger {
          background: linear-gradient(90deg, #f56565 0%, #e53e3e 100%);
        }

        .progress-text {
          font-size: 14px;
          color: #718096;
          text-align: center;
        }

        .alert {
          padding: 12px 16px;
          border-radius: 8px;
          margin-top: 16px;
          font-size: 14px;
          font-weight: 600;
        }

        .alert-warning {
          background-color: #fef5e7;
          color: #dd6b20;
          border: 1px solid #fbd38d;
        }

        .alert-danger {
          background-color: #fff5f5;
          color: #e53e3e;
          border: 1px solid #fc8181;
        }

        .btn {
          padding: 10px 20px;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 600;
          transition: all 0.2s;
        }

        .btn-danger {
          background-color: #f56565;
          color: white;
        }

        .btn-danger:hover {
          background-color: #e53e3e;
        }

        .btn-secondary {
          background-color: white;
          color: #4a5568;
          border: 2px solid #e2e8f0;
        }

        .btn-secondary:hover:not(:disabled) {
          background-color: #f7fafc;
          border-color: #cbd5e0;
        }

        .btn-sm {
          padding: 6px 12px;
          font-size: 13px;
        }

        .btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .loading-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 400px;
        }

        .loading-spinner {
          width: 40px;
          height: 40px;
          border: 4px solid #e2e8f0;
          border-top-color: #667eea;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        .no-data {
          text-align: center;
          color: #a0aec0;
          padding: 40px;
        }
      `}</style>
    </div>
  );
}

export default SettingsPage;
