import React, { useState, useEffect } from 'react';
import '../styles/CollectionDetailPage.css';

const API_BASE = "http://127.0.0.1:8765";
const DEFAULT_USER = "default_user";

function CollectionDetailPage({ onNavigate, showStatus, collectionName }) {
  const [collection, setCollection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (collectionName) {
      loadCollectionDetail();
    }
  }, [collectionName]);

  const loadCollectionDetail = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/data/collections/${collectionName}?user_id=${DEFAULT_USER}&limit=20`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch collection: ${response.status}`);
      }

      const data = await response.json();
      setCollection(data);
    } catch (error) {
      console.error('Error loading collection:', error);
      showStatus(`❌ Failed to load collection: ${error.message}`, 'error');
      setTimeout(() => onNavigate('data-management'), 2000);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    showStatus(`📤 Exporting ${collectionName}...`, 'info');

    try {
      const response = await fetch(
        `${API_BASE}/api/data/collections/${collectionName}/export?user_id=${DEFAULT_USER}`
      );

      if (!response.ok) {
        throw new Error(`Export failed: ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${collectionName}_${DEFAULT_USER}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      showStatus(`✅ Exported successfully!`, 'success');
    } catch (error) {
      console.error('Export error:', error);
      showStatus(`❌ Export failed: ${error.message}`, 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    showStatus(`🗑️ Deleting ${collectionName}...`, 'info');

    try {
      const response = await fetch(
        `${API_BASE}/api/data/collections/${collectionName}?user_id=${DEFAULT_USER}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        throw new Error(`Delete failed: ${response.status}`);
      }

      showStatus(`✅ Collection deleted successfully!`, 'success');
      setTimeout(() => onNavigate('data-management'), 1000);
    } catch (error) {
      console.error('Delete error:', error);
      showStatus(`❌ Delete failed: ${error.message}`, 'error');
      setDeleting(false);
      setDeleteConfirm(false);
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const renderValue = (value) => {
    if (value === null || value === undefined) {
      return <span className="null-value">null</span>;
    }
    if (typeof value === 'string' && value.length > 100) {
      return <span className="truncated-value" title={value}>{value.substring(0, 100)}...</span>;
    }
    return value;
  };

  if (loading) {
    return (
      <div className="page collection-detail-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading collection...</p>
        </div>
      </div>
    );
  }

  if (!collection) {
    return (
      <div className="page collection-detail-page">
        <div className="empty-state">
          <p>Collection not found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page collection-detail-page">
      {/* Page Header */}
      <div className="page-header-simple">
        <div className="header-left">
          <button className="back-button" onClick={() => onNavigate('data-management')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div className="header-title-group">
            <h1 className="page-title">{collection.collection_name}</h1>
            <p className="page-subtitle">
              {collection.total_records} records • {formatBytes(collection.size_bytes)}
            </p>
          </div>
        </div>
        <div className="header-right">
          <button
            className="header-action-button export"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? (
              <>
                <span className="button-spinner"></span>
                <span>Exporting...</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                <span>Export CSV</span>
              </>
            )}
          </button>
          <button
            className="header-action-button delete"
            onClick={() => setDeleteConfirm(true)}
            disabled={deleting}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            <span>Delete</span>
          </button>
        </div>
      </div>

      {/* Page Content */}
      <div className="page-content">
        {/* Data Preview */}
        <div className="data-section">
          <div className="section-header">
            <h2>Data Preview</h2>
            <p className="section-subtitle">
              Showing {collection.preview_count} of {collection.total_records} records (most recent)
            </p>
          </div>

          {collection.preview_data.length === 0 ? (
            <div className="empty-data">
              <p>No data to preview</p>
            </div>
          ) : (
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    {collection.all_fields.map((field) => (
                      <th key={field}>{field}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {collection.preview_data.map((row, idx) => (
                    <tr key={idx}>
                      {collection.all_fields.map((field) => (
                        <td key={field}>{renderValue(row[field])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => !deleting && setDeleteConfirm(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-icon delete">⚠️</div>
            <h3>Delete Collection?</h3>
            <p>
              Are you sure you want to delete <strong>{collection.collection_name}</strong>?
              <br />
              This will permanently delete {collection.total_records} records.
              <br />
              <strong>This action cannot be undone.</strong>
            </p>
            <div className="modal-actions">
              <button
                className="modal-button cancel"
                onClick={() => setDeleteConfirm(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                className="modal-button delete"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete Collection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CollectionDetailPage;
