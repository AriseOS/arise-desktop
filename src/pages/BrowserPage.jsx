/**
 * BrowserPage — Chrome-style multi-tab browser page.
 *
 * Tab bar at top shows all active WebContentsView tabs from the 8-view pool.
 * Mode bar shows contextual status (recording, agent live browsing).
 * EmbeddedBrowser renders the active tab's native view.
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { EmbeddedBrowser } from '../components/EmbeddedBrowser';
import LoginWelcome from '../components/LoginWelcome';
import Icon from '../components/Icons';
import { api } from '../utils/api';
import { useAgentStore, useBrowserTabStore } from '../store';
import './BrowserPage.css';

/**
 * Extract display-friendly domain from URL.
 */
function getDomain(url) {
  if (!url) return '';
  try {
    const u = new URL(url);
    return u.hostname.replace('www.', '');
  } catch {
    return url.slice(0, 30);
  }
}

/**
 * Tab icon per mode.
 */
const TAB_ICONS = {
  login: 'logIn',
  recording: 'record',
  live: 'robot',
  preview: 'file',
  idle: 'globe',
};

/**
 * Mode indicator dot colors (using design system semantic colors).
 */
const MODE_DOT_COLORS = {
  recording: 'var(--status-error-text)',
  live: 'var(--primary-main)',
  login: 'var(--primary-main)',
  preview: 'var(--primary-main)',
};

