/**
 * Behavior Tracker - Captures user interactions using aria-ref system
 *
 * Records user actions in the same format as action_executor.py expects,
 * using the persistent ref system from unified_analyzer.js.
 *
 * Output format matches ActionExecutor actions:
 *   { type: "click", ref: "e42", text: "Submit", role: "button" }
 *   { type: "type", ref: "e15", text: "hello", role: "textbox" }
 */
(function() {
    // Prevent multiple initialization
    if (window._behaviorTrackerInitialized) return;
    window._behaviorTrackerInitialized = true;

    console.log("🎯 Behavior Tracker initialized (ref-based)");

    // =========================================================================
    // Element Info Collector - Uses aria-ref from unified_analyzer.js
    // =========================================================================

    function getElementRef(element) {
        if (!element) return null;

        // Get aria-ref assigned by unified_analyzer.js
        const ref = element.getAttribute('aria-ref');
        if (ref) return ref;

        // Walk up to find nearest parent with aria-ref
        let parent = element.parentElement;
        let depth = 0;
        while (parent && depth < 5) {
            const parentRef = parent.getAttribute('aria-ref');
            if (parentRef) return parentRef;
            parent = parent.parentElement;
            depth++;
        }

        return null;
    }

    function getElementRole(element) {
        if (!element) return null;

        // Check explicit role attribute
        const role = element.getAttribute('role');
        if (role) return role;

        // Infer role from tag name
        const tagName = element.tagName.toLowerCase();
        const roleMap = {
            'a': 'link',
            'button': 'button',
            'input': element.type === 'checkbox' ? 'checkbox'
                   : element.type === 'radio' ? 'radio'
                   : 'textbox',
            'select': 'combobox',
            'textarea': 'textbox',
            'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
            'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
            'img': 'img',
            'nav': 'navigation',
            'main': 'main',
            'ul': 'list', 'ol': 'list',
            'li': 'listitem',
            'table': 'table',
            'tr': 'row',
            'td': 'cell', 'th': 'cell'
        };

        return roleMap[tagName] || 'generic';
    }

    function getElementText(element) {
        if (!element) return '';

        // Check aria-label first
        const ariaLabel = element.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel.trim();

        // Check aria-labelledby
        const labelledBy = element.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.textContent.trim();
        }

        // For inputs, use placeholder or value
        if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
            return element.placeholder || '';
        }

        // Get visible text content (limited)
        const text = (element.textContent || '').trim();
        return text.slice(0, 100);
    }

    function getElementInfo(element) {
        if (!element) return null;

        const ref = getElementRef(element);
        const role = getElementRole(element);
        const text = getElementText(element);
        const tagName = element.tagName.toLowerCase();

        // For links, capture href (useful when ref is missing during navigation)
        let href = null;
        if (tagName === 'a') {
            href = element.href;
        } else {
            // Check if element is inside a link
            const linkParent = element.closest('a');
            if (linkParent) {
                href = linkParent.href;
            }
        }

        return {
            ref: ref,
            role: role,
            text: text,
            tagName: tagName,
            href: href
        };
    }

    // =========================================================================
    // Operation Reporter
    // =========================================================================

    function report(type, elementInfo, additionalData) {
        const timestamp = new Date().toISOString();

        const operation = {
            type: type,
            timestamp: timestamp,
            url: window.location.href
        };

        // Add element info if available
        if (elementInfo) {
            if (elementInfo.ref) operation.ref = elementInfo.ref;
            if (elementInfo.text) operation.text = elementInfo.text;
            if (elementInfo.role) operation.role = elementInfo.role;
            if (elementInfo.href) operation.href = elementInfo.href;
        }

        // Merge additional data
        if (additionalData) {
            Object.assign(operation, additionalData);
        }

        // Report via CDP binding or postMessage
        if (window.reportUserBehavior) {
            try {
                window.reportUserBehavior(JSON.stringify(operation));
            } catch (e) {
                console.warn('Failed to report via CDP:', e);
            }
        } else {
            // Chrome Extension fallback
            window.postMessage({
                source: 'ami-tracker',
                operation: operation
            }, '*');
        }
    }

    // =========================================================================
    // Click Handler
    // =========================================================================

    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;

    document.addEventListener('mousedown', function(e) {
        isDragging = false;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
    }, true);

    document.addEventListener('mousemove', function(e) {
        if (e.buttons === 1) {
            const distance = Math.sqrt(
                Math.pow(e.clientX - dragStartX, 2) +
                Math.pow(e.clientY - dragStartY, 2)
            );
            if (distance > 5) {
                isDragging = true;
            }
        }
    }, true);

    document.addEventListener('click', function(e) {
        // Skip if this was a drag operation
        if (isDragging) {
            isDragging = false;
            return;
        }

        const info = getElementInfo(e.target);
        // Always report click, even without ref (e.g., navigation links)
        report('click', info);
    }, true);

    // =========================================================================
    // Input Handler (debounced)
    // =========================================================================

    const inputTimeouts = new Map();
    const INPUT_DEBOUNCE_MS = 1500;

    document.addEventListener('input', function(e) {
        const element = e.target;
        const tagName = element.tagName.toLowerCase();

        // Only track actual input fields
        if (tagName !== 'input' && tagName !== 'textarea' && element.contentEditable !== 'true') {
            return;
        }

        // Skip password fields
        if (element.type === 'password' || element.type === 'hidden') {
            return;
        }

        const info = getElementInfo(element);
        if (!info) return;

        // Debounce by element ref
        const key = info.ref;
        if (inputTimeouts.has(key)) {
            clearTimeout(inputTimeouts.get(key));
        }

        const timeout = setTimeout(() => {
            const value = element.value || '';
            if (value.trim()) {
                report('type', info, {
                    value: value
                });
            }
            inputTimeouts.delete(key);
        }, INPUT_DEBOUNCE_MS);

        inputTimeouts.set(key, timeout);
    }, true);

    // =========================================================================
    // Navigation Handler
    // =========================================================================

    let currentUrl = window.location.href;

    // Only in main frame
    if (window.self === window.top) {
        // URL polling for SPA navigation
        setInterval(function() {
            if (window.location.href !== currentUrl) {
                const fromUrl = currentUrl;
                currentUrl = window.location.href;

                report('navigate', null, {
                    url: currentUrl,
                    from_url: fromUrl
                });
            }
        }, 500);

        // Popstate for browser back/forward
        window.addEventListener('popstate', function() {
            const fromUrl = currentUrl;
            currentUrl = window.location.href;

            report('navigate', null, {
                url: currentUrl,
                from_url: fromUrl
            });
        });
    }

    // =========================================================================
    // Scroll Handler (throttled)
    // =========================================================================

    let scrollTimeout;
    let lastScrollY = window.scrollY;
    const SCROLL_THRESHOLD = 100;

    window.addEventListener('scroll', function() {
        clearTimeout(scrollTimeout);

        scrollTimeout = setTimeout(function() {
            const currentScrollY = window.scrollY;
            const delta = currentScrollY - lastScrollY;

            if (Math.abs(delta) > SCROLL_THRESHOLD) {
                report('scroll', null, {
                    direction: delta > 0 ? 'down' : 'up',
                    amount: Math.abs(Math.round(delta))
                });
                lastScrollY = currentScrollY;
            }
        }, 150);
    });

    // =========================================================================
    // Select (Dropdown) Handler
    // =========================================================================

    document.addEventListener('change', function(e) {
        const element = e.target;

        if (element.tagName.toLowerCase() === 'select') {
            const info = getElementInfo(element);
            if (info) {
                report('select', info, {
                    value: element.value
                });
            }
        }
    }, true);

    // =========================================================================
    // Enter Key Handler
    // =========================================================================

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            const info = getElementInfo(e.target);
            report('enter', info);
        }
    }, true);

    // =========================================================================
    // Copy/Paste Handlers
    // =========================================================================

    document.addEventListener('copy', function(e) {
        const selection = window.getSelection();
        const text = selection ? selection.toString() : '';

        if (text) {
            report('copy', null, {
                text: text.slice(0, 200)
            });
        }
    });

    document.addEventListener('paste', function(e) {
        const info = getElementInfo(e.target);
        const clipboardData = e.clipboardData || window.clipboardData;
        const text = clipboardData ? clipboardData.getData('text') : '';

        report('paste', info, {
            text: text.slice(0, 200)
        });
    });

    // =========================================================================
    // Text Selection Handler (drag-based)
    // =========================================================================

    document.addEventListener('mouseup', function(e) {
        if (isDragging) {
            setTimeout(function() {
                const selection = window.getSelection();
                const text = selection ? selection.toString().trim() : '';

                if (text.length > 0) {
                    report('select_text', null, {
                        text: text.slice(0, 200)
                    });
                }
            }, 10);
        }
        isDragging = false;
    }, true);

    console.log("✅ Behavior Tracker ready");
})();
