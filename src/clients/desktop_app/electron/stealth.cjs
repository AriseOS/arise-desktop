/**
 * Anti-detection stealth script.
 * Injected into each WebContentsView on 'did-finish-load' to avoid bot detection.
 */

const STEALTH_SCRIPT = `
  // Save original values before overriding to maintain consistency
  const originalLanguages = navigator.languages ? [...navigator.languages] : ['en-US', 'en'];
  const originalHardwareConcurrency = navigator.hardwareConcurrency || 8;
  const originalDeviceMemory = navigator.deviceMemory || 8;

  // Hide webdriver property
  Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
  });

  // Override plugins with proper PluginArray-like behavior
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const plugins = {
        length: 3,
        0: { name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer' },
        1: { name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        2: { name: 'Native Client', description: '', filename: 'internal-nacl-plugin' },
        item: function(index) { return this[index] || null; },
        namedItem: function(name) {
          for (let i = 0; i < this.length; i++) {
            if (this[i].name === name) return this[i];
          }
          return null;
        },
        refresh: function() {},
        [Symbol.iterator]: function* () {
          for (let i = 0; i < this.length; i++) {
            yield this[i];
          }
        }
      };
      return plugins;
    },
    configurable: true
  });

  // Use original system languages for consistency
  Object.defineProperty(navigator, 'languages', {
    get: () => originalLanguages,
    configurable: true
  });

  // Clamp hardwareConcurrency to common range (4-16)
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => Math.min(Math.max(originalHardwareConcurrency, 4), 16),
    configurable: true
  });

  // Clamp deviceMemory to common range (4-16)
  Object.defineProperty(navigator, 'deviceMemory', {
    get: () => Math.min(Math.max(originalDeviceMemory, 4), 16),
    configurable: true
  });

  // Fix WebGL vendor/renderer for both WebGL and WebGL2
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel(R) Iris(TM) Graphics 6100';
    return getParameter.call(this, parameter);
  };

  if (typeof WebGL2RenderingContext !== 'undefined') {
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(parameter) {
      if (parameter === 37445) return 'Intel Inc.';
      if (parameter === 37446) return 'Intel(R) Iris(TM) Graphics 6100';
      return getParameter2.call(this, parameter);
    };
  }

  // Override chrome runtime to look like a real Chrome browser
  if (!window.chrome) {
    window.chrome = {};
  }
  if (!window.chrome.runtime) {
    window.chrome.runtime = {
      connect: function() { return { onMessage: { addListener: function() {} }, postMessage: function() {} }; },
      sendMessage: function() {},
      onMessage: { addListener: function() {}, removeListener: function() {} },
      onConnect: { addListener: function() {}, removeListener: function() {} },
      id: undefined
    };
  }

  // Force visibilityState to "visible" for off-screen WebContentsView.
  // Many SPAs throttle timers, pause rAF, or skip rendering when hidden.
  // Without this patch, JS-heavy sites may hang waiting for animations.
  Object.defineProperty(document, 'visibilityState', {
    get: () => 'visible',
    configurable: true
  });
  Object.defineProperty(document, 'hidden', {
    get: () => false,
    configurable: true
  });
  // Swallow visibilitychange events so pages never learn they're off-screen
  document.addEventListener('visibilitychange', function(e) {
    e.stopImmediatePropagation();
  }, true);

  // Hide automation variables
  const automationVars = [
    '__webdriver_evaluate', '__selenium_evaluate', '__webdriver_script_fn',
    '__driver_evaluate', '__fxdriver_evaluate', '__driver_unwrapped',
    'domAutomation', 'domAutomationController'
  ];
  automationVars.forEach(v => {
    Object.defineProperty(window, v, {
      get: () => undefined,
      set: () => {},
      configurable: true,
      enumerable: false
    });
  });
`;

module.exports = { STEALTH_SCRIPT };
