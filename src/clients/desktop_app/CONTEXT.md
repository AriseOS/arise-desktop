# src/clients/desktop_app/

Desktop application built with Electron and Python daemon.

## Directories

- `src/` - Frontend source (React/JSX)
- `electron/` - Electron main process (JS)
- `ami_daemon/` - Python daemon with BaseAgent runtime
- `src-tauri/` - Legacy Tauri backend (Rust) — being phased out

## Architecture

```
Electron Main Process ←→ React Frontend (renderer)
       ↓
  WebView Pool (8 WebContentsView, CDP)
       ↓
  Python Daemon (launched by DaemonLauncher)
       ↓
  BaseAgent (Playwright connects to Electron via CDP)
```

### Electron Files

| File | Purpose |
|------|---------|
| `electron/main.js` | Entry point: CDP port, BrowserWindow, IPC handlers, daemon lifecycle |
| `electron/preload.js` | contextBridge exposing `window.electronAPI` |
| `electron/daemon-launcher.js` | Python daemon spawn, port discovery, graceful shutdown |
| `electron/webview-manager.js` | WebContentsView pool (8 views) for browser automation |
| `electron/stealth.js` | Anti-detection script injected into each WebContentsView |

### Key Design Decisions

- **No external Chrome**: Electron's built-in Chromium IS the browser for automation
- **CDP port**: Found at startup, passed to daemon via `BROWSER_CDP_PORT` env var
- **Shared cookies**: All WebContentsViews use `persist:user_login` partition
- **Pool pages**: Identified by `about:blank?ami=pool` marker URL

## Key Frontend Pages

- `src/pages/ExecutionHistoryPage.jsx` - Workflow execution history viewer
- `src/pages/QuickStartPage.jsx` - Recording start page
- `src/pages/RecordingPage.jsx` - Recording page with real-time operation feedback
- `src/pages/MyWorkflowsPage.jsx` - Workflow list and management

## See Also

- `ami_daemon/CONTEXT.md` for backend daemon details
- `ami_daemon/base_agent/core/CONTEXT.md` for BaseAgent details
