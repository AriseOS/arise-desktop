/**
 * Settings Store
 *
 * Manages application settings including appearance/theme preferences.
 * Persists settings via Electron Store (IPC).
 */

import { createStore } from 'zustand/vanilla';

// Storage key for persistence in electron-store
const STORAGE_KEY = 'ami_settings';

// Save settings to electron-store (async, fire-and-forget)
const saveSettings = (settings) => {
  // Extract only the serializable settings (exclude functions)
  const { appearance, autoConfirmDelay, showTokenUsage, soundEnabled, notificationsEnabled } = settings;
  const data = { appearance, autoConfirmDelay, showTokenUsage, soundEnabled, notificationsEnabled };
  window.electronAPI.storeSet(STORAGE_KEY, data).catch((e) => {
    console.error('[settingsStore] Failed to save settings:', e);
  });
};

// Default settings
const DEFAULTS = {
  appearance: 'light',
  autoConfirmDelay: 30,
  showTokenUsage: true,
  soundEnabled: true,
  notificationsEnabled: true,
};

// Create the store (starts with defaults, async loads persisted values)
const settingsStore = createStore((set, get) => ({
  // State (starts with defaults)
  ...DEFAULTS,

  // Flag to track if persisted settings have been loaded
  _loaded: false,

  /**
   * Load persisted settings from electron-store.
   * Called once on app startup.
   */
  loadPersistedSettings: async () => {
    try {
      const saved = await window.electronAPI.storeGet(STORAGE_KEY);
      if (saved && typeof saved === 'object') {
        set({
          appearance: saved.appearance || DEFAULTS.appearance,
          autoConfirmDelay: saved.autoConfirmDelay ?? DEFAULTS.autoConfirmDelay,
          showTokenUsage: saved.showTokenUsage ?? DEFAULTS.showTokenUsage,
          soundEnabled: saved.soundEnabled ?? DEFAULTS.soundEnabled,
          notificationsEnabled: saved.notificationsEnabled ?? DEFAULTS.notificationsEnabled,
          _loaded: true,
        });
      } else {
        set({ _loaded: true });
      }
    } catch (e) {
      console.error('[settingsStore] Failed to load settings:', e);
      set({ _loaded: true });
    }
  },

  // === Appearance ===

  /**
   * Set appearance theme
   * @param {'light' | 'dark' | 'transparent' | 'system'} appearance
   */
  setAppearance: (appearance) => {
    set({ appearance });
    saveSettings({ ...get(), appearance });
  },

  /**
   * Get current appearance
   */
  getAppearance: () => {
    return get().appearance;
  },

  /**
   * Toggle between light and dark mode
   */
  toggleDarkMode: () => {
    const current = get().appearance;
    const next = current === 'dark' ? 'light' : 'dark';
    set({ appearance: next });
    saveSettings({ ...get(), appearance: next });
  },

  // === Auto Confirm ===

  /**
   * Set auto-confirm delay
   * @param {number} seconds - Delay in seconds (0 to disable)
   */
  setAutoConfirmDelay: (seconds) => {
    set({ autoConfirmDelay: seconds });
    saveSettings({ ...get(), autoConfirmDelay: seconds });
  },

  /**
   * Get auto-confirm delay
   */
  getAutoConfirmDelay: () => {
    return get().autoConfirmDelay;
  },

  // === Token Usage ===

  /**
   * Set show token usage preference
   */
  setShowTokenUsage: (show) => {
    set({ showTokenUsage: show });
    saveSettings({ ...get(), showTokenUsage: show });
  },

  /**
   * Get show token usage preference
   */
  getShowTokenUsage: () => {
    return get().showTokenUsage;
  },

  // === Sound ===

  /**
   * Set sound enabled preference
   */
  setSoundEnabled: (enabled) => {
    set({ soundEnabled: enabled });
    saveSettings({ ...get(), soundEnabled: enabled });
  },

  /**
   * Get sound enabled preference
   */
  getSoundEnabled: () => {
    return get().soundEnabled;
  },

  // === Notifications ===

  /**
   * Set notifications enabled preference
   */
  setNotificationsEnabled: (enabled) => {
    set({ notificationsEnabled: enabled });
    saveSettings({ ...get(), notificationsEnabled: enabled });
  },

  /**
   * Get notifications enabled preference
   */
  getNotificationsEnabled: () => {
    return get().notificationsEnabled;
  },

  // === Reset ===

  /**
   * Reset all settings to defaults
   */
  resetSettings: () => {
    set({ ...DEFAULTS });
    saveSettings(DEFAULTS);
  },
}));

export default settingsStore;
