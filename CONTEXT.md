# Arise Desktop App

Desktop application built with Electron + TypeScript daemon.

## Directories

- `src/` - Frontend source (React/JSX)
- `electron/` - Electron main process (CJS)
- `daemon-ts/` - TypeScript daemon (Express + arise-browser)
- `icons/` - App icons (icns, ico, png)
- `scripts/` - Build and run scripts
- `docs/` - Design documents

## Architecture

```
Electron Main Process <-> React Frontend (renderer)
       |
  WebView Pool (8 WebContentsView, CDP)
       |
  TypeScript Daemon (launched by DaemonLauncher)
       |
  Agent (arise-browser connects to Electron via CDP)
```

### Browser Engine

Browser automation primitives (PageSnapshot, ActionExecutor, BrowserConfig, BehaviorRecorder) come from the **arise-browser** package. Daemon keeps only `browser-session.ts` — an Electron-specific BrowserSession that manages CDP pool pages and implements arise-browser's `SessionRef` interface.

```
arise-browser (npm package)
  └── PageSnapshot, ActionExecutor, BrowserConfig, BehaviorRecorder

daemon-ts/src/browser/browser-session.ts (Electron-specific)
  └── CDP pool management, webview ID tracking, daemon lifecycle
  └── implements SessionRef, uses arise-browser components internally
```

### Electron Files

| File | Purpose |
|------|---------|
| `electron/main.cjs` | Entry point: CDP port, BrowserWindow, IPC handlers, daemon lifecycle |
| `electron/preload.cjs` | contextBridge exposing `window.electronAPI` |
| `electron/daemon-launcher.cjs` | TypeScript daemon spawn, port discovery, graceful shutdown |
| `electron/webview-manager.cjs` | WebContentsView pool (8 views) for browser automation |
| `electron/stealth.cjs` | Anti-detection script injected into each WebContentsView |

### Key Design Decisions

- **No external Chrome**: Electron's built-in Chromium IS the browser for automation
- **CDP port**: Found at startup, passed to daemon via `BROWSER_CDP_PORT` env var
- **Shared cookies**: All WebContentsViews use `persist:user_login` partition
- **Pool pages**: Identified by `about:blank?ami=pool` marker URL
- **Element text via structured details**: Click/type/select tools capture element info from arise-browser's cached elements map into `AgentToolResult.details` (preserved in messages, never sent to LLM). ExecutionDataCollector reads `details.element_name` for workflow learning — no regex parsing.

## Key Frontend Pages

- `src/pages/ExecutionHistoryPage.jsx` - Workflow execution history viewer
- `src/pages/QuickStartPage.jsx` - Recording start page
- `src/pages/RecordingPage.jsx` - Recording page with real-time operation feedback
- `src/pages/MyWorkflowsPage.jsx` - Workflow list and management

## See Also

- `daemon-ts/` for backend daemon details
