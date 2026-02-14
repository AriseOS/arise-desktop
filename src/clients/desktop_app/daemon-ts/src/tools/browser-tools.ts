/**
 * Browser Tools — All browser automation tools as AgentTool<TSchema>[].
 *
 * Ported from browser_toolkit.py.
 *
 * 15 tools: visit_page, click, type, enter, back, forward, scroll,
 * select, press_key, mouse_control, get_page_snapshot, get_tab_info,
 * switch_tab, new_tab, close_tab.
 *
 * Each tool:
 * 1. Gets browser session
 * 2. Executes action via ActionExecutor
 * 3. Waits for stability
 * 4. Returns snapshot + page context + tab info
 * 5. Sends screenshot SSE event
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import { BrowserSession } from "../browser/browser-session.js";
import { BrowserConfig } from "../browser/config.js";
import { ActionExecutor } from "../browser/action-executor.js";
import type { SSEEmitter } from "../events/emitter.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("browser-tools");

// ===== Shared helpers =====

async function getSession(sessionId: string): Promise<BrowserSession> {
  const session = BrowserSession.getInstance(sessionId);
  await session.ensureBrowser();
  return session;
}

async function waitForStability(session: BrowserSession): Promise<void> {
  const page = session.currentPage;
  if (!page || page.isClosed()) return;

  try {
    await page.waitForLoadState("domcontentloaded", {
      timeout: BrowserConfig.domLoadedTimeout,
    });
    try {
      await page.waitForLoadState("networkidle", {
        timeout: BrowserConfig.networkIdleTimeout,
      });
    } catch {
      // Network idle is optional
    }
  } catch {
    // Don't fail if wait times out
  }
}

async function getPageContext(session: BrowserSession): Promise<string> {
  const page = session.currentPage;
  if (!page || page.isClosed()) return "";
  try {
    const url = page.url();
    const title = await page.title();
    return `**Current Page:** ${title}\n**URL:** ${url}`;
  } catch {
    return "";
  }
}

async function getTabInfoSummary(session: BrowserSession): Promise<string> {
  try {
    const tabInfo = await session.getTabInfo();
    if (tabInfo.length <= 1) return "";
    const currentTabId = session.currentTabId;
    const currentTab = tabInfo.find((t) => t.tab_id === currentTabId);
    const currentTitle = currentTab
      ? String(currentTab.title || "Unknown").slice(0, 50)
      : "Unknown";
    return `**Tabs:** ${tabInfo.length} open (current: ${currentTabId} - ${currentTitle})`;
  } catch {
    return "";
  }
}

const SNAPSHOT_URL_TIP =
  "> **Note**: This snapshot does NOT include href URLs. To see all links with their URLs, call `browser_get_page_snapshot(include_links=true)` instead of clicking each link.\n\n";

async function getSnapshot(session: BrowserSession, forceRefresh = false): Promise<string> {
  try {
    const snapshot = await session.getSnapshot({ forceRefresh });
    // Strip inline href suffixes to save tokens
    return SNAPSHOT_URL_TIP + snapshot.replace(/ -> https?:\/\/\S+/g, "");
  } catch (e) {
    logger.debug({ err: e }, "Failed to get snapshot");
    return `[Snapshot unavailable: ${e}]`;
  }
}

async function sendScreenshotEvent(
  session: BrowserSession,
  emitter?: SSEEmitter,
): Promise<void> {
  if (!emitter) return;
  try {
    const screenshotUri = await session.takeScreenshot();
    if (!screenshotUri) return;

    const page = session.currentPage;
    if (!page || page.isClosed()) return;

    emitter.emitScreenshot(
      screenshotUri,
      page.url(),
      await page.title(),
      session.currentTabId || undefined,
      session.webviewId || undefined,
    );
  } catch (e) {
    logger.debug({ err: e }, "Screenshot event send failed");
  }
}

async function buildActionResult(
  session: BrowserSession,
  resultMessage: string,
  options?: {
    waitStability?: boolean;
    forceRefresh?: boolean;
    emitter?: SSEEmitter;
  },
): Promise<string> {
  if (options?.waitStability) {
    await waitForStability(session);
  }

  const parts = [resultMessage];

  const tabInfo = await getTabInfoSummary(session);
  if (tabInfo) parts.push(tabInfo);

  const pageCtx = await getPageContext(session);
  if (pageCtx) parts.push(pageCtx);

  const snap = await getSnapshot(session, options?.forceRefresh);
  if (snap) parts.push(snap);

  await sendScreenshotEvent(session, options?.emitter);

  return parts.join("\n\n");
}

async function formatTabInfo(session: BrowserSession): Promise<string> {
  const tabInfo = await session.getTabInfo();
  if (tabInfo.length === 0) return "No tabs open.";

  const lines = [`**Open Tabs (${tabInfo.length} total):**`];
  for (const tab of tabInfo) {
    const marker = tab.is_current ? "\u2192 " : "  ";
    const title = String(tab.title || "Untitled").slice(0, 50);
    lines.push(`${marker}[${tab.tab_id}] ${title}`);
    lines.push(`       URL: ${tab.url}`);
  }
  return lines.join("\n");
}

// ===== Tool definitions =====

// Shared details type for tool results
type ToolDetails = undefined;

function textResult(text: string): AgentToolResult<ToolDetails> {
  return { content: [{ type: "text", text }], details: undefined };
}

// ----- browser_visit_page -----

const visitPageSchema = Type.Object({
  url: Type.String({ description: "The URL to navigate to" }),
});

function createVisitPageTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof visitPageSchema> {
  return {
    name: "browser_visit_page",
    label: "Browser",
    description:
      "Navigate to a URL and return the page snapshot. The returned snapshot lists interactive elements with ref IDs (e.g., [ref=e1]). Use these ref IDs with browser_click, browser_type, and browser_select to interact with elements.",
    parameters: visitPageSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      await session.visit(params.url);
      const result = await buildActionResult(session, `Navigated to ${params.url}`, { emitter });
      return textResult(result);
    },
  };
}

// ----- browser_click -----

const clickSchema = Type.Object({
  ref: Type.String({ description: 'The ref ID of the element to click, from a page snapshot (e.g., "e1", "e2")' }),
});

function createClickTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof clickSchema> {
  return {
    name: "browser_click",
    label: "Browser",
    description: "Performs a click on an element on the page. May open a new tab if the element is a link.",
    parameters: clickSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({ type: "click", ref: params.ref });

      if (actionResult.success) {
        const details = actionResult.details as Record<string, unknown>;
        const newTabCreated = details.new_tab_created as boolean;
        const newTabId = details.new_tab_index;
        const clickInfo = newTabCreated && newTabId
          ? `Clicked, opened new tab (now on tab ${newTabId})`
          : "Clicked successfully";
        const result = await buildActionResult(session, clickInfo, {
          waitStability: true,
          forceRefresh: newTabCreated,
          emitter,
        });
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Click failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_type -----

const typeSchema = Type.Object({
  ref: Type.String({ description: 'The ref ID of the input element, from a snapshot (e.g., "e1")' }),
  text: Type.String({ description: "The text to type into the element" }),
});

function createTypeTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof typeSchema> {
  return {
    name: "browser_type",
    label: "Browser",
    description: "Types text into an input element on the page.",
    parameters: typeSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({ type: "type", text: params.text, ref: params.ref });

      if (actionResult.success) {
        const result = await buildActionResult(session, "Typed text successfully", { emitter });
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Type failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_enter -----

const enterSchema = Type.Object({});

function createEnterTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof enterSchema> {
  return {
    name: "browser_enter",
    label: "Browser",
    description: "Simulates pressing the Enter key on the currently focused element. Useful for submitting forms or search queries after using browser_type.",
    parameters: enterSchema,
    execute: async (_id, _params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({ type: "enter" });

      if (actionResult.success) {
        const result = await buildActionResult(session, "Pressed Enter successfully", { emitter });
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Enter failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_back -----

const backSchema = Type.Object({});

function createBackTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof backSchema> {
  return {
    name: "browser_back",
    label: "Browser",
    description: "Navigate back in browser history.",
    parameters: backSchema,
    execute: async (_id, _params) => {
      const session = await getSession(sessionId);
      await session.execAction({ type: "back" });
      const result = await buildActionResult(session, "Navigated back", { emitter });
      return textResult(result);
    },
  };
}

// ----- browser_forward -----

const forwardSchema = Type.Object({});

function createForwardTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof forwardSchema> {
  return {
    name: "browser_forward",
    label: "Browser",
    description: "Navigate forward in browser history.",
    parameters: forwardSchema,
    execute: async (_id, _params) => {
      const session = await getSession(sessionId);
      await session.execAction({ type: "forward" });
      const result = await buildActionResult(session, "Navigated forward", { emitter });
      return textResult(result);
    },
  };
}

// ----- browser_scroll -----

const scrollSchema = Type.Object({
  direction: Type.Union([Type.Literal("up"), Type.Literal("down")], {
    description: 'Scroll direction ("up" or "down")',
    default: "down",
  }),
  amount: Type.Number({ description: "Scroll amount in pixels", default: 300 }),
});

function createScrollTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof scrollSchema> {
  return {
    name: "browser_scroll",
    label: "Browser",
    description: "Scroll the page up or down by a specified number of pixels.",
    parameters: scrollSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const direction = params.direction || "down";
      const amount = params.amount || 300;
      await session.execAction({ type: "scroll", direction, amount });
      const result = await buildActionResult(session, `Scrolled ${direction} by ${amount}px`, { emitter });
      return textResult(result);
    },
  };
}

// ----- browser_select -----

const selectSchema = Type.Object({
  ref: Type.String({ description: "The ref ID of the combobox/select element from the page snapshot" }),
  value: Type.String({ description: "The visible text of the option to select" }),
});

function createSelectTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof selectSchema> {
  return {
    name: "browser_select",
    label: "Browser",
    description:
      'Select an option from a dropdown, combobox, or <select> element. Use this (not browser_click) when the snapshot shows a "combobox" or "select" element.',
    parameters: selectSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({ type: "select", ref: params.ref, value: params.value });

      if (actionResult.success) {
        const result = await buildActionResult(session, `Selected '${params.value}' successfully`, { emitter });
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Select failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_press_key -----

const pressKeySchema = Type.Object({
  keys: Type.Array(Type.String(), {
    description:
      'List of keys to press. For combinations, all keys are pressed together. Examples: ["Enter"], ["Control", "a"], ["Shift", "Tab"]',
  }),
});

function createPressKeyTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof pressKeySchema> {
  return {
    name: "browser_press_key",
    label: "Browser",
    description:
      "Press key or key combinations in the browser. Supports single keys (Enter, Escape, Tab) and combinations (Control+a, Control+c).",
    parameters: pressKeySchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({ type: "press_key", keys: params.keys });

      if (actionResult.success) {
        const keyCombo = params.keys.join("+");
        const result = await buildActionResult(session, `Pressed keys: ${keyCombo}`, { emitter });
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Press key failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_mouse_control -----

const mouseControlSchema = Type.Object({
  x: Type.Number({ description: "X-coordinate for the mouse action (pixels from left)" }),
  y: Type.Number({ description: "Y-coordinate for the mouse action (pixels from top)" }),
  control: Type.Union(
    [Type.Literal("click"), Type.Literal("dblclick"), Type.Literal("right_click")],
    { description: 'Type of click action: "click", "dblclick", or "right_click"', default: "click" },
  ),
});

function createMouseControlTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof mouseControlSchema> {
  return {
    name: "browser_mouse_control",
    label: "Browser",
    description:
      "Control the mouse to interact with browser using x, y coordinates. Use this when you cannot locate an element by ref.",
    parameters: mouseControlSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const actionResult = await session.execAction({
        type: "mouse_control",
        control: params.control || "click",
        x: params.x,
        y: params.y,
      });

      if (actionResult.success) {
        const result = await buildActionResult(
          session,
          `Mouse ${params.control || "click"} at coordinates (${params.x}, ${params.y})`,
          { emitter },
        );
        return textResult(result);
      } else {
        const result = await buildActionResult(session, `Mouse control failed: ${actionResult.message}`, { emitter });
        return textResult(result);
      }
    },
  };
}

// ----- browser_get_page_snapshot -----

const getPageSnapshotSchema = Type.Object({
  include_links: Type.Boolean({
    description: "If true, shows href URLs inline next to elements",
    default: false,
  }),
});

function createGetPageSnapshotTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof getPageSnapshotSchema> {
  return {
    name: "browser_get_page_snapshot",
    label: "Browser",
    description:
      'Gets a textual snapshot of the page\'s interactive elements. Each element has a unique ref ID used by other tools. Example: \'- link "Sign In" [ref=e1]\'. Set include_links=true to see href URLs.',
    parameters: getPageSnapshotSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const page = session.currentPage;
      if (!page || page.isClosed()) {
        return textResult("Error: No active page available");
      }

      const url = page.url();
      const title = await page.title();
      const header = `**Current Page:**\n- URL: ${url}\n- Title: ${title}\n\n`;

      let snapshot = await session.getSnapshot();

      if (!params.include_links) {
        snapshot = snapshot.replace(/ -> https?:\/\/\S+/g, "");
        return textResult(SNAPSHOT_URL_TIP + header + snapshot);
      }

      return textResult(header + snapshot);
    },
  };
}

// ----- browser_get_tab_info -----

const getTabInfoSchema = Type.Object({});

function createGetTabInfoTool(sessionId: string): AgentTool<typeof getTabInfoSchema> {
  return {
    name: "browser_get_tab_info",
    label: "Browser",
    description:
      "Get information about all open browser tabs. Shows tab IDs, titles, and URLs. The current tab is marked with an arrow.",
    parameters: getTabInfoSchema,
    execute: async (_id, _params) => {
      const session = await getSession(sessionId);
      const result = await formatTabInfo(session);
      return textResult(result);
    },
  };
}

// ----- browser_switch_tab -----

const switchTabSchema = Type.Object({
  tab_id: Type.String({ description: 'The tab ID to switch to (e.g., "tab-001", "tab-002")' }),
});

function createSwitchTabTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof switchTabSchema> {
  return {
    name: "browser_switch_tab",
    label: "Browser",
    description:
      "Switch to a different browser tab by its ID. Use browser_get_tab_info first to see available tabs.",
    parameters: switchTabSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const success = await session.switchToTab(params.tab_id);
      if (!success) {
        return textResult(`Error: Failed to switch to tab '${params.tab_id}'. Use browser_get_tab_info to see available tabs.`);
      }

      const pageCtx = await getPageContext(session);
      const tabInfoText = await formatTabInfo(session);
      const snap = await getSnapshot(session, true);

      const parts = [`Switched to tab '${params.tab_id}'`];
      if (pageCtx) parts.push(pageCtx);
      parts.push(tabInfoText);
      if (snap) parts.push(snap);

      await sendScreenshotEvent(session, emitter);
      return textResult(parts.join("\n\n"));
    },
  };
}

// ----- browser_new_tab -----

const newTabSchema = Type.Object({
  url: Type.Optional(Type.String({ description: "Optional URL to navigate to in the new tab" })),
});

function createNewTabTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof newTabSchema> {
  return {
    name: "browser_new_tab",
    label: "Browser",
    description:
      "Open a new browser tab, optionally navigating to a URL. Creates a new tab and switches to it.",
    parameters: newTabSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);

      // Use Tab Group to organize tabs by task (session_id)
      const [tabId] = await session.createTabInGroup(sessionId, params.url);
      await session.switchToTab(tabId);

      const pageCtx = await getPageContext(session);
      const tabInfoText = await formatTabInfo(session);
      const snap = await getSnapshot(session, true);

      const resultMsg = params.url
        ? `Opened new tab '${tabId}' and navigated to ${params.url}`
        : `Opened new tab '${tabId}'`;

      const parts = [resultMsg];
      if (pageCtx) parts.push(pageCtx);
      parts.push(tabInfoText);
      if (snap) parts.push(snap);

      await sendScreenshotEvent(session, emitter);
      return textResult(parts.join("\n\n"));
    },
  };
}

// ----- browser_close_tab -----

const closeTabSchema = Type.Object({
  tab_id: Type.String({ description: 'The tab ID to close (e.g., "tab-001", "tab-002")' }),
});

function createCloseTabTool(sessionId: string, emitter?: SSEEmitter): AgentTool<typeof closeTabSchema> {
  return {
    name: "browser_close_tab",
    label: "Browser",
    description:
      "Close a browser tab by its ID. Use browser_get_tab_info first to see available tabs.",
    parameters: closeTabSchema,
    execute: async (_id, params) => {
      const session = await getSession(sessionId);
      const success = await session.closeTab(params.tab_id);
      if (!success) {
        return textResult(`Error: Failed to close tab '${params.tab_id}'. Use browser_get_tab_info to see available tabs.`);
      }

      const pageCtx = await getPageContext(session);
      const tabInfoText = await formatTabInfo(session);
      const snap = await getSnapshot(session, true);

      const parts = [`Closed tab '${params.tab_id}'`];
      if (pageCtx) parts.push(pageCtx);
      parts.push(tabInfoText);
      if (snap) parts.push(snap ?? "No active tab remaining.");

      await sendScreenshotEvent(session, emitter);
      return textResult(parts.join("\n\n"));
    },
  };
}

// ===== Tool set builders =====

/** All available browser tool names. */
export const ALL_BROWSER_TOOLS = [
  "browser_visit_page",
  "browser_back",
  "browser_forward",
  "browser_scroll",
  "browser_click",
  "browser_type",
  "browser_enter",
  "browser_select",
  "browser_press_key",
  "browser_mouse_control",
  "browser_get_page_snapshot",
  "browser_get_tab_info",
  "browser_switch_tab",
  "browser_new_tab",
  "browser_close_tab",
] as const;

