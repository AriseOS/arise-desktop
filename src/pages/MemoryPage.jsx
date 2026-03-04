import { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import { api } from '../utils/api';
import Icon from '../components/Icons';
import '../styles/MemoryPage.css';

/**
 * Memory Test Page
 * Displays memory statistics, query interface, and search results
 * In local mode, shows a prompt to login for memory features
 */
function MemoryPage({ session, showStatus, isLocalMode, onNavigateToLogin }) {
  const { t } = useTranslation();
  const userId = session?.username;

  // Stats state
  const [stats, setStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);

  // Query state
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [queryResult, setQueryResult] = useState(null);

  // Clear memory state
  const [clearing, setClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Load stats on mount
  useEffect(() => {
    if (userId) {
      loadStats();
    }
  }, [userId]);

  const loadStats = async () => {
    setLoadingStats(true);
    try {
      const data = await api.getMemoryStats();
      setStats(data.stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
      showStatus(`Failed to load stats: ${error.message}`, 'error');
    } finally {
      setLoadingStats(false);
    }
  };

  // Semantic search disabled — query(task) deprecated, use /memory/plan via daemon instead
  const handleSearch = async () => {
    showStatus('Task query is deprecated. Use the agent planning flow instead.', 'info');
  };

  const handleClearMemory = async () => {
    setShowClearConfirm(false);
    setClearing(true);

    try {
      const result = await api.clearMemory();
      showStatus(`Memory cleared: ${result.deleted_states} states, ${result.deleted_phrases} phrases`, 'success');
      await loadStats();
      setQueryResult(null);
    } catch (error) {
      console.error('Failed to clear memory:', error);
      showStatus(`Failed to clear: ${error.message}`, 'error');
    } finally {
      setClearing(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !searching) {
      handleSearch();
    }
  };

  const renderMemoryLevel = (level) => {
    const labels = { L1: 'Full Match', L2: 'Partial Match', L3: 'No Match' };
    const colorClass = level === 'L1' ? 'high' : level === 'L2' ? 'medium' : 'low';
    return (
      <span className={`score-badge ${colorClass}`}>
        {level} — {labels[level] || level}
      </span>
    );
  };

  const renderQueryResult = () => {
    if (!queryResult) return null;

    const states = queryResult.states || [];
    const actions = queryResult.actions || [];
    const phrase = queryResult.cognitive_phrase;
    const level = queryResult.metadata?.memory_level || 'L3';

    return (
      <div className="results-section">
        <h3>
          Query Result
          {' '}{renderMemoryLevel(level)}
        </h3>

        {/* CognitivePhrase */}
        {phrase && (
          <div className="result-card path-card">
            <div className="result-header">
              <span className="result-type">Workflow: {phrase.label}</span>
            </div>
            {phrase.description && (
              <div className="path-description">{phrase.description}</div>
            )}
          </div>
        )}

        {/* States as step cards */}
        {states.length > 0 && (
          <div className="results-list">
            {states.map((state, idx) => {
              const action = actions.find(a => a.source === state.id);
              return (
                <div key={idx} className="result-card path-card">
                  <div className="path-step">
                    <div className="step-state">
                      <div className="step-state-header">
                        <Icon icon="globe" />
                        <span className="state-title">{state.page_title || 'Untitled'}</span>
                        {state.domain && <span className="state-domain">{state.domain}</span>}
                      </div>
                      {state.page_url && (
                        <div className="state-url">{state.page_url}</div>
                      )}
                      {state.description && (
                        <div className="intent-description">{state.description}</div>
                      )}
                    </div>
                    {action && (
                      <div className="step-action">
                        <Icon icon="arrow-right" />
                        <span className="action-description">{action.description || action.type || 'Navigate'}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {states.length === 0 && !phrase && (
          <div className="stats-empty">No matching memory found</div>
        )}
      </div>
    );
  };

  // Local mode — show login prompt
  if (isLocalMode) {
    return (
      <div className="memory-page">
        <div className="memory-content">
          <div className="memory-header">
            <h1>
              <Icon icon="database" />
              Memory Explorer
            </h1>
          </div>
          <div className="card" style={{
            padding: '40px',
            textAlign: 'center',
            maxWidth: '480px',
            margin: '60px auto'
          }}>
            <Icon icon="lock" size={48} style={{ color: 'var(--text-tertiary)', marginBottom: '16px' }} />
            <h2 style={{ marginBottom: '8px' }}>{t('memory.loginRequired')}</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
              {t('memory.loginRequiredDesc')}
            </p>
            <button
              className="btn btn-primary"
              onClick={onNavigateToLogin}
            >
              <Icon icon="logIn" size={18} />
              <span>{t('memory.loginBtn')}</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="memory-page">
      <div className="memory-content">
        {/* Header */}
        <div className="memory-header">
          <h1>
            <Icon icon="database" />
            Memory Explorer
          </h1>
          <p className="subtitle">
            Search and explore your workflow memory
          </p>
        </div>

        {/* Stats Section */}
        <div className="stats-section">
          <div className="section-header">
            <h2>Memory Statistics</h2>
            <button
              className="btn-refresh"
              onClick={loadStats}
              disabled={loadingStats}
            >
              <Icon icon={loadingStats ? 'loader' : 'refresh'} />
              Refresh
            </button>
          </div>

          {loadingStats ? (
            <div className="stats-loading">Loading statistics...</div>
          ) : stats ? (
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{stats.total_states}</div>
                <div className="stat-label">States</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.total_intent_sequences}</div>
                <div className="stat-label">Intent Sequences</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.total_page_instances}</div>
                <div className="stat-label">Page Instances</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.total_actions}</div>
                <div className="stat-label">Actions</div>
              </div>
              <div className="stat-card wide">
                <div className="stat-value domains">
                  {stats.domains?.length > 0 ? stats.domains.join(', ') : 'None'}
                </div>
                <div className="stat-label">Domains</div>
              </div>
            </div>
          ) : (
            <div className="stats-empty">No statistics available</div>
          )}
        </div>

        {/* Query Section */}
        <div className="query-section">
          <h2>Semantic Search</h2>
          <p className="section-description">
            Describe what you want to do. The system will find the relevant operation paths.
          </p>

          <div className="query-controls">
            <div className="search-input-row">
              <input
                type="text"
                className="search-input"
                placeholder="e.g., '通过榜单查看产品团队信息'"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={searching}
              />
              <button
                className="btn-search"
                onClick={handleSearch}
                disabled={searching || !query.trim()}
              >
                <Icon icon={searching ? 'loader' : 'search'} />
                {searching ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>

          {/* Results */}
          {renderQueryResult()}
        </div>

        {/* Clear Memory Section */}
        <div className="danger-section">
          <h2>Danger Zone</h2>
          <div className="danger-content">
            <p>Clear all memory data. This action cannot be undone.</p>
            <button
              className="btn-danger"
              onClick={() => setShowClearConfirm(true)}
              disabled={clearing || (stats?.total_states === 0)}
            >
              <Icon icon={clearing ? 'loader' : 'trash'} />
              {clearing ? 'Clearing...' : 'Clear Memory'}
            </button>
          </div>
        </div>

        {/* Clear Confirmation Dialog */}
        {showClearConfirm && (
          <div className="confirm-overlay">
            <div className="confirm-dialog">
              <h3>Clear Memory?</h3>
              <p>
                This will delete all {stats?.total_states || 0} states and
                {' '}{stats?.total_actions || 0} actions from your memory.
                This action cannot be undone.
              </p>
              <div className="confirm-buttons">
                <button
                  className="btn-cancel"
                  onClick={() => setShowClearConfirm(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn-confirm-danger"
                  onClick={handleClearMemory}
                >
                  Yes, Clear Memory
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MemoryPage;
