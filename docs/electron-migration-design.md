# Electron Migration Design: Embedded Browser Architecture

## 1. Background

### Problems to Solve

| # | Problem | Root Cause |
|---|---------|-----------|
| P0 | **Click steals focus** — Agent's click/type operations activate Chrome window, interrupting user | Chrome is a separate OS window; OS-level focus switch is unavoidable |
| P1 | **Browser state unstable** — CDP disconnects, zombie processes, lock file issues; ~900 lines of lifecycle management code | Chrome is an external process decoupled from app lifecycle |
| P2 | **Limited concurrency** — Single Chrome process, shared BrowserContext, TabGroup isolation is incomplete | No WebView pool; all tabs in one window |
| P3 | **User can't see agent work** — Frontend shows screenshots only, not real-time | No embedded browser rendering |
| P4 | **"Take Control" not implemented** — User can't intervene during agent execution | Separate Chrome window can't be embedded in app |
| P5 | **No login sharing** — Agent's Chrome has no access to user's login sessions | Separate Chrome profile, no cookie sharing mechanism |

### Why Electron

Tauri uses system WebView (WebKit on macOS). WebKit does not support CDP. There is no way to embed a Chromium-based browser inside a Tauri window.

Electron's internal Chromium can:
- Expose CDP via `--remote-debugging-port` (Playwright connects directly)
- Render pages in `WebContentsView` embedded in the app window (no separate window = no focus stealing)
- Share cookies across views via partition (no sync needed)
- Bind browser lifecycle to app lifecycle (no external process management)

Reference implementation: Eigent (in `third-party/eigent/`).

---

## 2. Architecture

### Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Electron Main Process (Node.js)                │
│                                                                    │
│  ┌───────────────────┐   ┌────────────────────────────────────┐  │
│  │  BrowserWindow     │   │  WebContentsView Pool              │  │
│  │  (React App)       │   │  partition: persist:user_login     │  │
│  │  partition: default │   │                                    │  │
│  │                     │   │  [view-0] [view-1] ... [view-7]  │  │
│  │  React UI renders   │   │  Offscreen at (-9999, -9999)      │  │
│  │  here               │   │  Agent claims via CDP page pool   │  │
│  └───────────────────┘   └────────────────────────────────────┘  │
│                                                                    │
│  ● CDP: http://127.0.0.1:{dynamic_port}                          │
│  ● DaemonManager: spawn/kill Python daemon                        │
│  ● IPC Handlers: port discovery, file ops, webview control        │
│  ● Stealth: UA override, disable AutomationControlled             │
└─────────────────────────────┬────────────────────────────────────┘
                              │ CDP (connect_over_cdp)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Python Daemon (unchanged)                                        │
│  FastAPI on :8765                                                 │
│                                                                    │
│  Playwright → CDP → Electron's WebContentsView pages              │
│  - page.evaluate() → unified_analyzer.js ✅                       │
│  - page.add_init_script() → stealth script ✅                     │
│  - CDP Page.addScriptToEvaluateOnNewDocument ✅                    │
│  - CDP Runtime.addBinding ✅                                       │
│  - Locator click (force=True) ✅                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| **Electron Main** | Node.js | WebView pool, CDP port, daemon management, IPC, stealth injection |
| **Electron Renderer** | React (existing frontend) | UI, embedded browser display, Take Control, login browser |
| **Python Daemon** | FastAPI (unchanged) | Agent execution, Playwright CDP connection, script injection, behavior recording |

---

## 3. Electron Main Process

### 3.1 Entry Point (`electron/main.js`)

```
App startup sequence:
1. app.commandLine.appendSwitch('remote-debugging-port', dynamicPort)
2. app.commandLine.appendSwitch('disable-blink-features', 'AutomationControlled')
3. Set user-agent to normal Chrome UA (remove Electron identifier)
4. app.whenReady() →
   a. Create BrowserWindow (React UI, partition: default)
   b. Create WebViewManager → 8 WebContentsView (partition: persist:user_login)
   c. Start DaemonManager → spawn Python daemon with env BROWSER_CDP_PORT
5. app.on('window-all-closed') → stop daemon → quit
```

**CRITICAL**: Do NOT use `app.commandLine.appendSwitch('user-data-dir', ...)` — it silently does nothing in Electron. Do NOT use `app.setPath('sessionData', ...)` for CDP isolation — it redirects ALL partition storage. Use `--remote-debugging-port` alone.

