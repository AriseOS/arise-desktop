import React, { useState, useEffect } from 'react';
import { useTranslation } from "react-i18next";
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/CognitivePhrasesPage.css';

function CognitivePhrasesPage({ session, onNavigate, showStatus }) {
  const { t } = useTranslation();
  const [phrases, setPhrases] = useState([]);
  const [filteredPhrases, setFilteredPhrases] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [shareConfirm, setShareConfirm] = useState(null);
  const [sharingId, setSharingId] = useState(null);

  // Fetch phrases from API
  useEffect(() => {
    const fetchPhrases = async () => {
      try {
        const data = await api.listCognitivePhrases(100);
        setPhrases(data.phrases || []);
        setFilteredPhrases(data.phrases || []);
      } catch (error) {
        console.error('Error fetching cognitive phrases:', error);
        showStatus(`Failed to load phrases: ${error.message}`, 'error');
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

  const handleViewDetails = (phraseId) => {
    onNavigate('memory-detail', { phraseId });
  };

  const handleDeleteClick = (phrase) => {
    setDeleteConfirm({
      id: phrase.id,
      name: phrase.label || truncateText(phrase.description, 50)
    });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { id } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus('Deleting phrase...', 'info');
      await api.deleteCognitivePhrase(id);

      // Remove from local state
      setPhrases(prev => prev.filter(p => p.id !== id));
      setFilteredPhrases(prev => prev.filter(p => p.id !== id));

      showStatus('Phrase deleted successfully', 'success');
    } catch (error) {
      console.error('Error deleting phrase:', error);
      showStatus(`Failed to delete: ${error.message}`, 'error');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(null);
  };

  const handleShareClick = (e, phrase) => {
    e.preventDefault();
    e.stopPropagation();
    setShareConfirm({
      id: phrase.id,
      name: phrase.label || truncateText(phrase.description, 50)
    });
  };

  const handleShareConfirm = async () => {
    if (!shareConfirm) return;

    const { id } = shareConfirm;
    setShareConfirm(null);
    setSharingId(id);
    try {
      await api.shareCognitivePhrase(id);
      showStatus('Memory shared to public library', 'success');
    } catch (error) {
      console.error('Error sharing phrase:', error);
      showStatus(`Failed to share: ${error.message}`, 'error');
    } finally {
      setSharingId(null);
    }
  };

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
          <p>{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="cognitive-phrases-page">
      {/* Header */}
      <div className="page-header">
        <button className="btn-icon" onClick={() => onNavigate('main')} aria-label="Go Back">
          <Icon name="arrowLeft" />
        </button>
        <h1 className="page-title"><Icon name="brain" /> Memories</h1>
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
            placeholder="Search memories..."
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
            ? 'No memories found'
            : `${filteredPhrases.length} ${filteredPhrases.length === 1 ? 'memory' : 'memories'}`}
        </p>
      </div>

      {/* Phrases List */}
      <div className="phrases-list">
        {filteredPhrases.length === 0 ? (
          <div className="empty-state">
            {phrases.length === 0 ? (
              <>
                <div className="empty-icon"><Icon name="brain" /></div>
                <h3>No memories yet</h3>
                <p>Memories are created when you record workflows. Start recording to build your memory.</p>
                <button className="btn-start-recording" onClick={() => onNavigate('quick-start')}>
                  <span className="button-icon"><Icon name="video" /></span>
                  <span>Start Recording</span>
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
            <div key={phrase.id} className="phrase-card" onClick={() => handleViewDetails(phrase.id)}>
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
                    <span className="meta-item">
                      <Icon name="activity" />
                      {phrase.access_count || 0} accesses
                    </span>
                    <span className="meta-item">
                      <Icon name="check" />
                      {phrase.success_count || 0} successes
                    </span>
                    {phrase.created_at && (
                      <span className="meta-item">
                        <Icon name="clock" />
                        {formatDate(phrase.created_at)}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="phrase-actions">
                <button
                  className="btn btn-primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleViewDetails(phrase.id);
                  }}
                >
                  <Icon name="eye" />
                  View
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={(e) => handleShareClick(e, phrase)}
                  disabled={sharingId === phrase.id}
                >
                  <Icon name={sharingId === phrase.id ? "loader" : "upload"} />
                  {sharingId === phrase.id ? 'Sharing...' : 'Share'}
                </button>
                <button
                  className="btn-icon-danger"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteClick(phrase);
                  }}
                  title="Delete memory"
                >
                  <Icon name="trash" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Share Confirmation Modal */}
      {shareConfirm && (
        <div className="modal-overlay" onClick={() => setShareConfirm(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Share to Public</h3>
            </div>
            <div className="modal-body">
              <p>Share <strong>{shareConfirm.name}</strong> to the public library?</p>
              <p className="share-info-text">When others use your shared memory, you'll earn tokens as a reward.</p>
              <p className="warning-text">This action is currently irrevocable.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setShareConfirm(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleShareConfirm}>
                <Icon name="upload" /> Share
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={handleDeleteCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Delete Memory</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete <strong>{deleteConfirm.name}</strong>?</p>
              <p className="warning-text">This action cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                Cancel
              </button>
              <button className="btn btn-danger-solid" onClick={handleDeleteConfirm}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CognitivePhrasesPage;
