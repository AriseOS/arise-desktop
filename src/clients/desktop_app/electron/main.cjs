/**
 * Electron main process entry point.
 *
 * Startup sequence:
 * 1. Find available CDP port SYNCHRONOUSLY, set command-line switches (before app.ready)
 * 2. Set user-agent to normal Chrome UA
 * 3. app.whenReady() →
 *    a. Set UA on persist:user_login session
 *    b. Create BrowserWindow (React UI)
 *    c. Create WebViewManager → 8 WebContentsView pool
 *    d. Register IPC handlers
 *    e. Start DaemonLauncher → spawn Python daemon
 *    f. Load frontend content
 * 4. Lifecycle: window-all-closed → stop daemon → quit
 */

const { app, BrowserWindow, ipcMain, shell, session } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { WebViewManager } = require('./webview-manager.cjs');
const { DaemonLauncher } = require('./daemon-launcher.cjs');

// ==================== Find available CDP port (SYNCHRONOUS) ====================
// appendSwitch('remote-debugging-port') MUST be called before app.ready.
// We use synchronous port probing via execSync to guarantee the switch is set
// before Chromium launches — no race conditions with async event loop ordering.

function findCdpPortSync(startPort) {
  const { execSync } = require('child_process');
  for (let port = startPort; port < startPort + 100; port++) {
    try {
      // Check if port is in use by trying to connect
      if (process.platform === 'win32') {
        const result = execSync(`netstat -aon | findstr ":${port} "`, { encoding: 'utf8', timeout: 1000 });
        if (result.includes('LISTENING')) continue; // Port in use
      } else {
        // lsof returns exit code 0 if something is listening, 1 if not
        try {
          execSync(`lsof -i :${port} -sTCP:LISTEN`, { timeout: 1000, stdio: 'ignore' });
          continue; // Port in use (lsof found a listener)
        } catch {
          // lsof returned non-zero → port is free
        }
      }
      return port;
    } catch {
      return port; // If check fails, assume port is free
    }
  }
  return startPort; // fallback
}

const cdpPort = findCdpPortSync(9222);
app.commandLine.appendSwitch('remote-debugging-port', String(cdpPort));
console.log(`[Main] CDP port: ${cdpPort}`);

// ==================== Anti-fingerprint (before app.ready) ====================

app.commandLine.appendSwitch('disable-blink-features', 'AutomationControlled,Accelerated2dCanvas');