### 3.2 WebView Pool (`electron/webview-manager.js`)

Pre-create 8 `WebContentsView` instances on app startup:

```javascript
// Each view configuration:
{
    webPreferences: {
        partition: 'persist:user_login',   // Shared login cookies
        nodeIntegration: false,
        contextIsolation: true,
        backgroundThrottling: true,
        disableBlinkFeatures: 'AutomationControlled',
    }
}
```

- Initial URL: `about:blank?ami=pool` (marker for Playwright to identify pool pages)
- Initial position: `{ x: -9999 + i*100, y: -9999 + i*100, width: 1920, height: 1080 }`
- Each view gets stealth script injected on `did-finish-load` event

**Why `width: 1920, height: 1080` even when offscreen**: Playwright's `page.evaluate()` and locator operations work regardless of position, but `innerWidth`/`innerHeight` report the bounds set. Keeping realistic dimensions avoids page layout issues.

### 3.3 IPC Handlers

| Channel | Direction | Purpose |
|---------|-----------|---------|
| `get-daemon-port` | Renderer → Main | Read `~/.ami/daemon.port` |
| `read-daemon-logs` | Renderer → Main | Read `~/.ami/logs/app.log` |
| `check-browser-installed` | Renderer → Main | (Always true — Electron IS the browser) |
| `open-path` | Renderer → Main | `shell.openPath()` |
| `reveal-in-folder` | Renderer → Main | `shell.showItemInFolder()` |
| `show-webview` | Renderer → Main | Move WebContentsView on-screen |
| `hide-webview` | Renderer → Main | Move WebContentsView off-screen |
| `hide-all-webviews` | Renderer → Main | Move all views off-screen |
| `get-webview-url` | Renderer → Main | Read `view.webContents.getURL()` |
| `navigate-webview` | Renderer → Main | `view.webContents.loadURL(url)` |
| `webview-go-back` | Renderer → Main | `view.webContents.goBack()` |
| `webview-go-forward` | Renderer → Main | `view.webContents.goForward()` |
| `webview-reload` | Renderer → Main | `view.webContents.reload()` |
| `get-cookies` | Renderer → Main | `session.cookies.get({})` |
| `remove-cookies` | Renderer → Main | `session.cookies.remove(url, name)` |
| `url-updated` | Main → Renderer | Push URL change events from webview |

### 3.4 Daemon Manager (`electron/daemon-launcher.js`)

Port of `python_daemon.rs` to Node.js:

```
Start:
  - Detect daemon binary (production) or python3 script (development)
  - spawn() with env: { BROWSER_CDP_PORT: dynamicPort }
  - Wait for ~/.ami/daemon.port file (30s timeout)

Stop:
  - Unix: process.kill(pid, 'SIGTERM'), wait 5s, then SIGKILL
  - Windows: HTTP POST /api/v1/app/shutdown, wait 10s, then force kill
```

No changes needed to daemon.py — it reads `BROWSER_CDP_PORT` env var to connect via CDP.

### 3.5 Anti-Detection (`electron/stealth.js`)

Applied at two layers:

**Electron app level** (in main.js):
- `disable-blink-features=AutomationControlled`
- Override `app.userAgentFallback` to standard Chrome UA

**Per-WebContentsView** (injected on `did-finish-load`):
- `navigator.webdriver = undefined`
- Spoof `navigator.plugins` (Chrome PDF Plugin, etc.)
- Spoof WebGL vendor/renderer (Intel Inc.)
- Remove automation-related global variables

---

## 4. User Login Browser

### Design: In-App WebContentsView (Not Separate Process)

Unlike Eigent (which spawns a separate Electron subprocess for login), we use the **same WebView pool**.

All WebContentsView instances share partition `persist:user_login`. A user logging into LinkedIn in the login view means agents instantly have those cookies — **no sync, no restart**.

### User Flow

```
1. User clicks "Open Browser" in app UI
2. Frontend sends IPC: show-webview(id='login')
3. Electron Main:
   a. Pick a WebContentsView from the pool (or use a dedicated login view)
   b. setBounds() to visible area (alongside or replacing React UI panel)
   c. Navigate to requested URL (default: google.com)
4. Frontend shows:
   ┌──────────────────────────────────────────────┐
   │  [←] [→] [↻] [🏠]  https://linkedin.com    │
   │  ┌──────────────────────────────────────────┐│
   │  │                                          ││
   │  │         LinkedIn Login Page              ││
   │  │         (real embedded browser)          ││
   │  │                                          ││
   │  └──────────────────────────────────────────┘│
   │                              [Close Browser] │
   └──────────────────────────────────────────────┘
5. User logs in normally
6. User clicks "Close Browser"
7. Frontend sends IPC: hide-webview(id='login')
8. WebContentsView moves back to (-9999, -9999)
9. Cookies already in persist:user_login — agents can use them immediately ✅
```

