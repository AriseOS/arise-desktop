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
import { BACKEND_CONFIG, initBackendPort } from '../config/backend';

// API endpoints
// CRS (Claude Relay Service) - User Management and LLM Proxy
const CRS_BASE = 'https://api.ariseos.com'; // CRS production URL

// Get backend URL dynamically (port may change)
const getBackendBase = () => BACKEND_CONFIG.httpBase;

// Connection error event handling
// Used to notify App when backend becomes unreachable
let connectionErrorCallback = null;

/**
 * Register a callback to be called when backend connection fails
 * @param {function} callback - Called with error info when connection fails
 */
export const onConnectionError = (callback) => {
  connectionErrorCallback = callback;
};

/**
 * Check if an error is a connection error (network failure, refused, etc.)
 */
const isConnectionError = (error) => {
  if (!error) return false;
  const message = error.message?.toLowerCase() || '';
  return (
    message.includes('failed to fetch') ||
    message.includes('network') ||
    message.includes('econnrefused') ||
    message.includes('connection refused') ||
    message.includes('net::err_connection_refused') ||
    message.includes('load failed') ||
    error.name === 'TypeError' && message.includes('fetch')
  );
};

/**
 * API client utility
 */
export const api = {
  // ============================================================================
  // System APIs
  // ============================================================================

  /**
   * Initialize the API client (discover daemon port)
   * Note: Usually not needed to call directly - waitForBackend() calls this automatically
   * @param {boolean} forceRefresh - If true, re-read port from file even if cached
   * @returns {Promise<number>} The discovered port
   */
  async init(forceRefresh = false) {
    return await initBackendPort(forceRefresh);
  },

  /**
   * Get the backend base URL
   * @returns {string} Backend base URL
   */
  getBackendUrl() {
    return getBackendBase();
  },

  /**
   * Check backend health
   * @returns {Promise<boolean>} True if backend is ready
   */
  async healthCheck() {
    try {
      const response = await fetch(`${getBackendBase()}/api/v1/health`, {
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
   * Automatically discovers daemon port on each retry (daemon may still be starting)
   * @param {number} timeoutMs - Max wait time in ms (default 20000)
   * @returns {Promise<boolean>} True if ready, False if timed out
   */
  async waitForBackend(timeoutMs = 20000) {
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      // Fail fast if Electron's daemon launcher already reported a startup error
      if (window.electronAPI?.getDaemonStartError) {
        const startError = await window.electronAPI.getDaemonStartError();
        if (startError) {
          console.error('[API] Daemon failed to start:', startError);
          return false;
        }
      }

      // Re-read port file on each attempt (daemon may have just written it)
      await initBackendPort(true);

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
      const response = await fetch(`${getBackendBase()}/api/v1/app/version`, {
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
      const response = await fetch(`${getBackendBase()}/api/v1/app/diagnostic`, {
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
    // TODO: CRS quota endpoint not yet implemented, return null for now
    console.log('[API] Quota status: CRS endpoint not implemented, skipping');
    return null;

    // Uncomment when CRS implements /api/users/quota endpoint:
    // try {
    //   // CRS uses JWT token for quota endpoint
    //   const session = await auth.getSession();
    //   if (!session || !session.token) {
    //     throw new Error('Not logged in');
    //   }
    //
    //   console.log('[API] Fetching quota status from CRS');
    //
    //   const response = await fetch(`${CRS_BASE}/api/users/quota`, {
    //     headers: {
    //       'Authorization': `Bearer ${session.token}`
    //     }
    //   });
    //
    //   if (!response.ok) {
    //     throw new Error('Failed to get quota status');
    //   }
    //
    //   const result = await response.json();
    //   console.log('[API] Quota status retrieved (CRS)');
    //
    //   // CRS returns: { success, data: { current_usage, limit, remaining, percent_used, quota_exceeded, reset_date } }
    //   return result.data;
    // } catch (error) {
    //   console.error('[API] Quota status error:', error);
    //   throw error;
    // }
  },

  // ============================================================================
  // App Backend APIs (with auto-injected API key)
  // ============================================================================

  /**
   * Call App Backend with auto-injected auth headers
   * - X-Ami-API-Key: CRS API key (if logged in)
   * - X-User-Id: current username (if logged in)
   *
   * @param {string} endpoint - API endpoint path (e.g., "/api/browser/start")
   * @param {object} options - Fetch options (method, body, headers, etc.)
   * @returns {Promise<any>} Response data
   */
  async callAppBackend(endpoint, options = {}) {
    try {
      const session = await auth.getSession();
      const apiKey = session?.apiKey ?? await auth.getApiKey();
      const userId = session?.username;

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
      // Auto-inject X-User-Id for user-scoped operations (e.g., memory)
      if (userId) {
        headers['X-User-Id'] = userId;
      }

      const response = await fetch(`${getBackendBase()}${endpoint}`, {
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
      // On connection error: invalidate cached port (daemon may have restarted on a new port)
      if (isConnectionError(error)) {
        console.warn('[API] Connection error — invalidating cached daemon port');
        initBackendPort(true).catch(() => {});
        if (connectionErrorCallback) {
          connectionErrorCallback({ endpoint, error });
        }
      }
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
    try {
      const session = await auth.getSession();
      const apiKey = session?.apiKey ?? await auth.getApiKey();
      const userId = session?.username;

      const headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };

      if (apiKey) {
        headers['X-Ami-API-Key'] = apiKey;
      }
      if (userId) {
        headers['X-User-Id'] = userId;
      }

      return await fetch(`${getBackendBase()}${endpoint}`, {
        ...options,
        headers
      });
    } catch (error) {
      // On connection error: invalidate cached port (daemon may have restarted on a new port)
      if (isConnectionError(error)) {
        initBackendPort(true).catch(() => {});
        if (connectionErrorCallback) {
          connectionErrorCallback({ endpoint, error });
        }
      }
      throw error;
    }
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
  // Credentials APIs
  // ============================================================================

  /**
   * Get stored credentials (API keys are masked).
   * @returns {Promise<object>} Credentials by provider, e.g. { anthropic: { api_key: "sk-***1234" } }
   */
  async getCredentials() {
    return await this.callAppBackend('/api/v1/settings/credentials');
  },

  /**
   * Save credentials for a provider.
   * @param {string} provider - Provider name, e.g. "anthropic"
   * @param {object} config - Credential config, e.g. { api_key: "sk-ant-...", base_url: "..." }
   * @returns {Promise<object>} Result with success status
   */
  async setCredentials(provider, config) {
    return await this.callAppBackend('/api/v1/settings/credentials', {
      method: 'POST',
      body: JSON.stringify({ [provider]: config }),
    });
  },

  // ============================================================================
  // Convenience Methods for App Backend
  // ============================================================================

  // startBrowser / stopBrowser removed — in Electron mode, the browser
  // (Chromium) is always running. No separate start/stop needed.

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
   * Generate Workflow directly from Recording or task description (NEW v2 API)
   *
   * This bypasses MetaFlow and uses the new WorkflowBuilder architecture.
   *
   * @param {object} options - Generation options
   * @param {string} options.userId - User ID (required)
   * @param {string} options.taskDescription - Task description (required)
   * @param {string} options.recordingId - Recording ID (optional)
   * @param {string} options.userQuery - User query (optional)
   * @param {boolean} options.enableDialogue - Keep session for follow-up dialogue (default: true)
   * @param {boolean} options.enableSemanticValidation - Enable semantic validation (default: true)
   * @returns {Promise<object>} Workflow result with session_id for dialogue
   */
  async generateWorkflowDirect(options) {
    const {
      userId,
      taskDescription,
      recordingId = null,
      userQuery = null,
      enableDialogue = true,
      enableSemanticValidation = true
    } = options;

    return await this.callAppBackend('/api/v1/workflows/generate', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        task_description: taskDescription,
        recording_id: recordingId,
        user_query: userQuery,
        enable_dialogue: enableDialogue,
        enable_semantic_validation: enableSemanticValidation
      })
    });
  },

  /**
   * Generate Workflow with streaming progress (SSE)
   *
   * @param {object} options - Same as generateWorkflowDirect
   * @param {function} onProgress - Callback for progress updates
   * @returns {Promise<object>} Final workflow result
   */
  async generateWorkflowStream(options, onProgress) {
    const {
      userId,
      taskDescription,
      recordingId = null,
      userQuery = null,
      enableSemanticValidation = true
    } = options;

    const response = await this.callAppBackendRaw('/api/v1/workflows/generate-stream', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        task_description: taskDescription,
        recording_id: recordingId,
        user_query: userQuery,
        enable_semantic_validation: enableSemanticValidation
      })
    });

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.statusText}`);
    }

    // Read SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult = null;

    while (true) {
      const { done, value } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: !done });
      }

      // Process complete SSE events
      const lines = buffer.split('\n');

      // If done, we process all lines including the last one
      // If not done, we keep the last line in buffer as it might be incomplete
      buffer = done ? '' : (lines.pop() || '');

      for (const line of lines) {
        if (line.trim() === '') continue; // Skip empty lines

        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6);
          try {
            const event = JSON.parse(jsonStr);
            console.log('[SSE] Received event:', event);
            if (onProgress) {
              onProgress(event);
            }
            if (event.status === 'completed' || event.workflow_id) {
              console.log('[SSE] Setting finalResult:', event);
              finalResult = event;
            }
          } catch (e) {
            console.error('[SSE] Failed to parse event:', jsonStr, e);
          }
        }
      }

      if (done) break;
    }

    return finalResult;
  },

  /**
   * Chat with a Workflow session (SSE streaming)
   *
   * @param {string} sessionId - Workflow session ID
   * @param {string} message - User message
   * @param {function} onEvent - Callback for each SSE event: {type, message, workflow_yaml?}
   * @returns {Promise<object>} Final result with workflow_yaml if updated
   */
  async workflowChat(sessionId, message, onEvent = null) {
    // Ensure message is a string
    let messageStr
    if (typeof message === 'string') {
      messageStr = message
    } else if (message && typeof message === 'object') {
      // If it's an object with content property, use that
      messageStr = typeof message.content === 'string' ? message.content : String(message.content || '')
    } else {
      messageStr = String(message || '')
    }

    console.log('[workflowChat] sessionId:', sessionId, 'message:', messageStr.substring(0, 100))

    const response = await this.callAppBackendRaw(`/api/v1/workflow-sessions/${sessionId}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message: messageStr })
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Request failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult = { workflow_updated: false, workflow_yaml: null, message: '' };
    let streamError = null;  // Track errors thrown from event processing

    const processLine = (line) => {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));

          if (onEvent) {
            onEvent(data);
          }

          if (data.type === 'workflow_updated' || data.type === 'complete') {
            if (data.workflow_yaml) {
              finalResult.workflow_updated = true;
              finalResult.workflow_yaml = data.workflow_yaml;
            }
          }

          if (data.type === 'complete') {
            finalResult.message = data.message;
          }

          if (data.type === 'error') {
            streamError = new Error(data.message);
          }
        } catch (parseError) {
          // Only log JSON parse errors, don't throw
          console.warn('[API] Failed to parse SSE event:', line, parseError);
        }
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (value) {
          buffer += decoder.decode(value, { stream: !done });
        }

        // Process complete SSE events
        const lines = buffer.split('\n');

        // If done, we process all lines including the last one
        // If not done, we keep the last line in buffer as it might be incomplete
        buffer = done ? '' : (lines.pop() || '');

        for (const line of lines) {
          if (line.trim() === '') continue;  // Skip empty lines
          processLine(line);
        }

        if (done) break;
      }
    } finally {
      reader.releaseLock();
    }

    // Throw error after stream is fully processed
    if (streamError) {
      throw streamError;
    }

    return finalResult;
  },

  /**
   * Close a Workflow session
   *
   * @param {string} sessionId - Workflow session ID
   * @returns {Promise<object>} Close result
   */
  async closeWorkflowSession(sessionId) {
    return await this.callAppBackend(`/api/v1/workflow-sessions/${sessionId}`, {
      method: 'DELETE'
    });
  },

  /**
   * Create a dialogue session for an existing Workflow
   *
   * This is used when opening a Workflow that was generated previously
   * and the user wants to modify it via dialogue.
   *
   * @param {string} userId - User ID
   * @param {string} workflowId - Workflow ID
   * @param {string} workflowYaml - Current Workflow YAML content
   * @param {Array} chatHistory - Optional chat history to restore context
   *   Format: [{type: 'user'|'assistant', content: string}, ...]
   * @returns {Promise<object>} Session creation result with session_id
   */
  async createWorkflowSession(userId, workflowId, workflowYaml, chatHistory = null) {
    const body = {
      user_id: userId,
      workflow_id: workflowId,
      workflow_yaml: workflowYaml
    };
    if (chatHistory && chatHistory.length > 0) {
      // Filter out error messages and convert to backend format
      // Ensure content is always a string to avoid cyclic structure errors
      body.chat_history = chatHistory
        .filter(msg => msg.type === 'user' || msg.type === 'assistant')
        .map(msg => ({
          role: msg.type,
          content: typeof msg.content === 'string' ? msg.content : String(msg.content || '')
        }));
    }
    return await this.callAppBackend('/api/v1/workflow-sessions', {
      method: 'POST',
      body: JSON.stringify(body)
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
   * Stop a running workflow execution
   *
   * @param {string} taskId - Task ID to stop
   * @returns {Promise<object>} Stop result with success, stopped_at_step, message
   */
  async stopWorkflow(taskId) {
    return await this.callAppBackend(`/api/v1/executions/${taskId}/stop`, {
      method: 'POST'
    });
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
  },

  // ============================================================================
  // Memory APIs
  // ============================================================================

  /**
   * Add recording to user's workflow memory
   *
   * @param {string} userId - User ID
   * @param {object} options - Options
   * @param {string} options.recordingId - Recording ID to load operations from
   * @param {Array} options.operations - Direct operations array (alternative to recordingId)
   * @param {string} options.sessionId - Session identifier
   * @param {boolean} options.generateEmbeddings - Whether to generate embeddings for semantic search
   * @returns {Promise<object>} Result with states_added, states_merged, etc.
   */
  async addToMemory(userId, { recordingId = null, operations = null, sessionId = null, generateEmbeddings = false } = {}) {
    return await this.callAppBackend('/api/v1/memory/add', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        recording_id: recordingId,
        operations: operations,
        session_id: sessionId,
        generate_embeddings: generateEmbeddings
      })
    });
  },

  /**
   * Query user's workflow memory using natural language
   *
   * The system automatically analyzes the query and returns the most relevant
   * operation paths with States, Actions, and IntentSequences.
   *
   * @param {string} userId - User ID
   * @param {string} query - Natural language query describing the task
   * @param {object} options - Query options
   * @param {number} options.topK - Number of paths to return (default: 3)
   * @param {number} options.minScore - Minimum similarity score 0-1 (default: 0.5)
   * @param {string} options.domain - Filter by domain (optional)
   * @returns {Promise<object>} Response with paths array, each containing steps with state/action/intent_sequence
   */
  async queryMemory(userId, query, { topK = 3, minScore = 0.5, domain = null } = {}) {
    return await this.callAppBackend('/api/v1/memory/query', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        query: query,
        top_k: topK,
        min_score: minScore,
        domain: domain
      })
    });
  },

  /**
   * Get user's workflow memory statistics
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Memory statistics (states, sequences, actions, domains)
   */
  async getMemoryStats(userId) {
    return await this.callAppBackend(`/api/v1/memory/stats?user_id=${userId}`);
  },

  /**
   * Clear user's workflow memory
   *
   * @param {string} userId - User ID
   * @returns {Promise<object>} Result with deleted counts
   */
  async clearMemory(userId) {
    return await this.callAppBackend(`/api/v1/memory?user_id=${userId}`, {
      method: 'DELETE'
    });
  },

  // ============================================================================
  // CognitivePhrase APIs
  // ============================================================================

  /**
   * List all cognitive phrases from memory
   *
   * @param {number} limit - Maximum number of phrases to return (default: 50)
   * @returns {Promise<object>} Response with phrases array
   */
  async listCognitivePhrases(limit = 50) {
    return await this.callAppBackend(`/api/v1/memory/phrases?limit=${limit}`);
  },

  /**
   * Get a single cognitive phrase with full details
   *
   * @param {string} phraseId - CognitivePhrase ID
   * @returns {Promise<object>} Response with phrase, states, and intent_sequences
   */
  async getCognitivePhrase(phraseId, { source } = {}) {
    const params = source ? `?source=${source}` : '';
    return await this.callAppBackend(`/api/v1/memory/phrases/${phraseId}${params}`);
  },

  /**
   * Delete a cognitive phrase from memory
   *
   * @param {string} phraseId - CognitivePhrase ID to delete
   * @returns {Promise<object>} Result with success status
   */
  async deleteCognitivePhrase(phraseId) {
    return await this.callAppBackend(`/api/v1/memory/phrases/${phraseId}`, {
      method: 'DELETE'
    });
  },

  /**
   * List public (community) cognitive phrases
   *
   * @param {number} limit - Maximum number of phrases to return
   * @param {string} sort - Sort order: "popular" or "recent"
   * @returns {Promise<object>} Result with phrases array and total count
   */
  async listPublicCognitivePhrases(limit = 50, sort = 'popular') {
    return await this.callAppBackend(`/api/v1/memory/phrases/public?limit=${limit}&sort=${sort}`);
  },

  /**
   * Check if a private phrase has been published to public memory
   *
   * @param {string} phraseId - Private phrase ID
   * @returns {Promise<object>} { published: bool, public_phrase_id?: string }
   */
  async getPublishStatus(phraseId) {
    return await this.callAppBackend(`/api/v1/memory/publish-status?phrase_id=${phraseId}`);
  },

  /**
   * Share a cognitive phrase from private memory to public memory
   *
   * @param {string} phraseId - CognitivePhrase ID to share
   * @returns {Promise<object>} Result with success and public_phrase_id
   */
  async shareCognitivePhrase(phraseId) {
    return await this.callAppBackend('/api/v1/memory/publish', {
      method: 'POST',
      body: JSON.stringify({ phrase_id: phraseId }),
    });
  },

  /**
   * Remove a phrase from public memory
   *
   * @param {string} phraseId - Private phrase ID
   * @returns {Promise<object>} Result with success status
   */
  async unpublishCognitivePhrase(phraseId) {
    return await this.callAppBackend('/api/v1/memory/unpublish', {
      method: 'POST',
      body: JSON.stringify({ phrase_id: phraseId }),
    });
  },

  // ============================================================================
  // Session APIs (Simple conversation persistence)
  // ============================================================================

  /**
   * Get current session with messages
   *
   * If session has expired (> 30 min), automatically creates a new session
   * and carries context from previous session.
   *
   * @param {number} limit - Maximum messages to return (default: 50)
   * @returns {Promise<object>} Session info with messages
   */
  async getSession(limit = 50) {
    return await this.callAppBackend(`/api/v1/session?limit=${limit}`);
  },

  /**
   * Append a message to current session
   *
   * @param {string} role - Message role (user, assistant, system)
   * @param {string} content - Message content
   * @param {object} options - Optional parameters
   * @param {string} options.messageId - Message ID (auto-generated if not provided)
   * @param {Array} options.attachments - Attachments
   * @param {object} options.metadata - Metadata
   * @returns {Promise<object>} Created message info
   */
  async appendSessionMessage(role, content, { messageId, attachments, metadata } = {}) {
    return await this.callAppBackend('/api/v1/session/message', {
      method: 'POST',
      body: JSON.stringify({
        role,
        content,
        message_id: messageId,
        attachments,
        metadata,
      })
    });
  },

  /**
   * Force create a new session
   *
   * @returns {Promise<object>} New session info
   */
  async createNewSession() {
    return await this.callAppBackend('/api/v1/session/new', {
      method: 'POST'
    });
  },

  /**
   * Get historical messages across sessions (cursor-based pagination)
   *
   * Traverses the session chain backward, useful for infinite scroll.
   *
   * @param {string} beforeTimestamp - ISO timestamp cursor
   * @param {number} limit - Max messages to return (default: 30)
   * @returns {Promise<object>} { messages, has_more, oldest_timestamp }
   */
  async getSessionHistory(beforeTimestamp, limit = 30) {
    const params = new URLSearchParams({
      before_timestamp: beforeTimestamp,
      limit: String(limit),
    });
    return await this.callAppBackend(`/api/v1/session/history?${params}`);
  },

  /**
   * Touch session to keep it alive
   */
  async touchSession() {
    return await this.callAppBackend('/api/v1/session/touch', {
      method: 'POST'
    });
  },

  // ============================================================================
  // Conversation Memory APIs
  // ============================================================================

  /**
   * Create a new conversation
   *
   * Note: user_id is automatically injected from the current session.
   *
   * @param {object} options - Conversation options
   * @param {string} options.title - Conversation title
   * @param {string} options.taskId - Associated task ID (optional)
   * @param {Array<string>} options.tags - Tags (optional)
   * @returns {Promise<object>} Created conversation with conversation_id
   */
  async createConversation({ title, taskId = null, tags = [] }) {
    // Get user_id from session
    const session = await auth.getSession();
    const userId = session?.username;

    if (!userId) {
      throw new Error('User not logged in');
    }

    return await this.callAppBackend('/api/v1/conversations', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        title,
        task_id: taskId,
        tags
      })
    });
  },

  /**
   * Get conversation details
   *
   * @param {string} conversationId - Conversation ID
   * @returns {Promise<object>} Conversation details
   */
  async getConversation(conversationId) {
    return await this.callAppBackend(`/api/v1/conversations/${conversationId}`);
  },

  /**
   * List conversations
   *
   * @param {object} options - Query options
   * @param {number} options.limit - Max results (default: 20)
   * @param {number} options.offset - Offset for pagination (default: 0)
   * @param {string} options.status - Filter by status (optional)
   * @returns {Promise<object>} Conversations list
   */
  async listConversations({ limit = 20, offset = 0, status = null } = {}) {
    let url = `/api/v1/conversations?limit=${limit}&offset=${offset}`;
    if (status) {
      url += `&status=${status}`;
    }
    return await this.callAppBackend(url);
  },

  /**
   * Update conversation
   *
   * @param {string} conversationId - Conversation ID
   * @param {object} updates - Fields to update (title, summary, status, tags, memory_level)
   * @returns {Promise<object>} Updated conversation
   */
  async updateConversation(conversationId, updates) {
    return await this.callAppBackend(`/api/v1/conversations/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates)
    });
  },

  /**
   * Delete conversation
   *
   * @param {string} conversationId - Conversation ID
   * @returns {Promise<object>} Deletion result
   */
  async deleteConversation(conversationId) {
    return await this.callAppBackend(`/api/v1/conversations/${conversationId}`, {
      method: 'DELETE'
    });
  },

  /**
   * Get messages from a conversation
   *
   * @param {string} conversationId - Conversation ID
   * @param {object} options - Query options
   * @param {number} options.limit - Max messages (default: 50)
   * @param {number} options.fromLine - Start from line (optional)
   * @returns {Promise<object>} Messages list
   */
  async getConversationMessages(conversationId, { limit = 50, fromLine = null } = {}) {
    let url = `/api/v1/conversations/${conversationId}/messages?limit=${limit}`;
    if (fromLine) {
      url += `&from_line=${fromLine}`;
    }
    return await this.callAppBackend(url);
  },

  /**
   * Append a message to conversation
   *
   * @param {string} conversationId - Conversation ID
   * @param {object} message - Message to append
   * @param {string} message.role - Message role (user/assistant/system)
   * @param {string} message.content - Message content
   * @param {string} message.agentId - Agent ID (optional)
   * @param {Array} message.attachments - Attachments (optional)
   * @param {object} message.metadata - Additional metadata (optional)
   * @param {number} message.inputTokens - Input tokens used (optional)
   * @param {number} message.outputTokens - Output tokens used (optional)
   * @returns {Promise<object>} Created message
   */
  async appendConversationMessage(conversationId, {
    role,
    content,
    agentId = null,
    attachments = [],
    metadata = {},
    inputTokens = null,
    outputTokens = null
  }) {
    return await this.callAppBackend(`/api/v1/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        role,
        content,
        agent_id: agentId,
        attachments,
        metadata,
        input_tokens: inputTokens,
        output_tokens: outputTokens
      })
    });
  },

  /**
   * Append an event to conversation
   *
   * @param {string} conversationId - Conversation ID
   * @param {object} event - Event to append
   * @param {string} event.eventType - Event type (task_started, browser_navigated, etc.)
   * @param {object} event.data - Event data
   * @returns {Promise<object>} Created event
   */
  async appendConversationEvent(conversationId, { eventType, data = {} }) {
    return await this.callAppBackend(`/api/v1/conversations/${conversationId}/events`, {
      method: 'POST',
      body: JSON.stringify({
        event_type: eventType,
        data
      })
    });
  },

  /**
   * Search conversations
   *
   * @param {string} query - Search query
   * @param {object} options - Search options
   * @param {number} options.limit - Max results (default: 10)
   * @param {boolean} options.searchContent - Search in message content (default: true)
   * @returns {Promise<object>} Search results
   */
  async searchConversations(query, { limit = 10, searchContent = true } = {}) {
    return await this.callAppBackend('/api/v1/conversations/search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        limit,
        search_content: searchContent
      })
    });
  },

  /**
   * Get conversation statistics
   *
   * @returns {Promise<object>} Statistics
   */
  async getConversationStats() {
    return await this.callAppBackend('/api/v1/conversations/stats');
  }
};
