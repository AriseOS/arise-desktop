// Popup script for Ami Chrome Extension

// Page elements
let loginPage, mainPage, aboutPage, myPage, loginForm;
let currentUser = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup DOM loaded, initializing...');

  // Get page elements
  loginPage = document.getElementById('login-page');
  mainPage = document.getElementById('main-page');
  aboutPage = document.getElementById('about-page');
  myPage = document.getElementById('my-page');
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
  myPage.classList.add('hidden');
}

// Show main page
function showMainPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.remove('hidden');
  aboutPage.classList.add('hidden');
  myPage.classList.add('hidden');
}

// Show about page
function showAboutPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.add('hidden');
  aboutPage.classList.remove('hidden');
  myPage.classList.add('hidden');
}

// Show my workflows page
async function showMyPage() {
  loginPage.classList.add('hidden');
  mainPage.classList.add('hidden');
  aboutPage.classList.add('hidden');
  myPage.classList.remove('hidden');

  // Load workflows
  await loadMyWorkflows();
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

  // Back buttons
  document.getElementById('back-to-main').addEventListener('click', showMainPage);
  document.getElementById('back-from-my').addEventListener('click', showMainPage);
  document.getElementById('back-from-workflow').addEventListener('click', showMyPage);
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
  showMyPage();
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

// Load my workflows
async function loadMyWorkflows() {
  if (!currentUser || !currentUser.token) {
    showStatus('⚠️ 请先登录', 'error');
    showLoginPage();
    return;
  }

  const container = document.getElementById('workflow-list-container');
  container.innerHTML = '<div style="text-align: center; padding: 20px; color: #8e8e93;">加载中...</div>';

  try {
    const response = await fetch('http://localhost:8000/api/agents?default=true', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentUser.token}`
      }
    });

    if (!response.ok) {
      if (response.status === 401) {
        showStatus('⚠️ 登录已过期，请重新登录', 'error');
        handleLogout();
        return;
      }
      throw new Error(`API error: ${response.status}`);
    }

    const workflows = await response.json();

    if (workflows.length === 0) {
      // Show empty state
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📋</div>
          <div class="empty-state-title">还没有 Workflow</div>
          <div class="empty-state-desc">您可以通过录制或对话创建 Workflow</div>
        </div>
      `;
    } else {
      // Show workflow list
      container.innerHTML = workflows.map(workflow => `
        <div class="workflow-item" data-id="${workflow.agent_id}">
          <div class="workflow-item-info">
            <div class="workflow-item-name">${workflow.name}</div>
            ${workflow.description ? `<div class="workflow-item-desc">${workflow.description}</div>` : ''}
          </div>
          <div class="workflow-item-arrow">›</div>
        </div>
      `).join('');

      // Add click listeners
      container.querySelectorAll('.workflow-item').forEach(item => {
        item.addEventListener('click', () => {
          const workflowId = item.dataset.id;
          console.log('Clicked workflow:', workflowId);
          showWorkflowDetail(workflowId);
        });
      });
    }
  } catch (error) {
    console.error('Load workflows error:', error);
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
        <div class="empty-state-title">加载失败</div>
        <div class="empty-state-desc">无法获取 Workflow 列表</div>
      </div>
    `;
  }
}

// Show workflow detail page
async function showWorkflowDetail(workflowId) {
  console.log('Loading workflow detail:', workflowId);

  // Hide all pages
  document.querySelectorAll('#login-page, #main-page, #about-page, #my-page, #workflow-detail-page').forEach(page => {
    page.classList.add('hidden');
  });

  // Show workflow detail page
  document.getElementById('workflow-detail-page').classList.remove('hidden');

  const contentContainer = document.getElementById('workflow-detail-content');
  contentContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #8e8e93;">Loading workflow...</div>';

  try {
    // Fetch workflow data
    const response = await fetch(`http://localhost:8000/api/agents/${workflowId}/workflow`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentUser.token}`
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const workflowData = await response.json();
    console.log('Workflow data:', workflowData);

    // Render workflow visualization
    renderWorkflowVisualization(workflowData);

  } catch (error) {
    console.error('Load workflow detail error:', error);
    contentContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
        <div class="empty-state-title">加载失败</div>
        <div class="empty-state-desc">无法获取 Workflow 详情</div>
      </div>
    `;
  }
}

// Render workflow visualization using SVG
function renderWorkflowVisualization(workflowData) {
  const container = document.getElementById('workflow-detail-content');

  if (!workflowData || !workflowData.steps || workflowData.steps.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div class="empty-state-title">无流程数据</div>
        <div class="empty-state-desc">该 Workflow 没有流程信息</div>
      </div>
    `;
    return;
  }

  const steps = workflowData.steps;
  const connections = workflowData.connections || [];

  // Calculate compact layout for small screen
  const nodeWidth = 140;
  const nodeHeight = 60;
  const horizontalGap = 40;
  const verticalGap = 30;
  const nodesPerRow = 2; // 2 nodes per row for compact layout

  // Position nodes in grid
  const nodePositions = steps.map((step, index) => {
    const row = Math.floor(index / nodesPerRow);
    const col = index % nodesPerRow;
    return {
      ...step,
      x: col * (nodeWidth + horizontalGap) + 20,
      y: row * (nodeHeight + verticalGap) + 20
    };
  });

  // Calculate SVG size
  const maxRow = Math.ceil(steps.length / nodesPerRow);
  const svgWidth = nodesPerRow * (nodeWidth + horizontalGap) + 40;
  const svgHeight = maxRow * (nodeHeight + verticalGap) + 40;

  // Create SVG
  let svg = `
    <div class="workflow-info">
      <h3>Workflow Structure</h3>
      <p>${steps.length} steps · ${connections.length} connections</p>
    </div>
    <div class="workflow-canvas">
      <svg width="${svgWidth}" height="${svgHeight}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
            <polygon points="0 0, 10 3, 0 6" fill="#8e8e93" />
          </marker>
        </defs>
  `;

  // Draw connections first (so they appear behind nodes)
  connections.forEach(conn => {
    const fromNode = nodePositions.find(n => n.id === conn.from);
    const toNode = nodePositions.find(n => n.id === conn.to);

    if (fromNode && toNode) {
      const x1 = fromNode.x + nodeWidth / 2;
      const y1 = fromNode.y + nodeHeight;
      const x2 = toNode.x + nodeWidth / 2;
      const y2 = toNode.y;

      svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#8e8e93" stroke-width="2" marker-end="url(#arrowhead)" />`;
    }
  });

  // Draw nodes
  nodePositions.forEach((node, index) => {
    const nodeColor = getNodeColor(node.type);

    svg += `
      <g class="workflow-node" data-node-index="${index}">
        <rect class="node-rect" x="${node.x}" y="${node.y}" width="${nodeWidth}" height="${nodeHeight}"
              rx="8" fill="${nodeColor}" stroke="#667eea" stroke-width="2" />
        <text class="node-text" x="${node.x + nodeWidth/2}" y="${node.y + nodeHeight/2 - 5}"
              text-anchor="middle" font-size="13" font-weight="600" fill="#1c1c1e">
          ${truncateText(node.name, 18)}
        </text>
        <text x="${node.x + nodeWidth/2}" y="${node.y + nodeHeight/2 + 10}"
              text-anchor="middle" font-size="11" fill="#666">
          ${truncateText(node.type, 16)}
        </text>
      </g>
    `;
  });

  svg += '</svg></div>';

  container.innerHTML = svg;

  // Add click listeners to nodes
  container.querySelectorAll('.workflow-node').forEach((nodeEl, index) => {
    nodeEl.addEventListener('click', () => {
      showNodeDetail(steps[index]);
    });
  });
}

