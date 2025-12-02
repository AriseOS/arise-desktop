/**
 * Authentication and Session Management
 * Uses Tauri Store API for secure local storage
 */

import { load } from '@tauri-apps/plugin-store';

// Store instance (lazy loaded)
let store = null;

/**
 * Get or create store instance
 */
async function getStore() {
  if (!store) {
    store = await load('.ami-settings.dat', { autoSave: true });
  }
  return store;
}

/**
 * Authentication utility
 */
export const auth = {
  /**
   * Save user session after successful login/registration
   *
   * @param {string} apiKey - User's Ami API key (ami_xxxxx format)
   * @param {string} username - Username
   * @param {string} email - User email
   * @param {object} userData - Additional user data
   */
  async saveSession(apiKey, username, email, userData = {}) {
    try {
      const store = await getStore();
      await store.set('user_api_key', apiKey);
      await store.set('username', username);
      await store.set('email', email);
      await store.set('user_data', userData);
      await store.set('login_timestamp', new Date().toISOString());
      await store.save();

      console.log('[Auth] Session saved successfully');
    } catch (error) {
      console.error('[Auth] Failed to save session:', error);
      throw new Error('Failed to save session');
    }
  },

  /**
   * Get current user session
   *
   * @returns {Promise<object>} Session data or null if not logged in
   */
  async getSession() {
    try {
      const store = await getStore();
      const apiKey = await store.get('user_api_key');
      const username = await store.get('username');
      const email = await store.get('email');
      const userData = await store.get('user_data');
      const loginTimestamp = await store.get('login_timestamp');

      if (!apiKey) {
        return null;
      }

      return {
        apiKey,
        username,
        email,
        userData: userData || {},
        loginTimestamp
      };
    } catch (error) {
      console.error('[Auth] Failed to get session:', error);
      return null;
    }
  },

  /**
   * Get user's API key
   *
   * @returns {Promise<string|null>} API key or null if not logged in
   */
  async getApiKey() {
    try {
      const store = await getStore();
      const apiKey = await store.get('user_api_key');
      return apiKey || null;
    } catch (error) {
      console.error('[Auth] Failed to get API key:', error);
      return null;
    }
  },

  /**
   * Clear user session (logout)
   */
  async clearSession() {
    try {
      const store = await getStore();
      await store.delete('user_api_key');
      await store.delete('username');
      await store.delete('email');
      await store.delete('user_data');
      await store.delete('login_timestamp');
      await store.save();

      console.log('[Auth] Session cleared');
    } catch (error) {
      console.error('[Auth] Failed to clear session:', error);
      throw new Error('Failed to clear session');
    }
  },

  /**
   * Check if user is logged in
   *
   * @returns {Promise<boolean>} True if logged in, false otherwise
   */
  async isLoggedIn() {
    try {
      const store = await getStore();
      const apiKey = await store.get('user_api_key');
      return !!apiKey;
    } catch (error) {
      console.error('[Auth] Failed to check login status:', error);
      return false;
    }
  },

  /**
   * Update user data in session
   *
   * @param {object} updates - Fields to update
   */
  async updateSession(updates) {
    try {
      const store = await getStore();
      if (updates.username) {
        await store.set('username', updates.username);
      }
      if (updates.email) {
        await store.set('email', updates.email);
      }
      if (updates.userData) {
        await store.set('user_data', updates.userData);
      }
      await store.save();

      console.log('[Auth] Session updated');
    } catch (error) {
      console.error('[Auth] Failed to update session:', error);
      throw new Error('Failed to update session');
    }
  }
};
