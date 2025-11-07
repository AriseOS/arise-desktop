// Content script for AgentCrafter Chrome Extension
// This script runs in the context of web pages

console.log('AgentCrafter extension content script loaded');

// Listen for messages from popup or background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'capturePage') {
    const pageData = capturePageData();
    sendResponse({ success: true, data: pageData });
    return true;
  }

  if (request.action === 'highlightElement') {
    highlightElement(request.selector);
    sendResponse({ success: true });
    return true;
  }

  if (request.action === 'clickElement') {
    const success = clickElement(request.selector);
    sendResponse({ success });
    return true;
  }

  if (request.action === 'fillInput') {
    const success = fillInput(request.selector, request.value);
    sendResponse({ success });
    return true;
  }
});

// Capture page data
function capturePageData() {
  const data = {
    url: window.location.href,
    title: document.title,
    html: document.documentElement.outerHTML,
    text: document.body.innerText,
    meta: {
      description: document.querySelector('meta[name="description"]')?.content || '',
      keywords: document.querySelector('meta[name="keywords"]')?.content || '',
      author: document.querySelector('meta[name="author"]')?.content || ''
    },
    links: Array.from(document.querySelectorAll('a')).map(a => ({
      text: a.innerText,
      href: a.href
    })).slice(0, 50), // Limit to 50 links
    images: Array.from(document.querySelectorAll('img')).map(img => ({
      src: img.src,
      alt: img.alt
    })).slice(0, 20), // Limit to 20 images
    forms: Array.from(document.querySelectorAll('form')).map(form => ({
      action: form.action,
      method: form.method,
      inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
        name: input.name,
        type: input.type,
        id: input.id,
        placeholder: input.placeholder
      }))
    })),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollY: window.scrollY,
      scrollX: window.scrollX
    }
  };

  return data;
}

// Highlight element on page
function highlightElement(selector) {
  try {
    const element = document.querySelector(selector);
    if (!element) return false;

    // Create highlight overlay
    const highlight = document.createElement('div');
    highlight.style.cssText = `
      position: absolute;
      border: 3px solid #667eea;
      background: rgba(102, 126, 234, 0.2);
      pointer-events: none;
      z-index: 999999;
      transition: all 0.3s;
    `;

    const rect = element.getBoundingClientRect();
    highlight.style.top = (rect.top + window.scrollY) + 'px';
    highlight.style.left = (rect.left + window.scrollX) + 'px';
    highlight.style.width = rect.width + 'px';
    highlight.style.height = rect.height + 'px';

    document.body.appendChild(highlight);

    // Remove highlight after 3 seconds
    setTimeout(() => {
      highlight.remove();
    }, 3000);

    return true;
  } catch (error) {
    console.error('Error highlighting element:', error);
    return false;
  }
}

// Click element
function clickElement(selector) {
  try {
    const element = document.querySelector(selector);
    if (!element) return false;

    element.click();
    return true;
  } catch (error) {
    console.error('Error clicking element:', error);
    return false;
  }
}

// Fill input
function fillInput(selector, value) {
  try {
    const element = document.querySelector(selector);
    if (!element) return false;

    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  } catch (error) {
    console.error('Error filling input:', error);
    return false;
  }
}

// Add floating action button for quick access
function addFloatingButton() {
  const fab = document.createElement('div');
  fab.id = 'agentcrafter-fab';
  fab.innerHTML = '🤖';
  fab.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    font-size: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 999999;
    transition: all 0.3s;
  `;

  fab.addEventListener('mouseenter', () => {
    fab.style.transform = 'scale(1.1)';
    fab.style.boxShadow = '0 6px 16px rgba(0, 0, 0, 0.4)';
  });

  fab.addEventListener('mouseleave', () => {
    fab.style.transform = 'scale(1)';
    fab.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
  });

  fab.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'openPopup' });
  });

  document.body.appendChild(fab);
}

// Initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', addFloatingButton);
} else {
  addFloatingButton();
}