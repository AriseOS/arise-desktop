import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/ExplorePage.css';

function ExplorePage({ session, onNavigate, showStatus }) {
  const [phrases, setPhrases] = useState([]);
  const [filteredPhrases, setFilteredPhrases] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('popular');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPublicPhrases();
  }, [sortBy]);

  const fetchPublicPhrases = async () => {
    setLoading(true);
    try {
      const data = await api.listPublicCognitivePhrases(100, sortBy);
      setPhrases(data.phrases || []);
      setFilteredPhrases(data.phrases || []);
    } catch (error) {
      console.error('Error fetching public phrases:', error);
      showStatus(`Failed to load community memories: ${error.message}`, 'error');
      setPhrases([]);
      setFilteredPhrases([]);
    } finally {
      setLoading(false);
    }
  };

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
      const contributorMatch = phrase.contributor_id?.toLowerCase().includes(query);
      return labelMatch || descMatch || contributorMatch;
    });

    setFilteredPhrases(filtered);
  }, [searchQuery, phrases]);

  const truncateText = (text, maxLength) => {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return '';
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
      <div className="explore-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading community memories...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="explore-page">
      {/* Header */}
      <div className="explore-header">
        <div className="explore-header-top">
          <button className="btn-icon" onClick={() => onNavigate('main')} aria-label="Go Back">
            <Icon name="arrowLeft" />
          </button>
          <h1 className="explore-title">
            <Icon name="compass" /> Explore
          </h1>
          <div className="header-spacer"></div>
        </div>

        {/* Search */}
        <div className="explore-search-wrapper">
          <span className="search-icon"><Icon name="search" /></span>
          <input
            type="text"
            className="explore-search-input"
            placeholder="Search community memories..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              <Icon name="x" />
            </button>
          )}
        </div>

        {/* Sort tabs + count */}
        <div className="explore-toolbar">
          <div className="sort-tabs">
            <button
              className={`sort-tab ${sortBy === 'popular' ? 'active' : ''}`}
              onClick={() => setSortBy('popular')}
            >
              <Icon name="activity" size={14} />
              Popular
            </button>
            <button
              className={`sort-tab ${sortBy === 'recent' ? 'active' : ''}`}
              onClick={() => setSortBy('recent')}
            >
              <Icon name="clock" size={14} />
              Newest
            </button>
          </div>
          <span className="explore-count">
            {filteredPhrases.length} {filteredPhrases.length === 1 ? 'memory' : 'memories'}
          </span>
        </div>
      </div>

      {/* Grid */}
      <div className="explore-content">
        {filteredPhrases.length === 0 ? (
          <div className="explore-empty">
            {phrases.length === 0 ? (
              <>
                <div className="empty-icon"><Icon name="globe" /></div>
                <h3>No community memories yet</h3>
                <p>Be the first to publish a memory! Go to Memories, open a workflow, and click Publish.</p>
              </>
            ) : (
              <>
                <div className="empty-icon"><Icon name="search" /></div>
                <h3>No results found</h3>
                <p>Try a different search query</p>
                <button className="btn btn-secondary" onClick={() => setSearchQuery('')}>
                  Clear Search
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="explore-grid">
            {filteredPhrases.map((phrase) => (
              <div key={phrase.id} className="explore-card" onClick={() => onNavigate('memory-detail', { phraseId: phrase.id, isPublic: true })}>
                <div className="card-icon">
                  <Icon name="route" />
                </div>
                <h3 className="card-title">
                  {truncateText(phrase.label || 'Unnamed Workflow', 60)}
                </h3>
                <p className="card-description">
                  {truncateText(phrase.description, 100)}
                </p>
                <div className="card-stats">
                  <span className="card-stat" title="Times used">
                    <Icon name="activity" size={13} />
                    {phrase.use_count || 0}
                  </span>
                  <span className="card-stat" title="Steps">
                    <Icon name="route" size={13} />
                    {phrase.state_count || 0}
                  </span>
                  {phrase.contributed_at && (
                    <span className="card-stat" title="Published">
                      <Icon name="clock" size={13} />
                      {formatDate(phrase.contributed_at)}
                    </span>
                  )}
                </div>
                <div className="card-footer">
                  <span className="card-contributor" title={phrase.contributor_id}>
                    <Icon name="user" size={13} />
                    {phrase.contributor_id || 'Anonymous'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ExplorePage;
