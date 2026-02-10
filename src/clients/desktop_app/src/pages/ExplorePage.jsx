import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/CognitivePhrasesPage.css';

function ExplorePage({ session, onNavigate, showStatus }) {
  const [phrases, setPhrases] = useState([]);
  const [filteredPhrases, setFilteredPhrases] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  // Fetch public phrases from API
  useEffect(() => {
    const fetchPhrases = async () => {
      try {
        const data = await api.listPublicPhrases(100);
        setPhrases(data.phrases || []);
        setFilteredPhrases(data.phrases || []);
      } catch (error) {
        console.error('Error fetching public phrases:', error);
        showStatus(`Failed to load public library: ${error.message}`, 'error');
        setPhrases([]);
        setFilteredPhrases([]);
      } finally {
        setLoading(false);
      }
    };

    fetchPhrases();
  }, []);

  // Search filter
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredPhrases(phrases);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = phrases.filter(phrase => {
      const labelMatch = phrase.label?.toLowerCase().includes(query);
      const descMatch = phrase.description?.toLowerCase().includes(query);
      return labelMatch || descMatch;
    });

    setFilteredPhrases(filtered);
  }, [searchQuery, phrases]);

  const truncateText = (text, maxLength) => {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return 'Unknown';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="cognitive-phrases-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="cognitive-phrases-page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title"><Icon name="compass" /> Explore</h1>
        <div className="header-spacer"></div>
      </div>

      {/* Search Bar */}
      <div className="search-section">
        <div className="search-input-wrapper">
          <span className="search-icon">
            <Icon name="search" />
          </span>
          <input
            type="text"
            className="search-input"
            placeholder="Search public memories..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              <Icon name="x" />
            </button>
          )}
        </div>
      </div>

      {/* Results Count */}
      <div className="results-info">
        <p className="results-count">
          {filteredPhrases.length === 0
            ? 'No shared memories yet'
            : `${filteredPhrases.length} shared ${filteredPhrases.length === 1 ? 'memory' : 'memories'}`}
        </p>
      </div>

      {/* Phrases List */}
      <div className="phrases-list">
        {filteredPhrases.length === 0 ? (
          <div className="empty-state">
            {phrases.length === 0 ? (
              <>
                <div className="empty-icon"><Icon name="compass" /></div>
                <h3>No shared memories yet</h3>
                <p>Be the first to share! Go to Memories and share a workflow to the public library.</p>
                <button className="btn-start-recording" onClick={() => onNavigate('memories')}>
                  <span className="button-icon"><Icon name="brain" /></span>
                  <span>Go to Memories</span>
                </button>
              </>
            ) : (
              <>
                <div className="empty-icon"><Icon name="search" /></div>
                <h3>No results found</h3>
                <p>Try adjusting your search query</p>
                <button className="btn-clear-search" onClick={() => setSearchQuery('')}>
                  Clear Search
                </button>
              </>
            )}
          </div>
        ) : (
          filteredPhrases.map((phrase) => (
            <div key={phrase.id} className="phrase-card" onClick={() => onNavigate('memory-detail', { phraseId: phrase.id, source: 'public' })}>
              <div className="phrase-header">
                <div className="phrase-icon"><Icon name="route" /></div>
                <div className="phrase-info">
                  <h3 className="phrase-title">
                    {phrase.label || 'Unnamed Workflow'}
                  </h3>
                  <p className="phrase-description">
                    {truncateText(phrase.description, 120)}
                  </p>
                  <div className="phrase-meta">
                    {phrase.contributor_id && (
                      <span className="meta-item">
                        <Icon name="user" />
                        {phrase.contributor_id}
                      </span>
                    )}
                    {phrase.contributed_at && (
                      <span className="meta-item">
                        <Icon name="clock" />
                        {formatDate(phrase.contributed_at)}
                      </span>
                    )}
                    <span className="meta-item">
                      <Icon name="activity" />
                      {phrase.use_count || 0} uses
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ExplorePage;
