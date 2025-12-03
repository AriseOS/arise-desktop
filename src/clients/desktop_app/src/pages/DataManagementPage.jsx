import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
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
      showStatus(`Failed to load collections: ${error.message}`, 'error');
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
            <Icon icon="arrowLeft" />
          </button>
          <h1 className="page-title"><Icon icon="database" size={28} /> Data Collections</h1>
        </div>
        <div className="header-right">
          <button className="icon-button" onClick={loadCollections} title="Refresh">
            <Icon icon="refreshCw" size={20} />
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
            <div className="empty-icon"><Icon icon="package" size={48} /></div>
            <h3>No Data Collections Yet</h3>
            <p>Data collections will appear here when you run workflows that store data.</p>
          </div>
        ) : (
          <div className="collections-container">
            <div className="collections-header">
              <h2><Icon icon="layers" size={20} /> Collections ({collections.length})</h2>
              <p className="collections-subtitle">
                Data extracted and stored by your workflows
              </p>
            </div>

            <div className="collections-grid">
              {collections.map((collection) => (
                <div key={collection.collection_name} className="collection-card">
                  <div className="collection-header">
                    <div className="collection-icon"><Icon icon="database" size={24} /></div>
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
                      <Icon icon="eye" size={14} />
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
