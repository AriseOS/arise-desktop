import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import "./App.css";
import "./extension.css";
import Icon from "./components/Icons";

// Import utilities
import { auth } from "./utils/auth";
import { api, onConnectionError } from "./utils/api";
import { useAgentStore, useBrowserTabStore } from "./store";

// Import pages
import SetupPage from "./pages/SetupPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";
import RecordingReplayPage from "./pages/RecordingReplayPage";
import QuickStartPage from "./pages/QuickStartPage";
import RecordingAnalysisPage from "./pages/RecordingAnalysisPage";
import GenerationPage from "./pages/GenerationPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowGenerationPage from "./pages/WorkflowGenerationPage";
import WorkflowResultPage from "./pages/WorkflowResultPage";
import ExecutionMonitorPage from "./pages/ExecutionMonitorPage";
import ExecutionResultPage from "./pages/ExecutionResultPage";
import RecordingsLibraryPage from "./pages/RecordingsLibraryPage";
import RecordingDetailPage from "./pages/RecordingDetailPage";
import CognitivePhrasesPage from "./pages/CognitivePhrasesPage";
import CognitivePhraseDetailPage from "./pages/CognitivePhraseDetailPage";
// MetaflowPreviewPage removed - MetaFlow is now internal, users work with Workflows directly
// DataManagementPage removed - Data is now per-workflow, see WorkflowDetailPage "Data" tab
import WorkflowExecutionLivePage from "./pages/WorkflowExecutionLivePage";
import DocsPage from "./pages/DocsPage";
import BackendErrorPage from "./pages/BackendErrorPage";
import AgentPage from "./pages/AgentPage";
import MemoryPage from "./pages/MemoryPage";
import HomePage from "./pages/HomePage";
import ExplorePage from "./pages/ExplorePage";
import BrowserPage from "./pages/BrowserPage";

// Import setup styles
import "./styles/SetupPage.css";

