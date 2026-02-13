/**
 * IntegrationList Component
 *
 * Cloud service integrations management UI.
 * Based on Eigent's IntegrationList for Gmail, Drive, Calendar, Notion.
 *
 * Features:
 * - List of available integrations
 * - OAuth flow handling
 * - Token configuration for non-OAuth services
 * - Status indicators (installed/not installed)
 */
import React, { useState, useEffect } from 'react';
import Icon from './Icons';
import { api } from '../utils/api';

// Available integrations configuration
export const INTEGRATIONS = [
  {
    id: 'gmail',
    name: 'Gmail',
    icon: '📧',
    color: '#EA4335',
    description: 'Send and receive emails',
    authType: 'oauth',
    provider: 'google',
    scopes: ['gmail.readonly', 'gmail.send', 'gmail.compose'],
    envVars: ['GMAIL_CREDENTIALS_PATH'],
    features: ['Send emails', 'Search inbox', 'Read messages', 'Manage labels'],
  },
  {
    id: 'google_drive',
    name: 'Google Drive',
    icon: '📁',
    color: '#4285F4',
    description: 'Access and manage files',
    authType: 'oauth',
    provider: 'google',
    scopes: ['drive.readonly', 'drive.file'],
    envVars: ['GDRIVE_CREDENTIALS_PATH'],
    features: ['List files', 'Read content', 'Create files', 'Upload/download'],
  },
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    icon: '📅',
    color: '#0F9D58',
    description: 'Manage calendar events',
    authType: 'oauth',
    provider: 'google',
    scopes: ['calendar', 'calendar.events'],
    envVars: ['GCAL_CREDENTIALS_PATH'],
    features: ['List events', 'Create events', 'Quick add', 'Free/busy info'],
  },
  {
    id: 'notion',
    name: 'Notion',
    icon: '📝',
    color: '#000000',
    description: 'Access Notion pages and databases',
    authType: 'token',
    envVars: ['NOTION_API_KEY'],
    configFields: [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'secret_xxx...' },
    ],
    features: ['Search pages', 'Read content', 'Create pages', 'Query databases'],
  },
];

/**
 * Integration List Component
 */
function IntegrationList({
  onIntegrationChange,
  showTitle = true,
  compact = false,
  className = '',
}) {
  const [installed, setInstalled] = useState([]);
  const [loading, setLoading] = useState(true);
  const [configuring, setConfiguring] = useState(null);
  const [installing, setInstalling] = useState(null);
  const [error, setError] = useState(null);

  // Load installed integrations on mount
  useEffect(() => {
    loadInstalledIntegrations();
  }, []);

  const loadInstalledIntegrations = async () => {
    try {
      setLoading(true);
      const response = await api.callAppBackend('/api/v1/integrations/list');
      setInstalled(response.installed || []);
    } catch (e) {
      console.error('Failed to load integrations:', e);
      // Don't show error for missing endpoint - just show all as uninstalled
      setInstalled([]);
    } finally {
      setLoading(false);
    }
  };

  const handleInstall = async (integration) => {
    setInstalling(integration.id);
    setError(null);

    try {
      if (integration.authType === 'oauth') {
        await startOAuthFlow(integration);
      } else if (integration.authType === 'token') {
        setConfiguring(integration);
        setInstalling(null);
      }
    } catch (e) {
      console.error('Install error:', e);
      setError(`Failed to install ${integration.name}: ${e.message}`);
      setInstalling(null);
    }
  };

  const startOAuthFlow = async (integration) => {
    // OAuth flow not yet implemented in Electron
    console.warn('OAuth flow not yet implemented for integration:', integration.id);
    setError('OAuth flow not yet available');
    setInstalling(null);
  };

  const handleSaveConfig = async (integrationId, config) => {
    try {
      await api.callAppBackend(`/api/v1/integrations/configure/${integrationId}`, {
        method: 'POST',
        body: JSON.stringify(config),
      });

      setInstalled(prev => [...prev, integrationId]);
      onIntegrationChange?.(integrationId, 'installed');
      setConfiguring(null);
    } catch (e) {
      console.error('Configure error:', e);
      setError(`Failed to configure: ${e.message}`);
    }
  };

  const handleUninstall = async (integrationId) => {
    try {
      await api.callAppBackend(`/api/v1/integrations/uninstall/${integrationId}`, {
        method: 'POST',
      });

      setInstalled(prev => prev.filter(id => id !== integrationId));
      onIntegrationChange?.(integrationId, 'uninstalled');
    } catch (e) {
      console.error('Uninstall error:', e);
      setError(`Failed to uninstall: ${e.message}`);
    }
  };

  if (loading) {
    return (
      <div className={`integration-list loading ${className}`}>
        <div className="loading-spinner" />
        <span>Loading integrations...</span>
      </div>
    );
  }

  return (
    <div className={`integration-list ${compact ? 'compact' : ''} ${className}`}>
      {showTitle && (
        <div className="list-header">
          <span className="header-icon">🔌</span>
          <h3 className="header-title">Cloud Integrations</h3>
          <span className="header-count">
            {installed.length}/{INTEGRATIONS.length} installed
          </span>
        </div>
      )}

      {error && (
        <div className="error-message">
          <Icon name="alert" size={16} />
          <span>{error}</span>
          <button onClick={() => setError(null)}>
            <Icon name="close" size={14} />
          </button>
        </div>
      )}

      <div className="integrations-grid">
        {INTEGRATIONS.map(integration => (
          <IntegrationCard
            key={integration.id}
            integration={integration}
            installed={installed.includes(integration.id)}
            installing={installing === integration.id}
            onInstall={() => handleInstall(integration)}
            onUninstall={() => handleUninstall(integration.id)}
            compact={compact}
          />
        ))}
      </div>

      {/* Configuration Dialog */}
      {configuring && (
        <ConfigurationDialog
          integration={configuring}
          onSave={(config) => handleSaveConfig(configuring.id, config)}
          onClose={() => setConfiguring(null)}
        />
      )}
    </div>
  );
}

