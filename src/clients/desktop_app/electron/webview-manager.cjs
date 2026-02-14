/**
 * WebViewManager — manages a pool of WebContentsView instances for browser automation.
 * Each view shares the 'persist:user_login' partition for cookie sharing.
 * Playwright connects via CDP and claims pool pages by their marker URL.
 */

const { WebContentsView, session } = require('electron');
const { STEALTH_SCRIPT } = require('./stealth.cjs');

const POOL_SIZE = 16;
const POOL_MARKER = 'about:blank?ami=pool'; // Base marker; actual URLs include &viewId=N

// Off-screen dimensions for agent browsing.
// Must be full viewport size so that Chromium's CSS layout viewport matches
// what the agent expects (1920×1080). Position off-screen so the user can't see it.
// Same approach as Eigent: setBounds({ x: -1919, y: -1079, width: 1920, height: 1080 }).
const OFFSCREEN_WIDTH = 1920;
const OFFSCREEN_HEIGHT = 1080;

class WebViewManager {
  constructor(win) {
    this.win = win;
    this.views = new Map(); // id → { view, isShow }
  }

  /**
   * Create the initial pool of WebContentsView instances.
   */
  initPool() {
    for (let i = 0; i < POOL_SIZE; i++) {
      this._createView(String(i));
    }
    console.log(`[WebViewManager] Pool initialized with ${POOL_SIZE} views`);
  }

