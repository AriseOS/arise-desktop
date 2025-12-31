import React, { useState, useEffect } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/UserFlowsPage.css';

function UserFlowsPage({ session, onNavigate, showStatus }) {
  const userId = session?.username;
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecording, setSelectedRecording] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { sessionId, recordingName }

  useEffect(() => {
    if (userId) {
      loadRecordings();
    }
  }, [userId]);

  const loadRecordings = async () => {
    try {
      setLoading(true);
      showStatus("加载录制流程列表...", "info");

      const data = await api.callAppBackend(`/api/v1/recordings?user_id=${userId}`);
      setRecordings(data.recordings || []);
      showStatus("录制流程列表加载成功", "success");

    } catch (error) {
      console.error("Load recordings error:", error);
      showStatus("加载录制流程失败", "error");
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

      // Generate MetaFlow from recording
      showStatus("正在生成 MetaFlow...", "info");

      const metaflowResult = await api.generateMetaflowFromRecording(
        recording.session_id,
        recording.description,
        null,  // user_query
        userId
      );
      showStatus("MetaFlow 生成成功！正在跳转预览...", "success");

      // Navigate to MetaFlow preview page (user will review and generate workflow from there)
      setTimeout(() => {
        onNavigate("metaflow-preview", {
          metaflowId: metaflowResult.metaflow_id,
          metaflowYaml: metaflowResult.metaflow_yaml
        });
      }, 500);

    } catch (error) {
      console.error("Generate MetaFlow error:", error);
      showStatus(`生成 MetaFlow 失败: ${error.message}`, "error");
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
      showStatus("Deleting recording...", "info");

      await api.callAppBackend(`/api/v1/recordings/${sessionId}?user_id=${userId}`, {
        method: 'DELETE'
      });

      setRecordings(prev => prev.filter(r => r.session_id !== sessionId));
      showStatus("Recording deleted successfully", "success");

    } catch (error) {
      console.error("Delete recording error:", error);
      showStatus(`Failed to delete recording: ${error.message}`, "error");
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
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="video" size={28} /> 用户流程</div>
        <button className="primary-button" onClick={handleNewRecording}>
          <Icon icon="plusCircle" size={20} />
          <span>新建录制</span>
        </button>
      </div>

      <div className="user-flows-content">
        <div className="page-section">
          <div className="section-header">
            <h3>录制流程列表</h3>
            <div className="section-actions">
              <button className="secondary-button" onClick={loadRecordings}>
                <Icon icon="refreshCw" size={16} />
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
              <div className="empty-state-icon"><Icon icon="video" size={48} /></div>
              <div className="empty-state-title">暂无录制流程</div>
              <div className="empty-state-desc">
                开始录制浏览器操作，创建你的第一个流程
              </div>
              <button className="primary-button" onClick={handleNewRecording}>
                <Icon icon="plusCircle" size={20} />
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
                          <span className="meta-icon"><Icon icon="globe" size={14} /></span>
                          <span className="meta-label">起始URL:</span>
                          <span className="meta-value">{recording.url}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="zap" size={14} /></span>
                          <span className="meta-label">操作数量:</span>
                          <span className="meta-value">{recording.operations_count} 个操作</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="calendar" size={14} /></span>
                          <span className="meta-label">录制时间:</span>
                          <span className="meta-value">{formatDate(recording.created_at)}</span>
                        </div>
                        <div className="meta-item">
                          <span className="meta-icon"><Icon icon="hash" size={14} /></span>
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
                          <Icon icon="play" size={16} />
                          <span>生成 Workflow</span>
                        </>
                      )}
                    </button>

                    <button className="action-button secondary">
                      <Icon icon="eye" size={16} />
                      <span>查看详情</span>
                    </button>

                    <button
                      className="action-button danger"
                      onClick={() => handleDeleteClick(recording)}
                    >
                      <Icon icon="trash2" size={16} />
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
            <h3><Icon icon="bookOpen" size={20} /> 使用指南</h3>
          </div>
          <div className="guide-content">
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="video" size={24} /></div>
              <div className="guide-text">
                <h4>录制流程</h4>
                <p>点击"新建录制"开始录制浏览器操作，系统会记录你的每一步操作</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="zap" size={24} /></div>
              <div className="guide-text">
                <h4>生成 Workflow</h4>
                <p>从录制流程直接生成可执行的 Workflow，无需等待 AI 处理</p>
              </div>
            </div>
            <div className="guide-item">
              <div className="guide-icon"><Icon icon="search" size={24} /></div>
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
