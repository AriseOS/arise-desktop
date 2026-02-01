/**
 * SSE Client Utility
 *
 * Provides Server-Sent Events (SSE) connection management for real-time
 * communication with the backend. Supports all 59 event types defined in
 * the backend action_types.py.
 *
 * Migration from WebSocket to SSE for better compatibility with HTTP/2
 * and standard web infrastructure.
 */

import { auth } from './auth';
import { BACKEND_CONFIG } from '../config/backend';

/**
 * Event types from backend action_types.py
 * These map to the 'action' field in SSE events
 */
export const SSEEventTypes = {
  // Task lifecycle
  TASK_STARTED: 'task_started',
  TASK_COMPLETED: 'task_completed',
  TASK_FAILED: 'task_failed',
  TASK_CANCELLED: 'task_cancelled',
  TASK_PAUSED: 'task_paused',
  TASK_RESUMED: 'task_resumed',

  // Agent lifecycle (DS-1: Added missing events)
  AGENT_CREATED: 'agent_created',
  AGENT_ACTIVATED: 'agent_activated',
  AGENT_DEACTIVATED: 'agent_deactivated',
  AGENT_COMPLETED: 'agent_completed',
  AGENT_ERROR: 'agent_error',
  ACTIVATE_AGENT: 'activate_agent',
  DEACTIVATE_AGENT: 'deactivate_agent',
  AGENT_THINKING: 'agent_thinking',

  // Toolkit events
  TOOLKIT_STARTED: 'toolkit_started',
  TOOLKIT_COMPLETED: 'toolkit_completed',
  TOOLKIT_FAILED: 'toolkit_failed',
  TOOLKIT_PROGRESS: 'toolkit_progress',
  ACTIVATE_TOOLKIT: 'activate_toolkit',
  DEACTIVATE_TOOLKIT: 'deactivate_toolkit',

  // Tool events
  TOOL_STARTED: 'tool_started',
  TOOL_COMPLETED: 'tool_completed',
  TOOL_FAILED: 'tool_failed',

  // LLM events
  LLM_REQUEST_STARTED: 'llm_request_started',
  LLM_REQUEST_COMPLETED: 'llm_request_completed',
  LLM_REASONING: 'llm_reasoning',
  LLM_STREAMING: 'llm_streaming',

  // Browser events
  BROWSER_STARTED: 'browser_started',
  BROWSER_STOPPED: 'browser_stopped',
  BROWSER_NAVIGATED: 'browser_navigated',
  BROWSER_ACTION: 'browser_action',
  BROWSER_SCREENSHOT: 'browser_screenshot',
  SCREENSHOT: 'screenshot',

  // Conversation events
  MESSAGE_ADDED: 'message_added',
  MESSAGE_UPDATED: 'message_updated',
  CONVERSATION_SUMMARY: 'conversation_summary',

  // Human interaction
  HUMAN_QUESTION: 'human_question',
  HUMAN_RESPONSE_RECEIVED: 'human_response_received',
  HUMAN_MESSAGE: 'human_message',
  WAIT_CONFIRM: 'wait_confirm',      // Simple answer waiting for user (Eigent pattern)
  CONFIRMED: 'confirmed',            // Task confirmed as complex, starting decomposition
  ASK: 'ask',

  // Memory events
  MEMORY_LOADED: 'memory_loaded',
  MEMORY_RESULT: 'memory_result',  // Backend MemoryResultData event
  MEMORY_QUERY: 'memory_query',
  MEMORY_UPDATED: 'memory_updated',
  MEMORY_LEVEL: 'memory_level',
  MEMORY_EVENT: 'memory_event',

  // Reasoner events
  REASONER_QUERY_STARTED: 'reasoner_query_started',
  REASONER_WORKFLOW_STARTED: 'reasoner_workflow_started',
  REASONER_WORKFLOW_COMPLETED: 'reasoner_workflow_completed',
  REASONER_FALLBACK: 'reasoner_fallback',

  // Loop iteration
  LOOP_ITERATION: 'loop_iteration',

  // Working directory events
  WORKSPACE_CREATED: 'workspace_created',
  WORKSPACE_FILE_CREATED: 'workspace_file_created',
  WORKSPACE_FILE_UPDATED: 'workspace_file_updated',

  // Terminal events
  TERMINAL_OUTPUT: 'terminal_output',
  TERMINAL_COMMAND: 'terminal_command',
  TERMINAL: 'terminal',

  // Progress and status
  PROGRESS_UPDATE: 'progress_update',
  STATUS_UPDATE: 'status_update',

  // Notes
  NOTES_UPDATED: 'notes_updated',

  // Task decomposition events (DS-1: Added missing events)
  TASK_DECOMPOSED: 'task_decomposed',
  SUBTASK_STATE: 'subtask_state',
  TASK_REPLANNED: 'task_replanned',
  STREAMING_DECOMPOSE: 'streaming_decompose',
  DECOMPOSE_PROGRESS: 'decompose_progress',

  // Workforce events (DS-1: Added missing events)
  WORKFORCE_STARTED: 'workforce_started',
  WORKFORCE_COMPLETED: 'workforce_completed',
  WORKFORCE_STOPPED: 'workforce_stopped',
  WORKER_ASSIGNED: 'worker_assigned',
  WORKER_STARTED: 'worker_started',
  WORKER_COMPLETED: 'worker_completed',
  WORKER_FAILED: 'worker_failed',
  ASSIGN_TASK: 'assign_task',
  DYNAMIC_TASKS_ADDED: 'dynamic_tasks_added',

  // Heartbeat
  HEARTBEAT: 'heartbeat',

  // Error
  ERROR: 'error',

  // System
  NOTICE: 'notice',
  END: 'end',

  // Connection
  CONNECTED: 'connected',
};

