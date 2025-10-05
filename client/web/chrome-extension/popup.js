// Popup script for AgentCrafter Chrome Extension

// Get current tab information
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0]) {
    document.getElementById('current-url').value = tabs[0].url;
    document.getElementById('page-title').value = tabs[0].title;
  }
});

// Show status message
function showStatus(message, type = 'info') {
  const statusEl = document.getElementById('status-message');
  statusEl.innerHTML = `<div class="status status-${type}">${message}</div>`;

  setTimeout(() => {
    statusEl.innerHTML = '';
  }, 3000);
}

// Capture current page
document.getElementById('capture-page').addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Send message to content script to capture page info
    chrome.tabs.sendMessage(tab.id, { action: 'capturePage' }, (response) => {
      if (chrome.runtime.lastError) {
        showStatus('❌ Failed to capture page', 'error');
        return;
      }

      if (response && response.success) {
        showStatus('✅ Page captured successfully!', 'success');
        console.log('Captured data:', response.data);

        // Store captured data
        chrome.storage.local.set({
          lastCapture: {
            ...response.data,
            timestamp: new Date().toISOString()
          }
        });
      }
    });
  } catch (error) {
    showStatus('❌ Error capturing page', 'error');
    console.error('Capture error:', error);
  }
});

// Run workflow
document.getElementById('run-workflow').addEventListener('click', async () => {
  try {
    showStatus('⏳ Running workflow...', 'info');

    // Get stored user info
    const result = await chrome.storage.local.get(['userToken', 'userId']);

    if (!result.userToken) {
      showStatus('⚠️ Please login first', 'error');
      return;
    }

    // Call backend API to run workflow
    const response = await fetch('http://localhost:8000/api/v1/agents/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${result.userToken}`
      },
      body: JSON.stringify({
        user_id: result.userId,
        agent_id: 'browser-session-test-workflow'
      })
    });

    if (response.ok) {
      showStatus('✅ Workflow started!', 'success');
    } else {
      showStatus('❌ Failed to start workflow', 'error');
    }
  } catch (error) {
    showStatus('❌ Error running workflow', 'error');
    console.error('Workflow error:', error);
  }
});

// Open dashboard
document.getElementById('open-dashboard').addEventListener('click', () => {
  chrome.tabs.create({ url: 'http://localhost:3000' });
});

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'workflowUpdate') {
    showStatus(message.message, message.status);
  }
});