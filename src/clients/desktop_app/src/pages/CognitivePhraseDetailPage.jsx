import React, { useState, useEffect, useCallback } from 'react';
import ReactFlow, { Controls, Background, MiniMap, useNodesState, useEdgesState } from 'reactflow';
import 'reactflow/dist/style.css';
import Icon from '../components/Icons';
import CustomNode from '../components/CustomNode';
import SimpleFloatingEdge from '../components/SimpleFloatingEdge';
import { api } from '../utils/api';
import { transformCognitivePhraseData } from '../utils/flowLayout';
import '../styles/CognitivePhraseDetailPage.css';

const nodeTypes = { custom: CustomNode };
const edgeTypes = { floating: SimpleFloatingEdge };

function CognitivePhraseDetailPage({ session, onNavigate, showStatus, phraseId, isPublic = false }) {
  const [phrase, setPhrase] = useState(null);
  const [states, setStates] = useState([]);
  const [intentSequences, setIntentSequences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [isPublished, setIsPublished] = useState(false);

  // ReactFlow state
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [expandedNodeIds, setExpandedNodeIds] = useState(new Set());

  // Toggle node expansion
  const handleToggleExpand = useCallback((nodeId) => {
    setExpandedNodeIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId);
      } else {
        newSet.add(nodeId);
      }
      return newSet;
    });
  }, []);

  // Fetch phrase data
  useEffect(() => {
    if (!phraseId) return;

    const fetchPhrase = async () => {
      try {
        const data = await api.getCognitivePhrase(phraseId, isPublic ? { source: 'public' } : {});
        setPhrase(data.phrase);
        setStates(data.states || []);
        setIntentSequences(data.intent_sequences || []);
      } catch (error) {
        console.error('Error fetching phrase:', error);
        showStatus(`Failed to load memory: ${error.message}`, 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchPhrase();
  }, [phraseId, isPublic]);

  // Check publish status for private phrases
  useEffect(() => {
    if (!phraseId || isPublic) return;

    const checkStatus = async () => {
      try {
        const status = await api.getPublishStatus(phraseId);
        setIsPublished(status.published || false);
      } catch (error) {
        console.error('Error checking publish status:', error);
      }
    };

    checkStatus();
  }, [phraseId, isPublic]);

  // Update graph when data or expansion state changes
  useEffect(() => {
    if (!phrase || states.length === 0) return;

    const { nodes: newNodes, edges: newEdges } = transformCognitivePhraseData(
      phrase,
      states,
      intentSequences,
      expandedNodeIds,
      handleToggleExpand
    );

    setNodes(newNodes);
    setEdges(newEdges);
  }, [phrase, states, intentSequences, expandedNodeIds, handleToggleExpand]);

  const handlePublishToggle = async () => {
    setPublishing(true);
    try {
      if (isPublished) {
        const result = await api.unpublishCognitivePhrase(phraseId);
        if (result.success) {
          setIsPublished(false);
          showStatus('Memory unpublished from community', 'success');
        } else {
          showStatus('Failed to unpublish memory', 'error');
        }
      } else {
        const result = await api.shareCognitivePhrase(phraseId);
        if (result.success) {
          setIsPublished(true);
          showStatus('Memory published to community!', 'success');
        } else {
          showStatus('Failed to publish memory', 'error');
        }
      }
    } catch (error) {
      console.error('Error toggling publish:', error);
      showStatus(`Failed: ${error.message}`, 'error');
    } finally {
      setPublishing(false);
    }
  };

  const handleDelete = async () => {
    setDeleteConfirm(false);

    try {
      showStatus('Deleting memory...', 'info');
      await api.deleteCognitivePhrase(phraseId);
      showStatus('Memory deleted successfully', 'success');
      onNavigate('memories');
    } catch (error) {
      console.error('Error deleting phrase:', error);
      showStatus(`Failed to delete: ${error.message}`, 'error');
    }
  };

  const formatDuration = (ms) => {
    if (!ms) return 'Unknown';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    }
    return `${seconds}s`;
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp).toLocaleString();
  };

  if (loading) {
    return (
      <div className="cognitive-phrase-detail-page">
        <div className="loading-container">
          <div className="spinner-large"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (!phrase) {
    return (
      <div className="cognitive-phrase-detail-page">
        <div className="error-container">
          <Icon name="alertCircle" />
          <h3>Memory not found</h3>
          <button className="btn btn-primary" onClick={() => onNavigate(isPublic ? 'explore' : 'memories')}>
            {isPublic ? 'Back to Explore' : 'Back to Memories'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cognitive-phrase-detail-page">
      {/* Header */}
      <div className="page-header">
        <button className="btn-icon" onClick={() => onNavigate(isPublic ? 'explore' : 'memories')} aria-label="Go Back">
          <Icon name="arrowLeft" />
        </button>
        <h1 className="page-title">{phrase.label || 'Unnamed Workflow'}</h1>
        <div className="header-actions">
          {isPublic ? (
            <button
              className="btn btn-primary"
              onClick={() => onNavigate('main', { initialMessage: phrase.description })}
              style={{ padding: '6px 14px', fontSize: '13px', gap: '6px' }}
            >
              <Icon name="play" size={16} />
              <span>Run</span>
            </button>
          ) : (
            <>
              <button
                className={`btn ${isPublished ? 'btn-secondary' : 'btn-primary'}`}
                onClick={handlePublishToggle}
                disabled={publishing}
                style={{ padding: '6px 14px', fontSize: '13px', gap: '6px' }}
              >
                <Icon name={isPublished ? 'x' : 'upload'} size={16} />
                <span>{publishing ? '...' : (isPublished ? 'Unpublish' : 'Publish')}</span>
              </button>
              <button
                className="btn-icon-danger"
                onClick={() => setDeleteConfirm(true)}
                title="Delete"
              >
                <Icon name="trash" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Description */}
      <div className="description-section">
        <p className="description-text">{phrase.description}</p>
      </div>

      {/* Stats Grid */}
      <div className="stats-section">
        <div className="stats-grid">
          <div className="stat-item">
            <span className="stat-value">{phrase.state_path?.length || 0}</span>
            <span className="stat-label">States</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{phrase.action_path?.length || 0}</span>
            <span className="stat-label">Actions</span>
          </div>
          {isPublic ? (
            <div className="stat-item">
              <span className="stat-value">{phrase.use_count || 0}</span>
              <span className="stat-label">Uses</span>
            </div>
          ) : (
            <>
              <div className="stat-item">
                <span className="stat-value">{phrase.access_count || 0}</span>
                <span className="stat-label">Accesses</span>
              </div>
              <div className="stat-item">
                <span className="stat-value">{phrase.success_count || 0}</span>
                <span className="stat-label">Successes</span>
              </div>
            </>
          )}
        </div>
        <div className="meta-info">
          {isPublic && phrase.contributor_id && (
            <span className="meta-item"><Icon name="user" /> {phrase.contributor_id}</span>
          )}
          <span className="meta-item"><Icon name="clock" /> {formatDate(isPublic ? phrase.contributed_at : phrase.created_at)}</span>
        </div>
      </div>

      {/* Graph Visualization */}
      <div className="graph-container">
        <div className="graph-header">
          <h2><Icon name="route" /> Workflow Graph</h2>
          <div className="graph-legend">
            <span className="legend-item">
              <span className="legend-color" style={{ background: '#3b82f6' }}></span>
              State
            </span>
            <span className="legend-item">
              <span className="legend-color" style={{ background: '#10b981' }}></span>
              IntentSequence
            </span>
          </div>
        </div>
        <div className="graph-view">
          {nodes.length > 0 ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.1}
              maxZoom={2}
              defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
            >
              <Background color="#e5e7eb" gap={16} />
              <Controls position="bottom-right" />
              <MiniMap
                nodeColor={(node) => {
                  if (node.data?.nodeType === 'state') return '#3b82f6';
                  if (node.data?.nodeType === 'intent_sequence') return '#10b981';
                  return '#94a3b8';
                }}
                maskColor="rgba(0, 0, 0, 0.1)"
              />
            </ReactFlow>
          ) : (
            <div className="empty-graph">
              <Icon name="route" />
              <p>No graph data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Delete Memory</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete <strong>{phrase.label || 'this memory'}</strong>?</p>
              <p className="warning-text">This action cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setDeleteConfirm(false)}>
                Cancel
              </button>
              <button className="btn btn-danger-solid" onClick={handleDelete}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CognitivePhraseDetailPage;