export default function BrowserPage({
  onNavigate,
  showStatus,
  session,
  // Initial params from navigation
  mode: initialMode,
  viewId: initialViewId,
  sessionId: initialSessionId,
  source: initialSource,
  // Preview params
  filePath: initialFilePath,
  fileName: initialFileName,
  fileType: initialFileType,
}) {
  // --- Store ---
  const activeTabId = useBrowserTabStore((s) => s.activeTabId);
  const views = useBrowserTabStore((s) => s.views);
  const recordingMeta = useBrowserTabStore((s) => s.recordingMeta);
  const previewMeta = useBrowserTabStore((s) => s.previewMeta);
  const fetchAllViews = useBrowserTabStore((s) => s.fetchAllViews);
  const onViewStateChanged = useBrowserTabStore((s) => s.onViewStateChanged);
  const setViewMode = useBrowserTabStore((s) => s.setViewMode);
  const switchTab = useBrowserTabStore((s) => s.switchTab);
  const closeTab = useBrowserTabStore((s) => s.closeTab);
  const setRecordingMeta = useBrowserTabStore((s) => s.setRecordingMeta);
  const clearRecordingMeta = useBrowserTabStore((s) => s.clearRecordingMeta);

  const activeView = views[activeTabId];

  // --- Agent store subscriptions ---
  const browserViewId = useAgentStore((s) => {
    const t = s.activeTaskId ? s.tasks[s.activeTaskId] : null;
    return t?.browserViewId || null;
  });

  // Active tab's mode — agentStore resets live→idle on task completion
  const activeMode = activeView?.mode || 'idle';

  // Derive active tabs from views (memoized to avoid new array on every render)
  const activeTabs = useMemo(() => {
    const POOL_MARKER = 'about:blank?ami=pool';
    const CLAIMED_MARKER = 'about:blank?ami=claimed';
    const tabs = [];
    for (const [id, view] of Object.entries(views)) {
      const isPool = !view.url || view.url.startsWith(POOL_MARKER);
      const isClaimed = view.url && view.url.startsWith(CLAIMED_MARKER);
      if (id === '0' || (!isPool && !isClaimed)) {
        tabs.push({ id, ...view });
      }
    }
    tabs.sort((a, b) => {
      if (a.mode === 'login' && b.mode !== 'login') return -1;
      if (b.mode === 'login' && a.mode !== 'login') return 1;
      return parseInt(a.id) - parseInt(b.id);
    });
    return tabs;
  }, [views]);

  // --- Recording state ---
  const [operationsCount, setOperationsCount] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startTimeRef = useRef(null);

  // --- Mount: fetch views, subscribe to events ---
  useEffect(() => {
    fetchAllViews();

    const cleanup = window.electronAPI?.onViewStateChanged((viewId, info) => {
      onViewStateChanged(viewId, info);
    });

    const pollTimer = setInterval(fetchAllViews, 2000);

    return () => {
      cleanup?.();
      clearInterval(pollTimer);
    };
  }, []);

  // --- Handle initial pageParams (mode + viewId from navigation) ---
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (initialMode === 'preview' && initialFilePath) {
      useBrowserTabStore.getState().openPreview(initialFilePath, initialFileName, initialFileType);
    } else if (initialMode && initialViewId) {
      setViewMode(initialViewId, initialMode);
      switchTab(initialViewId);

      if (initialMode === 'recording' && initialSessionId) {
        setRecordingMeta(initialViewId, {
          sessionId: initialSessionId,
          source: initialSource,
          startTime: Date.now(),
        });
        startTimeRef.current = Date.now();
      }
    } else {
      // No explicit params — ensure view "0" has login mode for tab bar display,
      // but keep whatever activeTabId the store already has (last selected tab).
      const currentViews = useBrowserTabStore.getState().views;
      if (!currentViews['0']?.mode || currentViews['0'].mode === 'idle') {
        setViewMode('0', 'login');
      }
    }
  }, []);

  // --- Watch agentStore browserViewId — auto-switch to agent's tab ---
  // Live mode is set directly by agentStore SSE handlers (supports parallel subtasks).
  // This effect only handles tab switching when agent starts browsing.
  const prevBrowserViewIdRef = useRef(null);
  useEffect(() => {
    if (browserViewId && browserViewId !== prevBrowserViewIdRef.current) {
      switchTab(browserViewId);
    }
    prevBrowserViewIdRef.current = browserViewId;
  }, [browserViewId]);

  // --- Recording: poll operations ---
  useEffect(() => {
    if (activeMode !== 'recording') return;

    const pollInterval = setInterval(async () => {
      try {
        const result = await api.callAppBackend('/api/v1/recordings/current/operations', {
          method: 'GET',
        });
        if (result.is_recording) {
          setOperationsCount(result.operations_count || 0);
        }
      } catch {
        // Silently ignore
      }
    }, 500);

    return () => clearInterval(pollInterval);
  }, [activeMode]);

  // --- Recording: elapsed time ---
  useEffect(() => {
    if (activeMode !== 'recording') return;

    const meta = recordingMeta[activeTabId];
    const start = meta?.startTime || startTimeRef.current || Date.now();
    startTimeRef.current = start;

    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [activeMode, activeTabId]);

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  // --- Recording: stop & save ---
  const handleStopRecording = async () => {
    showStatus?.('Stopping recording...', 'info');

    const recordingTabId = activeTabId;
    try {
      const result = await api.callAppBackend('/api/v1/recordings/stop', {
        method: 'POST',
        body: JSON.stringify({ user_id: session?.username }),
      });

      const meta = recordingMeta[recordingTabId];
      clearRecordingMeta(recordingTabId);
      // Close the recording tab (navigates view back to pool)
      closeTab(recordingTabId);

      const sessionId = result.session_id || meta?.sessionId || initialSessionId;

      // Analyze recording with AI to generate name and description
      showStatus?.('Analyzing recording...', 'info');
      let analysisName = '';
      let analysisTaskDesc = '';
      try {
        const analysisResult = await api.analyzeRecording(sessionId, session?.username);
        analysisName = analysisResult.name || '';
        analysisTaskDesc = analysisResult.task_description || '';

        // Save analysis metadata to recording
        await api.callAppBackend(`/api/v1/recordings/${sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({
            name: analysisName,
            task_description: analysisTaskDesc,
            user_query: analysisResult.user_query,
            user_id: session?.username,
          }),
        });
      } catch (analysisError) {
        console.error('Recording analysis failed:', analysisError);
        // Continue without analysis — not critical
      }

      showStatus?.('Recording saved!', 'success');

      onNavigate('recording-analysis', {
        sessionId,
        name: analysisName,
        taskDescription: analysisTaskDesc,
        operationsCount: result.operations_count || operationsCount,
        localFilePath: result.local_file_path,
        userId: session?.username,
        source: meta?.source || initialSource,
      });
    } catch (error) {
      console.error('Stop recording error:', error);
      showStatus?.(`Failed to stop recording: ${error.message}`, 'error');
    }
  };

  // --- Recording: cancel ---
  const handleCancelRecording = async () => {
    const recordingTabId = activeTabId;
    try {
      await api.callAppBackend('/api/v1/recordings/stop', {
        method: 'POST',
        body: JSON.stringify({ user_id: session?.username }),
      });
    } catch {
      // Ignore
    }
    clearRecordingMeta(recordingTabId);
    // Close the recording tab (navigates view back to pool)
    closeTab(recordingTabId);
  };

  // --- Close tab ---
  const handleCloseTab = (e, tabId) => {
    e.stopPropagation(); // Don't trigger tab switch
    // If closing a recording tab, stop recording first
    if (views[tabId]?.mode === 'recording') {
      handleCancelRecording();
      return;
    }
    closeTab(tabId);
  };

  // Initial URL — no default page; login tab shows welcome overlay instead
  const initialUrl = '';

  // Show welcome overlay when login tab is active with no real URL loaded
  const showWelcome = activeMode === 'login' && (
    !activeView?.url ||
    activeView.url.startsWith('about:blank')
  );

  // --- Tab bar ---
  const renderTabBar = () => (
    <div className="browser-tab-bar">
      <div className="browser-tab-bar-inner">
        {activeTabs.map((tab, index) => {
          const isActive = tab.id === activeTabId;
          const prevActive = index > 0 && activeTabs[index - 1].id === activeTabId;
          const iconName = TAB_ICONS[tab.mode] || 'globe';
          const accentColor = MODE_DOT_COLORS[tab.mode];
          const label = tab.mode === 'login'
            ? 'Login'
            : tab.mode === 'preview'
            ? (previewMeta[tab.id]?.fileName || tab.title || 'Preview')
            : tab.title || getDomain(tab.url) || `Tab ${tab.id}`;
          const canClose = tab.id !== '0' && tab.mode !== 'control';
          const showSep = index > 0 && !isActive && !prevActive;

          return (
            <React.Fragment key={tab.id}>
              {showSep && <div className="browser-tab-separator" />}
              <div
                className={`browser-tab${isActive ? ' active' : ''}${canClose ? '' : ' no-close'}`}
                onClick={() => switchTab(tab.id)}
                title={tab.url || label}
              >
                {accentColor && (
                  <span className="browser-tab-accent" style={{ background: accentColor }} />
                )}
                <span className="browser-tab-icon">
                  <Icon name={iconName} size={14} />
                </span>
                <span className="browser-tab-label">{label}</span>
                {canClose && (
                  <span className="browser-tab-close" onClick={(e) => handleCloseTab(e, tab.id)}>
                    <Icon name="x" size={10} />
                  </span>
                )}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );

  // --- Mode bar (below tabs, recording/live only) ---
  const renderModeBar = () => {
    if (activeMode === 'recording') {
      return (
        <div className="browser-mode-bar recording">
          <button className="browser-mode-btn" onClick={handleCancelRecording}>
            Cancel
          </button>
          <div className="browser-mode-status">
            <span className="browser-mode-dot" style={{ background: 'var(--status-error-text)' }} />
            <span className="browser-mode-label" style={{ color: 'var(--status-error-text)' }}>
              Recording
            </span>
            <span className="browser-mode-separator">·</span>
            <span className="browser-mode-time">{formatTime(elapsedSeconds)}</span>
            <span className="browser-mode-separator">·</span>
            <span className="browser-mode-detail">{operationsCount} actions</span>
          </div>
          <button className="browser-mode-btn danger" onClick={handleStopRecording}>
            <Icon name="stop" size={12} />
            Stop & Save
          </button>
        </div>
      );
    }

    if (activeMode === 'live') {
      return (
        <div className="browser-mode-bar live">
          <div className="browser-mode-status">
            <span className="browser-mode-dot pulse" style={{ background: 'var(--primary-main)' }} />
            <span className="browser-mode-label" style={{ color: 'var(--primary-main)' }}>
              Arise is browsing
            </span>
          </div>
        </div>
      );
    }

    if (activeMode === 'preview') {
      const meta = previewMeta[activeTabId];
      return (
        <div className="browser-mode-bar preview">
          <div className="browser-mode-status">
            <Icon name="file" size={14} />
            <span className="browser-mode-label">
              {meta?.fileName || 'File Preview'}
            </span>
          </div>
          <button className="browser-mode-btn" onClick={() => closeTab(activeTabId)}>
            <Icon name="x" size={12} />
            Close Preview
          </button>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="browser-page">
      {renderTabBar()}
      {renderModeBar()}
      <div className={`browser-page-content${showWelcome ? ' show-welcome' : ''}`}>
        <EmbeddedBrowser
          viewId={activeTabId}
          visible={!showWelcome}
          interactive={true}
          showControls={activeMode !== 'preview'}
          initialUrl={initialUrl}
        />
        {showWelcome && <LoginWelcome />}
      </div>
    </div>
  );
}