/**
 * Single integration card
 */
function IntegrationCard({
  integration,
  installed,
  installing,
  onInstall,
  onUninstall,
  compact = false,
}) {
  const [expanded, setExpanded] = useState(false);

  if (compact) {
    return (
      <div className={`integration-card compact ${installed ? 'installed' : ''}`}>
        <span
          className="card-icon"
          style={{ backgroundColor: `${integration.color}20` }}
        >
          {integration.icon}
        </span>
        <span className="card-name">{integration.name}</span>
        <span className={`status-dot ${installed ? 'installed' : ''}`} />
      </div>
    );
  }

  return (
    <div className={`integration-card ${installed ? 'installed' : ''}`}>
      <div className="card-header">
        <span
          className="card-icon"
          style={{ backgroundColor: `${integration.color}20` }}
        >
          {integration.icon}
        </span>
        <div className="card-info">
          <h4 className="card-name">{integration.name}</h4>
          <p className="card-description">{integration.description}</p>
        </div>
        <div className="card-status">
          {installed ? (
            <span className="status-badge installed">
              <Icon name="check" size={12} />
              Installed
            </span>
          ) : (
            <span className="status-badge">Not installed</span>
          )}
        </div>
      </div>

      {/* Features (expandable) */}
      {integration.features && (
        <div className={`card-features ${expanded ? 'expanded' : ''}`}>
          <button
            className="features-toggle"
            onClick={() => setExpanded(!expanded)}
          >
            <span>Features</span>
            <Icon name={expanded ? 'chevronUp' : 'chevronDown'} size={14} />
          </button>
          {expanded && (
            <ul className="features-list">
              {integration.features.map((feature, idx) => (
                <li key={idx}>
                  <Icon name="check" size={12} />
                  {feature}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="card-actions">
        {installed ? (
          <button
            className="btn btn-secondary btn-sm"
            onClick={onUninstall}
          >
            Uninstall
          </button>
        ) : (
          <button
            className="btn btn-primary btn-sm"
            onClick={onInstall}
            disabled={installing}
          >
            {installing ? (
              <>
                <span className="spinner-sm" />
                Installing...
              </>
            ) : (
              <>
                <Icon name="plus" size={14} />
                Install
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Configuration dialog for token-based integrations
 */
function ConfigurationDialog({
  integration,
  onSave,
  onClose,
}) {
  const [config, setConfig] = useState({});
  const [error, setError] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();

    // Validate required fields
    const missingFields = (integration.configFields || [])
      .filter(field => field.required !== false && !config[field.key]);

    if (missingFields.length > 0) {
      setError(`Please fill in: ${missingFields.map(f => f.label).join(', ')}`);
      return;
    }

    onSave(config);
  };

  return (
    <div className="config-dialog-overlay" onClick={onClose}>
      <div className="config-dialog" onClick={e => e.stopPropagation()}>
        <div className="dialog-header">
          <span className="dialog-icon">{integration.icon}</span>
          <h3>Configure {integration.name}</h3>
          <button className="close-btn" onClick={onClose}>
            <Icon name="close" size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="dialog-body">
            {error && (
              <div className="error-message">
                <Icon name="alert" size={14} />
                {error}
              </div>
            )}

            {(integration.configFields || []).map(field => (
              <div key={field.key} className="form-group">
                <label>{field.label}</label>
                <input
                  type={field.type || 'text'}
                  value={config[field.key] || ''}
                  onChange={e => setConfig({ ...config, [field.key]: e.target.value })}
                  placeholder={field.placeholder}
                />
                {field.helpText && (
                  <span className="help-text">{field.helpText}</span>
                )}
              </div>
            ))}

            {integration.id === 'notion' && (
              <div className="help-section">
                <h4>How to get your Notion API Key:</h4>
                <ol>
                  <li>Go to <a href="https://www.notion.so/my-integrations" target="_blank" rel="noopener noreferrer">Notion Integrations</a></li>
                  <li>Click "New integration"</li>
                  <li>Give it a name and select your workspace</li>
                  <li>Copy the "Internal Integration Token"</li>
                  <li>Share your pages/databases with the integration</li>
                </ol>
              </div>
            )}
          </div>

          <div className="dialog-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Configuration
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Compact integration status bar
 */
export function IntegrationStatusBar({ className = '' }) {
  const [installed, setInstalled] = useState([]);

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const response = await api.callAppBackend('/api/v1/integrations/list');
        setInstalled(response.installed || []);
      } catch (e) {
        // Ignore errors
      }
    };
    loadStatus();
  }, []);

  const installedIntegrations = INTEGRATIONS.filter(i => installed.includes(i.id));

  if (installedIntegrations.length === 0) return null;

  return (
    <div className={`integration-status-bar ${className}`}>
      <span className="status-label">Connected:</span>
      {installedIntegrations.map(integration => (
        <span
          key={integration.id}
          className="status-item"
          title={integration.name}
        >
          {integration.icon}
        </span>
      ))}
    </div>
  );
}

export default IntegrationList;