/**
 * SSE Client class for managing Server-Sent Events connections
 *
 * Reconnection Strategy (following Eigent's pattern):
 * - Auto-retry on connection errors (network issues, connection refused, etc.)
 * - Exponential backoff with max 10 attempts for network errors
 * - Immediate retry for transient errors (up to 3 times)
 * - Stop retrying for fatal errors (HTTP 4xx, parse errors, etc.)
 */
export class SSEClient {
  constructor() {
    this.eventSource = null;
    this.abortController = null;
    this.taskId = null;
    this.handlers = new Map();
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10; // Increased from 3 to handle longer network issues
    this.reconnectDelay = 1000;
    this.options = null; // Store options for reconnection
  }

  /**
   * Connect to SSE endpoint for a task
   *
   * @param {string} taskId - The task ID to subscribe to
   * @param {object} options - Connection options
   * @param {function} options.onEvent - Callback for all events
   * @param {function} options.onError - Callback for errors
   * @param {function} options.onClose - Callback when connection closes
   * @returns {Promise<void>}
   */
  async connect(taskId, options = {}) {
    const { onEvent, onError, onClose } = options;

    // Close existing connection if any
    this.disconnect();

    this.taskId = taskId;
    this.options = options; // Store for reconnection
    this.abortController = new AbortController();

    const apiKey = await auth.getApiKey();
    const sseUrl = `${BACKEND_CONFIG.httpBase}/api/v1/quick-task/stream/${taskId}`;

    console.log('[SSE] Connecting to:', sseUrl);

    try {
      // Use fetch with ReadableStream for SSE
      // This approach works better than EventSource for custom headers
      const response = await fetch(sseUrl, {
        method: 'GET',
        headers: {
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache',
          ...(apiKey && { 'X-Ami-API-Key': apiKey }),
        },
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        // HTTP errors (4xx, 5xx) - check if retriable
        const error = new Error(`SSE connection failed: ${response.status} ${response.statusText}`);
        error.status = response.status;
        throw error;
      }

      this.isConnected = true;
      this.reconnectAttempts = 0;
      console.log('[SSE] Connected successfully');

      // Process the stream
      await this._processStream(response.body, onEvent, onError);

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('[SSE] Connection aborted');
        // Don't call onClose here, it was intentionally aborted
        return;
      }

      console.error('[SSE] Connection error:', error);

      // Check if this is a retriable error (following Eigent's pattern)
      if (this._isRetriableError(error)) {
        console.warn('[SSE] Retriable error detected, will attempt reconnection...');
        this._handleReconnect(taskId, options);
      } else {
        // Fatal error - don't retry
        console.error('[SSE] Fatal error, stopping reconnection attempts:', error.message);
        if (onError) {
          onError(error);
        }
        if (onClose) {
          onClose();
        }
      }
      return;
    }

    // Normal stream end
    this.isConnected = false;
    if (onClose) {
      onClose();
    }
  }

  /**
   * Check if an error is retriable (following Eigent's pattern)
   * @private
   */
  _isRetriableError(error) {
    // Network errors are retriable
    if (error instanceof TypeError) {
      return true;
    }

    // Check error message for common retriable patterns
    const retriablePatterns = [
      'Failed to fetch',
      'ECONNREFUSED',
      'ECONNRESET',
      'ETIMEDOUT',
      'NetworkError',
      'network error',
      'Network request failed',
      'ERR_NETWORK',
      'ERR_CONNECTION_REFUSED',
      'ERR_CONNECTION_RESET',
      'ERR_INTERNET_DISCONNECTED',
    ];

    const errorMessage = error.message || '';
    for (const pattern of retriablePatterns) {
      if (errorMessage.includes(pattern)) {
        return true;
      }
    }

    // HTTP 5xx errors are retriable (server errors)
    if (error.status && error.status >= 500 && error.status < 600) {
      return true;
    }

    // HTTP 4xx errors are NOT retriable (client errors like 404, 401, etc.)
    if (error.status && error.status >= 400 && error.status < 500) {
      return false;
    }

    // Default: retry for unknown errors
    return true;
  }

