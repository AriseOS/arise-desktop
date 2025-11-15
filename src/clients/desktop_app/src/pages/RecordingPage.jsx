import React, { useState } from 'react';

const API_BASE = "http://127.0.0.1:8765";
const DEFAULT_USER = "default_user";

function RecordingPage({ onNavigate, showStatus }) {
  const [recordUrl, setRecordUrl] = useState("https://www.google.com");
  const [recordTitle, setRecordTitle] = useState("");
  const [recordDescription, setRecordDescription] = useState("");

  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [operationsCount, setOperationsCount] = useState(0);

  const [uploading, setUploading] = useState(false);
  const [quickGenerating, setQuickGenerating] = useState(false);

  // Start recording
  const handleStartRecording = async () => {
    if (!recordUrl || !recordTitle || !recordDescription) {
      showStatus("⚠️ 请填写所有必填项", "error");
      return;
    }

    try {
      showStatus("🎬 启动录制...", "info");

      const response = await fetch(`${API_BASE}/api/recording/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: recordUrl,
          title: recordTitle,
          description: recordDescription,
          task_metadata: { task_description: recordDescription }
        })
      });

      if (!response.ok) throw new Error(`API error: ${response.status}`);

      const result = await response.json();
      setRecording(true);
      setSessionId(result.session_id);
      showStatus("✅ 录制已开始！请在浏览器中操作", "success");
    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`❌ 启动录制失败: ${error.message}`, "error");
    }
  };

  // Stop recording
  const handleStopRecording = async () => {
    try {
      showStatus("⏹️ 停止录制...", "info");

      const response = await fetch(`${API_BASE}/api/recording/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      if (!response.ok) throw new Error(`API error: ${response.status}`);

      const result = await response.json();
      setRecording(false);
      setOperationsCount(result.operations_count);
      showStatus(`✅ 录制完成！捕获了 ${result.operations_count} 个操作`, "success");
    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`❌ 停止录制失败: ${error.message}`, "error");
      setRecording(false);
    }
  };

  // Upload recording
  const handleUpload = async () => {
    if (!sessionId) {
      showStatus("⚠️ 没有可上传的录制", "error");
      return;
    }

    try {
      setUploading(true);
      showStatus("📤 上传录制到云端...", "info");

      const response = await fetch(`${API_BASE}/api/recordings/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: recordDescription,
          user_id: DEFAULT_USER
        })
      });

      if (!response.ok) throw new Error("Upload failed");

      const result = await response.json();
      showStatus("✅ 上传成功！录制已保存到云端", "success");

      // Return to main page after successful upload
      setTimeout(() => {
        onNavigate("main");
      }, 2000);
    } catch (error) {
      console.error("Upload error:", error);
      showStatus(`❌ 上传失败: ${error.message}`, "error");
    } finally {
      setUploading(false);
    }
  };

  // Generate MetaFlow from recording
  const handleQuickGenerate = async () => {
    if (!sessionId) {
      showStatus("⚠️ 没有可生成MetaFlow的录制", "error");
      return;
    }

    try {
      setQuickGenerating(true);

      // Generate MetaFlow from recording
      showStatus("⚡ 正在生成MetaFlow...", "info");

      const metaflowResponse = await fetch(`${API_BASE}/api/metaflows/from-recording`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: recordDescription,
          user_id: DEFAULT_USER
        })
      });

      if (!metaflowResponse.ok) {
        throw new Error("MetaFlow generation failed");
      }

      const metaflowResult = await metaflowResponse.json();
      showStatus("✅ MetaFlow生成成功！正在跳转预览...", "success");

      // Navigate to MetaFlow preview page (user will review and generate workflow from there)
      setTimeout(() => {
        onNavigate("metaflow-preview", {
          metaflowId: metaflowResult.metaflow_id,
          metaflowYaml: metaflowResult.metaflow_yaml
        });
      }, 500);
    } catch (error) {
      console.error("Generate MetaFlow error:", error);
      showStatus(`❌ 生成失败: ${error.message}`, "error");
    } finally {
      setQuickGenerating(false);
    }
  };

  return (
    <div className="page record-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate("main")} disabled={recording}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">录制 Workflow</div>
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
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="12" r="8"></circle>
                </svg>
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
              <p className="recording-hint">
                请在自动打开的浏览器窗口中执行操作<br/>
                完成后点击下方按钮停止录制
              </p>
              <p className="session-info">Session ID: {sessionId}</p>

              <button
                className="start-record-button recording"
                onClick={handleStopRecording}
              >
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12"></rect>
                </svg>
                <span>停止录制</span>
              </button>
            </div>
          )}

          {/* Step 3: Recording completed, ready to upload */}
          {sessionId && !recording && (
            <div className="recording-complete">
              <div className="complete-icon">✅</div>
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
                  disabled={quickGenerating || uploading}
                >
                  {quickGenerating ? "生成中..." : "⚡ 快速生成 Workflow"}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={handleUpload}
                  disabled={uploading || quickGenerating}
                >
                  {uploading ? "上传中..." : "📤 上传到云端"}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setSessionId("");
                    setOperationsCount(0);
                    setRecordTitle("");
                    setRecordDescription("");
                  }}
                  disabled={uploading || quickGenerating}
                >
                  🔄 重新录制
                </button>
              </div>

              <p className="upload-hint">
                ⚡ 快速生成：直接从录制操作生成可执行的Workflow<br/>
                📤 上传到云端：进入对话生成 MetaFlow 流程
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );
}

export default RecordingPage;