// Get node color based on type
function getNodeColor(type) {
  switch(type) {
    case 'start':
      return '#d1fae5'; // Light green
    case 'end':
      return '#fecaca'; // Light red
    default:
      return '#dbeafe'; // Light blue
  }
}

// Truncate text to fit in node
function truncateText(text, maxLength) {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength - 3) + '...';
}

// Show node detail in modal
function showNodeDetail(nodeData) {
  const modal = document.createElement('div');
  modal.className = 'node-detail-modal';
  modal.innerHTML = `
    <div class="node-detail-content">
      <h3>${nodeData.name}</h3>
      <div class="detail-item">
        <div class="detail-label">Type:</div>
        <div class="detail-value">${nodeData.type || 'N/A'}</div>
      </div>
      <div class="detail-item">
        <div class="detail-label">Description:</div>
        <div class="detail-value">${nodeData.description || 'No description'}</div>
      </div>
      <div class="detail-item">
        <div class="detail-label">ID:</div>
        <div class="detail-value">${nodeData.id || 'N/A'}</div>
      </div>
      <button class="close-modal-btn">Close</button>
    </div>
  `;

  document.body.appendChild(modal);

  // Close modal on button click or background click
  modal.querySelector('.close-modal-btn').addEventListener('click', () => {
    modal.remove();
  });

  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.remove();
    }
  });
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