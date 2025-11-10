import { useState } from "react";
import "./App.css";
import "./extension.css";

// Import pages
import RecordingPage from "./pages/RecordingPage";
import GenerationPage from "./pages/GenerationPage";
import MyWorkflowsPage from "./pages/MyWorkflowsPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowResultPage from "./pages/WorkflowResultPage";

function App() {
  // Navigation state
  const [currentPage, setCurrentPage] = useState("main");
  const [pageParams, setPageParams] = useState({});

  // Status message
  const [statusMessage, setStatusMessage] = useState("");
  const [statusType, setStatusType] = useState("info");

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

  // Main page
  const renderMainPage = () => (
    <div className="page main-page">
      <div className="page-header">
        <div className="page-title">🤖 AgentCrafter Desktop</div>
      </div>

      <div className="main-content">
        <div className="welcome-section">
          <h2>欢迎使用 AgentCrafter</h2>
          <p>通过录制浏览器操作，自动生成可执行的工作流</p>
        </div>

        <div className="action-cards">
          <div className="action-card" onClick={() => navigate("recording")}>
            <div className="card-icon">📹</div>
            <div className="card-title">录制操作</div>
            <div className="card-desc">
              录制浏览器操作并上传
            </div>
            <div className="card-arrow">→</div>
          </div>

          <div className="action-card primary" onClick={() => navigate("generation")}>
            <div className="card-icon">🤖</div>
            <div className="card-title">生成 Workflow</div>
            <div className="card-desc">
              描述任务，AI 生成工作流
            </div>
            <div className="card-arrow">→</div>
          </div>

          <div className="action-card" onClick={() => navigate("workflows")}>
            <div className="card-icon">📋</div>
            <div className="card-title">我的 Workflow</div>
            <div className="card-desc">
              查看和管理已创建的工作流
            </div>
            <div className="card-arrow">→</div>
          </div>
        </div>

        <div className="workflow-info">
          <h3>三种使用方式</h3>
          <div className="info-grid">
            <div className="info-item">
              <div className="info-icon">📹</div>
              <div className="info-title">录制操作</div>
              <div className="info-desc">录制浏览器操作并上传到云端，供 AI 学习和分析</div>
            </div>
            <div className="info-item">
              <div className="info-icon">🤖</div>
              <div className="info-title">生成 Workflow</div>
              <div className="info-desc">描述你的任务，AI 自动生成 MetaFlow 和可执行的 Workflow</div>
            </div>
            <div className="info-item">
              <div className="info-icon">📋</div>
              <div className="info-title">管理和执行</div>
              <div className="info-desc">查看、执行和管理你的 Workflow，查看执行结果</div>
            </div>
          </div>
        </div>
      </div>

      <div className="footer">
        <p>AgentCrafter v1.0.0 - Powered by BaseAgent</p>
      </div>
    </div>
  );

  // Render current page
  const renderPage = () => {
    switch (currentPage) {
      case "main":
        return renderMainPage();

      case "recording":
        return (
          <RecordingPage
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "generation":
        return (
          <GenerationPage
            onNavigate={navigate}
            showStatus={showStatus}
            params={pageParams}
          />
        );

      case "workflows":
        return (
          <MyWorkflowsPage
            currentUser={{ token: null }}
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
