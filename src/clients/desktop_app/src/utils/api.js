/**
 * API Client with Auto-injected API Key
 * Handles communication with Claude Relay Service (CRS) and App Backend
 *
 * Migration Notes:
 * - Migrated from old API Proxy to Claude Relay Service (CRS)
 * - CRS uses /api/users/* endpoints for user management
 * - API key prefix changed from ami_ to cr_ (configurable in CRS)
 */

import { auth } from './auth';
import { BACKEND_CONFIG } from '../config/backend';

// API endpoints
// CRS (Claude Relay Service) - User Management and LLM Proxy
const CRS_BASE = 'https://api.ariseos.com'; // CRS production URL
const APP_BACKEND_BASE = BACKEND_CONFIG.httpBase;

/**
 * API client utility
 */
export const api = {
  // ============================================================================
  // System APIs
  // ============================================================================

  /**
   * Check backend health
   * @returns {Promise<boolean>} True if backend is ready
   */
  async healthCheck() {
    try {
      const response = await fetch(`${APP_BACKEND_BASE}/health`, {
        method: 'GET',
        // Short timeout to avoid long hangs
        signal: AbortSignal.timeout(2000)
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  },

  /**
   * Wait for backend to be ready
   * @param {number} timeoutMs - Max wait time in ms (default 20000)
   * @returns {Promise<boolean>} True if ready, False if timed out
   */
  async waitForBackend(timeoutMs = 20000) {
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      if (await this.healthCheck()) {
        return true;
      }
      // Wait 1s before retry
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    return false;
  },

  /**
   * Get app version and update status
   * @returns {Promise<object>} Version info with update_required flag
   */
  async getVersionInfo() {
    try {
      const response = await fetch(`${APP_BACKEND_BASE}/api/v1/app/version`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[API] Failed to get version info:', error);
      return {
        version: 'unknown',
        compatible: true,
        update_required: false,
        error: error.message
      };
    }
  },

  /**
   * Upload diagnostic package to cloud
   * @param {string} userDescription - Optional description of the issue
   * @returns {Promise<object>} Result with diagnostic_id
   */
  async uploadDiagnostic(userDescription = null) {
    try {
      // Get user_id from session - require login
      const session = await auth.getSession();
      if (!session?.username) {
        throw new Error('Please login to upload diagnostic');
      }

      const body = {
        user_id: session.username,
        ...(userDescription && { user_description: userDescription })
      };
      const response = await fetch(`${APP_BACKEND_BASE}/api/v1/app/diagnostic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(60000) // 60s timeout for diagnostic upload
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }
      return await response.json();
    } catch (error) {
      console.error('[API] Failed to upload diagnostic:', error);
      throw error;
    }
  },

  // ============================================================================
  // Auth APIs (API Proxy)
  // ============================================================================

  /**
   * Register new user (CRS)
   *
   * @param {string} username - Username
   * @param {string} email - Email address
   * @param {string} password - Password
   * @returns {Promise<object>} Registration result with API key
   */
  async register(username, email, password) {
    try {
      console.log('[API] Registering user with CRS:', username);

      const response = await fetch(`${CRS_BASE}/api/users/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        // CRS returns error.message or error.detail
        throw new Error(error.message || error.detail || 'Registration failed');
      }

      const result = await response.json();
      console.log('[API] Registration successful (CRS Extension)');

      // Adapt CRS Extension response format
      // CRS Extension returns: { success, data: { user, apiKey, apiKeyId }, message }
      const regUser = result.data.user;
      return {
        success: result.success,
        user: {
          user_id: regUser.id,
          username: regUser.username,
          email: regUser.email,
          // CRS Extension uses is_active/isActive boolean, not status string
          is_active: regUser.isActive ?? regUser.is_active ?? true,
          is_admin: regUser.role === 'admin',
          trial_end: regUser.trialEndDate || regUser.trial_end_date,
          quota: regUser.quota
        },
        api_key: result.data.apiKey,
        api_key_id: result.data.apiKeyId
      };
    } catch (error) {
      console.error('[API] Registration error:', error);
      throw error;
    }
  },

  /**
   * Login user (CRS)
   *
   * IMPORTANT: CRS only supports email-based login (not username)
   *
   * @param {string} emailOrUsername - Email address (CRS requires email)
   * @param {string} password - Password
   * @returns {Promise<object>} Login result with API key
   */
  async login(emailOrUsername, password) {
    try {
      console.log('[API] Logging in user with CRS:', emailOrUsername);

      // CRS only supports email login
      // Detect if input is email or username
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      const isEmail = emailRegex.test(emailOrUsername);

      if (!isEmail) {
        // TODO: Option 1 - Throw error and require email
        throw new Error('CRS only supports email login. Please use your email address.');

        // TODO: Option 2 - Call backend to convert username → email (requires new endpoint)
        // const email = await this.convertUsernameToEmail(emailOrUsername);
      }

      const email = emailOrUsername;

      const response = await fetch(`${CRS_BASE}/api/users/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || error.detail || 'Login failed');
      }

      const result = await response.json();
      console.log('[API] Login successful (CRS)');

      // CRS login returns JWT token but NOT the API key
      // We need to fetch user profile to get the API key
      const profileResponse = await fetch(`${CRS_BASE}/api/users/profile`, {
        headers: {
          'Authorization': `Bearer ${result.data.token}`
        }
      });

      if (!profileResponse.ok) {
        throw new Error('Failed to fetch user profile');
      }

      const profile = await profileResponse.json();

      // Adapt CRS Extension response format
      // CRS Extension login returns: { success, data: { token, user, expiresIn } }
      // CRS Extension profile returns: { success, data: { user, apiKeys, status } }
      // NOTE: CRS Extension returns DECRYPTED plaintext API keys
      const loginUser = result.data.user;
      return {
        success: result.success,
        token: result.data.token,
        user: {
          user_id: loginUser.id,
          username: loginUser.username,
          email: loginUser.email,
          // CRS Extension uses is_active/isActive boolean, not status string
          is_active: loginUser.isActive ?? loginUser.is_active ?? true,
          is_admin: loginUser.role === 'admin'
        },
        // CRS Extension returns plaintext API key (decrypted from encrypted storage)
        api_key: profile.data.apiKeys?.[0]?.key || null,
        api_keys: profile.data.apiKeys
      };
    } catch (error) {
      console.error('[API] Login error:', error);
      throw error;
    }
  },

  /**
   * Get user's quota status from CRS
   *
   * NOTE: CRS uses JWT token authentication for this endpoint, not API key
   *
   * @returns {Promise<object>} Quota status
   */
  async getQuotaStatus() {
    try {
      // CRS uses JWT token for quota endpoint
      const session = await auth.getSession();
      if (!session || !session.token) {
        throw new Error('Not logged in');
      }

      console.log('[API] Fetching quota status from CRS');

      const response = await fetch(`${CRS_BASE}/api/users/quota`, {
        headers: {
          'Authorization': `Bearer ${session.token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to get quota status');
      }

      const result = await response.json();
      console.log('[API] Quota status retrieved (CRS)');

      // CRS returns: { success, data: { current_usage, limit, remaining, percent_used, quota_exceeded, reset_date } }
      return result.data;
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

  /**
   * Call App Backend and return raw Response (for streaming SSE)
   *
   * @param {string} endpoint - API endpoint path
   * @param {object} options - Fetch options (method, body, headers, etc.)
   * @returns {Promise<Response>} Raw fetch Response
   */
  async callAppBackendRaw(endpoint, options = {}) {
    const apiKey = await auth.getApiKey();

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (apiKey) {
      headers['X-Ami-API-Key'] = apiKey;
    }

    return await fetch(`${APP_BACKEND_BASE}${endpoint}`, {
      ...options,
      headers
    });
  },

  // ============================================================================
  // Generic HTTP Methods for App Backend
  // ============================================================================

  /**
   * Generic GET request to App Backend
   *
   * @param {string} endpoint - API endpoint path
   * @returns {Promise<any>} Response data
   */
  async get(endpoint) {
    return await this.callAppBackend(endpoint, {
      method: 'GET'
    });
  },

  /**
   * Generic POST request to App Backend
   *
   * @param {string} endpoint - API endpoint path
   * @param {object} data - Request body data
   * @returns {Promise<any>} Response data
   */
  async post(endpoint, data = {}) {
    return await this.callAppBackend(endpoint, {
      method: 'POST',
      body: JSON.stringify(data)
    });
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
    return await this.callAppBackend('/api/v1/browser/start', {
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
    return await this.callAppBackend('/api/v1/browser/stop', {
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
    return await this.callAppBackend('/api/v1/recordings/start', {
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
    return await this.callAppBackend('/api/v1/recordings/stop', {
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
    return await this.callAppBackend(`/api/v1/recordings/${sessionId}/upload`, {
      method: 'POST',
      body: JSON.stringify({
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
    return await this.callAppBackend('/api/v1/metaflows/generate', {
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
    return await this.callAppBackend('/api/v1/metaflows/from-recording', {
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
    return await this.callAppBackend('/api/v1/workflows/generate', {
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
  async executeWorkflow(workflowId, userId) {
    return await this.callAppBackend(`/api/v1/workflows/${workflowId}/execute`, {
      method: 'POST',
      body: JSON.stringify({
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
    return await this.callAppBackend(`/api/v1/executions/${taskId}`);
  },

  /**
   * List all workflows
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Workflows list
   */
  async listWorkflows(userId) {
    return await this.callAppBackend(`/api/v1/workflows?user_id=${userId}`);
  },

  /**
   * Get workflow detail
   *
   * @param {string} workflowId - Workflow ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Workflow detail
   */
  async getWorkflowDetail(workflowId, userId) {
    return await this.callAppBackend(`/api/v1/workflows/${workflowId}?user_id=${userId}`);
  },

  /**
   * Get dashboard data
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Dashboard data
   */
  async getDashboard(userId) {
    return await this.callAppBackend(`/api/v1/dashboard?user_id=${userId}`);
  },

  /**
   * Analyze recording operations
   *
   * @param {string} sessionId - Recording session ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Analysis result
   */
  async analyzeRecording(sessionId, userId) {
    return await this.callAppBackend(`/api/v1/recordings/${sessionId}/analyze`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId
      })
    });
  },

  /**
   * List workflow execution history for a specific workflow
   *
   * @param {string} workflowId - Workflow ID
   * @param {string} userId - User ID
   * @param {number} limit - Max results (default 100)
   * @param {string} status - Filter by status (optional)
   * @returns {Promise<object>} Execution history list
   */
  async listWorkflowHistory(workflowId, userId, limit = 100, status = null) {
    let url = `/api/v1/workflows/${workflowId}/history?user_id=${userId}&limit=${limit}`;
    if (status) {
      url += `&status=${status}`;
    }
    return await this.callAppBackend(url);
  },

  /**
   * Get execution detail with logs for a specific workflow run
   *
   * @param {string} workflowId - Workflow ID
   * @param {string} runId - Execution run ID
   * @param {string} userId - User ID
   * @returns {Promise<object>} Execution detail with logs
   */
  async getWorkflowRunDetail(workflowId, runId, userId) {
    return await this.callAppBackend(`/api/v1/workflows/${workflowId}/history/${runId}?user_id=${userId}`);
  }
};
