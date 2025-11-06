// Background service worker for AgentCrafter Chrome Extension

console.log('AgentCrafter extension background script loaded');

// In-memory storage for captured operations (persists while background script runs)
let capturedOperations = [];

// Extension installation
chrome.runtime.onInstalled.addListener((details) => {
  console.log('Extension installed/updated', details.reason);

  if (details.reason === 'install') {
    // Set default settings
    chrome.storage.local.set({
      enabled: true,
      autoCapture: false,
      apiEndpoint: 'http://localhost:8000'
    });
  }
});

// Initialize Side Panel behavior - open on action click
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error('Error setting side panel behavior:', error));

console.log('Side panel behavior initialized: openPanelOnActionClick = true');

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // Get captured operations
  if (request.action === 'getCapturedOperations') {
    sendResponse({ success: true, operations: capturedOperations });
    return true;
  }

  // Clear captured operations
  if (request.action === 'clearCapturedOperations') {
    capturedOperations = [];
    sendResponse({ success: true });
    return true;
  }

  if (request.action === 'captureTab') {
    captureTabScreenshot()
      .then(dataUrl => {
        sendResponse({ success: true, screenshot: dataUrl });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }

  if (request.action === 'executeWorkflow') {
    executeWorkflow(request.workflowId, request.params)
      .then(result => {
        sendResponse({ success: true, result });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep message channel open for async response
  }

  if (request.action === 'storeData') {
    chrome.storage.local.set(request.data, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (request.action === 'getData') {
    chrome.storage.local.get(request.keys, (data) => {
      sendResponse({ success: true, data });
    });
    return true;
  }

  if (request.action === 'sendOperation') {
    // Store operation in memory first
    capturedOperations.push(request.operation);

    // Then send to backend
    sendOperationToBackend(request.sessionId, request.token, request.operation)
      .then(result => {
        sendResponse({ success: true, operation_count: result.operation_count });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }

  // Handle file download requests
  if (request.action === 'downloadFile') {
    handleFileDownload(request.blobUrl, request.filename)
      .then(downloadId => {
        sendResponse({ success: true, downloadId });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }
});

// Capture tab screenshot
async function captureTabScreenshot() {
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, {
      format: 'png'
    });
    return dataUrl;
  } catch (error) {
    console.error('Error capturing screenshot:', error);
    throw error;
  }
}

// Store blob URLs to prevent premature cleanup
const activeBlobUrls = new Map();

// Handle file download from popup/sidepanel
async function handleFileDownload(blobUrl, filename) {
  try {
    console.log(`Starting download: ${filename} from ${blobUrl}`);

    // Start download
    const downloadId = await chrome.downloads.download({
      url: blobUrl,
      filename: filename,
      saveAs: false,
      conflictAction: 'uniquify'
    });

    console.log(`Download started with ID: ${downloadId}`);

    // Store the blob URL with download ID for cleanup after download completes
    activeBlobUrls.set(downloadId, { url: blobUrl, filename: filename });

    return downloadId;
  } catch (error) {
    console.error('Error downloading file:', error);
    throw error;
  }
}

// Listen for download completion to clean up blob URLs
chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current === 'complete') {
    const downloadId = delta.id;
    const blobInfo = activeBlobUrls.get(downloadId);

    if (blobInfo) {
      console.log(`Download completed: ${blobInfo.filename} (ID: ${downloadId})`);

      // Send message to revoke the blob URL in the popup context
      chrome.runtime.sendMessage({
        action: 'revokeBlobUrl',
        url: blobInfo.url
      }).catch(() => {
        // Popup might be closed, that's OK
      });

      // Clean up our tracking
      activeBlobUrls.delete(downloadId);
    }
  }

  // Handle download errors
  if (delta.error) {
    const downloadId = delta.id;
    const blobInfo = activeBlobUrls.get(downloadId);

    if (blobInfo) {
      console.error(`Download failed: ${blobInfo.filename} - ${delta.error.current}`);

      // Clean up
      chrome.runtime.sendMessage({
        action: 'revokeBlobUrl',
        url: blobInfo.url
      }).catch(() => {});

      activeBlobUrls.delete(downloadId);
    }
  }
});

// Send operation to backend
async function sendOperationToBackend(sessionId, token, operation) {
  try {
    const apiEndpoint = 'http://localhost:8000';

    const response = await fetch(`${apiEndpoint}/api/recording/operation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        session_id: sessionId,
        operation: operation
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending operation to backend:', error);
    throw error;
  }
}

// Execute workflow
async function executeWorkflow(workflowId, params) {
  try {
    // Get stored credentials
    const storage = await chrome.storage.local.get(['userToken', 'userId', 'apiEndpoint']);

    const apiEndpoint = storage.apiEndpoint || 'http://localhost:8000';

    if (!storage.userToken) {
      throw new Error('Not authenticated');
    }

    // Call backend API
    const response = await fetch(`${apiEndpoint}/api/v1/agents/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${storage.userToken}`
      },
      body: JSON.stringify({
        user_id: storage.userId,
        agent_id: workflowId,
        params: params
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error executing workflow:', error);
    throw error;
  }
}

// Monitor tab updates for auto-capture
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    const storage = await chrome.storage.local.get(['autoCapture']);

    if (storage.autoCapture) {
      try {
        const response = await chrome.tabs.sendMessage(tabId, { action: 'capturePage' });
        if (response && response.success) {
          console.log('Auto-captured page:', tab.url);
        }
      } catch (error) {
        // Ignore errors for pages where content script isn't loaded
        console.debug('Could not auto-capture:', error);
      }
    }
  }
});

// Periodic authentication check (every 15 seconds)
const AUTH_CHECK_INTERVAL = 15000; // 15 seconds
let authCheckTimer = null;

async function checkAuthStatus() {
  try {
    const storage = await chrome.storage.local.get(['userToken', 'userId', 'username']);

    if (!storage.userToken) {
      // No token, skip check
      return;
    }

    // Use lightweight ping API to check auth status
    const response = await fetch('http://localhost:8000/api/ping', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${storage.userToken}`
      }
    });

    if (response.status === 401) {
      console.log('❌ Auth check failed - token invalid or expired (401)');

      // Clear user data
      await chrome.storage.local.remove(['userToken', 'userId', 'username', 'currentPage', 'selectedWorkflowId']);

      // Notify any open popups to redirect to login
      chrome.runtime.sendMessage({
        action: 'authExpired'
      }).catch(() => {
        // Ignore error if no popup is open
      });

      console.log('✅ User logged out due to token expiration');
    } else if (response.ok) {
      console.log('✅ Auth check passed');
    } else {
      console.log(`⚠️ Auth check: unexpected status ${response.status}`);
    }
  } catch (error) {
    // Network error, don't log out user
    console.debug('Auth check network error (ignored):', error.message);
  }
}

// Start periodic auth check
function startAuthCheck() {
  if (authCheckTimer) {
    clearInterval(authCheckTimer);
  }

  authCheckTimer = setInterval(checkAuthStatus, AUTH_CHECK_INTERVAL);
  console.log(`🔐 Started periodic auth check (every ${AUTH_CHECK_INTERVAL / 1000}s)`);

  // Run first check immediately
  checkAuthStatus();
}

// Start auth check on extension load
startAuthCheck();

console.log('Background script initialization complete');