  /**
   * Process SSE stream
   * @private
   * @returns {Promise<{streamEnded: boolean, error: Error|null}>}
   */
  async _processStream(body, onEvent, onError) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamError = null;

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          console.log('[SSE] Stream ended normally');
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // Process complete events
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        let currentEvent = null;
        let currentData = [];

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            // Append data lines (SSE can have multiple data: lines)
            currentData.push(line.slice(5).trim());
          } else if (line === '' && currentData.length > 0) {
            // Empty line marks end of event
            // Join multi-line data with newlines
            const dataStr = currentData.join('\n');
            try {
              const rawData = JSON.parse(dataStr);

              // Handle backend format: {"step": "action_type", "data": {...}}
              // Extract the inner data and merge with step as event type
              let event;
              if (rawData.step && rawData.data) {
                // Backend sends {"step": "agent_thinking", "data": {action, ...}}
                event = {
                  event: rawData.step,
                  action: rawData.step,
                  ...rawData.data,
                };
              } else {
                // Fallback for direct format
                event = {
                  event: currentEvent || rawData.action || 'message',
                  ...rawData,
                };
              }

              console.log('[SSE] Event received:', event.event, event);

              // Call registered handlers
              this._dispatchEvent(event);

              // Call general callback
              if (onEvent) {
                onEvent(event);
              }
            } catch (parseError) {
              console.warn('[SSE] Failed to parse event data:', dataStr, parseError);
            }

            currentEvent = null;
            currentData = [];
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('[SSE] Stream aborted');
        throw error; // Re-throw abort errors
      }

      console.error('[SSE] Stream processing error:', error);
      streamError = error;

      // Check if this is a retriable error
      if (this._isRetriableError(error)) {
        console.warn('[SSE] Stream error is retriable, will attempt reconnection...');
        // Attempt reconnection
        this._handleReconnect(this.taskId, this.options);
      } else {
        // Non-retriable error
        if (onError) {
          onError(error);
        }
      }
    } finally {
      try {
        reader.releaseLock();
      } catch (e) {
        // Ignore errors when releasing lock
      }
    }

    return { streamEnded: !streamError, error: streamError };
  }

  /**
   * Dispatch event to registered handlers
   * @private
   */
  _dispatchEvent(event) {
    const eventType = event.event || event.action;

    // Call specific handler
    const handler = this.handlers.get(eventType);
    if (handler) {
      handler(event);
    }

    // Call wildcard handler
    const wildcardHandler = this.handlers.get('*');
    if (wildcardHandler) {
      wildcardHandler(event);
    }
  }

  /**
   * Handle reconnection with exponential backoff
   * @private
   *
   * Following Eigent's pattern:
   * - Auto-retry on connection errors
   * - Exponential backoff (1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s, 512s)
   * - Max delay capped at 30 seconds
   * - 10 total attempts before giving up
   */
  _handleReconnect(taskId, options) {
    if (!taskId || !options) {
      console.error('[SSE] Cannot reconnect: missing taskId or options');
      return;
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;

      // Exponential backoff with max delay of 30 seconds
      const baseDelay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      const delay = Math.min(baseDelay, 30000);

      console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

      // Clear any existing reconnection timer
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
      }

      this._reconnectTimer = setTimeout(() => {
        this._reconnectTimer = null;

        // Check if we've been disconnected manually
        if (!this.taskId) {
          console.log('[SSE] Reconnection cancelled: client was disconnected');
          return;
        }

        console.log(`[SSE] Attempting reconnection (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        this.connect(taskId, options);
      }, delay);
    } else {
      console.error('[SSE] Max reconnection attempts reached, giving up');

      // Notify about connection failure
      const { onError, onClose } = options;
      if (onError) {
        onError(new Error('SSE connection failed after max reconnection attempts'));
      }
      if (onClose) {
        onClose();
      }

      // Reset state
      this.isConnected = false;
      this.taskId = null;
    }
  }

  /**
   * Register event handler
   *
   * @param {string} eventType - Event type to handle (or '*' for all)
   * @param {function} handler - Handler function
   */
  on(eventType, handler) {
    this.handlers.set(eventType, handler);
  }

  /**
   * Remove event handler
   *
   * @param {string} eventType - Event type to remove handler for
   */
  off(eventType) {
    this.handlers.delete(eventType);
  }

  /**
   * Send message to server (via separate HTTP request)
   * SSE is one-way, so we use POST for sending
   *
   * @param {string} type - Message type
   * @param {object} data - Message data
   */
  async send(type, data) {
    if (!this.taskId) {
      throw new Error('Not connected to any task');
    }

    const apiKey = await auth.getApiKey();
    const response = await fetch(`${BACKEND_CONFIG.httpBase}/api/v1/quick-task/message/${this.taskId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(apiKey && { 'X-Ami-API-Key': apiKey }),
      },
      body: JSON.stringify({ type, ...data }),
    });

    if (!response.ok) {
      throw new Error(`Failed to send message: ${response.status}`);
    }

    return await response.json();
  }

  /**
   * Send human response
   *
   * @param {string} response - Human response text
   */
  async sendHumanResponse(response) {
    return await this.send('human_response', { response });
  }

  /**
   * Disconnect from SSE stream
   */
  disconnect() {
    // Clear any pending reconnection timer
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }

    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }

    this.isConnected = false;
    this.taskId = null;
    this.options = null;
    this.reconnectAttempts = 0;
    this.handlers.clear();
    console.log('[SSE] Disconnected');
  }

  /**
   * Check if connected
   * @returns {boolean}
   */
  get connected() {
    return this.isConnected;
  }
}

