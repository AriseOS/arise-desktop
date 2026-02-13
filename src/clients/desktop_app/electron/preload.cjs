/**
 * Preload script — exposes Electron IPC to the renderer via contextBridge.
 * The renderer accesses these via window.electronAPI.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Daemon
  getDaemonPort: () => ipcRenderer.invoke('get-daemon-port'),
  getDaemonStartError: () => ipcRenderer.invoke('get-daemon-start-error'),
  readDaemonLogs: (maxLines) => ipcRenderer.invoke('read-daemon-logs', maxLines),

  // Browser check (always true — Electron IS the browser)
  checkBrowserInstalled: () => ipcRenderer.invoke('check-browser-installed'),

  // File operations
  readFile: (filePath, encoding) => ipcRenderer.invoke('read-file', filePath, encoding),
  openPath: (filePath) => ipcRenderer.invoke('open-path', filePath),
  revealInFolder: (filePath) => ipcRenderer.invoke('reveal-in-folder', filePath),

  // Store (key-value persistence via electron-store)
  storeGet: (key) => ipcRenderer.invoke('store-get', key),
  storeSet: (key, value) => ipcRenderer.invoke('store-set', key, value),
  storeDelete: (key) => ipcRenderer.invoke('store-delete', key),

  // WebView controls
  showWebview: (id, bounds) => ipcRenderer.invoke('show-webview', id, bounds),
  hideWebview: (id) => ipcRenderer.invoke('hide-webview', id),
  hideAllWebviews: () => ipcRenderer.invoke('hide-all-webviews'),
  getWebviewUrl: (id) => ipcRenderer.invoke('get-webview-url', id),
  navigateWebview: (id, url) => ipcRenderer.invoke('navigate-webview', id, url),
  webviewGoBack: (id) => ipcRenderer.invoke('webview-go-back', id),
  webviewGoForward: (id) => ipcRenderer.invoke('webview-go-forward', id),
  webviewReload: (id) => ipcRenderer.invoke('webview-reload', id),

  // Cookies
  getCookies: (filter) => ipcRenderer.invoke('get-cookies', filter),
  removeCookies: (url, name) => ipcRenderer.invoke('remove-cookies', url, name),
  clearAllCookies: () => ipcRenderer.invoke('clear-all-cookies'),

  // All views info (for tab bar)
  getAllWebviewInfo: () => ipcRenderer.invoke('get-all-webview-info'),

  // Events (Main → Renderer)
  onUrlUpdated: (callback) => {
    const listener = (_event, viewId, url) => callback(viewId, url);
    ipcRenderer.on('url-updated', listener);
    return () => ipcRenderer.removeListener('url-updated', listener);
  },

  onViewStateChanged: (callback) => {
    const listener = (_event, viewId, info) => callback(viewId, info);
    ipcRenderer.on('view-state-changed', listener);
    return () => ipcRenderer.removeListener('view-state-changed', listener);
  },
});
