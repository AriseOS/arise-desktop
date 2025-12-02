import React, { useState, useEffect } from 'react';
import '../styles/DataManagementPage.css';

const API_BASE = "http://127.0.0.1:8765";

function DataManagementPage({ session, onNavigate, showStatus }) {
  const userId = session?.username || 'default_user';
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCollections();
  }, []);

  const loadCollections = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/data/collections?user_id=${userId}`);

      if (!response.ok) {
        throw new Error(`Failed to fetch collections: ${response.status}`);
      }

      const data = await response.json();
      setCollections(data.collections || []);
    } catch (error) {
      console.error('Error loading collections:', error);
      showStatus(`❌ Failed to load collections: ${error.message}`, 'error');
      setCollections([]);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = (collectionName) => {
    onNavigate('collection-detail', { collectionName });
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className="page data-management-page">
      {/* Page Header */}
      <div className="page-header-simple">
        <div className="header-left">
          <button className="back-button" onClick={() => onNavigate('main')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <h1 className="page-title">Data Collections</h1>
        </div>
        <div className="header-right">
          <button className="icon-button" onClick={loadCollections} title="Refresh">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 11-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>
              <path d="M21 3v5h-5"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Page Content */}
      <div className="page-content">
        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading collections...</p>
          </div>
        ) : collections.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📦</div>
            <h3>No Data Collections Yet</h3>
            <p>Data collections will appear here when you run workflows that store data.</p>
          </div>
        ) : (
          <div className="collections-container">
            <div className="collections-header">
              <h2>Collections ({collections.length})</h2>
              <p className="collections-subtitle">
                Data extracted and stored by your workflows
              </p>
            </div>

            <div className="collections-grid">
              {collections.map((collection) => (
                <div key={collection.collection_name} className="collection-card">
                  <div className="collection-header">
                    <div className="collection-icon">💾</div>
                    <div className="collection-info">
                      <h3 className="collection-name">{collection.collection_name}</h3>
                      <p className="collection-meta">
                        {collection.records_count} records • {formatBytes(collection.size_bytes)}
                      </p>
                    </div>
                  </div>

                  <div className="collection-fields">
                    <p className="fields-label">Fields:</p>
                    <div className="fields-list">
                      {collection.fields.slice(0, 5).map((field, idx) => (
                        <span key={idx} className="field-tag">{field}</span>
                      ))}
                      {collection.fields.length > 5 && (
                        <span className="field-tag more">+{collection.fields.length - 5} more</span>
                      )}
                    </div>
                  </div>

                  <div className="collection-actions">
                    <button
                      className="action-button primary"
                      onClick={() => handleViewDetail(collection.collection_name)}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                      <span>View Details</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DataManagementPage;