/** Default enabled tools (matches Eigent's browser_agent defaults). */
export const DEFAULT_BROWSER_TOOLS = [
  "browser_visit_page",
  "browser_click",
  "browser_type",
  "browser_back",
  "browser_forward",
  "browser_select",
  "browser_switch_tab",
  "browser_enter",
  "browser_get_page_snapshot",
  "browser_scroll",
] as const;

/**
 * Create all browser tools for a given session.
 *
 * @param sessionId - Browser session ID (used for pool management)
 * @param emitter - Optional SSE emitter for screenshot events
 * @param enabledTools - Subset of tools to return. If undefined, uses DEFAULT_BROWSER_TOOLS.
 */
export function createBrowserTools(
  sessionId: string,
  emitter?: SSEEmitter,
  enabledTools?: readonly string[],
): AgentTool<any>[] {
  const allTools: Record<string, AgentTool<any>> = {
    browser_visit_page: createVisitPageTool(sessionId, emitter),
    browser_click: createClickTool(sessionId, emitter),
    browser_type: createTypeTool(sessionId, emitter),
    browser_enter: createEnterTool(sessionId, emitter),
    browser_back: createBackTool(sessionId, emitter),
    browser_forward: createForwardTool(sessionId, emitter),
    browser_scroll: createScrollTool(sessionId, emitter),
    browser_select: createSelectTool(sessionId, emitter),
    browser_press_key: createPressKeyTool(sessionId, emitter),
    browser_mouse_control: createMouseControlTool(sessionId, emitter),
    browser_get_page_snapshot: createGetPageSnapshotTool(sessionId, emitter),
    browser_get_tab_info: createGetTabInfoTool(sessionId),
    browser_switch_tab: createSwitchTabTool(sessionId, emitter),
    browser_new_tab: createNewTabTool(sessionId, emitter),
    browser_close_tab: createCloseTabTool(sessionId, emitter),
  };

  const enabled = enabledTools ?? DEFAULT_BROWSER_TOOLS;
  const result: AgentTool<any>[] = [];

  for (const name of enabled) {
    const tool = allTools[name];
    if (tool) {
      result.push(tool);
    } else {
      logger.warn({ toolName: name }, "Unknown browser tool name");
    }
  }

  logger.info({ count: result.length }, "Created browser tools");
  return result;
}
