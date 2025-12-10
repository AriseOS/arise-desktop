import { useState, useEffect } from "react";
import "./App.css";
import "./extension.css";
import Icon from "./components/Icons";

// Import utilities
import { auth } from "./utils/auth";
import { api } from "./utils/api";

// Import pages
import SetupPage from "./pages/SetupPage";
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
import WorkflowExecutionLivePage from "./pages/WorkflowExecutionLivePage";
import ScraperOptimizationPage from "./pages/ScraperOptimizationPage";

// Import setup styles
import "./styles/SetupPage.css";

function App() {
  // Setup state
  const [setupComplete, setSetupComplete] = useState(false);
  const [setupChecking, setSetupChecking] = useState(true);

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

  // Check setup status on mount
  useEffect(() => {
    checkSetupStatus();
  }, []);

  const checkSetupStatus = async () => {
    try {
      const response = await api.get("/api/browser/installation-status");
      if (response.status === "ready") {
        setSetupComplete(true);
        // Once setup is complete, check login status
        checkLoginStatus();
      } else {
        // Setup not complete, show setup page
        setSetupComplete(false);
      }
    } catch (error) {
      console.error("[App] Failed to check setup status:", error);
      // Assume setup needed
      setSetupComplete(false);
    } finally {
      setSetupChecking(false);
    }
  };

  const handleSetupComplete = () => {
    setSetupComplete(true);
    // After setup, check login status
    checkLoginStatus();
  };

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

  const handleLogout = async () => {
    // Clear local state
    setIsLoggedIn(false);
    setSession(null);
    setHasWorkflows(false);
    setRecentWorkflows([]);

    // Navigate to login page
    navigate('login');

    console.log('[App] User logged out');
  };

  // Browser state
  const [browserOpening, setBrowserOpening] = useState(false);

  // Open browser handler
  const handleOpenBrowser = async () => {
    if (browserOpening) return;

    setBrowserOpening(true);
    showStatus("Opening browser...", "info");

    try {
      const result = await api.startBrowser(false);

      if (result.status === "already_running") {
        showStatus("Browser is already running", "success");
      } else {
        showStatus("Browser opened successfully!", "success");
      }
    } catch (error) {
      console.error("Open browser error:", error);
      showStatus(`Failed to open browser: ${error.message}`, "error");
    } finally {
      setBrowserOpening(false);
    }
  };

  // Check if user has workflows
  const [hasWorkflows, setHasWorkflows] = useState(false);
  const [recentWorkflows, setRecentWorkflows] = useState([]);
  const [dashboardLoading, setDashboardLoading] = useState(true);

  // Load dashboard data
  const fetchDashboard = async () => {
    if (!session?.username) {
      console.log('[App] Cannot fetch dashboard: user not logged in');
      setHasWorkflows(false);
      setRecentWorkflows([]);
      return;
    }

    try {
      const data = await api.getDashboard(session.username);

      // Determine if user is returning user based on workflow count
      setHasWorkflows(data.has_workflows || data.total_workflows > 0);
      setRecentWorkflows(data.recent_workflows || []);
    } catch (error) {
      console.error('Error fetching dashboard:', error);
      // Default to new user experience on error
      setHasWorkflows(false);
      setRecentWorkflows([]);
    } finally {
      setDashboardLoading(false);
    }
  };

  // Load dashboard data on mount and when returning to main page
  useEffect(() => {
    if (currentPage === "main" && session?.username) {
      fetchDashboard();
    }
  }, [currentPage, session?.username]);

  // Main page for NEW users
  const renderNewUserHome = () => (
    <div className="page home-page new-user fade-in">
      <div className="home-hero">

        <h1 className="hero-title">Welcome to Ami</h1>
        <p className="hero-subtitle">Let AI automate your repetitive work</p>
      </div>

      <div className="card home-main-card" style={{ padding: '40px', maxWidth: '600px', margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '16px' }}>Start your first automation</h2>
        <p style={{ textAlign: 'center', marginBottom: '32px', color: 'var(--text-secondary)' }}>
          Just perform the task once, copy the data you need.<br />
          Leave the rest to AI.
        </p>

        <div className="flex-row" style={{ gap: '20px', justifyContent: 'center' }}>
          <button className="btn btn-primary" onClick={() => navigate("quick-start")} style={{ padding: '12px 24px', fontSize: '16px', minWidth: '180px', justifyContent: 'center' }}>
            <Icon name="record" size={20} />
            <span>Start Recording</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={handleOpenBrowser}
            disabled={browserOpening}
            style={{ padding: '12px 24px', fontSize: '16px', minWidth: '180px', justifyContent: 'center' }}
          >
            <Icon name="browser" size={20} />
            <span>{browserOpening ? "Opening..." : "Open Browser"}</span>
          </button>
        </div>

        <div style={{ textAlign: 'center', marginTop: '24px' }}>
          <a style={{ color: 'var(--primary-main)', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }} onClick={() => navigate("workflows")}>
            See what others are using it for →
          </a>
        </div>
      </div>

      <button className="btn btn-secondary" title="Help" style={{ position: 'fixed', bottom: '30px', right: '30px', borderRadius: '50%', width: '48px', height: '48px', padding: 0 }}>
        <Icon name="help" size={24} />
      </button>

      <button
        className="btn-icon-ghost"
        title="Settings"
        onClick={() => navigate("settings")}
        style={{ position: 'absolute', top: '20px', right: '20px' }}
      >
        <Icon name="settings" size={24} />
      </button>

      <div className="footer" style={{ textAlign: 'center', marginTop: '40px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
        <p>Ami v1.0.0 • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );

  // Main page for RETURNING users
  const renderReturningUserHome = () => (
    <div className="page home-page returning-user fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Good Morning, {session?.username || 'User'}</h1>
          <p className="page-subtitle">Ready to automate your work?</p>
        </div>
        <button
          className="btn-icon"
          title="Settings"
          onClick={() => navigate("settings")}
        >
          <Icon name="settings" size={24} />
        </button>
      </div>

      <div className="home-content">
        {/* Quick Start Section */}
        <div className="card" style={{ padding: '24px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ fontSize: '20px', marginBottom: '8px' }}>Create new workflow</h2>
            <p style={{ margin: 0 }}>Record your actions and let AI learn from them.</p>
          </div>
          <div className="flex-row" style={{ gap: '12px' }}>
            <button className="btn btn-primary" onClick={() => navigate("quick-start")} style={{ minWidth: '140px', justifyContent: 'center' }}>
              <Icon name="record" size={18} />
              <span>Start Recording</span>
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleOpenBrowser}
              disabled={browserOpening}
              style={{ minWidth: '140px', justifyContent: 'center' }}
            >
              <Icon name="browser" size={18} />
              <span>{browserOpening ? "Opening..." : "Open Browser"}</span>
            </button>
          </div>
        </div>

        {/* Recent Workflows Section */}
        <div className="recent-section">
          <div className="flex-row" style={{ justifyContent: 'space-between', marginBottom: '16px', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>Recent Workflows</h3>
            <a style={{ color: 'var(--primary-main)', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }} onClick={() => navigate("workflows")}>
              View All
            </a>
          </div>

          <div className="recent-workflows flex-col" style={{ gap: '12px' }}>
            {recentWorkflows.map((workflow) => (
              <div key={workflow.id} className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderRadius: 'var(--radius-lg)' }}>
                <div className="flex-row" style={{ gap: '16px', alignItems: 'center' }}>
                  <div style={{
                    width: '40px', height: '40px',
                    borderRadius: '50%',
                    backgroundColor: workflow.status === "success" ? 'var(--status-success-bg)' : 'var(--status-warning-bg)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: workflow.status === "success" ? 'var(--status-success-text)' : 'var(--status-warning-text)'
                  }}>
                    <Icon name={workflow.status === "success" ? "check" : "alert"} size={20} />
                  </div>
                  <div>
                    <h4 style={{ fontSize: '16px', margin: '0 0 4px 0' }}>{workflow.name}</h4>
                    <p style={{ fontSize: '13px', margin: 0 }}>
                      Last run: {workflow.lastRun}
                    </p>
                  </div>
                </div>
                <div className="flex-row" style={{ gap: '8px' }}>
                  <button className="btn btn-primary" style={{ padding: '8px 16px', fontSize: '13px' }} onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <Icon name="play" size={14} />
                    <span>Run</span>
                  </button>
                  <button className="btn btn-secondary" style={{ padding: '8px 16px', fontSize: '13px' }} onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <span>Details</span>
                  </button>
                </div>
              </div>
            ))}
            {recentWorkflows.length === 0 && (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                No recent workflows found.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  // Main page
  const renderMainPage = () => {
    if (dashboardLoading) {
      return (
        <div className="page auth-loading-page flex-center" style={{ height: '100vh' }}>
          <div className="auth-loading flex-col" style={{ alignItems: 'center', gap: '16px' }}>
            <div className="loading-spinner"></div>
            <p>Loading Dashboard...</p>
          </div>
        </div>
      );
    }
    return hasWorkflows ? renderReturningUserHome() : renderNewUserHome();
  };

  // Render current page
  const renderPage = () => {
    // Show loading while checking setup
    if (setupChecking) {
      return (
        <div className="page auth-loading-page flex-center" style={{ height: '100vh' }}>
          <div className="auth-loading flex-col" style={{ alignItems: 'center', gap: '16px' }}>
            <div className="loading-spinner"></div>
            <p>Loading...</p>
          </div>
        </div>
      );
    }

    // Show setup page if setup not complete
    if (!setupComplete) {
      return <SetupPage onSetupComplete={handleSetupComplete} />;
    }

    // Show loading while checking auth
    if (authChecking) {
      return (
        <div className="page auth-loading-page flex-center" style={{ height: '100vh' }}>
          <div className="auth-loading flex-col" style={{ alignItems: 'center', gap: '16px' }}>
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
            onLogout={handleLogout}
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

      case "workflow-execution-live":
        return (
          <WorkflowExecutionLivePage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            taskId={pageParams.taskId}
            workflowName={pageParams.workflowName}
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

      case "scraper-optimization":
        return (
          <ScraperOptimizationPage
            session={session}
            pageParams={pageParams}
            onNavigate={navigate}
            showStatus={showStatus}
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
      { id: "quick-start", icon: "record", label: "Record" },
      { id: "workflows", icon: "workflows", label: "Workflows" },
      { id: "recordings-library", icon: "library", label: "Library" },
      { id: "data-management", icon: "data", label: "Data" },
      { id: "conversational-generation", icon: "chat", label: "AI Chat" }
    ];

    return (
      <nav className="bottom-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => navigate(item.id)}
          >
            <span className="nav-icon">
              <Icon name={item.icon} size={24} />
            </span>
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
          {statusType === 'success' && <Icon name="check" size={16} />}
          {statusType === 'error' && <Icon name="alert" size={16} />}
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
