import { useState, useEffect } from "react";
import "./App.css";
import "./extension.css";

// Import utilities
import { auth } from "./utils/auth";
import { api } from "./utils/api";

// Import pages
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";
import RecordingPage from "./pages/RecordingPage";
import QuickStartPage from "./pages/QuickStartPage";
import RecordingAnalysisPage from "./pages/RecordingAnalysisPage";
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
import DataManagementPage from "./pages/DataManagementPage";
import CollectionDetailPage from "./pages/CollectionDetailPage";

function App() {
  // Auth state
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [session, setSession] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);

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

  // Check login status on mount
  useEffect(() => {
    checkLoginStatus();
  }, []);

  const checkLoginStatus = async () => {
    try {
      const loggedIn = await auth.isLoggedIn();
      setIsLoggedIn(loggedIn);

      if (loggedIn) {
        const sessionData = await auth.getSession();
        setSession(sessionData);
        console.log('[App] User is logged in:', sessionData?.username);
      } else {
        console.log('[App] User is not logged in');
      }
    } catch (error) {
      console.error('[App] Failed to check login status:', error);
      setIsLoggedIn(false);
    } finally {
      setAuthChecking(false);
    }
  };

  const handleLoginSuccess = async () => {
    await checkLoginStatus();
  };

  const handleRegisterSuccess = async () => {
    await checkLoginStatus();
  };

  // Browser state
  const [browserOpening, setBrowserOpening] = useState(false);

  // Open browser handler
  const handleOpenBrowser = async () => {
    if (browserOpening) return;

    setBrowserOpening(true);
    showStatus("🌐 Opening browser...", "info");

    try {
      const result = await api.startBrowser(false);

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

  // Load dashboard data
  const fetchDashboard = async () => {
    try {
      const data = await api.getDashboard();

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
          Just perform the task once, copy the data you need.<br />
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
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </button>

      <button
        className="settings-button"
        title="Settings"
        onClick={() => navigate("settings")}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v6m0 6v6M6 12H1m6 0h6m6 0h4" />
        </svg>
      </button>

      <div className="footer">
        <p>Ami v1.0.0 • {session?.username && `Logged in as ${session.username}`}</p>
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
          <button
            className="icon-button"
            title="Settings"
            onClick={() => navigate("settings")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v6m0 6v6M6 12H1m6 0h6m6 0h4" />
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
                      <polygon points="5 3 19 12 5 21 5 3" />
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
        <p>Ami v1.0.0 • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );

  // Main page
  const renderMainPage = () => {
    return hasWorkflows ? renderReturningUserHome() : renderNewUserHome();
  };

  // Render current page
  const renderPage = () => {
    // Show loading while checking auth
    if (authChecking) {
      return (
        <div className="page auth-loading-page">
          <div className="auth-loading">
            <div className="loading-spinner"></div>
            <p>Loading...</p>
          </div>
        </div>
      );
    }

    // Show login/register pages if not logged in
    if (!isLoggedIn) {
      if (currentPage === 'register') {
        return (
          <RegisterPage
            navigate={navigate}
            showStatus={showStatus}
            onRegisterSuccess={handleRegisterSuccess}
          />
        );
      }
      // Default to login page for all routes when not logged in
      return (
        <LoginPage
          navigate={navigate}
          showStatus={showStatus}
          onLoginSuccess={handleLoginSuccess}
        />
      );
    }

    // User is logged in, show app pages
    switch (currentPage) {
      case "login":
      case "register":
        // Redirect to main if trying to access login/register while logged in
        navigate("main");
        return renderMainPage();

      case "settings":
        return (
          <SettingsPage
            navigate={navigate}
            showStatus={showStatus}
          />
        );

      case "main":
        return renderMainPage();

      case "recording":
        return (
          <RecordingPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "quick-start":
        return (
          <QuickStartPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "user-flows":
        return (
          <UserFlowsPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "generation":
        return (
          <GenerationPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            params={pageParams}
          />
        );

      case "workflows":
        return (
          <MyWorkflowsPage
            session={session}
            onNavigate={navigate}
            onLogout={() => { }}
          />
        );

      case "workflow-detail":
        return (
          <WorkflowDetailPage
            session={session}
            workflowId={pageParams.workflowId}
            autoRun={pageParams.autoRun}
            onNavigate={navigate}
            showStatus={showStatus}
            onLogout={() => { }}
          />
        );

      case "workflow-result":
        return (
          <WorkflowResultPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams.recordingData}
          />
        );

      case "workflow-generation":
        return (
          <WorkflowGenerationPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams}
          />
        );

      case "execution-monitor":
        return (
          <ExecutionMonitorPage
            session={session}
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
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            workflowId={pageParams.workflowId}
            executionId={pageParams.executionId}
          />
        );

      case "recordings-library":
        return (
          <RecordingsLibraryPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "recording-detail":
        return (
          <RecordingDetailPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            sessionId={pageParams.sessionId}
          />
        );

      case "conversational-generation":
        return (
          <ConversationalGenerationPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "recording-analysis":
        return (
          <RecordingAnalysisPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            pageData={pageParams}
          />
        );

      case "metaflow-preview":
        return (
          <MetaflowPreviewPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            metaflowId={pageParams.metaflowId}
            metaflowYaml={pageParams.metaflowYaml}
          />
        );

      case "data-management":
        return (
          <DataManagementPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "collection-detail":
        return (
          <CollectionDetailPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            collectionName={pageParams.collectionName}
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
      { id: "data-management", icon: "💾", label: "Data" },
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