const chromeVersion = process.versions.chrome || '131.0.0.0';
const platformUA = (() => {
  switch (process.platform) {
    case 'darwin':
      return `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;
    case 'win32':
      return `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;
    default:
      return `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;
  }
})();
app.userAgentFallback = platformUA;

// ==================== Single instance lock ====================

if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// ==================== Global state ====================

let win = null;
let webViewManager = null;
let daemonLauncher = null;
let electronStore = null;
let isQuitting = false;

// ==================== electron-store (lazy) ====================

let storePromise = null;
async function getStore() {
  if (!storePromise) {
    // electron-store v10+ is ESM-only, use dynamic import
    storePromise = (async () => {
      const Store = (await import('electron-store')).default;
      return new Store({ name: 'ami-settings' });
    })();
  }
  return storePromise;
}

// ==================== IPC Handlers ====================

function registerIpcHandlers() {
  // --- Daemon port ---
  ipcMain.handle('get-daemon-port', () => {
    const portFile = path.join(os.homedir(), '.ami', 'daemon.port');
    try {
      if (fs.existsSync(portFile)) {
        const content = fs.readFileSync(portFile, 'utf-8').trim();
        const port = parseInt(content, 10);
        if (!isNaN(port) && port > 0) {
          return { success: true, port, source: 'file' };
        }
        return { success: true, port: 8765, source: 'default', warning: `Invalid port file content: ${content}` };
      }
    } catch (e) {
      return { success: true, port: 8765, source: 'default', warning: `Failed to read port file: ${e.message}` };
    }
    return { success: true, port: 8765, source: 'default' };
  });

  // --- Daemon logs ---
  ipcMain.handle('read-daemon-logs', (_event, maxLines = 100) => {
    const logPath = path.join(os.homedir(), '.ami', 'logs', 'app.log');
    try {
      if (!fs.existsSync(logPath)) {
        return { success: false, error: 'Log file not found', path: logPath, logs: [] };
      }
      const content = fs.readFileSync(logPath, 'utf-8');
      const lines = content.split('\n').filter(Boolean);
      const start = Math.max(0, lines.length - maxLines);
      return {
        success: true,
        path: logPath,
        logs: lines.slice(start),
        total_lines: lines.length,
      };
    } catch (e) {
      return { success: false, error: e.message, path: logPath, logs: [] };
    }
  });

  // --- Browser check (always true — Electron IS the browser) ---
  ipcMain.handle('check-browser-installed', () => {
    return { available: true, browser_type: 'electron-embedded' };
  });

  // --- File operations ---
  ipcMain.handle('read-file', (_event, filePath, encoding = 'utf-8') => {
    try {
      // Security: restrict file reads to the user's .ami directory
      const resolved = path.resolve(filePath);
      const amiDir = path.join(os.homedir(), '.ami');
      if (!resolved.startsWith(amiDir + path.sep) && resolved !== amiDir) {
        return { success: false, error: `Access denied: file reads restricted to ${amiDir}` };
      }
      if (!fs.existsSync(resolved)) {
        return { success: false, error: `File does not exist: ${filePath}` };
      }
      const content = fs.readFileSync(resolved, encoding);
      return { success: true, content };
    } catch (e) {
      return { success: false, error: e.message };
    }
  });

  ipcMain.handle('open-path', async (_event, filePath) => {
    if (!fs.existsSync(filePath)) {
      return { success: false, error: `Path does not exist: ${filePath}` };
    }
    const errorMessage = await shell.openPath(filePath);
    if (errorMessage) {
      return { success: false, error: errorMessage };
    }
    return { success: true, path: filePath };
  });

  ipcMain.handle('reveal-in-folder', (_event, filePath) => {
    if (!fs.existsSync(filePath)) {
      return { success: false, error: `Path does not exist: ${filePath}` };
    }
    shell.showItemInFolder(filePath);
    return { success: true, path: filePath };
  });

  // --- Store (key-value) ---
  ipcMain.handle('store-get', async (_event, key) => {
    try {
      const store = await getStore();
      return store.get(key);
    } catch (e) {
      console.error(`[Store] get(${key}) failed:`, e.message);
      return undefined;
    }
  });

  ipcMain.handle('store-set', async (_event, key, value) => {
    try {
      const store = await getStore();
      store.set(key, value);
    } catch (e) {
      console.error(`[Store] set(${key}) failed:`, e.message);
    }
  });

  ipcMain.handle('store-delete', async (_event, key) => {
    try {
      const store = await getStore();
      store.delete(key);
    } catch (e) {
      console.error(`[Store] delete(${key}) failed:`, e.message);
    }
  });

  // --- WebView controls ---
  ipcMain.handle('show-webview', (_event, id, bounds) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.showView(id, bounds);
  });

  ipcMain.handle('hide-webview', (_event, id) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.hideView(id);
  });

  ipcMain.handle('hide-all-webviews', () => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    webViewManager.hideAll();
    return { success: true };
  });

  ipcMain.handle('get-webview-url', (_event, id) => {
    if (!webViewManager) return null;
    return webViewManager.getUrl(id);
  });

  ipcMain.handle('get-all-webview-info', () => {
    if (!webViewManager) return {};
    return webViewManager.getAllViewsInfo();
  });

  ipcMain.handle('navigate-webview', async (_event, id, url) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.navigate(id, url);
  });

  ipcMain.handle('webview-go-back', (_event, id) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.goBack(id);
  });

  ipcMain.handle('webview-go-forward', (_event, id) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.goForward(id);
  });

  ipcMain.handle('webview-reload', (_event, id) => {
    if (!webViewManager) return { success: false, error: 'WebViewManager not ready' };
    return webViewManager.reload(id);
  });

  // --- Cookies ---
  ipcMain.handle('get-cookies', async (_event, filter = {}) => {
    const ses = session.fromPartition('persist:user_login');
    return ses.cookies.get(filter);
  });

  ipcMain.handle('remove-cookies', async (_event, url, name) => {
    const ses = session.fromPartition('persist:user_login');
    await ses.cookies.remove(url, name);
    return { success: true };
  });

  ipcMain.handle('clear-all-cookies', async () => {
    const ses = session.fromPartition('persist:user_login');
    await ses.clearStorageData({ storages: ['cookies'] });
    return { success: true };
  });
}

// ==================== App lifecycle ====================

app.whenReady().then(async () => {
  // CDP port is determined synchronously before app.ready — no await needed.

  // Set UA on the shared login partition
  session.fromPartition('persist:user_login').setUserAgent(platformUA);

  // Content Security Policy — restrict script/resource loading
  // In dev mode, Vite injects inline scripts (React Fast Refresh preamble) that
  // require 'unsafe-inline'. Only enforce strict CSP in production builds.
  const isDevMode = !app.isPackaged || process.env.AMI_DEV_MODE || process.env.VITE_DEV_SERVER_URL;
  if (!isDevMode) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data: https: http:; " +
            "font-src 'self' data:; " +
            "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*;"
          ],
        },
      });
    });
  }

  // Register IPC handlers
  registerIpcHandlers();

  // Create main window
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    center: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  // Create WebView pool
  webViewManager = new WebViewManager(win);
  webViewManager.initPool();

  // Start daemon — surface errors to renderer via IPC
  let daemonStartError = null;
  daemonLauncher = new DaemonLauncher(cdpPort);
  daemonLauncher.start().catch((err) => {
    console.error('[Main] Failed to start daemon:', err);
    daemonStartError = err.message || String(err);
  });

  // Expose daemon startup error to renderer
  ipcMain.handle('get-daemon-start-error', () => daemonStartError);

  // Load frontend
  const isDev = !app.isPackaged || process.env.AMI_DEV_MODE || process.env.VITE_DEV_SERVER_URL;
  if (isDev) {
    const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:1420';
    win.loadURL(devUrl);
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // Show window when content is ready
  win.webContents.on('did-finish-load', () => {
    win.show();
  });

  // DevTools: only when explicitly requested via AMI_DEBUG=1
  if (process.env.AMI_DEBUG) {
    win.webContents.openDevTools({ mode: 'detach' });
  }

  // Crash recovery: reload on renderer crash (max 3 attempts)
  let mainCrashCount = 0;
  win.webContents.on('render-process-gone', (_event, details) => {
    mainCrashCount++;
    console.error(`[Main] Renderer crashed (${mainCrashCount}): ${details.reason}`);
    if (mainCrashCount > 3) {
      console.error('[Main] Too many crashes, giving up');
      return;
    }
    setTimeout(() => {
      if (win && !win.isDestroyed()) {
        win.reload();
      }
    }, 1000 * mainCrashCount);
  });
});

// Quit when all windows are closed
app.on('window-all-closed', () => {
  // On macOS/Linux/Windows, when last window closes → quit
  // Actual cleanup happens in before-quit
  app.quit();
});

// Graceful shutdown — stop daemon before quitting
app.on('before-quit', async (event) => {
  if (isQuitting) return; // Already handling shutdown
  isQuitting = true;

  if (daemonLauncher) {
    event.preventDefault();
    try {
      await daemonLauncher.stop();
    } catch (err) {
      console.error('[Main] Error stopping daemon:', err);
    }
    daemonLauncher = null;
  }

  if (webViewManager) {
    webViewManager.destroy();
    webViewManager = null;
  }

  app.quit(); // Safe: isQuitting is true, so we won't re-enter
});

// Focus existing window when second instance is launched
app.on('second-instance', () => {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});
