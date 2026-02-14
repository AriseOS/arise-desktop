/**
 * BrowserSession — CDP connection to Electron's embedded Chromium.
 *
 * Ported from browser_session.py (HybridBrowserSession).
 *
 * Key concepts:
 * - Connects via CDP to Electron's Chromium (BROWSER_CDP_PORT env var)
 * - 8 WebContentsView pool (shared `persist:user_login` partition)
 * - Pool pages marked with `ami=pool` URL
 * - Tab management with Tab Group support
 * - Singleton per session-id
 */

import { chromium, type Browser, type BrowserContext, type Page } from "playwright";
import { BrowserConfig } from "./config.js";
import { PageSnapshot } from "./page-snapshot.js";
import { ActionExecutor } from "./action-executor.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("browser-session");

// ===== Async Mutex =====

class Mutex {
  private _queue: (() => void)[] = [];
  private _locked = false;

  async acquire(): Promise<void> {
    if (!this._locked) {
      this._locked = true;
      return;
    }
    await new Promise<void>((resolve) => this._queue.push(resolve));
  }

  release(): void {
    const next = this._queue.shift();
    if (next) next();
    else this._locked = false;
  }
}

// ===== Tab Group =====

const TAB_GROUP_COLORS = ["blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange"];

interface TabGroup {
  taskId: string;
  title: string;
  color: string;
  tabs: Map<string, Page>;
  currentTabId?: string;
}

// ===== Tab ID Generator =====

let _tabCounter = 0;

function nextTabId(): string {
  _tabCounter++;
  return `tab-${String(_tabCounter).padStart(3, "0")}`;
}

// ===== BrowserSession =====

export class BrowserSession {
  // Singleton registry
  private static _instances = new Map<string, BrowserSession>();
  private static _daemonSession: BrowserSession | null = null;

  // Connection
  private _browser: Browser | null = null;
  private _context: BrowserContext | null = null;
  private _playwright: Awaited<ReturnType<typeof chromium["connectOverCDP"]>> | null = null;

  // Pages
  private _pages = new Map<string, Page>();
  private _page: Page | null = null;
  private _currentTabId: string | null = null;

  // Track all claimed pool pages across all sessions to prevent double-allocation
  private static _claimedPages = new WeakSet<Page>();

  // Mutex for pool page claiming — ensures only one session claims at a time
  // (matches Python _pool_claim_lock). Without this, concurrent _claimPoolPage()
  // calls cause "Navigation to about:blank is interrupted by another navigation".
  private static _poolClaimLock = new Mutex();

  // Tab Groups
  private _tabGroups = new Map<string, TabGroup>();
  private _colorIndex = 0;

  // Page → Electron viewId mapping (for frontend display / pool return)
  private _pageToViewId = new Map<Page, string>();

  // Components
  snapshot: PageSnapshot | null = null;
  executor: ActionExecutor | null = null;

  // Config
  private _sessionId: string;
  private _cdpPort: number | null;

  constructor(sessionId: string) {
    this._sessionId = sessionId;
    const cdpPortStr = process.env.BROWSER_CDP_PORT;
    this._cdpPort = cdpPortStr ? parseInt(cdpPortStr) : null;
  }

  get sessionId(): string {
    return this._sessionId;
  }

  get isConnected(): boolean {
    return this._browser?.isConnected() ?? false;
  }

  get currentPage(): Page | null {
    return this._page;
  }

  get currentTabId(): string | null {
    return this._currentTabId;
  }

  /** Return the Electron WebContentsView ID for the active page ("0"-"7" or null). */
  get webviewId(): string | null {
    return this._page ? (this._pageToViewId.get(this._page) ?? null) : null;
  }

  // ===== Singleton =====

  static getInstance(sessionId: string): BrowserSession {
    let instance = BrowserSession._instances.get(sessionId);
    if (!instance) {
      instance = new BrowserSession(sessionId);
      BrowserSession._instances.set(sessionId, instance);
    }
    return instance;
  }

  /** Get an existing instance without creating a new one. */
  static getExistingInstance(sessionId: string): BrowserSession | null {
    return BrowserSession._instances.get(sessionId) ?? null;
  }

  static getDaemonSession(): BrowserSession | null {
    return BrowserSession._daemonSession;
  }

