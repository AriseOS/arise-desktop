// Popup script for AgentCrafter Chrome Extension

// Page elements
let loginPage, mainPage, loginForm, logoutBtn;
let currentUser = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup DOM loaded, initializing...');

  // Get page elements
  loginPage = document.getElementById('login-page');
  mainPage = document.getElementById('main-page');
  loginForm = document.getElementById('login-form');
  logoutBtn = document.getElementById('logout-btn');

  // Check login status
  await checkLoginStatus();

  // Setup event listeners
  setupEventListeners();

  console.log('Popup initialization complete');
});

// Check if user is logged in
async function checkLoginStatus() {
  try {
    const result = await chrome.storage.local.get(['userToken', 'userId', 'username']);
    console.log('Checking login status, stored data:', result);

    if (result.userToken && result.userId) {
      // User is logged in
      currentUser = {
        token: result.userToken,
        userId: result.userId,
        username: result.username || 'User'
      };
      console.log('User is logged in:', currentUser.username);
      showMainPage();
    } else {
      // User is not logged in
      console.log('User is not logged in');
      showLoginPage();
    }
  } catch (error) {
    console.error('Error checking login status:', error);
    showLoginPage();
  }
}

// Show login page
function showLoginPage() {
  loginPage.classList.remove('hidden');
  mainPage.classList.add('hidden');
}

// Show main page
function showMainPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.remove('hidden');

  // Update user info
  if (currentUser) {
    document.getElementById('display-username').textContent = currentUser.username;
  }

  // Load current tab info
  loadCurrentTabInfo();
}

// Load current tab information
async function loadCurrentTabInfo() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      document.getElementById('current-url').value = tab.url;
      document.getElementById('page-title').value = tab.title;
    }
  } catch (error) {
    console.error('Error loading tab info:', error);
  }
}

// Setup event listeners
function setupEventListeners() {
  // Login form submit
  loginForm.addEventListener('submit', handleLogin);

  // Logout button
  logoutBtn.addEventListener('click', handleLogout);

  // Main page buttons
  document.getElementById('capture-page').addEventListener('click', handleCapturePage);
  document.getElementById('run-workflow').addEventListener('click', handleRunWorkflow);
  document.getElementById('open-dashboard').addEventListener('click', handleOpenDashboard);
}

// Handle login
async function handleLogin(e) {
  e.preventDefault();

  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const loginBtn = document.getElementById('login-btn');

  if (!username || !password) {
    showStatus('请输入用户名和密码', 'error');
    return;
  }

  try {
    // Disable login button
    loginBtn.disabled = true;
    loginBtn.innerHTML = '<span class="loading"></span>登录中...';

    // Call backend API to login
    const apiEndpoint = 'http://localhost:8000';
    const response = await fetch(`${apiEndpoint}/api/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    });

    if (response.ok) {
      const data = await response.json();

      // Store user info
      const userData = {
        userToken: data.access_token,
        userId: data.user.id,
        username: data.user.username
      };

      await chrome.storage.local.set(userData);
      console.log('User data saved to storage:', userData);

      currentUser = {
        token: data.access_token,
        userId: data.user.id,
        username: data.user.username
      };

      showStatus('✅ 登录成功！', 'success');

      // Clear form
      loginForm.reset();

      // Show main page after short delay
      setTimeout(() => {
        showMainPage();
      }, 500);
    } else {
      const error = await response.json();
      showStatus(`❌ 登录失败: ${error.detail || '用户名或密码错误'}`, 'error');
    }
  } catch (error) {
    console.error('Login error:', error);
    showStatus('❌ 连接服务器失败，请检查后端是否运行', 'error');
  } finally {
    // Re-enable login button
    loginBtn.disabled = false;
    loginBtn.innerHTML = '登录';
  }
}

// Handle logout
async function handleLogout() {
  try {
    // Clear stored user info
    await chrome.storage.local.remove(['userToken', 'userId', 'username']);
    currentUser = null;

    showStatus('✅ 已退出登录', 'success');

    // Show login page after short delay
    setTimeout(() => {
      showLoginPage();
    }, 500);
  } catch (error) {
    console.error('Logout error:', error);
    showStatus('❌ 退出登录失败', 'error');
  }
}

// Handle capture page
async function handleCapturePage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Send message to content script to capture page info
    chrome.tabs.sendMessage(tab.id, { action: 'capturePage' }, (response) => {
      if (chrome.runtime.lastError) {
        showStatus('❌ 页面捕获失败', 'error');
        return;
      }

      if (response && response.success) {
        showStatus('✅ 页面捕获成功！', 'success');
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
    showStatus('❌ 页面捕获出错', 'error');
    console.error('Capture error:', error);
  }
}

// Handle run workflow
async function handleRunWorkflow() {
  if (!currentUser || !currentUser.token) {
    showStatus('⚠️ 请先登录', 'error');
    showLoginPage();
    return;
  }

  try {
    showStatus('⏳ 工作流运行中...', 'info');

    // Call backend API to run workflow
    const response = await fetch('http://localhost:8000/api/v1/agents/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentUser.token}`
      },
      body: JSON.stringify({
        user_id: currentUser.userId,
        agent_id: 'browser-session-test-workflow'
      })
    });

    if (response.ok) {
      showStatus('✅ 工作流已启动！', 'success');
    } else if (response.status === 401) {
      showStatus('⚠️ 登录已过期，请重新登录', 'error');
      handleLogout();
    } else {
      showStatus('❌ 工作流启动失败', 'error');
    }
  } catch (error) {
    showStatus('❌ 工作流运行出错', 'error');
    console.error('Workflow error:', error);
  }
}

// Handle open dashboard
function handleOpenDashboard() {
  chrome.tabs.create({ url: 'http://localhost:3000' });
}

// Show status message
function showStatus(message, type = 'info') {
  const statusEl = document.getElementById('status-message');
  statusEl.innerHTML = `<div class="status status-${type}">${message}</div>`;

  setTimeout(() => {
    statusEl.innerHTML = '';
  }, 3000);
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'workflowUpdate') {
    showStatus(message.message, message.status);
  }
});