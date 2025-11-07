// Background service worker for AgentCrafter Chrome Extension

console.log('AgentCrafter extension background script loaded');

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

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Message received:', request);

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

console.log('Background script initialization complete');