### Cookie Management UI

| Action | Implementation |
|--------|---------------|
| View logged-in sites | IPC `get-cookies` → `session.fromPartition('persist:user_login').cookies.get({})` → group by domain |
| Delete site cookies | IPC `remove-cookies(domain)` → iterate and remove matching cookies |
| Clear all cookies | IPC `clear-all-cookies` → `session.fromPartition('persist:user_login').clearStorageData()` |

---

## 5. Take Control (Agent ↔ User Handoff)

### Flow

```
Agent working (view offscreen, controlled by Playwright):
  → User clicks "Take Control"
  → Frontend sends: POST /api/v1/task/{id}/take-control {action: "pause"}
  → Daemon pauses agent execution (agent stops sending Playwright commands)
  → Frontend sends IPC: show-webview(viewId)
  → WebContentsView moves on-screen, user sees live browser
  → User interacts directly

User done:
  → User clicks "Give Back to Agent"
  → Frontend sends IPC: hide-webview(viewId)
  → WebContentsView moves off-screen
  → Frontend sends: POST /api/v1/task/{id}/take-control {action: "resume"}
  → Agent resumes from current page state
```

### Key Constraint

During "Take Control", the agent MUST be paused. If Playwright and user interact with the same page simultaneously, actions will conflict. The pause/resume mechanism ensures mutual exclusion.

---

## 6. Behavior Recording

### Current vs New

| | Current (External Chrome) | New (Embedded WebContentsView) |
|---|---|---|
| Browser | Separate Chrome window | WebContentsView in app window |
| User experience | Must switch to Chrome window | Stays in app window |
| Focus | Chrome window steals focus | No focus issues |
| Login state | Separate profile, user re-logs in | Shared partition, already logged in |
| CDP connection | Connect to external Chrome process | Same CDP as agent execution |
| Process management | Launch/kill Chrome | Show/hide WebContentsView |

### Flow

```
1. User clicks "Start Recording"
2. Frontend sends IPC: show-webview(id)
3. WebContentsView moves on-screen, shows URL bar + recording indicator
4. Daemon starts behavior_recorder on this CDP page:
   - Inject behavior_tracker.js via Page.addScriptToEvaluateOnNewDocument
   - Register Runtime.addBinding('reportUserBehavior') for JS→Python callback
   - Listen page.on("response") for network monitoring
5. User browses and operates normally in the embedded browser
6. All operations captured in real-time (click, type, navigate, scroll)
7. User clicks "Stop Recording"
8. Frontend sends IPC: hide-webview(id)
9. Daemon stops recorder, generates operation sequence
10. Operation sequence → workflow analysis → CognitivePhrase
```

### Key Benefit

Recording and agent execution use the **same browser environment** (same partition, same stealth, same CDP). A workflow recorded in this browser will replay identically when the agent executes it — no environment mismatch.

### What Changes in Code

| File | Change |
|------|--------|
| `behavior_recorder.py` | No change — already uses CDP session on a Page object. The Page just comes from Electron's WebView pool instead of external Chrome |
| `recording_service.py` | Simplify — remove Chrome launch/stop logic. Just request a WebView page from the pool |
| `daemon.py` recording endpoints | Remove browser start/stop from recording flow. Add: request page from pool, attach recorder |

---

## 7. Concurrent Browser Operations

### Page Allocation

```
Python Daemon connects via CDP:
  browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
  context = browser.contexts[0]

  # Pool pages identified by marker URL
  pool_pages = [p for p in context.pages if 'ami=pool' in p.url]

  # Agent claims a page:
  page = pool_pages.pop()
  agent_pages[task_id] = page
```

### Concurrency Model

- 8 WebContentsView = 8 CDP pages = up to 8 concurrent agents
- Each agent claims one page from the pool
- All pages share `persist:user_login` partition (shared cookies)
- Agents operate independently — no shared state except cookies
- Global lock only for pool allocation (not per-page operations)

### Resource Management

