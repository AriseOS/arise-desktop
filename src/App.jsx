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
import RecordingAnalysisPage from "./pages/RecordingAnalysisPage";
import CognitivePhrasesPage from "./pages/CognitivePhrasesPage";
import CognitivePhraseDetailPage from "./pages/CognitivePhraseDetailPage";
import DocsPage from "./pages/DocsPage";
import BackendErrorPage from "./pages/BackendErrorPage";
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
  const [isLocalMode, setIsLocalMode] = useState(false);
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
    window.electronAPI.storeGet("arise_language").then((saved) => {
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
    window.electronAPI.storeSet("arise_language", language).catch((e) => {
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
        // Check if local mode was previously active
        try {
          const savedLocalMode = await window.electronAPI.storeGet('arise_local_mode');
          if (savedLocalMode) {
            // Verify credentials still exist
            const creds = await api.getCredentials();
            if (creds?.anthropic?.api_key) {
              console.log('[App] Restoring local mode');
              setIsLocalMode(true);
              // Recover any running backend tasks in local mode too
              useAgentStore.getState().recoverRunningTasks();
            } else {
              // Credentials gone, clear local mode flag
              await window.electronAPI.storeDelete('arise_local_mode');
            }
          } else {
            console.log('[App] User is not logged in');
          }
        } catch (e) {
          console.log('[App] User is not logged in');
        }
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

  const handleLocalModeStart = async () => {
    setIsLocalMode(true);
    await window.electronAPI.storeSet('arise_local_mode', true);
    console.log('[App] Entered local mode');
    // Recover any running backend tasks
    useAgentStore.getState().recoverRunningTasks();
  };

  const handleExitLocalMode = async () => {
    setIsLocalMode(false);
    await window.electronAPI.storeDelete('arise_local_mode');
    console.log('[App] Exited local mode');
    navigate('login');
  };

  const handleLogout = async () => {
    // Clear local state
    setIsLoggedIn(false);
    setIsLocalMode(false);
    setSession(null);
    // Clear local mode flag
    await window.electronAPI.storeDelete('arise_local_mode').catch(() => {});

    // Navigate to login page
    navigate('login');

    console.log('[App] User logged out');
  };



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

    // Show login/register pages if not logged in and not in local mode
    if (!isLoggedIn && !isLocalMode) {
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
          onLocalModeStart={handleLocalModeStart}
        />
      );
    }

    // User is logged in or in local mode, show app pages
    switch (currentPage) {
      case "login":
      case "register":
        // Redirect to main if trying to access login/register while logged in or in local mode
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
            isLocalMode={isLocalMode}
            onExitLocalMode={handleExitLocalMode}
          />
        );

      case "memory":
        return (
          <MemoryPage
            session={session}
            showStatus={showStatus}
            isLocalMode={isLocalMode}
            onNavigateToLogin={handleExitLocalMode}
          />
        );

      case "main":
        return renderMainPage();

      case "explore":
        return (
          <ExplorePage
            session={session}
            onNavigate={navigate}
            showStatus={showStatus}
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
            filePath={pageParams.filePath}
            fileName={pageParams.fileName}
            fileType={pageParams.fileType}
          />
        );

      default:
        return renderMainPage();
    }
  };

  // Bottom navigation bar - 4-tab design: Arise, Browser, Memories, Explore
  const renderBottomNav = () => {
    const navItems = [
      { id: "main", icon: "robot", label: "Arise" },
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
      <div className={`app-content ${["main", "browser"].includes(currentPage) ? 'full-width-page' : ''}`}>
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
