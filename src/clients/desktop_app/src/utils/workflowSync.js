/**
 * Workflow Resource Sync Service
 * Handles synchronization of workflow resources between local and cloud
 */

import { getCurrentUserId } from './currentUser';
import { BACKEND_CONFIG } from '../config/backend';

// Use daemon (local backend) for sync operations
// Daemon handles the actual sync between local storage and cloud
// Get URL dynamically since port may change
const getDaemonBase = () => BACKEND_CONFIG.httpBase;

/**
 * Check if workflow needs sync
 *
 * @param {string} workflowId - Workflow ID
 * @returns {Promise<object>} Sync status
 *   {
 *     needs_sync: boolean,
 *     direction: "upload" | "download" | "none",
 *     local_updated_at: string | null,
 *     cloud_updated_at: string | null
 *   }
 */
export async function checkSyncStatus(workflowId) {
  try {
    const userId = await getCurrentUserId();

    const response = await fetch(
      `${getDaemonBase()}/api/v1/workflows/${workflowId}/sync/status?user_id=${userId}`
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to check sync status');
    }

    return await response.json();
  } catch (error) {
    console.error('[WorkflowSync] Failed to check sync status:', error);
    throw error;
  }
}

/**
 * Sync workflow resources
 *
 * @param {string} workflowId - Workflow ID
 * @param {string|null} direction - Sync direction ("upload", "download", or null for auto)
 * @returns {Promise<object>} Sync result
 *   {
 *     success: boolean,
 *     message: string,
 *     synced_resources: Array,
 *     errors: Array
 *   }
 */
export async function syncResources(workflowId, direction = null) {
  try {
    const userId = await getCurrentUserId();

    const body = direction ? { direction } : {};

    const response = await fetch(
      `${getDaemonBase()}/api/v1/workflows/${workflowId}/sync?user_id=${userId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Sync failed');
    }

    return await response.json();
  } catch (error) {
    console.error('[WorkflowSync] Sync failed:', error);
    throw error;
  }
}

/**
 * List workflow resources
 *
 * @param {string} workflowId - Workflow ID
 * @param {string} source - "local" or "cloud"
 * @returns {Promise<object>} Resources list
 *   {
 *     workflow_id: string,
 *     updated_at: string,
 *     resources: {
 *       scraper_scripts: Array,
 *       code_agent_scripts: Array,
 *       custom_prompts: Array
 *     }
 *   }
 */
export async function listResources(workflowId, source = 'local') {
  try {
    const userId = await getCurrentUserId();

    const response = await fetch(
      `${getDaemonBase()}/api/v1/workflows/${workflowId}/resources?user_id=${userId}&source=${source}`
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to list resources');
    }

    return await response.json();
  } catch (error) {
    console.error('[WorkflowSync] Failed to list resources:', error);
    throw error;
  }
}

/**
 * Auto-sync on workflow view
 * Call this when user opens workflow detail page
 *
 * @param {string} workflowId - Workflow ID
 * @param {Function} onStatus - Callback for status updates (status) => void
 * @returns {Promise<object>} Sync result or null if no sync needed
 */
export async function autoSyncOnView(workflowId, onStatus = null) {
  try {
    // Check sync status
    if (onStatus) onStatus({ type: 'checking', message: 'Checking sync status...' });

    const status = await checkSyncStatus(workflowId);

    if (!status.needs_sync) {
      if (onStatus) onStatus({ type: 'synced', message: 'Workflow is up to date' });
      return null;
    }

    // Auto-download if cloud is newer
    if (status.direction === 'download') {
      if (onStatus) onStatus({ type: 'downloading', message: 'Downloading latest resources from cloud...' });

      const result = await syncResources(workflowId, 'download');

      if (result.success) {
        if (onStatus) {
          onStatus({
            type: 'downloaded',
            message: `Downloaded ${result.synced_resources.length} resources from cloud`,
            result
          });
        }
      }

      return result;
    }

    // Auto-upload if local is newer (symmetric with download behavior)
    if (status.direction === 'upload') {
      if (onStatus) onStatus({ type: 'uploading', message: 'Uploading local changes to cloud...' });

      const result = await syncResources(workflowId, 'upload');

      if (result.success) {
        if (onStatus) {
          onStatus({
            type: 'uploaded',
            message: `Uploaded ${result.synced_resources?.length || 0} resources to cloud`,
            result
          });
        }
      }

      return result;
    }

    return null;
  } catch (error) {
    console.error('[WorkflowSync] Auto-sync failed:', error);
    if (onStatus) {
      onStatus({
        type: 'error',
        message: `Sync failed: ${error.message}`,
        error
      });
    }
    throw error;
  }
}
