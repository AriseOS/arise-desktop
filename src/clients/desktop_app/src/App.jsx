import { useState, useEffect } from "react";
import "./App.css";
import "./extension.css";

// Import pages
import RecordingPage from "./pages/RecordingPage";
import QuickStartPage from "./pages/QuickStartPage";
import UserFlowsPage from "./pages/UserFlowsPage";
import GenerationPage from "./pages/GenerationPage";
import MyWorkflowsPage from "./pages/MyWorkflowsPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowGenerationPage from "./pages/WorkflowGenerationPage";
import WorkflowResultPage from "./pages/WorkflowResultPage";
import ExecutionMonitorPage from "./pages/ExecutionMonitorPage";
import ExecutionResultPage from "./pages/ExecutionResultPage";
import RecordingsLibraryPage from "./pages/RecordingsLibraryPage";
import RecordingDetailPage from "./pages/RecordingDetailPage";
import ConversationalGenerationPage from "./pages/ConversationalGenerationPage";
import MetaflowPreviewPage from "./pages/MetaflowPreviewPage";

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

  // Browser state
  const [browserOpening, setBrowserOpening] = useState(false);

  // Open browser handler
  const handleOpenBrowser = async () => {
    if (browserOpening) return;

    setBrowserOpening(true);
    showStatus("🌐 Opening browser...", "info");

    try {
      const response = await fetch(`${API_BASE}/api/browser/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ headless: false })
      });

      if (!response.ok) {
        throw new Error(`Failed to start browser: ${response.status}`);
      }

      const result = await response.json();

      if (result.status === "already_running") {
        showStatus("✅ Browser is already running", "success");
      } else {
        showStatus("✅ Browser opened successfully!", "success");
      }
    } catch (error) {
      console.error("Open browser error:", error);
      showStatus(`❌ Failed to open browser: ${error.message}`, "error");
    } finally {
      setBrowserOpening(false);
    }
  };

  // Check if user has workflows
  const [hasWorkflows, setHasWorkflows] = useState(false);
  const [recentWorkflows, setRecentWorkflows] = useState([]);

  const API_BASE = "http://127.0.0.1:8765";

  // Load dashboard data
  const fetchDashboard = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/dashboard`);

      if (!response.ok) {
        throw new Error(`Failed to fetch dashboard: ${response.status}`);
      }

      const data = await response.json();

      // Determine if user is returning user based on workflow count
      setHasWorkflows(data.has_workflows || data.total_workflows > 0);
      setRecentWorkflows(data.recent_workflows || []);
    } catch (error) {
      console.error('Error fetching dashboard:', error);
      // Default to new user experience on error
      setHasWorkflows(false);
      setRecentWorkflows([]);
    }
  };

  // Load dashboard data on mount and when returning to main page
  useEffect(() => {
    if (currentPage === "main") {
      fetchDashboard();
    }
  }, [currentPage]);

  // Main page for NEW users
  const renderNewUserHome = () => (
    <div className="page home-page new-user">
      <div className="home-hero">
        <div className="hero-icon">🤖</div>
        <h1 className="hero-title">Ami</h1>
        <p className="hero-subtitle">Let AI automate your repetitive work</p>
      </div>

      <div className="home-main-card">
        <h2 className="card-title">3 minutes to automate your workflow</h2>
        <p className="card-description">
          Just perform the task once, copy the data you need.<br/>
          Leave the rest to AI.
        </p>

        <div className="button-group">
          <button className="hero-button primary" onClick={() => navigate("quick-start")}>
            <span className="button-icon">🎬</span>
            <span>Start Recording</span>
          </button>

          <button
            className="hero-button secondary"
            onClick={handleOpenBrowser}
            disabled={browserOpening}
          >
            <span className="button-icon">🌐</span>
            <span>{browserOpening ? "Opening..." : "Open Browser"}</span>
          </button>
        </div>

        <a className="card-link" onClick={() => navigate("workflows")}>
          See what others are using it for →
        </a>
      </div>

      <button className="help-button" title="Help">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </button>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );

  // Main page for RETURNING users
  const renderReturningUserHome = () => (
    <div className="page home-page returning-user">
      <div className="page-header-simple">
        <div className="header-left">
          <div className="app-name">Ami</div>
        </div>
        <div className="header-right">
          <button className="icon-button" title="Settings">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 1v6m0 6v6"/>
            </svg>
          </button>
        </div>
      </div>

      <div className="home-content">
        {/* Quick Start Section */}
        <div className="quick-start-section">
          <div className="section-card">
            <div className="section-icon">🚀</div>
            <h2 className="section-title">Create new automation workflow</h2>
            <p className="section-subtitle">Perform once → Copy data → AI completes automatically</p>

            <div className="button-group">
              <button className="start-button primary" onClick={() => navigate("quick-start")}>
                <span className="button-icon">🎬</span>
                <span>Start Recording</span>
              </button>

              <button
                className="start-button secondary"
                onClick={handleOpenBrowser}
                disabled={browserOpening}
              >
                <span className="button-icon">🌐</span>
                <span>{browserOpening ? "Opening..." : "Open Browser"}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Recent Workflows Section */}
        <div className="recent-section">
          <div className="section-header-row">
            <h3>📌 Recent</h3>
            <a className="view-all-link" onClick={() => navigate("workflows")}>
              View All →
            </a>
          </div>

          <div className="recent-workflows">
            {recentWorkflows.map((workflow) => (
              <div key={workflow.id} className="recent-workflow-card">
                <div className="workflow-info-section">
                  <div className="workflow-status-icon">
                    {workflow.status === "success" ? "✅" : "⚠️"}
                  </div>
                  <div className="workflow-details">
                    <h4 className="workflow-name">{workflow.name}</h4>
                    <p className="workflow-last-run">
                      Last run: {workflow.lastRun} • {workflow.status === "success" ? "Success" : "Failed"}
                    </p>
                  </div>
                </div>
                <div className="workflow-action-buttons">
                  <button className="action-btn primary" onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="5 3 19 12 5 21 5 3"/>
                    </svg>
                    <span>Run</span>
                  </button>
                  <button className="action-btn secondary" onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <span>View Details</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="footer">
        <p>Ami v1.0.0</p>
      </div>
    </div>
  );

  // Main page
  const renderMainPage = () => {
    return hasWorkflows ? renderReturningUserHome() : renderNewUserHome();
  };

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

      case "quick-start":
        return (
          <QuickStartPage
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "user-flows":
        return (
          <UserFlowsPage
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

      case "workflow-generation":
        return (
          <WorkflowGenerationPage
            currentUser={{ token: null }}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams}
          />
        );

      case "execution-monitor":
        return (
          <ExecutionMonitorPage
            onNavigate={navigate}
            showStatus={showStatus}
            workflowId={pageParams.workflowId}
            workflowName={pageParams.workflowName}
            initialStatus={pageParams.status}
            initialSteps={pageParams.steps}
          />
        );

      case "execution-result":
        return (
          <ExecutionResultPage
            onNavigate={navigate}
            showStatus={showStatus}
            workflowId={pageParams.workflowId}
            executionId={pageParams.executionId}
          />
        );

      case "recordings-library":
        return (
          <RecordingsLibraryPage
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "recording-detail":
        return (
          <RecordingDetailPage
            onNavigate={navigate}
            showStatus={showStatus}
            sessionId={pageParams.sessionId}
          />
        );

      case "conversational-generation":
        return (
          <ConversationalGenerationPage
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "metaflow-preview":
        return (
          <MetaflowPreviewPage
            onNavigate={navigate}
            showStatus={showStatus}
            metaflowId={pageParams.metaflowId}
            metaflowYaml={pageParams.metaflowYaml}
          />
        );

      default:
        return renderMainPage();
    }
  };

  // Bottom navigation bar
  const renderBottomNav = () => {
    // Hide navigation on certain pages
    const hideNavPages = ["quick-start", "recording", "execution-monitor", "execution-result"];
    if (hideNavPages.includes(currentPage)) {
      return null;
    }

    const navItems = [
      { id: "quick-start", icon: "🎬", label: "Record" },
      { id: "workflows", icon: "📋", label: "Workflows" },
      { id: "recordings-library", icon: "📹", label: "Recordings" },
      { id: "conversational-generation", icon: "💬", label: "AI Chat" }
    ];

    return (
      <nav className="bottom-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => navigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </nav>
    );
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
      <div className="app-content">
        {renderPage()}
      </div>

      {/* Bottom Navigation */}
      {renderBottomNav()}
    </div>
  );
}

export default App;
