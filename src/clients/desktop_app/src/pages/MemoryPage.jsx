import { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import { api } from '../utils/api';
import Icon from '../components/Icons';
import '../styles/MemoryPage.css';

/**
 * Memory Test Page
 * Displays memory statistics, query interface, and search results
 */
function MemoryPage({ session, showStatus }) {
  const { t } = useTranslation();
  const userId = session?.username;

  // Stats state
  const [stats, setStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);

  // Query state
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [paths, setPaths] = useState([]);

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
      const data = await api.getMemoryStats(userId);
      setStats(data.stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
      showStatus(`Failed to load stats: ${error.message}`, 'error');
    } finally {
      setLoadingStats(false);
    }
  };

  const handleSearch = async () => {
    if (!query.trim()) {
      showStatus('Please enter a search query', 'warning');
      return;
    }

    setSearching(true);
    setPaths([]);

    try {
      const data = await api.queryMemory(userId, query, {
        topK: 5,
        minScore: 0.3
      });

      setPaths(data.paths || []);

      if (data.paths?.length === 0) {
        showStatus('No matching paths found', 'info');
      } else {
        const totalSteps = data.paths.reduce((sum, p) => sum + (p.steps?.length || 0), 0);
        showStatus(`Found ${data.paths.length} path(s) with ${totalSteps} steps`, 'success');
      }
    } catch (error) {
      console.error('Memory query failed:', error);
      showStatus(`Query failed: ${error.message}`, 'error');
    } finally {
      setSearching(false);
    }
  };

  const handleClearMemory = async () => {
    setShowClearConfirm(false);
    setClearing(true);

    try {
      const result = await api.clearMemory(userId);
      showStatus(`Memory cleared: ${result.deleted_states} states, ${result.deleted_actions} actions`, 'success');
      // Reload stats
      await loadStats();
      // Clear paths
      setPaths([]);
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

  const renderScore = (score) => {
    const percentage = Math.round(score * 100);
    const colorClass = score >= 0.8 ? 'high' : score >= 0.5 ? 'medium' : 'low';
    return (
      <span className={`score-badge ${colorClass}`}>
        {percentage}%
      </span>
    );
  };

  const renderStep = (step, stepIdx, isLast) => (
    <div key={stepIdx} className="path-step">
      {/* State */}
      {step.state && (
        <div className="step-state">
          <div className="step-state-header">
            <Icon icon="globe" />
            <span className="state-title">{step.state.page_title || 'Untitled'}</span>
            {step.state.domain && <span className="state-domain">{step.state.domain}</span>}
          </div>
          {step.state.page_url && (
            <div className="state-url">{step.state.page_url}</div>
          )}
        </div>
      )}

      {/* Intent Sequence */}
      {step.intent_sequence && (
        <div className="step-intents">
          {step.intent_sequence.description && (
            <div className="intent-description">{step.intent_sequence.description}</div>
          )}
          {step.intent_sequence.intents?.length > 0 && (
            <div className="intent-list">
              {step.intent_sequence.intents.slice(0, 5).map((intent, idx) => (
                <span key={idx} className="intent-tag">
                  <span className="intent-type">{intent.type}</span>
                  {intent.text && <span className="intent-text">{intent.text.substring(0, 30)}</span>}
                </span>
              ))}
              {step.intent_sequence.intents.length > 5 && (
                <span className="intent-more">+{step.intent_sequence.intents.length - 5} more</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Action arrow (if not last step) */}
      {!isLast && step.action && (
        <div className="step-action">
          <Icon icon="arrow-right" />
          <span className="action-description">{step.action.description || 'Navigate'}</span>
        </div>
      )}
    </div>
  );

  const renderPath = (path, pathIdx) => (
    <div key={pathIdx} className="result-card path-card">
      <div className="result-header">
        {renderScore(path.score)}
        <span className="result-type">Path ({path.steps?.length || 0} steps)</span>
      </div>
      {path.description && (
        <div className="path-description">{path.description}</div>
      )}
      <div className="path-steps">
        {path.steps?.map((step, stepIdx) =>
          renderStep(step, stepIdx, stepIdx === path.steps.length - 1)
        )}
      </div>
    </div>
  );

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
          {paths.length > 0 && (
            <div className="results-section">
              <h3>Operation Paths ({paths.length})</h3>
              <div className="results-list">
                {paths.map((path, idx) => renderPath(path, idx))}
              </div>
            </div>
          )}
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
