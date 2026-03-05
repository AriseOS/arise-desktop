/**
 * API Client with Auto-injected JWT Auth
 * All requests go through daemon-ts (localhost), which proxies to Cloud Backend.
 *
 * Auth: JWT tokens managed by daemon. Frontend fetches token on demand via GET /auth/token.
 * All calls: Bearer token auto-injected from daemon-backed auth.getToken()
 */

import { auth } from './auth';
import { BACKEND_CONFIG, initBackendPort } from '../config/backend';

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
   * Register new user (Cloud Backend)
   *
   * @param {string} username - Username
   * @param {string} email - Email address
   * @param {string} password - Password
   * @returns {Promise<object>} Registration result with JWT tokens
   */
  async register(username, email, password) {
    try {
      console.log('[API] Registering user:', username);

      const response = await fetch(`${getBackendBase()}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || error.detail || 'Registration failed');
      }

      const result = await response.json();
      console.log('[API] Registration successful');

      // Cloud Backend returns: { success, access_token, refresh_token, user_id, username }
      return {
        success: result.success,
        access_token: result.access_token,
        refresh_token: result.refresh_token,
        user: {
          id: result.user_id,
          username: result.username,
        },
      };
    } catch (error) {
      console.error('[API] Registration error:', error);
      throw error;
    }
  },

  /**
   * Login user (Cloud Backend)
   *
   * Supports both email and username login.
   *
   * @param {string} emailOrUsername - Email address or username
   * @param {string} password - Password
   * @returns {Promise<object>} Login result with JWT tokens
   */
  async login(emailOrUsername, password) {
    try {
      console.log('[API] Logging in user:', emailOrUsername);

      const response = await fetch(`${getBackendBase()}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: emailOrUsername, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || error.detail || 'Login failed');
      }

      const result = await response.json();
      console.log('[API] Login successful');

      // Cloud Backend returns: { access_token, refresh_token, user_id, username }
      return {
        success: true,
        access_token: result.access_token,
        refresh_token: result.refresh_token,
        user: {
          id: result.user_id,
          username: result.username,
        },
      };
    } catch (error) {
      console.error('[API] Login error:', error);
      throw error;
    }
  },

  /**
   * Get user's quota status
   *
   * @returns {Promise<object>} Quota status
   */
  async getQuotaStatus() {
    // TODO: Quota endpoint not yet implemented on Cloud Backend
    return null;
  },

  // ============================================================================
  // App Backend APIs (with auto-injected JWT token)
  // ============================================================================

  /**
   * Call App Backend with auto-injected Authorization header.
   *
   * Token refresh is handled by the daemon internally, so no 401 retry here.
   *
   * @param {string} endpoint - API endpoint path (e.g., "/api/browser/start")
   * @param {object} options - Fetch options (method, body, headers, etc.)
   * @returns {Promise<any>} Response data
   */
  async callAppBackend(endpoint, options = {}) {
    try {
      const token = await auth.getToken();

      const headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
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
      const token = await auth.getToken();

      const headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      return await fetch(`${getBackendBase()}${endpoint}`, {
        ...options,
        headers
      });
    } catch (error) {
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
   * Learn from recording operations via /memory/learn.
   * Converts raw recording operations to trace steps and sends to the unified learn endpoint.
   *
   * @param {string} task - Task description for the recording
   * @param {Array} operations - Raw recording operations [{type, url, text, value, ...}]
   * @param {object} options - Options
   * @param {string} options.source - Source identifier (default: "arise-desktop")
   * @returns {Promise<object>} Learn result with phrase_created, phrase_ids, etc.
   */
  async learnFromRecording(task, operations, { source = 'arise-desktop' } = {}) {
    // Map recording operation types to valid trace actions
    const actionMap = {
      click: 'click',
      type: 'type',
      input: 'type',
      navigate: 'navigate',
      scroll: 'scroll',
      select: 'select',
      submit: 'submit',
      enter: 'submit',
      change: 'type',
      keydown: null,   // skip — not a meaningful trace action
      hover: null,     // skip
      copy: null,      // skip
      paste: null,     // skip
      dataload: null,  // skip
    };

    const steps = [];
    let lastUrl = '';
    for (const op of operations) {
      const mapped = actionMap[op.type];
      if (!mapped) continue;
      const url = op.url || op.page_url || lastUrl;
      if (!url) continue;
      lastUrl = url;
      steps.push({
        url,
        action: mapped,
        target: op.text || op.selector || undefined,
        value: op.value || undefined,
      });
    }

    return await this.callAppBackend('/api/v1/memory/learn', {
      method: 'POST',
      body: JSON.stringify({
        type: 'browser_workflow',
        task: task || 'Recorded browser workflow',
        success: true,
        steps,
        source,
      })
    });
  },

  // queryMemory(task) deprecated — use /memory/plan via daemon instead

  /**
   * Get user's workflow memory statistics
   *
   * @returns {Promise<object>} Memory statistics (states, sequences, actions, domains)
   */
  async getMemoryStats() {
    return await this.callAppBackend('/api/v1/memory/stats');
  },

  /**
   * Clear user's workflow memory
   *
   * @returns {Promise<object>} Result with deleted counts
   */
  async clearMemory() {
    return await this.callAppBackend('/api/v1/memory', {
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
    return await this.callAppBackend('/api/v1/memory/share', {
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
