// Tracking script - captures user operations
(function() {
    if (window._agentcrafterRecorderInitialized) return;
    window._agentcrafterRecorderInitialized = true;

    console.log('🎯 AgentCrafter behavior tracker initialized');

    // Helper: get element XPath
    function getElementXPath(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return '';

        if (element.id) {
            return '//*[@id="' + element.id + '"]';
        }

        const parts = [];
        let current = element;

        while (current && current.nodeType === Node.ELEMENT_NODE) {
            const tagName = current.tagName.toLowerCase();

            if (tagName === 'html' || tagName === 'body') {
                current = current.parentElement;
                continue;
            }

            const siblings = Array.from(current.parentElement?.children || [])
                .filter(child => child.tagName === current.tagName);

            let pathSegment = tagName;
            if (siblings.length > 1) {
                const index = siblings.indexOf(current) + 1;
                pathSegment += '[' + index + ']';
            }

            parts.unshift(pathSegment);
            current = current.parentElement;
        }

        return '//' + parts.join('/');
    }

    // Helper: get element info
    function getElementInfo(element) {
        if (!element) return {};

        return {
            xpath: getElementXPath(element),
            id: element.id || '',
            tagName: element.tagName || '',
            className: element.className || '',
            textContent: (element.textContent || '').slice(0, 100),
            href: element.href || '',
            src: element.src || '',
            name: element.name || '',
            type: element.type || '',
            value: element.value ? element.value.slice(0, 50) : ''
        };
    }

    // Helper: report operation
    function reportOperation(type, element, additionalData) {
        const operation = {
            type: type,
            timestamp: Date.now(),
            url: window.location.href,
            page_title: document.title,
            element: element ? getElementInfo(element) : {},
            data: additionalData || {}
        };

        // Send to content script via window.postMessage
        window.postMessage({
            source: 'agentcrafter-tracker',
            operation: operation
        }, '*');
    }

    // Track clicks
    document.addEventListener('click', function(e) {
        reportOperation('click', e.target, {
            button: e.button,
            ctrlKey: e.ctrlKey,
            shiftKey: e.shiftKey,
            altKey: e.altKey,
            clientX: e.clientX,
            clientY: e.clientY
        });
    }, true);

    // Track input (debounced)
    let inputTimeouts = new Map();
    const INPUT_DEBOUNCE_DELAY = 1500;

    document.addEventListener('input', function(e) {
        const element = e.target;
        const tagName = element.tagName.toLowerCase();

        if (tagName === 'input' || tagName === 'textarea' || element.contentEditable === 'true') {
            if (element.type === 'password' || element.type === 'hidden') {
                return;
            }

            const elementId = element.id || element.name || Math.random().toString(36).substr(2, 9);

            if (inputTimeouts.has(elementId)) {
                clearTimeout(inputTimeouts.get(elementId));
            }

            const timeout = setTimeout(() => {
                if (element.value && element.value.trim() !== '') {
                    reportOperation('input', element, {
                        inputType: e.inputType,
                        actualValue: element.value,
                        valueLength: element.value.length,
                        fieldType: element.type || 'text',
                        isComplete: true
                    });
                }
                inputTimeouts.delete(elementId);
            }, INPUT_DEBOUNCE_DELAY);

            inputTimeouts.set(elementId, timeout);
        }
    }, true);

    // Track text selection
    document.addEventListener('mouseup', function(e) {
        const selection = window.getSelection();
        const selectedText = selection.toString();

        if (selectedText && selectedText.trim().length > 0) {
            const range = selection.getRangeAt(0);
            const element = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                ? range.commonAncestorContainer
                : range.commonAncestorContainer.parentElement;

            reportOperation('select', element, {
                selectedText: selectedText,
                textLength: selectedText.length,
                rangeStart: range.startOffset,
                rangeEnd: range.endOffset,
                singleElement: range.startContainer === range.endContainer
            });
        }
    }, true);

    // Track copy action
    document.addEventListener('copy', function(e) {
        const selection = window.getSelection();
        const copiedText = selection.toString();

        if (copiedText && copiedText.trim().length > 0) {
            const range = selection.getRangeAt(0);
            const element = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                ? range.commonAncestorContainer
                : range.commonAncestorContainer.parentElement;

            reportOperation('copy_action', element, {
                copiedText: copiedText,
                textLength: copiedText.length,
                copyMethod: 'selection',
                singleElement: range.startContainer === range.endContainer
            });
        }
    }, true);

    // Track navigation
    let currentUrl = window.location.href;

    const checkUrlChange = function() {
        if (window.location.href !== currentUrl) {
            reportOperation('navigate', null, {
                fromUrl: currentUrl,
                toUrl: window.location.href
            });
            currentUrl = window.location.href;
        }
    };

    if (window.self === window.top) {
        setInterval(checkUrlChange, 500);

        window.addEventListener('popstate', function() {
            reportOperation('navigate', null, {
                fromUrl: currentUrl,
                toUrl: window.location.href
            });
            currentUrl = window.location.href;
        });
    }

    console.log('✅ Behavior tracker ready');
})();