| Metric | Value | Notes |
|--------|-------|-------|
| Max concurrent agents | 8 | Configurable; matches WebView pool size |
| Memory per idle view | ~50-100MB | Chromium renderer process overhead |
| Total memory (8 views) | ~400-800MB | Acceptable for desktop app |
| CPU (idle, throttled) | Minimal | `backgroundThrottling: true` suspends timers |

---

## 8. Known Constraints & Mitigations

### 8.1 Off-Screen View Visibility (CRITICAL)

**Issue**: WebContentsView at `(-9999, -9999)` reports `visibilityState: "hidden"` and `innerWidth: 0`.

**Impact on our code**:

| API | Works off-screen? | Used in |
|-----|-------------------|---------|
| `page.evaluate()` | ✅ Yes | page_snapshot.py, behavior_recorder.py |
| `page.add_init_script()` | ✅ Yes | stealth injection |
| `locator.click(force=True)` | ✅ Yes | action_executor.py (primary click) |
| `page.keyboard.press()` | ✅ Yes | action_executor.py (enter) |
| `page.mouse.click(x, y)` | ❌ No | action_executor.py (`_mouse_control`) |
| `page.mouse.dblclick(x, y)` | ❌ No | action_executor.py (`_mouse_control`) |

**Mitigation**: `_mouse_control()` (coordinate-based click) must be refactored to use JavaScript `elementFromPoint()` + `element.click()` instead of CDP Input events. This is a minor change — `_mouse_control` is rarely used; the primary click path is locator-based.

### 8.2 Playwright Single Context

**Issue**: Playwright sees all WebContentsView pages as one BrowserContext (limitation of `connect_over_cdp`).

**Impact**: Cannot create separate contexts per agent (no per-agent cookie isolation).

**Mitigation**: This is actually what we want — shared `persist:user_login` cookies across all agents. If per-agent isolation is ever needed, use separate partitions per view group.

### 8.3 Package Size

| | Tauri | Electron |
|---|---|---|
| App binary | ~10MB | ~150MB |
| With daemon | ~200MB | ~350MB |

**Mitigation**: Acceptable trade-off. Functionality gains far outweigh size increase.

### 8.4 Shared Auth State

**Issue**: If agent logs out of a site in one view, it affects all views (shared cookies).

**Mitigation**: Agent prompts explicitly instruct: "NEVER log out of any website." This is already a design principle.

---

## 9. What Changes in Python Daemon

### Files to Delete

| File | Reason |
|------|--------|
| `browser_launcher.py` | No longer launching external Chrome — Electron IS the browser |

### Files to Simplify

| File | Current Lines | After | Changes |
|------|---------------|-------|---------|
| `browser_session.py` | ~1900 | ~600 | Remove: BrowserLauncher usage, health check loop, lock file management, process scanning, daemon session lifecycle. Keep: CDP connection via `connect_over_cdp`, tab/page management, TabGroup, snapshot/executor setup |
| `browser_manager.py` | ~200 | ~80 | Remove: Chrome start/stop. Keep: session management, status reporting |

### Files to Modify (Minor)

| File | Change |
|------|--------|
| `daemon.py` | Read `BROWSER_CDP_PORT` from env; remove browser start/stop endpoints |
| `action_executor.py` | Refactor `_mouse_control()` to use JS-level click instead of `page.mouse.click()` |
| `config_loader.py` | Remove Chrome-specific launch args config (stealth now handled by Electron) |

### Files Unchanged

All agent logic, task execution, memory integration, behavior recording, page snapshot — zero changes.

---

## 10. What Changes in Frontend

### Minimal IPC Migration (~50 lines)

| File | Change |
|------|--------|
| `src/config/backend.js` | `invoke('get_daemon_port')` → `window.electronAPI.getDaemonPort()` |
| `src/utils/auth.js` | Tauri Store → `electron-store` |
| `src/pages/SetupPage.jsx` | `invoke('check_browser_installed')` → always true |
| `src/pages/BackendErrorPage.jsx` | `invoke('read_daemon_logs')` → IPC |
| `src/components/.../FileAttachmentCard.jsx` | `invoke('open_path')` → IPC |

### New Frontend Features

