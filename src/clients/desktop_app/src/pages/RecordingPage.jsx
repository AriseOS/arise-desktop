import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import '../styles/RecordingPage.css';

function RecordingPage({ session, onNavigate, showStatus, version }) {
  const userId = session?.username;
  const [recordUrl, setRecordUrl] = useState("https://www.google.com");
  const [recordTitle, setRecordTitle] = useState("");
  const [recordDescription, setRecordDescription] = useState("");

  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [operationsCount, setOperationsCount] = useState(0);
  const [capturedOperations, setCapturedOperations] = useState([]);
  const operationsListRef = useRef(null);

  const [uploading, setUploading] = useState(false);

  // Poll for operations while recording
  useEffect(() => {
    if (!recording) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const result = await api.callAppBackend('/api/v1/recordings/current/operations', {
          method: "GET"
        });
        if (result.is_recording) {
          setCapturedOperations(result.operations || []);
          setOperationsCount(result.operations_count || 0);
        }
      } catch (error) {
        console.error('Failed to poll operations:', error);
      }
    }, 500);

    return () => {
      clearInterval(pollInterval);
    };
  }, [recording]);

  // Auto-scroll to bottom when new operations are added
  useEffect(() => {
    if (operationsListRef.current) {
      operationsListRef.current.scrollTop = operationsListRef.current.scrollHeight;
    }
  }, [capturedOperations]);

  // Get operation type label with icon
  const getOperationTypeLabel = (type) => {
    const typeLabels = {
      'click': { text: '点击', icon: 'mousePointer' },
      'input': { text: '输入', icon: 'keyboard' },
      'navigate': { text: '导航', icon: 'globe' },
      'scroll': { text: '滚动', icon: 'arrowDown' },
      'select': { text: '选择', icon: 'list' },
      'submit': { text: '提交', icon: 'checkCircle' },
      'hover': { text: '悬停', icon: 'mousePointer' },
      'keydown': { text: '按键', icon: 'keyboard' },
      'change': { text: '修改', icon: 'edit' }
    };
    const label = typeLabels[type] || { text: type || '操作', icon: 'mapPin' };
    return (
      <>
        <Icon icon={label.icon} size={14} />
        <span>{label.text}</span>
      </>
    );
  };

  // Start recording
  const handleStartRecording = async () => {
    if (!recordUrl || !recordTitle || !recordDescription) {
      showStatus("请填写所有必填项", "error");
      return;
    }

    try {
      showStatus("启动录制...", "info");

      const result = await api.callAppBackend('/api/v1/recordings/start', {
        method: "POST",
        body: JSON.stringify({
          url: recordUrl,
          user_id: userId,
          title: recordTitle,
          description: recordDescription,
          task_metadata: { task_description: recordDescription }
        })
      });
      setRecording(true);
      setSessionId(result.session_id);
      showStatus("录制已开始！请在浏览器中操作", "success");
    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`启动录制失败: ${error.message}`, "error");
    }
  };

  // Stop recording
  const handleStopRecording = async () => {
    try {
      showStatus("停止录制...", "info");

      const result = await api.callAppBackend('/api/v1/recordings/stop', {
        method: "POST"
      });
      setRecording(false);
      setOperationsCount(result.operations_count);
      showStatus(`录制完成！捕获了 ${result.operations_count} 个操作`, "success");
    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`停止录制失败: ${error.message}`, "error");
      setRecording(false);
    }
  };

  // Upload recording
  const handleUpload = async () => {
    if (!sessionId) {
      showStatus("没有可上传的录制", "error");
      return;
    }

    try {
      setUploading(true);
      showStatus("上传录制到云端...", "info");

      const result = await api.callAppBackend(`/api/v1/recordings/${sessionId}/upload`, {
        method: "POST",
        body: JSON.stringify({
          task_description: recordDescription,
          user_id: userId
        })
      });
      showStatus("上传成功！录制已保存到云端", "success");

      // Return to main page after successful upload
      setTimeout(() => {
        onNavigate("main");
      }, 2000);
    } catch (error) {
      console.error("Upload error:", error);
      showStatus(`上传失败: ${error.message}`, "error");
    } finally {
      setUploading(false);
    }
  };

  // Navigate to generation page with recording info
  const handleQuickGenerate = () => {
    if (!sessionId) {
      showStatus("没有可生成Workflow的录制", "error");
      return;
    }

    onNavigate('generation', {
      recordingId: sessionId,
      recordingName: recordDescription || sessionId,
      taskDescription: recordDescription || '',
      userQuery: ''
    });
  };

  return (
    <div className="page recording-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")} disabled={recording}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="video" size={28} /> 录制 Workflow</div>
      </div>

      <div className="record-content">
        <div className="record-form">
          {/* Step 1: Configuration */}
          {!recording && !sessionId && (
            <div className="form-section">
              <h3>配置录制信息</h3>

              <div className="input-group">
                <label>
                  <span>起始 URL <span className="required">*</span></span>
                </label>
                <input
                  type="text"
                  value={recordUrl}
                  onChange={(e) => setRecordUrl(e.target.value)}
                  placeholder="https://www.google.com"
                />
              </div>

              <div className="input-group">
                <label>
                  <span>标题 <span className="required">*</span></span>
                  <span className="input-hint">{recordTitle.length}/50</span>
                </label>
                <input
                  type="text"
                  value={recordTitle}
                  onChange={(e) => setRecordTitle(e.target.value)}
                  placeholder="例如：自动填写表单"
                  maxLength={50}
                />
              </div>

              <div className="input-group">
                <label>
                  <span>任务描述 <span className="required">*</span></span>
                  <span className="input-hint">{recordDescription.length}/500</span>
                </label>
                <textarea
                  value={recordDescription}
                  onChange={(e) => setRecordDescription(e.target.value)}
                  placeholder="详细描述这个工作流要完成什么任务...&#10;&#10;例如：打开 Google，搜索 coffee，查看搜索结果"
                  maxLength={500}
                  rows={6}
                />
              </div>

              <button
                className="start-record-button"
                onClick={handleStartRecording}
              >
                <Icon icon="circle" size={20} fill="currentColor" />
                <span>开始录制</span>
              </button>
            </div>
          )}

          {/* Step 2: Recording in progress */}
          {recording && (
            <div className="recording-status">
              <div className="recording-indicator">
                <div className="recording-dot"></div>
                <span>录制中...</span>
              </div>

              {/* Operations display */}
              <div className="operations-display">
                <div className="operations-header">
                  <span className="operations-title">已捕获操作</span>
                  <span className="operations-count">{capturedOperations.length} 个操作</span>
                </div>
                <div className="operations-list" ref={operationsListRef}>
                  {capturedOperations.length === 0 ? (
                    <div className="empty-operations">
                      <div className="empty-icon"><Icon icon="clipboard" size={48} /></div>
                      <div className="empty-text">等待捕获操作...</div>
                      <div className="empty-hint">请在浏览器中执行操作</div>
                    </div>
                  ) : (
                    capturedOperations.map((op, index) => (
                      <div key={index} className="operation-item">
                        <div className="operation-index">{index + 1}</div>
                        <div className="operation-details">
                          <div className="operation-type">{getOperationTypeLabel(op.type)}</div>
                          <div className="operation-info">
                            {op.element?.textContent && (
                              <div className="operation-text">
                                {op.element.textContent.slice(0, 50)}
                                {op.element.textContent.length > 50 ? '...' : ''}
                              </div>
                            )}
                            {op.data?.value && (
                              <div className="operation-value">
                                输入: {op.data.value.slice(0, 30)}
                                {op.data.value.length > 30 ? '...' : ''}
                              </div>
                            )}
                            {op.url && (
                              <div className="operation-url">
                                {(() => {
                                  try {
                                    return new URL(op.url).hostname;
                                  } catch {
                                    return op.url;
                                  }
                                })()}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <button
                className="start-record-button recording"
                onClick={handleStopRecording}
              >
                <Icon icon="square" size={20} />
                <span>停止录制</span>
              </button>
            </div>
          )}

          {/* Step 3: Recording completed, ready to upload */}
          {sessionId && !recording && (
            <div className="recording-complete">
              <div className="complete-icon"><Icon icon="checkCircle" size={48} /></div>
              <h3>录制完成</h3>

              <div className="recording-summary">
                <div className="summary-item">
                  <span className="label">Session ID:</span>
                  <span className="value">{sessionId}</span>
                </div>
                <div className="summary-item">
                  <span className="label">标题:</span>
                  <span className="value">{recordTitle}</span>
                </div>
                <div className="summary-item">
                  <span className="label">操作数量:</span>
                  <span className="value">{operationsCount} 个操作</span>
                </div>
                <div className="summary-item">
                  <span className="label">任务描述:</span>
                  <span className="value description">{recordDescription}</span>
                </div>
              </div>

              <div className="action-buttons">
                <button
                  className="btn btn-primary"
                  onClick={handleQuickGenerate}
                  disabled={uploading}
                >
                  <Icon icon="zap" size={16} />
                  <span>快速生成 Workflow</span>
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={handleUpload}
                  disabled={uploading}
                >
                  {uploading ? (
                    <>
                      <div className="btn-spinner"></div>
                      <span>上传中...</span>
                    </>
                  ) : (
                    <>
                      <Icon icon="upload" size={16} />
                      <span>上传到云端</span>
                    </>
                  )}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setSessionId("");
                    setOperationsCount(0);
                    setRecordTitle("");
                    setRecordDescription("");
                  }}
                  disabled={uploading}
                >
                  <Icon icon="refreshCw" size={16} />
                  <span>重新录制</span>
                </button>
              </div>

              <p className="upload-hint">
                ⚡ 快速生成：直接从录制操作生成可执行的Workflow<br />
                📤 上传到云端：进入对话生成 MetaFlow 流程
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="footer">
        <p>Ami v{version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );
}

export default RecordingPage;