  // ===== Connection =====

  async ensureBrowser(): Promise<void> {
    if (this._browser?.isConnected()) return;

    if (!this._cdpPort) {
      throw new Error("BROWSER_CDP_PORT not set — cannot connect to Electron");
    }

    logger.info({ cdpPort: this._cdpPort, sessionId: this._sessionId }, "Connecting via CDP");

    this._browser = await chromium.connectOverCDP(`http://127.0.0.1:${this._cdpPort}`);

    // Get the default context (Electron's persist:user_login partition)
    const contexts = this._browser.contexts();
    if (contexts.length === 0) {
      throw new Error("No browser contexts found via CDP");
    }
    this._context = contexts[0];

    logger.info(
      { contexts: contexts.length, pages: this._context.pages().length },
      "CDP connection established",
    );

    // Find pool pages and claim one
    await this._initializeFromPool();
  }

  private async _initializeFromPool(): Promise<void> {
    if (!this._context) return;

    const page = await this._takeOnePoolPage();
    if (page) {
      await this._registerClaimedPage(page);
    }
  }

  /**
   * Atomically find and claim ONE free pool page.
   * Returns null if no pool pages are available (non-fatal for init).
   * Only the scan + claim + goto("about:blank") need the lock.
   */
  private async _takeOnePoolPage(): Promise<Page | null> {
    if (!this._context) return null;

    await BrowserSession._poolClaimLock.acquire();
    try {
      for (const page of this._context.pages()) {
        try {
          const url = page.url();
          if (url.includes("ami=pool") && !page.isClosed() && !BrowserSession._claimedPages.has(page)) {
            BrowserSession._claimedPages.add(page);

            const match = url.match(/viewId=(\d+)/);
            const viewId = match?.[1];
            if (viewId) this._pageToViewId.set(page, viewId);

            // Navigate to claimed marker so:
            // 1. Other sessions won't re-claim it (no "ami=pool" in URL)
            // 2. Frontend tab bar won't show it as active (filters "ami=claimed")
            const claimedUrl = viewId
              ? `${BrowserConfig.claimedMarkerUrl}&viewId=${viewId}`
              : BrowserConfig.claimedMarkerUrl;
            await page.goto(claimedUrl);
            return page;
          }
        } catch {
          // skip closed pages
        }
      }
      return null;
    } finally {
      BrowserSession._poolClaimLock.release();
    }
  }

  /**
   * Register a claimed pool page as this session's active page.
   * Sets up snapshot, executor, and event listeners.
   *
   * No setViewportSize needed — Electron's WebContentsView.setBounds()
   * controls the CSS layout viewport directly. Off-screen views use
   * 1920×1080 bounds so the agent gets a full viewport.
   */
  private async _registerClaimedPage(page: Page): Promise<void> {
    const tabId = nextTabId();
    this._pages.set(tabId, page);
    this._page = page;
    this._currentTabId = tabId;
    this.snapshot = new PageSnapshot(page);
    this.executor = new ActionExecutor(page, this);

    page.on("popup", (popup) => this._handleNewPage(popup).catch((e) =>
      logger.warn({ err: e }, "Error handling popup"),
    ));

    page.on("crash", () => {
      logger.error({ tabId }, "Page crashed — removing from registry");
      this._pages.delete(tabId);
      BrowserSession._claimedPages.delete(page);
      if (this._currentTabId === tabId) {
        this._currentTabId = null;
        this._page = null;
        this.snapshot = null;
        this.executor = null;
      }
    });

    const viewId = this._pageToViewId.get(page);
    logger.info({ tabId, viewId }, "Page claimed and registered");
  }

  private async _handleNewPage(page: Page): Promise<void> {
    const tabId = nextTabId();
    this._pages.set(tabId, page);

    const cleanupOnGone = () => {
      this._pages.delete(tabId);
      if (this._currentTabId === tabId) {
        // Switch to another tab
        const nextEntry = this._pages.entries().next();
        if (!nextEntry.done) {
          const [nextId, nextPage] = nextEntry.value;
          this._currentTabId = nextId;
          this._page = nextPage;
          this.snapshot = new PageSnapshot(nextPage);
          this.executor = new ActionExecutor(nextPage, this);
        } else {
          this._currentTabId = null;
          this._page = null;
          this.snapshot = null;
          this.executor = null;
        }
      }
    };

    page.on("close", cleanupOnGone);
    page.on("crash", () => {
      logger.error({ tabId }, "Auto-registered page crashed — removing from registry");
      cleanupOnGone();
    });

    logger.info({ tabId, url: page.url() }, "New page auto-registered");
  }

