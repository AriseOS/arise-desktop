/**
 * Browser Tab Store
 *
 * Zustand store for multi-tab browser UI state.
 * Manages the 8-view pool as Chrome-style tabs.
 */

import { create } from 'zustand';

const POOL_MARKER = 'about:blank?ami=pool';
const CLAIMED_MARKER = 'about:blank?ami=claimed';

const useBrowserTabStore = create((set, get) => ({
  // { [viewId]: { url, title, mode } }
  // mode: "login" | "recording" | "live" | "control" | "idle"
  views: {},

  // Currently visible tab
  activeTabId: '7',

  // Recording metadata per view
  // { [viewId]: { sessionId, source, startTime } }
  recordingMeta: {},

  /**
   * Fetch all view info from Electron and populate views.
   */
  fetchAllViews: async () => {
    const info = await window.electronAPI?.getAllWebviewInfo();
    if (!info) return;

    const current = get().views;
    const updated = {};
    for (const [id, data] of Object.entries(info)) {
      updated[id] = {
        url: data.url || '',
        title: data.title || '',
        mode: current[id]?.mode || 'idle',
      };
    }
    set({ views: updated });
  },

  /**
   * Handle view-state-changed event from Electron.
   */
  onViewStateChanged: (viewId, info) => {
    console.log(`[browserTabStore] view-state-changed: viewId=${viewId} url=${info.url} title=${info.title}`);
    set((state) => ({
      views: {
        ...state.views,
        [viewId]: {
          ...state.views[viewId],
          url: info.url ?? state.views[viewId]?.url ?? '',
          title: info.title ?? state.views[viewId]?.title ?? '',
          mode: state.views[viewId]?.mode || 'idle',
        },
      },
    }));
  },

  /**
   * Set a view's mode.
   */
  setViewMode: (viewId, mode) => {
    set((state) => ({
      views: {
        ...state.views,
        [viewId]: {
          ...state.views[viewId],
          url: state.views[viewId]?.url || '',
          title: state.views[viewId]?.title || '',
          mode,
        },
      },
    }));
  },

  /**
   * Switch to a different tab. Hides previous view, sets new active tab.
   * NOTE: actual showView is handled by EmbeddedBrowser's bounds measurement.
   */
  switchTab: (viewId) => {
    const prev = get().activeTabId;
    console.log(`[browserTabStore] switchTab: ${prev} → ${viewId}`);
    if (prev && prev !== viewId) {
      window.electronAPI?.hideWebview(prev);
    }
    set({ activeTabId: viewId });
  },

  /**
   * Set recording metadata for a view.
   */
  setRecordingMeta: (viewId, meta) => {
    set((state) => ({
      recordingMeta: {
        ...state.recordingMeta,
        [viewId]: meta,
      },
    }));
  },

  /**
   * Clear recording metadata for a view.
   */
  clearRecordingMeta: (viewId) => {
    set((state) => {
      const { [viewId]: _, ...rest } = state.recordingMeta;
      return { recordingMeta: rest };
    });
  },

  /**
   * Close a tab — navigate view back to pool marker URL, reset mode.
   * If closing the active tab, switch to view "7".
   */
  closeTab: (viewId) => {
    // Don't allow closing the login tab
    if (viewId === '7') return;

    // Navigate back to pool marker
    window.electronAPI?.navigateWebview(viewId, `${POOL_MARKER}&viewId=${viewId}`);
    window.electronAPI?.hideWebview(viewId);

    set((state) => {
      const newActiveTabId = state.activeTabId === viewId ? '7' : state.activeTabId;
      return {
        views: {
          ...state.views,
          [viewId]: {
            url: `${POOL_MARKER}&viewId=${viewId}`,
            title: '',
            mode: 'idle',
          },
        },
        activeTabId: newActiveTabId,
      };
    });
  },

  /**
   * Get active tabs — views with url NOT starting with pool marker,
   * PLUS viewId "7" always shown. Sorted: login-first, then by id.
   */
  getActiveTabs: () => {
    const { views } = get();
    const tabs = [];

    for (const [id, view] of Object.entries(views)) {
      const isPool = !view.url || view.url.startsWith(POOL_MARKER);
      const isClaimed = view.url && view.url.startsWith(CLAIMED_MARKER);
      // Always show view "7" (login slot) + any non-pool/non-claimed views
      if (id === '7' || (!isPool && !isClaimed)) {
        tabs.push({ id, ...view });
      }
    }

    // Sort: login-mode first, then by numeric id
    tabs.sort((a, b) => {
      if (a.mode === 'login' && b.mode !== 'login') return -1;
      if (b.mode === 'login' && a.mode !== 'login') return 1;
      return parseInt(a.id) - parseInt(b.id);
    });

    return tabs;
  },
}));

export default useBrowserTabStore;