| Feature | Component | Description |
|---------|-----------|-------------|
| **Embedded Browser View** | `BrowserTab.jsx` (rewrite) | Show live WebContentsView instead of screenshots; URL bar, navigation controls |
| **Take Control** | `BrowserTab.jsx` | Pause agent → show view → user interacts → hide view → resume agent |
| **Login Browser** | `LoginBrowserPage.jsx` (new) | Open WebContentsView for user login; URL bar, back/forward/reload |
| **Cookie Manager** | `CookieManagerPage.jsx` (new) | List logged-in domains, delete cookies per domain |
| **Multi-Agent View** | `AgentPage.jsx` (enhance) | Show which agents are active, switch between their browser views |

---

## 11. Build & Packaging

### Structure

```
src/clients/desktop_app/
├── electron/
│   ├── main.cjs              # Entry point (CommonJS — Electron requires CJS)
│   ├── preload.cjs           # IPC bridge (contextBridge.exposeInMainWorld)
│   ├── webview-manager.cjs   # WebContentsView pool
│   ├── daemon-launcher.cjs   # Python daemon lifecycle
│   └── stealth.cjs           # Anti-detection scripts
├── resources/                # Bundled daemon (build-time only)
│   └── ami-daemon.app/       # macOS PyInstaller output
│   └── ami-daemon/           # Windows PyInstaller output
├── src/                      # React frontend (mostly unchanged)
├── package.json              # Updated: remove @tauri-apps, add electron + electron-builder
└── vite.config.js            # Unchanged
```

**Why `.cjs`**: `package.json` has `"type": "module"` for Vite/React ESM support. Electron's main process requires CommonJS (`require()`), so all electron files use `.cjs` extension.

### Removed

```
src-tauri/                  # Entire directory — no longer needed
├── src/main.rs
├── src/python_daemon.rs
├── Cargo.toml
├── tauri.conf.json
└── icons/
```

### Development

```bash
npm run electron:dev
# Runs: concurrently "vite" "wait-on tcp:1420 && electron ."
# Vite serves React at :1420, Electron loads from VITE_DEV_SERVER_URL
```

### Build Pipeline

```
Step 1: Python Daemon (unchanged)
  PyInstaller → ami-daemon binary → resources/

Step 2: Frontend + Electron
  npm run electron:build
  # Runs: vite build → electron-builder
  # electron-builder reads package.json "build" config
  # Output: release/ directory with .dmg (macOS) / .exe (Windows)
```

### Build Scripts

| Script | Platform | Description |
|--------|----------|-------------|
| `scripts/build_app_macos.sh` | macOS | PyInstaller daemon + electron-builder + code signing + notarization |
| `scripts/build_app_windows.ps1` | Windows | PyInstaller daemon + electron-builder + portable ZIP |
| `scripts/run_desktop_app.sh` | macOS/Linux | Dev mode: `npm run electron:dev` with env vars |
| `scripts/run_desktop_app.bat` | Windows | Dev mode: `npm run electron:dev` with env vars |

---

## 12. Migration Steps

### Phase 1: Electron Scaffold
- Create `electron/` directory with main.js, preload.js, webview-manager.js
- Implement DaemonManager (port from python_daemon.rs)
- Implement IPC handlers for existing Tauri commands
- Verify: app launches, daemon starts, frontend loads

### Phase 2: WebView Pool + CDP
- Implement WebViewManager with 8 WebContentsView instances
- Enable `--remote-debugging-port`
- Inject stealth scripts per view
- Verify: Playwright `connect_over_cdp` sees 8 pool pages

### Phase 3: Python Daemon Adaptation
- Delete `browser_launcher.py`
- Simplify `browser_session.py` (remove lifecycle management)
- Read `BROWSER_CDP_PORT` env var for CDP connection
- Refactor `_mouse_control()` in action_executor.py
- Verify: agent can navigate, click, type via CDP to Electron views

### Phase 4: Frontend Migration
- Replace Tauri API imports with Electron IPC
- Replace Tauri Store with electron-store
- Verify: all existing features work

### Phase 5: New Features
- Rewrite BrowserTab.jsx for embedded browser display
- Implement Take Control (pause/resume + show/hide webview)
- Implement Login Browser (show webview + URL bar)
- Implement Cookie Manager
- Verify: user can log in, agent can use cookies, take control works

### Phase 6: Build & Package
- Create electron-builder.yml
- Adapt build scripts (macOS/Windows)
- Code signing & notarization
- Verify: packaged app works on macOS and Windows

### Phase 7: Cleanup
- Remove `src-tauri/` directory
- Remove Tauri dependencies from package.json
- Update CONTEXT.md files