  // ===== Pool Management =====

  private async _claimPoolPage(): Promise<Page> {
    const MAX_RETRIES = 3;
    const RETRY_DELAY_MS = 3000;

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      const page = await this._takeOnePoolPage();
      if (page) return page;

      if (attempt < MAX_RETRIES - 1) {
        logger.warn(
          { attempt: attempt + 1, maxRetries: MAX_RETRIES },
          "No pool pages available, retrying...",
        );
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
      }
    }

    throw new Error("No pool pages available — all WebContentsViews are in use");
  }

  private async _returnPageToPool(page: Page): Promise<void> {
    try {
      BrowserSession._claimedPages.delete(page);
      if (!page.isClosed()) {
        // Restore pool marker URL with viewId so it can be reclaimed
        const viewId = this._pageToViewId.get(page);
        const poolUrl = viewId !== undefined
          ? `${BrowserConfig.poolMarkerUrl}&viewId=${viewId}`
          : BrowserConfig.poolMarkerUrl;
        await page.goto(poolUrl);
      }
      this._pageToViewId.delete(page);
    } catch (e) {
      logger.warn({ err: e }, "Error returning page to pool");
    }
  }

  // ===== Page Access =====

  async getPage(): Promise<Page> {
    await this.ensureBrowser();
    if (!this._page) {
      // _initializeFromPool may have lost the race for a pool page.
      // Claim one explicitly (with mutex + retry).
      logger.info({ sessionId: this._sessionId }, "No page after init — claiming from pool");
      const page = await this._claimPoolPage();
      await this._registerClaimedPage(page);
    }
    return this._page!;
  }

  // ===== Navigation =====

  async visit(url: string): Promise<string> {
    await this.ensureBrowser();
    const page = await this.getPage();

    await page.goto(url, { timeout: BrowserConfig.navigationTimeout });
    await page.waitForLoadState("domcontentloaded");

    try {
      await page.waitForLoadState("networkidle", {
        timeout: BrowserConfig.networkIdleTimeout,
      });
    } catch {
      logger.debug("Network idle timeout — continuing");
    }

    return `Navigated to ${url}`;
  }

  // ===== Snapshot =====

  async getSnapshot(options?: {
    forceRefresh?: boolean;
    diffOnly?: boolean;
    viewportLimit?: boolean;
  }): Promise<string> {
    if (!this.snapshot) return "<empty>";
    return this.snapshot.capture(options);
  }

  async getSnapshotWithElements(options?: {
    viewportLimit?: boolean;
  }): Promise<Record<string, unknown>> {
    if (!this.snapshot) {
      return { snapshotText: "<empty>", elements: {} };
    }
    return this.snapshot.getFullResult(options);
  }

  // ===== Action Execution =====

  async execAction(action: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (!this.executor) {
      return { success: false, message: "No executor available", details: {} };
    }
    return this.executor.execute(action);
  }

  // ===== Tab Management =====

  async getTabInfo(): Promise<Record<string, unknown>[]> {
    const tabs: Record<string, unknown>[] = [];
    for (const [tabId, page] of this._pages) {
      try {
        tabs.push({
          tab_id: tabId,
          url: page.isClosed() ? "(closed)" : page.url(),
          title: page.isClosed() ? "(closed)" : await page.title(),
          is_current: tabId === this._currentTabId,
        });
      } catch {
        tabs.push({
          tab_id: tabId,
          url: "(error)",
          title: "(error)",
          is_current: tabId === this._currentTabId,
        });
      }
    }
    return tabs;
  }

  async switchToTab(tabId: string): Promise<boolean> {
    const page = this._pages.get(tabId);
    if (!page || page.isClosed()) {
      return false;
    }

    this._currentTabId = tabId;
    this._page = page;
    this.snapshot = new PageSnapshot(page);
    this.executor = new ActionExecutor(page, this);

    logger.debug({ tabId }, "Switched to tab");
    return true;
  }

  async closeTab(tabId: string): Promise<boolean> {
    const page = this._pages.get(tabId);
    if (!page) return false;

    await this._returnPageToPool(page);
    this._pages.delete(tabId);

    // Switch to another tab if needed
    if (tabId === this._currentTabId) {
      const nextEntry = this._pages.entries().next();
      if (!nextEntry.done) {
        const [nextId] = nextEntry.value;
        await this.switchToTab(nextId);
      } else {
        this._currentTabId = null;
        this._page = null;
        this.snapshot = null;
        this.executor = null;
      }
    }

    return true;
  }

  async createNewTab(url?: string): Promise<[string, Page]> {
    await this.ensureBrowser();
    const page = await this._claimPoolPage();
    const tabId = nextTabId();

    if (url) {
      try {
        await page.goto(url, { timeout: BrowserConfig.navigationTimeout });
        await page.waitForLoadState("domcontentloaded");
      } catch (e) {
        logger.warn({ url, err: e }, "Navigation failed for new tab");
      }
    }

    this._pages.set(tabId, page);

    page.on("close", () => {
      this._pages.delete(tabId);
    });

    page.on("crash", () => {
      logger.error({ tabId }, "Page crashed in tab — removing from registry");
      this._pages.delete(tabId);
      BrowserSession._claimedPages.delete(page);
      if (this._currentTabId === tabId) {
        this._currentTabId = null;
        this._page = null;
        this.snapshot = null;
        this.executor = null;
      }
    });

    page.on("popup", (popup) => this._handleNewPage(popup).catch((e) =>
      logger.warn({ err: e }, "Error handling popup"),
    ));

    return [tabId, page];
  }

  // ===== Tab Group Management =====

  async createTabGroup(taskId: string, title?: string): Promise<TabGroup> {
    const existing = this._tabGroups.get(taskId);
    if (existing) return existing;

    const groupTitle = title ?? `task-${taskId.slice(0, 8)}`;
    const color = TAB_GROUP_COLORS[this._colorIndex % TAB_GROUP_COLORS.length];
    this._colorIndex++;

    const group: TabGroup = {
      taskId,
      title: groupTitle,
      color,
      tabs: new Map(),
    };

    this._tabGroups.set(taskId, group);
    logger.info({ taskId, title: groupTitle, color }, "Created Tab Group");
    return group;
  }

  async createTabInGroup(taskId: string, url?: string): Promise<[string, Page]> {
    await this.ensureBrowser();

    let group = this._tabGroups.get(taskId);
    if (!group) {
      group = await this.createTabGroup(taskId);
    }

    const page = await this._claimPoolPage();
    const tabId = nextTabId();

    if (url) {
      try {
        await page.goto(url, { timeout: BrowserConfig.navigationTimeout });
        await page.waitForLoadState("domcontentloaded");
      } catch (e) {
        logger.warn({ url, err: e }, "Navigation failed for new tab in group");
      }
    }

    group.tabs.set(tabId, page);
    this._pages.set(tabId, page);

    page.on("close", () => {
      this._pages.delete(tabId);
      group!.tabs.delete(tabId);
    });

    page.on("crash", () => {
      logger.error({ tabId, taskId }, "Page crashed in group tab — removing from registry");
      this._pages.delete(tabId);
      group!.tabs.delete(tabId);
      BrowserSession._claimedPages.delete(page);
      if (this._currentTabId === tabId) {
        this._currentTabId = null;
        this._page = null;
        this.snapshot = null;
        this.executor = null;
      }
    });

    page.on("popup", (popup) => this._handleNewPage(popup).catch((e) =>
      logger.warn({ err: e }, "Error handling popup"),
    ));

    logger.info({ tabId, taskId, groupTitle: group.title }, "Created tab in group");
    return [tabId, page];
  }

  async closeTabGroup(taskId: string): Promise<boolean> {
    const group = this._tabGroups.get(taskId);
    if (!group) return false;

    // Snapshot to array to avoid iterator corruption from page close event listeners
    const tabEntries = [...group.tabs];
    for (const [tabId, page] of tabEntries) {
      try {
        await this._returnPageToPool(page); // also clears _claimedPages
        this._pages.delete(tabId);
      } catch (e) {
        logger.warn({ tabId, err: e }, "Error returning tab to pool");
      }
    }
    group.tabs.clear();

    // Update current tab if it was in this group
    if (this._currentTabId && !this._pages.has(this._currentTabId)) {
      const nextEntry = this._pages.entries().next();
      if (!nextEntry.done) {
        await this.switchToTab(nextEntry.value[0]);
      } else {
        this._currentTabId = null;
        this._page = null;
        this.snapshot = null;
        this.executor = null;
      }
    }

    this._tabGroups.delete(taskId);
    logger.info({ taskId, title: group.title }, "Tab Group closed");
    return true;
  }

  getTabGroupsInfo(): Record<string, unknown>[] {
    const info: Record<string, unknown>[] = [];
    for (const [taskId, group] of this._tabGroups) {
      const tabs: Record<string, unknown>[] = [];
      for (const [tabId, page] of group.tabs) {
        try {
          tabs.push({
            tab_id: tabId,
            url: page.isClosed() ? "(closed)" : page.url(),
            is_current: tabId === group.currentTabId,
          });
        } catch {
          tabs.push({ tab_id: tabId, url: "(error)", is_current: false });
        }
      }
      info.push({
        task_id: taskId,
        title: group.title,
        color: group.color,
        tab_count: group.tabs.size,
        tabs,
      });
    }
    return info;
  }

  // ===== Screenshot =====

  async takeScreenshot(): Promise<string | null> {
    const page = this._page;
    if (!page || page.isClosed()) return null;

    try {
      const buffer = await page.screenshot({
        type: "jpeg",
        quality: 75,
        timeout: BrowserConfig.screenshotTimeout,
      });
      return `data:image/jpeg;base64,${buffer.toString("base64")}`;
    } catch (e) {
      logger.warn({ err: e }, "Screenshot failed");
      return null;
    }
  }

  // ===== Daemon Lifecycle =====

  static async startDaemonSession(): Promise<BrowserSession> {
    if (BrowserSession._daemonSession) {
      return BrowserSession._daemonSession;
    }

    const session = new BrowserSession("daemon");
    await session.ensureBrowser();
    BrowserSession._daemonSession = session;
    BrowserSession._instances.set("daemon", session);

    logger.info("Daemon browser session started");
    return session;
  }

  static async stopDaemonSession(): Promise<void> {
    if (BrowserSession._daemonSession) {
      await BrowserSession._daemonSession.close();
      BrowserSession._daemonSession = null;
      BrowserSession._instances.delete("daemon");
      logger.info("Daemon browser session stopped");
    }
  }

  // ===== Cleanup =====

  async close(): Promise<void> {
    // Return all pages to pool with their viewIds
    for (const page of this._pages.values()) {
      try {
        BrowserSession._claimedPages.delete(page);
        if (!page.isClosed()) {
          const viewId = this._pageToViewId.get(page);
          const poolUrl = viewId !== undefined
            ? `${BrowserConfig.poolMarkerUrl}&viewId=${viewId}`
            : BrowserConfig.poolMarkerUrl;
          await page.goto(poolUrl);
        }
      } catch {
        // best effort
      }
    }

    this._pages.clear();
    this._tabGroups.clear();
    this._pageToViewId.clear();
    this._page = null;
    this._currentTabId = null;
    this.snapshot = null;
    this.executor = null;

    // Release CDP browser reference (does NOT close Electron's browser process).
    // For CDP-connected browsers, close() would "clear all created contexts" which
    // could disrupt shared pool pages. Instead, just drop the reference.
    if (this._browser) {
      this._browser = null;
    }

    this._context = null;

    // Remove from instance registry to prevent zombie sessions
    BrowserSession._instances.delete(this._sessionId);
    if (BrowserSession._daemonSession === this) {
      BrowserSession._daemonSession = null;
    }
  }

  static async closeAllSessions(): Promise<void> {
    for (const session of BrowserSession._instances.values()) {
      try {
        await session.close();
      } catch (e) {
        logger.error({ sessionId: session._sessionId, err: e }, "Error closing session");
      }
    }
    BrowserSession._instances.clear();
    BrowserSession._daemonSession = null;
  }
}
