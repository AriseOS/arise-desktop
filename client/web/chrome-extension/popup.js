// Popup script for AgentCrafter Chrome Extension

// Page elements
let loginPage, mainPage, aboutPage, loginForm;
let currentUser = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup DOM loaded, initializing...');

  // Get page elements
  loginPage = document.getElementById('login-page');
  mainPage = document.getElementById('main-page');
  aboutPage = document.getElementById('about-page');
  loginForm = document.getElementById('login-form');

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
  aboutPage.classList.add('hidden');
}

// Show main page
function showMainPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.remove('hidden');
  aboutPage.classList.add('hidden');
}

// Show about page
function showAboutPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.add('hidden');
  aboutPage.classList.remove('hidden');
}

// Setup event listeners
function setupEventListeners() {
  // Login form submit
  loginForm.addEventListener('submit', handleLogin);

  // Menu items
  document.getElementById('menu-record').addEventListener('click', handleMenuRecord);
  document.getElementById('menu-chat').addEventListener('click', handleMenuChat);
  document.getElementById('menu-my').addEventListener('click', handleMenuMy);
  document.getElementById('menu-account').addEventListener('click', handleMenuAccount);
  document.getElementById('menu-about').addEventListener('click', handleMenuAbout);
  document.getElementById('menu-logout').addEventListener('click', handleLogout);

  // Back button
  document.getElementById('back-to-main').addEventListener('click', showMainPage);
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

// Menu handlers
function handleMenuRecord() {
  console.log('录制功能');
  showStatus('📹 录制功能开发中...', 'info');
  // TODO: Implement record functionality
}

function handleMenuChat() {
  console.log('对话功能');
  showStatus('💬 对话功能开发中...', 'info');
  // TODO: Implement chat functionality
}

function handleMenuMy() {
  console.log('我的 Workflow');
  showStatus('📋 我的 Workflow 功能开发中...', 'info');
  // TODO: Implement my workflows functionality
}

function handleMenuAccount() {
  console.log('账户设置');
  showStatus('👤 账户设置功能开发中...', 'info');
  // TODO: Implement account settings
}

function handleMenuAbout() {
  console.log('关于');
  showAboutPage();
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