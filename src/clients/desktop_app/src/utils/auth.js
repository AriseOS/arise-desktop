/**
 * Authentication and Session Management
 * Uses Electron Store via IPC for secure local storage
 */

/**
 * Authentication utility
 */
export const auth = {
  /**
   * Save user session after successful login/registration
   *
   * @param {string} apiKey - User's API key (cr_xxxxx format for CRS)
   * @param {string} username - Username
   * @param {string} email - User email
   * @param {object} userData - Additional user data
   * @param {string} token - JWT token (optional, from CRS login)
   */
  async saveSession(apiKey, username, email, userData = {}, token = null) {
    try {
      await window.electronAPI.storeSet('user_api_key', apiKey);
      await window.electronAPI.storeSet('username', username);
      await window.electronAPI.storeSet('email', email);
      await window.electronAPI.storeSet('user_data', userData);
      await window.electronAPI.storeSet('login_timestamp', new Date().toISOString());

      if (token) {
        await window.electronAPI.storeSet('jwt_token', token);
      }

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
      const apiKey = await window.electronAPI.storeGet('user_api_key');
      const username = await window.electronAPI.storeGet('username');
      const email = await window.electronAPI.storeGet('email');
      const userData = await window.electronAPI.storeGet('user_data');
      const loginTimestamp = await window.electronAPI.storeGet('login_timestamp');
      const token = await window.electronAPI.storeGet('jwt_token');

      if (!apiKey) {
        return null;
      }

      return {
        apiKey,
        username,
        email,
        userData: userData || {},
        loginTimestamp,
        token
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
      const apiKey = await window.electronAPI.storeGet('user_api_key');
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
      await window.electronAPI.storeDelete('user_api_key');
      await window.electronAPI.storeDelete('username');
      await window.electronAPI.storeDelete('email');
      await window.electronAPI.storeDelete('user_data');
      await window.electronAPI.storeDelete('login_timestamp');
      await window.electronAPI.storeDelete('jwt_token');

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
      const apiKey = await window.electronAPI.storeGet('user_api_key');
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
      if (updates.username) {
        await window.electronAPI.storeSet('username', updates.username);
      }
      if (updates.email) {
        await window.electronAPI.storeSet('email', updates.email);
      }
      if (updates.userData) {
        await window.electronAPI.storeSet('user_data', updates.userData);
      }

      console.log('[Auth] Session updated');
    } catch (error) {
      console.error('[Auth] Failed to update session:', error);
      throw new Error('Failed to update session');
    }
  }
};