function App() {
  const { t, i18n } = useTranslation();
  // Setup state
  const [setupComplete, setSetupComplete] = useState(false);
  const [setupChecking, setSetupChecking] = useState(true);
  const [backendChecking, setBackendChecking] = useState(false);
  const [backendError, setBackendError] = useState(false);

  // Refs to access current state in callbacks
  const setupCompleteRef = useRef(false);
  const backendErrorRef = useRef(false);

  // Keep refs in sync with state
  useEffect(() => {
    setupCompleteRef.current = setupComplete;
  }, [setupComplete]);

  useEffect(() => {
    backendErrorRef.current = backendError;
  }, [backendError]);

  // Version check state
  const [versionInfo, setVersionInfo] = useState(null);
  const [updateRequired, setUpdateRequired] = useState(false);

  // Diagnostic upload state
  const [diagnosticUploading, setDiagnosticUploading] = useState(false);
  const [diagnosticModalOpen, setDiagnosticModalOpen] = useState(false);
  const [diagnosticDescription, setDiagnosticDescription] = useState("");

  // Live browser auto-navigation — when agent starts browsing, navigate to browser page
  const activeTaskId = useAgentStore((state) => state.activeTaskId);
  const browserViewId = useAgentStore((state) => {
    const t = state.activeTaskId ? state.tasks[state.activeTaskId] : null;
    return t?.browserViewId || null;
  });

  // Upload diagnostic package - Step 1: Open Modal
  const handleUploadDiagnostic = () => {
    if (diagnosticUploading) return;
    setDiagnosticDescription("");
    setDiagnosticModalOpen(true);
  };

  // Upload diagnostic package - Step 2: Confirm Upload
  const confirmUploadDiagnostic = async () => {
    setDiagnosticModalOpen(false);
    setDiagnosticUploading(true);
    setDiagnosticUploading(true);
    showStatus(t('app.collectingData'), "info");

    try {
      const result = await api.uploadDiagnostic(diagnosticDescription);
      if (result.success) {
        showStatus(t('app.uploadSuccess', { id: result.diagnostic_id }), "success");
      } else {
        showStatus(t('app.uploadFailed'), "error");
      }
    } catch (error) {
      console.error("[App] Diagnostic upload failed:", error);
      showStatus(t('app.uploadError', { error: error.message }), "error");
    } finally {
      setDiagnosticUploading(false);
    }
  };

  // Auth state
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [session, setSession] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);

  // Navigation state
  const [currentPage, setCurrentPage] = useState("main");
  const [pageParams, setPageParams] = useState({});

  // UI language state for docs and related UI
  const [language, setLanguage] = useState("en");

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
    // Hide all webviews when leaving BrowserPage — native WebContentsView
    // sits above all DOM elements and would cover the new page otherwise.
    // We must also set _webviewsGloballyHidden SYNCHRONOUSLY so that any
    // pending rAF/timer callbacks in EmbeddedBrowser will see it and skip
    // their showWebview() call — React cleanup hasn't run yet at this point.
    if (currentPage === "browser" && page !== "browser") {
      window.__amiWebviewsHidden = true;
      window.electronAPI?.hideAllWebviews();
    }
    if (page === "browser") {
      window.__amiWebviewsHidden = false;
    }
    setCurrentPage(page);
    setPageParams(params);
  };

  // Check setup status on mount
  useEffect(() => {
    // Load persisted language from electron-store
    window.electronAPI.storeGet("ami_language").then((saved) => {
      if (saved === "en" || saved === "zh") {
        setLanguage(saved);
      }
    }).catch((e) => {
      console.error("[App] Failed to read language from storage:", e);
    });

    // Load persisted settings (appearance, etc.) — await to prevent race with user changes
    import('./store/settingsStore').then(async (mod) => {
      await mod.default.getState().loadPersistedSettings();
    }).catch((e) => {
      console.error("[App] Failed to load persisted settings:", e);
    });

    checkSetupStatus();

    // Listen for runtime connection errors
    onConnectionError(({ endpoint, error }) => {
      console.error(`[App] Backend connection lost at ${endpoint}:`, error);
      // Only trigger if we were previously connected (setupComplete) and not already showing error
      if (setupCompleteRef.current && !backendErrorRef.current) {
        setBackendError(true);
      }
    });
  }, []);

  useEffect(() => {
    window.electronAPI.storeSet("ami_language", language).catch((e) => {
      console.error("[App] Failed to save language to storage:", e);
    });
    i18n.changeLanguage(language);
  }, [language, i18n]);

  // Track agent browser state in store (no auto-navigation)
  const prevBrowserViewIdRef = useRef(null);
  useEffect(() => {
    if (browserViewId && !prevBrowserViewIdRef.current) {
      // Agent started browsing — update store so BrowserPage shows live mode if user navigates there
      useBrowserTabStore.getState().setViewMode(browserViewId, "live");
    } else if (!browserViewId && prevBrowserViewIdRef.current) {
      // Agent stopped browsing — reset mode to idle
      useBrowserTabStore.getState().setViewMode(prevBrowserViewIdRef.current, "idle");
    }
    prevBrowserViewIdRef.current = browserViewId;
  }, [browserViewId]);

  const checkSetupStatus = async () => {
    try {
      // Check browser availability (always true with Electron)
      const browserInfo = await window.electronAPI.checkBrowserInstalled();
      if (browserInfo.available) {
        // Browser is valid, but now we must wait for Backend
        setBackendChecking(true);
        setSetupChecking(false); // Stop setup check UI (if we want to switch)

        // Wait for backend (up to 20s)
        // waitForBackend automatically discovers daemon port on each retry
        const isReady = await api.waitForBackend();

        if (isReady) {
          // Check version after backend is ready
          const versionData = await api.getVersionInfo();
          setVersionInfo(versionData);

          if (versionData.update_required) {
            console.log('[App] Update required:', versionData);
            setUpdateRequired(true);
            // Don't proceed - show update required page
            return;
          }

          setSetupComplete(true);
          checkLoginStatus();
        } else {
          // Backend failed to start - show error page with logs
          console.error("Backend failed to start or connect.");
          setBackendError(true);
          setSetupComplete(false);
        }
      } else {
        // Setup not complete, show setup page
        setSetupComplete(false);
        setSetupChecking(false);
      }
    } catch (error) {
      console.error("[App] Failed to check setup status:", error);
      // Assume setup needed
      setSetupComplete(false);
      setSetupChecking(false);
    } finally {
      setBackendChecking(false);
    }
  };

  const handleSetupComplete = () => {
    setSetupComplete(true);
    // After setup, check login status
    checkLoginStatus();
  };

  const handleBackendRetry = async () => {
    setBackendError(false);
    setBackendChecking(true);

    try {
      // Try to reconnect to backend (10s timeout for retry)
      // waitForBackend automatically discovers daemon port on each retry
      const isReady = await api.waitForBackend(10000);

      if (isReady) {
        console.log('[App] Backend reconnected successfully');
        setBackendChecking(false);
        // If we were already logged in, just restore the state
        if (setupComplete) {
          return;
        }
        // Otherwise do full setup check
        setSetupChecking(true);
        await checkSetupStatus();
      } else {
        console.error('[App] Backend retry failed');
        setBackendError(true);
        setBackendChecking(false);
      }
    } catch (error) {
      console.error('[App] Backend retry error:', error);
      setBackendError(true);
      setBackendChecking(false);
    }
  };

  const checkLoginStatus = async () => {
    try {
      const loggedIn = await auth.isLoggedIn();
      setIsLoggedIn(loggedIn);

      if (loggedIn) {
        const sessionData = await auth.getSession();
        setSession(sessionData);
        console.log('[App] User is logged in:', sessionData?.username);

        // Recover any running backend tasks (e.g. after webview reload)
        useAgentStore.getState().recoverRunningTasks();
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

  // Open browser handler — navigate to browser page, restoring last active tab
  const handleOpenBrowser = async () => {
    navigate("browser");
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
        <h1 className="hero-title">{t('app.welcome')}</h1>
        <p className="hero-subtitle">{t('app.subtitle')}</p>
      </div>

      <div className="card home-main-card" style={{ padding: '40px', maxWidth: '600px', margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '16px' }}>{t('app.startFirstAutomation')}</h2>
        <p style={{ textAlign: 'center', marginBottom: '32px', color: 'var(--text-secondary)' }}>
          {t('app.recordDesc')}
        </p>

        <div className="flex-row" style={{ gap: '20px', justifyContent: 'center' }}>
          <button className="btn btn-primary" onClick={() => navigate("quick-start")} style={{ padding: '12px 24px', fontSize: '16px', minWidth: '180px', justifyContent: 'center' }}>
            <Icon name="record" size={20} />
            <span>{t('app.startRecording')}</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={handleOpenBrowser}
            disabled={browserOpening}
            style={{ padding: '12px 24px', fontSize: '16px', minWidth: '180px', justifyContent: 'center' }}
          >
            <Icon name="browser" size={20} />
            <span>{browserOpening ? t('app.opening') : t('app.openBrowser')}</span>
          </button>

        </div>

        <div style={{ textAlign: 'center', marginTop: '24px' }}>
          <a style={{ color: 'var(--primary-main)', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }} onClick={() => navigate("workflows")}>
            {t('app.seeOthers')}
          </a>
        </div>
      </div>

      <button
        className="btn btn-secondary"
        title="Help"
        style={{ position: 'fixed', bottom: '30px', right: '30px', borderRadius: '50%', width: '48px', height: '48px', padding: 0 }}
        onClick={() => navigate("docs", { topicId: "overview-getting-started" })}
      >
        <Icon name="book" size={24} />
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
        <p>Ami v{versionInfo?.version || '1.0.0'} • {session?.username && `Logged in as ${session.username}`}</p>
      </div>
    </div>
  );

  // Main page for RETURNING users
  const renderReturningUserHome = () => (
    <div className="page home-page returning-user fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t('app.goodMorning')}, {session?.username || 'User'}</h1>
          <p className="page-subtitle">{t('app.readyToAutomate')}</p>
        </div>
        <div className="flex-row" style={{ gap: '8px', alignItems: 'center' }}>
          <button
            className="btn-icon"
            title="Help"
            onClick={() => navigate("docs", { topicId: "overview-getting-started" })}
          >
            <Icon name="book" size={24} />
          </button>
          <button
            className="btn-icon"
            title="Memory Explorer"
            onClick={() => navigate("memory")}
          >
            <Icon name="database" size={24} />
          </button>
          <button
            className="btn-icon"
            title="Settings"
            onClick={() => navigate("settings")}
          >
            <Icon name="settings" size={24} />
          </button>
        </div>
      </div>

      <div className="home-content">
        {/* Quick Start Section */}
        <div className="card" style={{ padding: '24px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ fontSize: '20px', marginBottom: '8px' }}>{t('app.createNewWorkflow')}</h2>
            <p style={{ margin: 0 }}>{t('app.recordDesc')}</p>
          </div>
          <div className="flex-row" style={{ gap: '12px' }}>
            <button className="btn btn-primary" onClick={() => navigate("quick-start")} style={{ minWidth: '140px', justifyContent: 'center' }}>
              <Icon name="record" size={18} />
              <span>{t('app.startRecording')}</span>
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleOpenBrowser}
              disabled={browserOpening}
              style={{ minWidth: '140px', justifyContent: 'center' }}
            >
              <Icon name="browser" size={18} />
              <span>{browserOpening ? t('app.opening') : t('app.openBrowser')}</span>
            </button>
          </div>
        </div>

        {/* Recent Workflows Section */}
        <div className="recent-section">
          <div className="flex-row" style={{ justifyContent: 'space-between', marginBottom: '16px', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{t('app.recentWorkflows')}</h3>
            <a style={{ color: 'var(--primary-main)', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }} onClick={() => navigate("workflows")}>
              {t('app.viewAll')}
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
                    <p style={{ fontSize: '12px', margin: 0, color: 'var(--text-tertiary)' }}>
                      Created: {workflow.createdDate}
                    </p>
                  </div>
                </div>
                <div className="flex-row" style={{ gap: '8px' }}>
                  <button className="btn btn-primary" style={{ padding: '8px 16px', fontSize: '13px' }} onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <Icon name="play" size={14} />
                    <span>{t('common.run')}</span>
                  </button>
                  <button className="btn btn-secondary" style={{ padding: '8px 16px', fontSize: '13px' }} onClick={() => navigate("workflow-detail", { workflowId: workflow.id })}>
                    <span>{t('common.details')}</span>
                  </button>
                </div>
              </div>
            ))}
            {recentWorkflows.length === 0 && (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                {t('app.noRecentWorkflows')}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  // Main page - New HomePage (chat-style dashboard)
  const renderMainPage = () => {
    return (
      <HomePage
        session={session}
        onNavigate={navigate}
        showStatus={showStatus}
        version={versionInfo?.version || '1.0.0'}
        initialMessage={pageParams.initialMessage}
      />
    );
  };

  // Render update required page
  const renderUpdateRequired = () => (
    <div className="page update-required-page flex-center" style={{ height: '100vh', background: 'var(--bg-primary)' }}>
      <div className="card" style={{ padding: '40px', maxWidth: '500px', textAlign: 'center' }}>
        <div style={{ marginBottom: '24px' }}>
          <Icon name="alert" size={48} style={{ color: 'var(--status-warning-text)' }} />
        </div>
        <h1 style={{ fontSize: '24px', marginBottom: '16px' }}>{t('app.updateRequired')}</h1>
        <p style={{ marginBottom: '8px', color: 'var(--text-secondary)' }}>
          Your current version ({versionInfo?.version || 'unknown'}) is no longer supported.
        </p>
        <p style={{ marginBottom: '24px', color: 'var(--text-secondary)' }}>
          {t('app.updateDesc', { version: versionInfo?.minimum_version || 'latest' })}
        </p>
        <a
          href={versionInfo?.update_url || 'http://download.ariseos.com/releases/latest/'}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 24px', fontSize: '16px' }}
        >
          <Icon name="download" size={20} />
          <span>{t('app.downloadUpdate')}</span>
        </a>
        <p style={{ marginTop: '16px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
          Platform: {versionInfo?.platform || 'unknown'}
        </p>
      </div>
    </div>
  );

  // Render current page
  const renderPage = () => {
    // Show update required page if version is incompatible
    if (updateRequired && versionInfo) {
      return renderUpdateRequired();
    }

    // Show loading while checking setup
    if (setupChecking || backendChecking) {
      return (
        <div className="page auth-loading-page flex-center" style={{ height: '100vh' }}>
          <div className="auth-loading flex-col" style={{ alignItems: 'center', gap: '16px' }}>
            <div className="loading-spinner"></div>
            <p>{backendChecking ? t('backendError.connecting') : t('common.loading')}</p>
          </div>
        </div>
      );
    }

    // Show backend error page if connection failed
    if (backendError) {
      return <BackendErrorPage onRetry={handleBackendRetry} />;
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
            <p>{t('common.loading')}</p>
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
            language={language}
            onLanguageChange={setLanguage}
          />
        );

      case "memory":
        return (
          <MemoryPage
            session={session}
            showStatus={showStatus}
          />
        );

      case "main":
        return renderMainPage();

      case "replay":
        return (
          <RecordingReplayPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            navigationData={pageParams}
          />
        );

      case "quick-start":
        return (
          <QuickStartPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "generation":
        return (
          <GenerationPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            params={pageParams}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "explore":
        return (
          <ExplorePage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
          />
        );

      case "workflows":
        return (
          <ExplorePage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
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
            pageData={pageParams}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "workflow-result":
        return (
          <WorkflowResultPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams.recordingData}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "workflow-generation":
        return (
          <WorkflowGenerationPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            recordingData={pageParams}
            version={versionInfo?.version || '1.0.0'}
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
            taskId={pageParams.taskId}
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
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "recording-detail":
        return (
          <RecordingDetailPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            sessionId={pageParams.sessionId}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "memories":
        return (
          <CognitivePhrasesPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "memory-detail":
        return (
          <CognitivePhraseDetailPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            phraseId={pageParams.phraseId}
            isPublic={pageParams.isPublic || false}
            version={versionInfo?.version || '1.0.0'}
          />
        );


      case "recording-analysis":
        return (
          <RecordingAnalysisPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            pageData={pageParams}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      // metaflow-preview route removed - redirect to workflow-detail
      // MetaFlow is now internal, users work with Workflows directly
      case "metaflow-preview":
        // Legacy route - redirect to workflows list
        console.warn('[App] metaflow-preview route is deprecated, redirecting to workflows');
        navigate("workflows");
        return null;

      // data-management and collection-detail removed
      // Data is now per-workflow, see WorkflowDetailPage "Data" tab

      case "docs":
        return (
          <DocsPage
            language={language}
            onLanguageChange={setLanguage}
            onNavigate={navigate}
            showStatus={showStatus}
            topicId={pageParams.topicId}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "agent":
        return (
          <AgentPage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
            version={versionInfo?.version || '1.0.0'}
          />
        );

      case "browser":
        return (
          <BrowserPage
            mode={pageParams.mode || "login"}
            onNavigate={navigate}
            showStatus={showStatus}
            session={session}
            viewId={pageParams.viewId}
            sessionId={pageParams.sessionId}
            source={pageParams.source}
          />
        );

      default:
        return renderMainPage();
    }
  };

  // Bottom navigation bar - 4-tab design: Ami, Browser, Memories, Explore
  const renderBottomNav = () => {
    // Hide navigation on certain pages
    const hideNavPages = ["quick-start", "execution-monitor", "execution-result", "workflow-execution-live"];
    if (hideNavPages.includes(currentPage)) {
      return null;
    }

    const navItems = [
      { id: "main", icon: "robot", label: "Ami" },
      { id: "browser", icon: "globe", label: "Browser" },
      { id: "memories", icon: "brain", label: "Memories" },
      { id: "explore", icon: "compass", label: "Explore" },
    ];

    const handleNavClick = (id) => {
      if (id === "browser") {
        if (currentPage !== "browser") {
          navigate("browser");
        }
        // If already on browser page, do nothing — keep current tab
      } else {
        navigate(id);
      }
    };

    return (
      <nav className="bottom-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => handleNavClick(item.id)}
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
      <div className={`app-content ${["main", "agent", "workflow-execution-live", "browser"].includes(currentPage) ? 'full-width-page' : ''}`}>
        {renderPage()}
      </div>

      {/* Bottom Navigation */}
      {renderBottomNav()}

      {/* Diagnostic Upload Modal */}
      {diagnosticModalOpen && (
        <div className="modal-overlay" onClick={() => setDiagnosticModalOpen(false)}>
          <div className="modal-content log-upload-modal" onClick={(e) => e.stopPropagation()} style={{
            background: 'var(--bg-surface)',
            padding: '24px',
            borderRadius: '16px',
            width: '90%',
            maxWidth: '500px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
          }}>
            <div className="modal-header" style={{ marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>{t('app.diagnosticTitle')}</h3>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: '12px' }}>{t('app.diagnosticDesc')}</p>
              <textarea
                className="log-description-input"
                placeholder={t('app.describeIssue')}
                value={diagnosticDescription}
                onChange={(e) => setDiagnosticDescription(e.target.value)}
                rows={4}
                style={{
                  width: '100%',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                  backgroundColor: 'var(--bg-app)',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  lineHeight: '1.5',
                  resize: 'vertical',
                  minHeight: '100px',
                  marginBottom: '16px',
                  fontFamily: 'inherit'
                }}
              />
              <p className="modal-hint" style={{ fontSize: '13px', color: 'var(--text-tertiary)', margin: 0 }}>
                {t('app.uploadingLogs')}
              </p>
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setDiagnosticModalOpen(false)}
                style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border-subtle)', background: 'transparent', cursor: 'pointer' }}
              >
                {t('common.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={confirmUploadDiagnostic}
                style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: 'var(--primary-main)', color: 'white', cursor: 'pointer' }}
              >
                {t('app.confirmUpload')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
