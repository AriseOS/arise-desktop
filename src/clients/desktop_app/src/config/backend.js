/**
 * Backend Configuration
 * Centralized configuration for daemon connection
 */

export const BACKEND_CONFIG = {
  host: '127.0.0.1',
  port: 8765,

  get httpBase() {
    return `http://${this.host}:${this.port}`;
  },

  get wsBase() {
    return `ws://${this.host}:${this.port}`;
  }
};
