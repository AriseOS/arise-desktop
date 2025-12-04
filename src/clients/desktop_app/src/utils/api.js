/**
 * API Client with Auto-injected API Key
 * Handles communication with API Proxy and App Backend
 */

import { auth } from './auth';

// API endpoints
const API_PROXY_BASE = 'https://api.ariseos.com';
const APP_BACKEND_BASE = 'http://127.0.0.1:8765';

/**
 * API client utility
 */
export const api = {
  // ============================================================================
  // Auth APIs (API Proxy)
  // ============================================================================

  /**
   * Register new user
   *
   * @param {string} username - Username
   * @param {string} email - Email address
   * @param {string} password - Password
   * @returns {Promise<object>} Registration result with API key
   */
  async register(username, email, password) {
    try {
      console.log('[API] Registering user:', username);

      const response = await fetch(`${API_PROXY_BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Registration failed');
      }

      const data = await response.json();
      console.log('[API] Registration successful');

      return data; // { success: true, user: {...}, api_key: "ami_xxxxx" }
    } catch (error) {
      console.error('[API] Registration error:', error);
      throw error;
    }
  },

  /**
   * Login user
   *
   * @param {string} username - Username
   * @param {string} password - Password
   * @returns {Promise<object>} Login result with API key
   */
  async login(username, password) {
    try {
      console.log('[API] Logging in user:', username);

      const response = await fetch(`${API_PROXY_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
      }

      const data = await response.json();
      console.log('[API] Login successful');

      return data; // { success: true, user: {...}, api_key: "ami_xxxxx" }
    } catch (error) {
      console.error('[API] Login error:', error);
      throw error;
    }
  },

  /**
   * Get user's quota status from API Proxy
   *
   * @returns {Promise<object>} Quota status
   */
  async getQuotaStatus() {
    try {
      const apiKey = await auth.getApiKey();
      if (!apiKey) {
        throw new Error('Not logged in');
      }

      console.log('[API] Fetching quota status');

      const response = await fetch(`${API_PROXY_BASE}/api/stats/quota`, {
        headers: { 'x-api-key': apiKey }
      });

      if (!response.ok) {
        throw new Error('Failed to get quota status');
      }

      const data = await response.json();
      console.log('[API] Quota status retrieved');

      return data;
    } catch (error) {
      console.error('[API] Quota status error:', error);
      throw error;
    }
  },

  // ============================================================================
  // App Backend APIs (with auto-injected API key)
  // ============================================================================

  /**
   * Call App Backend with auto-injected X-Ami-API-Key header
   *
   * @param {string} endpoint - API endpoint path (e.g., "/api/browser/start")
   * @param {object} options - Fetch options (method, body, headers, etc.)
   * @returns {Promise<any>} Response data
   */
  async callAppBackend(endpoint, options = {}) {
    try {
      const apiKey = await auth.getApiKey();

      const headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };

      // Auto-inject X-Ami-API-Key if logged in
      if (apiKey) {
        headers['X-Ami-API-Key'] = apiKey;
        console.log(`[API] Calling ${endpoint} with API key`);
      } else {
        console.log(`[API] Calling ${endpoint} without API key`);
      }

      const response = await fetch(`${APP_BACKEND_BASE}${endpoint}`, {
        ...options,
        headers
      });

      if (!response.ok) {
        let errorMessage;
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.error || `Request failed: ${response.status}`;
        } catch {
          errorMessage = await response.text() || `Request failed: ${response.status}`;
        }
        throw new Error(errorMessage);
      }

      return await response.json();
    } catch (error) {
      console.error('[API] App Backend error:', error);
      throw error;
    }
  },

  // ============================================================================
  // Convenience Methods for App Backend
  // ============================================================================

  /**
   * Start browser
   *
   * @param {boolean} headless - Whether to run in headless mode
   * @returns {Promise<object>} Browser status
   */
  async startBrowser(headless = false) {
    return await this.callAppBackend('/api/browser/start', {
      method: 'POST',
      body: JSON.stringify({ headless })
    });
  },

  /**
   * Stop browser
   *
   * @returns {Promise<object>} Browser status
   */
  async stopBrowser() {
    return await this.callAppBackend('/api/browser/stop', {
      method: 'POST'
    });
  },

  /**
   * Start recording
   *
   * @param {string} url - Starting URL
   * @param {string} userId - User ID
   * @param {string} title - Recording title
   * @param {string} description - Recording description
   * @returns {Promise<object>} Recording session info
   */
  async startRecording(url, userId, title = '', description = '') {
    return await this.callAppBackend('/api/recording/start', {
      method: 'POST',
      body: JSON.stringify({ url, user_id: userId, title, description })
    });
  },

  /**
   * Stop recording
   *
   * @param {string} sessionId - Recording session ID
   * @returns {Promise<object>} Recording result
   */
  async stopRecording(sessionId) {
    return await this.callAppBackend('/api/recording/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    });
  },

  /**
   * Upload recording to Cloud Backend
   *
   * @param {string} sessionId - Recording session ID
   * @param {string} taskDescription - What the user did
   * @param {string} userQuery - What the user wants to do
   * @param {string} userId - User ID
   * @returns {Promise<object>} Upload result
   */
  async uploadRecording(sessionId, taskDescription, userQuery = null, userId) {
    return await this.callAppBackend('/api/recordings/upload', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        task_description: taskDescription,
        user_query: userQuery,
        user_id: userId
      })
    });
  },

  /**
   * Generate MetaFlow from Intent Memory Graph
   *
   * @param {string} taskDescription - Task description
   * @param {string} userQuery - User query (optional)
   * @param {string} userId - User ID
   * @returns {Promise<object>} MetaFlow result
   */
  async generateMetaflow(taskDescription, userQuery = null, userId) {
    return await this.callAppBackend('/api/metaflows/generate', {
      method: 'POST',
      body: JSON.stringify({
        task_description: taskDescription,
        user_query: userQuery,
        user_id: userId
      })
    });
  },

  /**
   * Generate MetaFlow from a specific recording
   *
   * @param {string} sessionId - Recording session ID
   * @param {string} taskDescription - Task description
   * @param {string} userQuery - User query (optional)
   * @param {string} userId - User ID
   * @returns {Promise<object>} MetaFlow result
   */
  async generateMetaflowFromRecording(sessionId, taskDescription, userQuery = null, userId) {
    return await this.callAppBackend('/api/metaflows/from-recording', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        task_description: taskDescription,
        user_query: userQuery,
        user_id: userId
      })
    });
  },

  /**
   * Generate Workflow from MetaFlow
   *
   * @param {string} metaflowId - MetaFlow ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Workflow result
   */
  async generateWorkflow(metaflowId, userId) {
    return await this.callAppBackend('/api/workflows/generate', {
      method: 'POST',
      body: JSON.stringify({
        metaflow_id: metaflowId,
        user_id: userId
      })
    });
  },

  /**
   * Execute workflow
   *
   * @param {string} workflowName - Workflow name
   * @param {string} userId - User ID
   * @returns {Promise<object>} Execution result with task_id
   */
  async executeWorkflow(workflowName, userId) {
    return await this.callAppBackend('/api/workflow/execute', {
      method: 'POST',
      body: JSON.stringify({
        workflow_name: workflowName,
        user_id: userId
      })
    });
  },

  /**
   * Get workflow execution status
   *
   * @param {string} taskId - Task ID
   * @returns {Promise<object>} Execution status
   */
  async getWorkflowStatus(taskId) {
    return await this.callAppBackend(`/api/workflow/status/${taskId}`);
  },

  /**
   * List all workflows
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Workflows list
   */
  async listWorkflows(userId) {
    return await this.callAppBackend(`/api/workflows?user_id=${userId}`);
  },

  /**
   * Get workflow detail
   *
   * @param {string} workflowId - Workflow ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Workflow detail
   */
  async getWorkflowDetail(workflowId, userId) {
    return await this.callAppBackend(`/api/workflows/${workflowId}?user_id=${userId}`);
  },

  /**
   * Get dashboard data
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Dashboard data
   */
  async getDashboard(userId) {
    return await this.callAppBackend(`/api/dashboard?user_id=${userId}`);
  },

  /**
   * Analyze recording operations
   *
   * @param {string} sessionId - Recording session ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Analysis result
   */
  async analyzeRecording(sessionId, userId) {
    return await this.callAppBackend('/api/recording/analyze', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        user_id: userId
      })
    });
  }
};
