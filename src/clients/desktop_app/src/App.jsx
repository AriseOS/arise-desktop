import { useState, useEffect } from "react";
import "./App.css";
import "./extension.css";

// Import pages
import MyWorkflowsPage from "./pages/MyWorkflowsPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowResultPage from "./pages/WorkflowResultPage";

// API base URL
const API_BASE = "http://127.0.0.1:8765";
const DEFAULT_USER = "default_user";

function App() {
  // Navigation state
  const [currentPage, setCurrentPage] = useState("main");
  const [pageParams, setPageParams] = useState({});

  // Status message
  const [statusMessage, setStatusMessage] = useState("");
  const [statusType, setStatusType] = useState("info"); // 'info' | 'success' | 'error'

  // Recording state
  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [recordUrl, setRecordUrl] = useState("https://www.google.com");
  const [recordTitle, setRecordTitle] = useState("");
  const [recordDescription, setRecordDescription] = useState("");

  // Workflow generation state
  const [metaflowId, setMetaflowId] = useState("");
  const [workflowName, setWorkflowName] = useState("");

  // Show status message
  const showStatus = (message, type = "info") => {
    setStatusMessage(message);
    setStatusType(type);
    setTimeout(() => setStatusMessage(""), 5000);
  };

  // Navigation helper
  const navigate = (page, params = {}) => {
    setCurrentPage(page);
    setPageParams(params);
  };

  // Recording: Start
  const handleStartRecording = async () => {
    if (!recordUrl || !recordTitle) {
      showStatus("⚠️ Please fill in URL and title", "error");
      return;
    }

    try {
      showStatus("🎬 Starting recording...", "info");

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

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      setRecording(true);
      setSessionId(result.session_id);
      showStatus("✅ Recording started! Perform actions in browser", "success");
    } catch (error) {
      console.error("Start recording error:", error);
      showStatus(`❌ Failed to start recording: ${error.message}`, "error");
    }
  };

  // Recording: Stop
  const handleStopRecording = async () => {
    try {
      showStatus("⏹️ Stopping recording...", "info");

      const response = await fetch(`${API_BASE}/api/recording/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      setRecording(false);
      showStatus(`✅ Recording stopped: ${result.operations_count} operations captured`, "success");
    } catch (error) {
      console.error("Stop recording error:", error);
      showStatus(`❌ Failed to stop recording: ${error.message}`, "error");
      setRecording(false);
    }
  };

  // Generate workflow (3-step flow)
  const handleGenerateWorkflow = async () => {
    if (!sessionId || !recordDescription) {
      showStatus("⚠️ Please complete recording first", "error");
      return;
    }

    try {
      // Step 1: Upload recording
      showStatus("📤 Uploading recording to cloud...", "info");
      const uploadResponse = await fetch(`${API_BASE}/api/recordings/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_description: recordDescription,
          user_id: DEFAULT_USER
        })
      });

      if (!uploadResponse.ok) throw new Error("Upload failed");
      const uploadResult = await uploadResponse.json();
      console.log("Upload result:", uploadResult);

      // Step 2: Generate MetaFlow
      showStatus("🔄 Generating MetaFlow... (30-60s)", "info");
      const metaflowResponse = await fetch(`${API_BASE}/api/metaflows/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_description: recordDescription,
          user_id: DEFAULT_USER
        })
      });

      if (!metaflowResponse.ok) throw new Error("MetaFlow generation failed");
      const metaflowResult = await metaflowResponse.json();
      setMetaflowId(metaflowResult.metaflow_id);
      console.log("MetaFlow result:", metaflowResult);

      // Step 3: Generate Workflow
      showStatus("⚙️ Generating Workflow... (30-60s)", "info");
      const workflowResponse = await fetch(`${API_BASE}/api/workflows/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metaflow_id: metaflowResult.metaflow_id,
          user_id: DEFAULT_USER
        })
      });

      if (!workflowResponse.ok) throw new Error("Workflow generation failed");
      const workflowResult = await workflowResponse.json();
      setWorkflowName(workflowResult.workflow_name);

      showStatus(`✅ Workflow generated: ${workflowResult.workflow_name}`, "success");

      // Clear form
      setSessionId("");
      setRecordTitle("");
      setRecordDescription("");

      // Navigate to workflows page
      setTimeout(() => navigate("workflows"), 2000);
    } catch (error) {
      console.error("Generate workflow error:", error);
      showStatus(`❌ Failed to generate workflow: ${error.message}`, "error");
    }
  };

  // Main page content
  const renderMainPage = () => (
    <div className="page main-page">
      <div className="page-header">
        <div className="page-title">🤖 AgentCrafter Desktop</div>
      </div>

      <div className="main-content">
        <div className="action-cards">
          <div className="action-card" onClick={() => navigate("record")}>
            <div className="card-icon">📹</div>
            <div className="card-title">录制 Workflow</div>
            <div className="card-desc">通过浏览器操作录制自动化流程</div>
          </div>

          <div className="action-card" onClick={() => navigate("workflows")}>
            <div className="card-icon">📋</div>
            <div className="card-title">我的 Workflows</div>
            <div className="card-desc">查看和管理已创建的工作流</div>
          </div>
        </div>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0</p>
      </div>
    </div>
  );

  // Record page content
  const renderRecordPage = () => (
    <div className="page record-page">
      <div className="page-header">
        <button className="back-button" onClick={() => navigate("main")} disabled={recording}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="page-title">录制 Workflow</div>
      </div>

      <div className="record-content">
        <div className="record-form">
          {!recording && !sessionId && (
            <div className="form-section">
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
                  <span>功能描述 <span className="required">*</span></span>
                  <span className="input-hint">{recordDescription.length}/500</span>
                </label>
                <textarea
                  value={recordDescription}
                  onChange={(e) => setRecordDescription(e.target.value)}
                  placeholder="详细描述这个工作流要完成什么任务..."
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

          {recording && (
            <div className="recording-status">
              <div className="recording-indicator">
                <div className="recording-dot"></div>
                <span>录制中...</span>
              </div>
              <p>请在浏览器中执行操作，完成后点击停止录制</p>
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

          {sessionId && !recording && (
            <div className="generation-section">
              <h3>✅ 录制完成</h3>
              <p>Session ID: {sessionId}</p>
              <button
                className="start-record-button"
                onClick={handleGenerateWorkflow}
              >
                ✨ 生成 Workflow
              </button>
              <p className="note">注意：生成过程需要 1-2 分钟</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  // Render current page
  const renderPage = () => {
    switch (currentPage) {
      case "main":
        return renderMainPage();
      case "record":
        return renderRecordPage();
      case "workflows":
        return (
          <MyWorkflowsPage
            currentUser={{ token: null }} // No auth needed
            onNavigate={navigate}
            onLogout={() => {}}
          />
        );
      case "workflow-detail":
        return (
          <WorkflowDetailPage
            currentUser={{ token: null }}
            workflowId={pageParams.workflowId}
            onNavigate={navigate}
            showStatus={showStatus}
            onLogout={() => {}}
          />
        );
      case "workflow-result":
        return (
          <WorkflowResultPage
            currentUser={{ token: null }}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams.recordingData}
          />
        );
      default:
        return renderMainPage();
    }
  };

  return (
    <div className="app">
      {/* Status Message */}
      {statusMessage && (
        <div className={`status-message status-${statusType}`}>
          {statusMessage}
        </div>
      )}

      {/* Page Content */}
      {renderPage()}
    </div>
  );
}

export default App;
