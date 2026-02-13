/**
 * Backend Configuration
 * Centralized configuration for daemon connection
 * Port is dynamically discovered from daemon.port file
 */

// Default port as fallback
const DEFAULT_PORT = 8765;

// Cached port value
let cachedPort = null;
let portInitPromise = null;

/**
 * Initialize the backend port by reading from daemon.port file
 * @param {boolean} forceRefresh - If true, ignore cache and re-read from file
 * @returns {Promise<number>} The discovered port
 */
export async function initBackendPort(forceRefresh = false) {
  // Return cached port if available and not forcing refresh
  if (!forceRefresh && cachedPort !== null) {
    return cachedPort;
  }

  // If forcing refresh, clear the existing promise to allow new read
  if (forceRefresh) {
    portInitPromise = null;
  }

  // Avoid duplicate concurrent reads
  if (portInitPromise) {
    return portInitPromise;
  }

  portInitPromise = (async () => {
    try {
      const result = await window.electronAPI.getDaemonPort();
      if (result.success && result.port) {
        cachedPort = result.port;
        console.log(`Backend port initialized: ${cachedPort} (source: ${result.source}, refresh: ${forceRefresh})`);
        if (result.warning) {
          console.warn(`Port discovery warning: ${result.warning}`);
        }
        return cachedPort;
      }
    } catch (error) {
      console.warn('Failed to get daemon port, using default:', error);
    }
    cachedPort = DEFAULT_PORT;
    return cachedPort;
  })();

  return portInitPromise;
}

/**
 * Get the current backend port (sync version)
 * Returns cached port or default if not yet initialized
 */
export function getBackendPort() {
  return cachedPort ?? DEFAULT_PORT;
}

export const BACKEND_CONFIG = {
  host: '127.0.0.1',

  get port() {
    return getBackendPort();
  },

  get httpBase() {
    return `http://${this.host}:${this.port}`;
  },

  get wsBase() {
    return `ws://${this.host}:${this.port}`;
  }
};
