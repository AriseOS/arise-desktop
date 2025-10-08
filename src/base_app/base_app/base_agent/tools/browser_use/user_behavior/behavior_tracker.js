/**
 * Simple User Behavior Monitor - JavaScript Client
 * Captures user interactions and sends them to Python via CDP binding
 */
(function() {
    // Prevent multiple initialization
    if (window._simpleUserBehaviorMonitorInitialized) return;
    window._simpleUserBehaviorMonitorInitialized = true;
    
    console.log("🎯 Simple User Behavior Monitor initialized");
    
    // Simplified XPath generation - ID-based only
    function getElementXPath(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) {
            return '';
        }
        
        // First, find ID-based ancestor
        let idBasedRoot = null;
        let currentElement = element;
        
        // Traverse up to find an element with ID
        while (currentElement && currentElement.nodeType === Node.ELEMENT_NODE) {
            if (currentElement.id && currentElement.id.trim() !== '') {
                idBasedRoot = currentElement;
                break;
            }
            currentElement = currentElement.parentElement;
        }
        
        // If we found an ID-based ancestor, build path from ID to target element
        if (idBasedRoot) {
            if (idBasedRoot === element) {
                // The element itself has an ID
                return `//*[@id="${idBasedRoot.id}"]`;
            } else {
                // Build path from ID element down to target element
                const pathFromIdToTarget = [];
                currentElement = element;
                
                // Build path upward until we reach the ID element
                while (currentElement && currentElement !== idBasedRoot) {
                    const currentTagName = currentElement.tagName.toLowerCase();
                    
                    // Skip html/body elements
                    if (currentTagName === 'html' || currentTagName === 'body') {
                        currentElement = currentElement.parentElement;
                        continue;
                    }
                    
                    // Calculate position for this element
                    const position = getElementPositionInOriginalDOM(currentElement);
                    let pathSegment = currentTagName;
                    if (position > 0) {
                        pathSegment += `[${position}]`;
                    }
                    
                    pathFromIdToTarget.unshift(pathSegment);
                    currentElement = currentElement.parentElement;
                }
                
                // Combine ID part with path to target
                const idPart = `//*[@id="${idBasedRoot.id}"]`;
                return pathFromIdToTarget.length > 0 ? `${idPart}/${pathFromIdToTarget.join('/')}` : idPart;
            }
        }
        
        // No ID found - generate complete relative path as fallback
        const parts = [];
        currentElement = element;
        
        while (currentElement && currentElement.nodeType === Node.ELEMENT_NODE) {
            const currentTagName = currentElement.tagName.toLowerCase();
            
            // Skip html/body for relative paths
            if (currentTagName === 'html' || currentTagName === 'body') {
                currentElement = currentElement.parentElement;
                continue;
            }
            
            const position = getElementPositionInOriginalDOM(currentElement);
            let pathSegment = currentTagName;
            if (position > 0) {
                pathSegment += `[${position}]`;
            }
            
            parts.unshift(pathSegment);
            currentElement = currentElement.parentElement;
        }
        
        return '//' + parts.join('/');
    }
    
    // Get position using browser-use logic - returns 0 if only element, otherwise 1-based index
    function getElementPositionInOriginalDOM(element) {
        if (!element.parentElement) {
            return 0;
        }
        
        const parent = element.parentElement;
        const tagName = element.tagName;
        
        // Find all siblings with same tag name
        const sameTagSiblings = Array.from(parent.children).filter(child => 
            child.nodeType === Node.ELEMENT_NODE && child.tagName === tagName
        );
        
        // Return 0 if it's the only element of its type
        if (sameTagSiblings.length <= 1) {
            return 0;
        }
        
        // Return 1-based index
        const index = sameTagSiblings.indexOf(element);
        return index >= 0 ? index + 1 : 0;
    }
    
    // Enhanced element info collector with XPath and ID
    const collector = {
        getElementInfo: function(element) {
            if (!element) return {};
            
            return {
                // Primary identifiers (most important)
                xpath: getElementXPath(element),
                id: element.id || '',
                
                // Secondary information
                tagName: element.tagName || '',
                className: element.className || '',
                textContent: (element.textContent || '').slice(0, 100),
                href: element.href || '',
                src: element.src || '',
                name: element.name || '',
                type: element.type || '',
                value: element.value ? element.value.slice(0, 50) : ''
            };
        },
        
        report: function(type, element, additionalData) {
            const data = {
                type: type,
                timestamp: Date.now(),
                url: window.location.href,
                page_title: document.title,
                element: element ? this.getElementInfo(element) : {},
                data: additionalData || {}
            };
            
            // Send to Python via CDP binding
            if (window.reportUserBehavior) {
                try {
                    window.reportUserBehavior(JSON.stringify(data));
                } catch (e) {
                    console.warn('Failed to report user behavior:', e);
                }
            }
        }
    };
    
    // Smart text selection detection based on drag operations
    let dragInfo = {
        isDown: false,
        isDragging: false,
        startX: 0,
        startY: 0
    };
    
    document.addEventListener('mousedown', function(e) {
        dragInfo.isDown = true;
        dragInfo.isDragging = false;
        dragInfo.startX = e.clientX;
        dragInfo.startY = e.clientY;
    }, true);
    
    document.addEventListener('mousemove', function(e) {
        if (dragInfo.isDown) {
            const distance = Math.sqrt(
                Math.pow(e.clientX - dragInfo.startX, 2) + 
                Math.pow(e.clientY - dragInfo.startY, 2)
            );
            
            if (distance > 5) {
                dragInfo.isDragging = true;
            }
        }
    }, true);
    
    document.addEventListener('mouseup', function(e) {
        if (dragInfo.isDragging) {
            setTimeout(() => {
                const selection = window.getSelection();
                if (selection.rangeCount > 0 && selection.toString().trim().length > 0) {
                    const range = selection.getRangeAt(0);
                    let targetElement;
                    
                    if (range.startContainer === range.endContainer) {
                        targetElement = range.startContainer.nodeType === Node.TEXT_NODE 
                            ? range.startContainer.parentElement 
                            : range.startContainer;
                    } else {
                        const containerElement = range.commonAncestorContainer;
                        targetElement = containerElement.nodeType === Node.TEXT_NODE 
                            ? containerElement.parentElement 
                            : containerElement;
                    }
                    
                    collector.report('select', targetElement, {
                        selectedText: selection.toString().slice(0, 200),
                        textLength: selection.toString().length,
                        rangeStart: range.startOffset,
                        rangeEnd: range.endOffset,
                        singleElement: range.startContainer === range.endContainer
                    });
                }
            }, 10);
        }
        
        dragInfo.isDown = false;
        dragInfo.isDragging = false;
    }, true);
    
    // Monitor user clicks
    document.addEventListener('click', function(e) {
        // Skip clicks that happen during or immediately after drag operations
        if (dragInfo.isDragging) {
            return;
        }
        
        collector.report('click', e.target, {
            button: e.button,
            ctrlKey: e.ctrlKey,
            shiftKey: e.shiftKey,
            altKey: e.altKey,
            clientX: e.clientX,
            clientY: e.clientY
        });
    }, true);
    
    // Smart input monitoring: debounced + sensitive field filtering
    let inputTimeouts = new Map();
    const INPUT_DEBOUNCE_DELAY = 1500; // 1.5 seconds after input stops
    
    document.addEventListener('input', function(e) {
        const element = e.target;
        const tagName = element.tagName.toLowerCase();
        
        // Only track inputs in actual input fields
        if (tagName === 'input' || tagName === 'textarea' || element.contentEditable === 'true') {
            // Skip sensitive fields for security
            if (element.type === 'password' || element.type === 'hidden') {
                return;
            }
            
            // Create unique identifier for the element
            const elementId = element.id || element.name || element.tagName + '_' + Math.random().toString(36).substr(2, 9);
            
            // Clear previous timeout for this element
            if (inputTimeouts.has(elementId)) {
                clearTimeout(inputTimeouts.get(elementId));
            }
            
            // Set new debounce timeout
            const timeout = setTimeout(() => {
                // Only report if there's actual content
                if (element.value && element.value.trim() !== '') {
                    collector.report('input', element, {
                        inputType: e.inputType,
                        actualValue: element.value,  // Complete input content
                        valueLength: element.value.length,
                        fieldType: element.type || 'text',
                        isComplete: true  // Mark as debounced complete input
                    });
                }
                inputTimeouts.delete(elementId);
            }, INPUT_DEBOUNCE_DELAY);
            
            inputTimeouts.set(elementId, timeout);
        }
    }, true);
    
    // Note: Removed old selectionchange-based monitoring
    // Now using drag-based selection detection for more precise control
    
    // Monitor copy events
    document.addEventListener('copy', function(e) {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            let targetElement;
            
            // Smart element detection: check if selection is within a single element
            if (range.startContainer === range.endContainer) {
                // Selection is within a single node (text node or element)
                targetElement = range.startContainer.nodeType === Node.TEXT_NODE 
                    ? range.startContainer.parentElement 
                    : range.startContainer;
            } else {
                // Selection spans multiple nodes, use common ancestor
                const containerElement = range.commonAncestorContainer;
                targetElement = containerElement.nodeType === Node.TEXT_NODE 
                    ? containerElement.parentElement 
                    : containerElement;
            }
                
            collector.report('copy_action', targetElement, {
                copiedText: selection.toString().slice(0, 200),
                textLength: selection.toString().length,
                copyMethod: 'selection',
                singleElement: range.startContainer === range.endContainer  // Add flag to indicate precision level
            });
        }
    });
    
    
    // Monitor page navigation (URL changes) - enhanced version
    let currentUrl = window.location.href;
    
    // Note: We don't report initial page load as navigation anymore
    // because CDP events already capture real navigation events.
    // Script initialization reporting would create duplicate records.
    
    // Only set up URL monitoring in main frame (not iframes)
    if (window.self === window.top) {
        const checkUrlChange = function() {
            if (window.location.href !== currentUrl) {
                collector.report('navigate', null, {
                    fromUrl: currentUrl,
                    toUrl: window.location.href,
                    navigation_source: 'url_polling',  // This is URL polling detection
                    is_main_frame: true
                });
                currentUrl = window.location.href;
            }
        };
        
        // Check URL changes every 500ms (for SPA navigation)
        setInterval(checkUrlChange, 500);
        
        // Also monitor popstate events (browser back/forward)
        window.addEventListener('popstate', function(event) {
            collector.report('navigate', null, {
                fromUrl: currentUrl,
                toUrl: window.location.href,
                navigation_source: 'popstate',  // This is browser back/forward
                is_main_frame: true
            });
            currentUrl = window.location.href;
        });
    }
    
    // Monitor scrolling (throttled to avoid spam)
    let scrollTimeout;
    let lastScrollY = window.scrollY;
    
    window.addEventListener('scroll', function() {
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(function() {
            const currentScrollY = window.scrollY;
            const scrollDirection = currentScrollY > lastScrollY ? 'down' : 'up';
            const scrollDelta = Math.abs(currentScrollY - lastScrollY);
            const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
            const scrollPercentage = maxScroll > 0 ? Math.round((currentScrollY / maxScroll) * 100) : 0;
            
            // Only report scrolls greater than 50px to reduce noise
            if (scrollDelta > 50) {
                collector.report('scroll', null, {
                    scrollDirection: scrollDirection,
                    scrollDelta: scrollDelta,
                    scrollPercentage: scrollPercentage
                });
                lastScrollY = currentScrollY;
            }
        }, 100); // 100ms throttle
    });
    
    
    
})();