/**
 * Create and export singleton instance
 */
export const sseClient = new SSEClient();

/**
 * Helper function to create SSE connection for a task
 *
 * @param {string} taskId - Task ID
 * @param {object} handlers - Event handlers object
 * @returns {SSEClient} SSE client instance
 */
export function createSSEConnection(taskId, handlers = {}) {
  const client = new SSEClient();

  // Register handlers
  Object.entries(handlers).forEach(([eventType, handler]) => {
    client.on(eventType, handler);
  });

  return client;
}

/**
 * Map backend event to frontend state update
 *
 * @param {object} event - SSE event
 * @returns {object} State update object
 */
export function mapEventToState(event) {
  const eventType = event.event || event.action;

  switch (eventType) {
    case SSEEventTypes.TASK_STARTED:
      return {
        status: 'running',
        executionPhase: 'starting',
      };

    case SSEEventTypes.TASK_COMPLETED:
      return {
        status: 'completed',
        executionPhase: 'completed',
        result: event.output,
        notes: event.notes,
      };

    case SSEEventTypes.TASK_FAILED:
      return {
        status: 'failed',
        executionPhase: 'failed',
        error: event.error,
      };

    case SSEEventTypes.AGENT_CREATED:
      return {
        agentCreated: {
          agentId: event.agent_id,
          agentName: event.agent_name,
          agentType: event.agent_type,
        },
      };

    case SSEEventTypes.TOOLKIT_STARTED:
      return {
        toolkitEvent: {
          type: 'started',
          toolkitName: event.toolkit_name,
          methodName: event.method_name,
          inputs: event.inputs,
          timestamp: event.timestamp,
        },
      };

    case SSEEventTypes.TOOLKIT_COMPLETED:
      return {
        toolkitEvent: {
          type: 'completed',
          toolkitName: event.toolkit_name,
          methodName: event.method_name,
          outputs: event.outputs,
          timestamp: event.timestamp,
        },
      };

    case SSEEventTypes.TOOL_STARTED:
      return {
        toolEvent: {
          type: 'started',
          toolName: event.tool_name,
          toolInput: event.tool_input,
          timestamp: event.timestamp,
        },
      };

    case SSEEventTypes.TOOL_COMPLETED:
      return {
        toolEvent: {
          type: 'completed',
          toolName: event.tool_name,
          result: event.result_preview,
          error: event.error,
          timestamp: event.timestamp,
        },
      };

    case SSEEventTypes.LLM_REASONING:
      return {
        reasoning: event.reasoning,
      };

    case SSEEventTypes.MEMORY_LOADED:
    case SSEEventTypes.MEMORY_RESULT:
      return {
        memoryPaths: event.paths || [],
        executionPhase: 'memory_loaded',
        hasWorkflow: event.has_workflow,
      };

    case SSEEventTypes.HUMAN_QUESTION:
      return {
        humanQuestion: {
          question: event.question,
          context: event.context,
        },
      };

    case SSEEventTypes.MESSAGE_ADDED:
      return {
        newMessage: {
          role: event.role,
          content: event.content,
          timestamp: event.timestamp,
        },
      };

    case SSEEventTypes.LOOP_ITERATION:
      return {
        loopIteration: event.step,
        currentTools: event.tools_called || [],
      };

    case SSEEventTypes.WORKSPACE_FILE_CREATED:
    case SSEEventTypes.WORKSPACE_FILE_UPDATED:
      return {
        workspaceFile: {
          path: event.file_path,
          content: event.content,
          action: eventType === SSEEventTypes.WORKSPACE_FILE_CREATED ? 'created' : 'updated',
        },
      };

    case SSEEventTypes.TERMINAL_OUTPUT:
      return {
        terminalOutput: event.output,
      };

    default:
      return { rawEvent: event };
  }
}

export default sseClient;
