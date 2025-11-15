import React, { useState, useEffect } from 'react';

const API_BASE = "http://127.0.0.1:8765";
const DEFAULT_USER = "default_user";

function UserFlowsPage({ onNavigate, showStatus }) {
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecording, setSelectedRecording] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }

  useEffect(() => {
    loadRecordings();
  }, []);

  const loadRecordings = async () => {
    try {
      setLoading(true);
      showStatus("📋 加载录制流程列表...", "info");
      
      const response = await fetch(`${API_BASE}/api/recordings/list?user_id=${DEFAULT_USER}`);
      
      if (!response.ok) {
        throw new Error(`Failed to load recordings: ${response.status}`);
      }
      
      const data = await response.json();
      setRecordings(data.recordings || []);
      showStatus("✅ 录制流程列表加载成功", "success");
      
    } catch (error) {
      console.error("Load recordings error:", error);
      showStatus("❌ 加载录制流程失败", "error");
      setRecordings([]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewRecording = () => {
    onNavigate("recording");
  };

  const handleQuickGenerate = async (recording) => {
    try {
      setSelectedRecording(recording.session_id);
      showStatus("⚡ 正在从录制生成 Workflow...", "info");

      const response = await fetch(`${API_BASE}/api/workflows/quick-generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: recording.session_id,
          task_description: recording.description,
          user_id: DEFAULT_USER
        })
      });

      if (!response.ok) {
        throw new Error(`生成失败: ${response.status}`);
      }

      const result = await response.json();
      showStatus("⚡ Workflow 生成成功！", "success");

      // Navigate to workflow detail page
      setTimeout(() => {
        onNavigate("workflow-detail", {
          workflowId: result.workflow_name,
          generatedFrom: "recording"
        });
      }, 1000);
      
    } catch (error) {
      console.error("Quick generate error:", error);
      showStatus(`❌ 生成 Workflow 失败: ${error.message}`, "error");
    } finally {
      setSelectedRecording(null);
    }
  };

  const handleDeleteClick = (recording) => {
    const recordingName = recording.title || `Recording ${recording.session_id}`;
    setDeleteConfirm({ sessionId: recording.session_id, recordingName });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const { sessionId } = deleteConfirm;
    setDeleteConfirm(null);

    try {
      showStatus("🗑️ Deleting recording...", "info");

      const response = await fetch(`${API_BASE}/api/recordings/${sessionId}?user_id=${DEFAULT_USER}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error(`Failed to delete recording: ${response.status}`);
      }

      setRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      showStatus("✅ Recording deleted successfully", "success");

    } catch (error) {
      console.error("Delete recording error:", error);
      showStatus(`❌ Failed to delete recording: ${error.message}`, "error");
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(null);
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return '#52c41a';
      case 'recording': return '#1890ff';
      case 'failed': return '#ff4d4f';
      default: return '#8c8c8c';
    }
  };

  return (
    <div className="page user-flows-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">📹 用户流程</div>
        <button className="primary-button" onClick={handleNewRecording}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="16"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
          </svg>
          <span>新建录制</span>
        </button>
      </div>

      <div className="user-flows-content">
        <div className="page-section">
          <div className="section-header">
            <h3>录制流程列表</h3>
            <div className="section-actions">
              <button className="secondary-button" onClick={loadRecordings}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23 4 23 10 17 10"/>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
                <span>刷新</span>
              </button>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>正在加载录制流程...</p>
            </div>
          ) : recordings.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📹</div>
              <div className="empty-state-title">暂无录制流程</div>
              <div className="empty-state-desc">
                开始录制浏览器操作，创建你的第一个流程
              </div>
              <button className="primary-button" onClick={handleNewRecording}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="16"/>
                  <line x1="8" y1="12" x2="16" y2="12"/>
                </svg>
                <span>开始录制</span>
              </button>
            </div>
          ) : (
            <div className="recordings-list">
              {recordings.map((recording) => (
                <div key={recording.session_id} className="recording-item">
                  <div className="recording-main">
                    <div className="recording-info">
                      <div className="recording-title">
                        <h4>{recording.title}</h4>
                        <div 
                          className="status-badge"
                          style={{ backgroundColor: getStatusColor(recording.status) }}
                        >
                          {recording.status === 'completed' ? '已完成' : 
                           recording.status === 'recording' ? '录制中' : '失败'}
                        </div>
                      </div>
                      
                      <div className="recording-description">
                        {recording.description}
                      </div>
                      
                      <div className="recording-meta">
                        <div className="meta-item">
                          <span className="meta-icon">🌐</span>
                          <span className="meta-label">起始URL:</span>
                          <span className="meta-value">{recording.url}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon">⚡</span>
                          <span className="meta-label">操作数量:</span>
                          <span className="meta-value">{recording.operations_count} 个操作</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon">📅</span>
                          <span className="meta-label">录制时间:</span>
                          <span className="meta-value">{formatDate(recording.created_at)}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon">🆔</span>
                          <span className="meta-label">会话ID:</span>
                          <span className="meta-value">{recording.session_id}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div className="recording-actions">
                    <button 
                      className="action-button primary"
                      onClick={() => handleQuickGenerate(recording)}
                      disabled={selectedRecording === recording.session_id}
                    >
                      {selectedRecording === recording.session_id ? (
                        <>
                          <span className="btn-spinner"></span>
                          <span>生成中...</span>
                        </>
                      ) : (
                        <>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                          </svg>
                          <span>生成 Workflow</span>
                        </>
                      )}
                    </button>
                    
                    <button className="action-button secondary">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                      <span>查看详情</span>
                    </button>
                    
                    <button
                      className="action-button danger"
                      onClick={() => handleDeleteClick(recording)}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                      <span>删除</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="page-section">
          <div className="section-header">
            <h3>📖 使用指南</h3>
          </div>
          <div className="guide-content">
            <div className="guide-item">
              <div className="guide-icon">📹</div>
              <div className="guide-text">
                <h4>录制流程</h4>
                <p>点击"新建录制"开始录制浏览器操作，系统会记录你的每一步操作</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon">⚡</div>
              <div className="guide-text">
                <h4>生成 Workflow</h4>
                <p>从录制流程直接生成可执行的 Workflow，无需等待 AI 处理</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon">🔍</div>
              <div className="guide-text">
                <h4>查看详情</h4>
                <p>查看录制的详细操作步骤，了解录制的具体内容</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={handleDeleteCancel}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Confirm Delete</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to delete <strong>"{deleteConfirm.recordingName}"</strong>?</p>
              <p className="warning-text">This action cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleDeleteCancel}>
                Cancel
              </button>
              <button className="btn-confirm-delete" onClick={handleDeleteConfirm}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserFlowsPage;
