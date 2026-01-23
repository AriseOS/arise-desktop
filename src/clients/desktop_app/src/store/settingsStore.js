/**
 * Settings Store
 *
 * Manages application settings including appearance/theme preferences.
 *
 * Ported from Eigent's authStore (appearance management portion).
 */

import { createStore } from 'zustand/vanilla';

// Storage key for persistence
const STORAGE_KEY = 'ami_settings';

// Load settings from localStorage
const loadSettings = () => {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.error('[settingsStore] Failed to load settings:', e);
  }
  return null;
};

// Save settings to localStorage
const saveSettings = (settings) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (e) {
    console.error('[settingsStore] Failed to save settings:', e);
  }
};

// Initial state
const createInitialState = () => {
  const saved = loadSettings();
  return {
    // Appearance: 'light', 'dark', 'transparent', or 'system'
    appearance: saved?.appearance || 'light',
    // Auto-confirm delay in seconds (0 = disabled)
    autoConfirmDelay: saved?.autoConfirmDelay ?? 30,
    // Show token usage
    showTokenUsage: saved?.showTokenUsage ?? true,
    // Enable sound notifications
    soundEnabled: saved?.soundEnabled ?? true,
    // Enable desktop notifications
    notificationsEnabled: saved?.notificationsEnabled ?? true,
  };
};

// Create the store
const settingsStore = createStore((set, get) => ({
  // State
  ...createInitialState(),

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
    const defaults = {
      appearance: 'light',
      autoConfirmDelay: 30,
      showTokenUsage: true,
      soundEnabled: true,
      notificationsEnabled: true,
    };
    set(defaults);
    saveSettings(defaults);
  },
}));

export default settingsStore;