  _createView(id) {
    const view = new WebContentsView({
      webPreferences: {
        partition: 'persist:user_login',
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        backgroundThrottling: true,
        disableBlinkFeatures: 'AutomationControlled,Accelerated2dCanvas',
      },
    });

    // Mute audio
    view.webContents.audioMuted = true;

    // Position off-screen at full viewport dimensions so that Chromium's
    // CSS layout viewport is 1920×1080 — matching what the agent expects.
    // No setViewportSize / Emulation.setDeviceMetricsOverride needed;
    // setBounds alone controls the CSS viewport naturally.
    view.setBounds({
      x: -(OFFSCREEN_WIDTH - 1),
      y: -(OFFSCREEN_HEIGHT - 1),
      width: OFFSCREEN_WIDTH,
      height: OFFSCREEN_HEIGHT,
    });

    // Inject stealth on every page load.
    // We use did-finish-load + executeJavaScript (same as Eigent reference).
    // NOTE: We do NOT use webContents.debugger.attach() because Playwright also
    // connects via CDP (--remote-debugging-port). Two CDP clients on the same
    // target causes conflicts and command failures.
    view.webContents.on('did-finish-load', () => {
      view.webContents.executeJavaScript(STEALTH_SCRIPT).catch(() => {});
    });

    // Track URL changes and notify renderer
    view.webContents.on('did-navigate', (_event, url) => {
      if (this.win && !this.win.isDestroyed()) {
        const info = this.views.get(id);
        if (info && info.isShow) {
          this.win.webContents.send('url-updated', id, url);
        }
        // Always fire view-state-changed for tab bar updates
        const title = view.webContents.isDestroyed() ? '' : view.webContents.getTitle();
        this.win.webContents.send('view-state-changed', id, { url, title });
      }
    });

    view.webContents.on('did-navigate-in-page', (_event, url) => {
      if (this.win && !this.win.isDestroyed()) {
        const info = this.views.get(id);
        if (info && info.isShow) {
          this.win.webContents.send('url-updated', id, url);
        }
        const title = view.webContents.isDestroyed() ? '' : view.webContents.getTitle();
        this.win.webContents.send('view-state-changed', id, { url, title });
      }
    });

    view.webContents.on('page-title-updated', (_event, title) => {
      if (this.win && !this.win.isDestroyed()) {
        const url = view.webContents.isDestroyed() ? '' : view.webContents.getURL();
        this.win.webContents.send('view-state-changed', id, { url, title });
      }
    });

    // Crash recovery: reload pool marker if renderer crashes
    view.webContents.on('render-process-gone', (_event, details) => {
      console.error(`[WebViewManager] View ${id} renderer crashed: ${details.reason}`);
      setTimeout(() => {
        if (!view.webContents.isDestroyed()) {
          console.log(`[WebViewManager] Reloading view ${id} after crash`);
          view.webContents.loadURL(`${POOL_MARKER}&viewId=${id}`);
        }
      }, 1000);
    });

    // Log load failures for diagnostics (skip aborted loads, errorCode -3)
    view.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
      if (errorCode === -3) return;
      console.warn(`[WebViewManager] View ${id} load failed: ${errorDescription} (${errorCode}) for ${validatedURL}`);
    });

    // Prevent popups — navigate in same view (only safe URL schemes)
    view.webContents.setWindowOpenHandler(({ url }) => {
      try {
        const parsed = new URL(url);
        if (['http:', 'https:', 'about:'].includes(parsed.protocol)) {
          view.webContents.loadURL(url);
        }
      } catch {
        // Invalid URL — ignore
      }
      return { action: 'deny' };
    });

    // Load pool marker URL with viewId for daemon to extract
    view.webContents.loadURL(`${POOL_MARKER}&viewId=${id}`);

    // Add as child of the main window
    this.win.contentView.addChildView(view);

    this.views.set(id, { view, isShow: false });
  }

  /**
   * Move a view on-screen at the given bounds.
   */
  showView(id, bounds) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };

    if (!bounds || typeof bounds.x !== 'number' || typeof bounds.y !== 'number'
        || typeof bounds.width !== 'number' || typeof bounds.height !== 'number') {
      return { success: false, error: 'Invalid bounds: must have numeric x, y, width, height' };
    }

    // Reject degenerate bounds (element not laid out or invalid)
    if (bounds.width < 10 || bounds.height < 10) {
      return { success: false, error: `Bounds too small: ${bounds.width}x${bounds.height}` };
    }

    info.isShow = true;

    if (!info.view.webContents.isDestroyed()) {
      info.view.webContents.setBackgroundThrottling(false);
    }

    info.view.setBounds(bounds);

    if (!info.view.webContents.isDestroyed()) {
      // Force repaint for views that were off-screen with backgroundThrottling
      info.view.webContents.invalidate();
    }

    // Send current URL to renderer
    if (this.win && !this.win.isDestroyed()) {
      const currentUrl = info.view.webContents.isDestroyed() ? '' : info.view.webContents.getURL();
      this.win.webContents.send('url-updated', id, currentUrl);
    }

    return { success: true };
  }

  /**
   * Move a view off-screen.
   */
  hideView(id) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };

    const url = info.view.webContents.isDestroyed() ? '(destroyed)' : info.view.webContents.getURL();
    console.log(`[WebViewManager] hideView(${id}) url=${url}`);

    // Restore full viewport dimensions off-screen so the agent's CSS
    // layout viewport stays at 1920×1080 while browsing in the background.
    info.view.setBounds({
      x: -(OFFSCREEN_WIDTH - 1),
      y: -(OFFSCREEN_HEIGHT - 1),
      width: OFFSCREEN_WIDTH,
      height: OFFSCREEN_HEIGHT,
    });
    info.isShow = false;

    if (!info.view.webContents.isDestroyed()) {
      info.view.webContents.setBackgroundThrottling(true);
    }

    return { success: true };
  }

  /**
   * Hide all views.
   */
  hideAll() {
    for (const [id] of this.views) {
      this.hideView(id);
    }
  }

  /**
   * Get info for all views: { "0": { url, title, isShow }, ... }
   */
  getAllViewsInfo() {
    const result = {};
    for (const [id, info] of this.views) {
      const wc = info.view.webContents;
      result[id] = {
        url: wc.isDestroyed() ? '' : wc.getURL(),
        title: wc.isDestroyed() ? '' : wc.getTitle(),
        isShow: info.isShow,
      };
    }
    return result;
  }

  /**
   * Get current URL of a view.
   */
  getUrl(id) {
    const info = this.views.get(id);
    if (!info) return null;
    return info.view.webContents.getURL();
  }

  /**
   * Navigate a view to a URL.
   */
  async navigate(id, url) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };

    // Validate URL scheme to prevent file://, javascript:, data: attacks
    try {
      const parsed = new URL(url);
      const allowed = ['http:', 'https:', 'about:'];
      if (!allowed.includes(parsed.protocol)) {
        return { success: false, error: `URL scheme '${parsed.protocol}' is not allowed` };
      }
    } catch {
      return { success: false, error: `Invalid URL: ${url}` };
    }

    try {
      await info.view.webContents.loadURL(url);
      return { success: true };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  goBack(id) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };
    if (info.view.webContents.canGoBack()) {
      info.view.webContents.goBack();
    }
    return { success: true };
  }

  goForward(id) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };
    if (info.view.webContents.canGoForward()) {
      info.view.webContents.goForward();
    }
    return { success: true };
  }

  reload(id) {
    const info = this.views.get(id);
    if (!info) return { success: false, error: `View ${id} not found` };
    info.view.webContents.reload();
    return { success: true };
  }

  /**
   * Destroy all views and clean up.
   */
  destroy() {
    for (const [id, info] of this.views) {
      try {
        if (!info.view.webContents.isDestroyed()) {
          info.view.webContents.removeAllListeners();
          info.view.webContents.close();
        }
        if (this.win && this.win.contentView) {
          this.win.contentView.removeChildView(info.view);
        }
      } catch (e) {
        console.error(`[WebViewManager] Error destroying view ${id}:`, e.message);
      }
    }
    this.views.clear();
  }
}

module.exports = { WebViewManager };
