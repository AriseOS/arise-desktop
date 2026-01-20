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
    
    // Enhanced element info collector with XPath and ID - only non-empty fields
    const collector = {
        getElementInfo: function(element) {
            if (!element) return {};

            // Only include non-empty meaningful fields
            const info = {};

            // Core positioning fields (always include if present)
            const xpath = getElementXPath(element);
            if (xpath) info.xpath = xpath;

            if (element.tagName) info.tagName = element.tagName;
            if (element.id) info.id = element.id;
            if (element.className) info.className = element.className;

            // Semantic information (only if non-empty)
            const text = (element.textContent || '').trim();
            if (text) info.textContent = text.slice(0, 100);

            // Link-related (only if present)
            if (element.href) info.href = element.href;
            if (element.src) info.src = element.src;

            // Form-related (only for input/select/textarea)
            if (element.name) info.name = element.name;
            if (element.type) info.type = element.type;
            if (element.value) info.value = element.value.slice(0, 50);

            return info;
        },
        
        report: function(type, element, additionalData) {
            // Generate human-readable timestamp
            const now = new Date();
            const timestamp = now.toISOString().slice(0, 19).replace('T', ' '); // "2025-10-10 17:52:57"

            const data = {
                type: type,
                timestamp: timestamp,
                url: window.location.href,
                page_title: document.title,
                element: element ? this.getElementInfo(element) : {},
                data: additionalData || {}
            };

            // Auto-detect environment and use appropriate communication method
            if (window.reportUserBehavior) {
                // Browser-use environment: Use CDP binding
                try {
                    window.reportUserBehavior(JSON.stringify(data));
                } catch (e) {
                    console.warn('Failed to report user behavior via CDP:', e);
                }
            } else {
                // Chrome Extension environment: Use window.postMessage
                window.postMessage({
                    source: 'ami-tracker',
                    operation: data
                }, '*');
            }
        }
    };

    // DataLoadDetector - Detects data loading events
    class DataLoadDetector {
        constructor() {
            this.lastBodyHeight = document.body.scrollHeight;
            this.heightChangeThreshold = 50; // 50px minimum height change (lowered from 100px)

            console.log('🔍 DataLoadDetector: Initial height =', this.lastBodyHeight, 'px');
            this.setupMutationObserver();
        }

        setupMutationObserver() {
            const observer = new MutationObserver((mutations) => {
                let addedElements = [];

                mutations.forEach(mutation => {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(node => {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                addedElements.push(node);
                            }
                        });
                    }
                });

                if (addedElements.length > 0) {
                    this.handleDOMChange(addedElements);
                }
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            console.log('📡 MutationObserver initialized for data load detection');
        }

        handleDOMChange(addedElements) {
            const currentHeight = document.body.scrollHeight;
            const heightChange = currentHeight - this.lastBodyHeight;

            console.log('🔍 DOM Changed:', {
                addedCount: addedElements.length,
                heightBefore: this.lastBodyHeight,
                heightAfter: currentHeight,
                heightChange: heightChange,
                threshold: this.heightChangeThreshold
            });

            // Condition: DOM change AND height increase
            if (addedElements.length > 0 && heightChange > this.heightChangeThreshold) {
                console.log('✅ Dataload triggered!');
                this.recordDataLoad(addedElements, heightChange, currentHeight);
                this.lastBodyHeight = currentHeight;
            } else {
                console.log('❌ Dataload NOT triggered:', {
                    reason: heightChange <= this.heightChangeThreshold ?
                        `Height change (${heightChange}px) <= threshold (${this.heightChangeThreshold}px)` :
                        'No elements added'
                });
            }
        }

        recordDataLoad(addedElements, heightChange, currentHeight) {
            // Analyze added elements
            const dataElements = addedElements.filter(el => this.isDataElement(el));

            // Sample elements (max 3)
            const sampleElements = addedElements.slice(0, 3).map(el => ({
                tagName: el.tagName,
                className: el.className || '',
                xpath: getElementXPath(el)
            }));

            // Report dataload operation
            collector.report('dataload', null, {
                added_elements_count: addedElements.length,
                data_elements_count: dataElements.length,
                height_before: this.lastBodyHeight,
                height_after: currentHeight,
                height_change: heightChange,
                sample_elements: sampleElements
            });
        }

        isDataElement(element) {
            const tag = element.tagName.toLowerCase();
            const classes = (element.className || '').toLowerCase();

            // Typical data container tags
            if (['article', 'li', 'tr'].includes(tag)) {
                return true;
            }

            // Typical data container class patterns
            const dataPatterns = ['item', 'card', 'post', 'product', 'entry', 'tile'];
            if (dataPatterns.some(pattern => classes.includes(pattern))) {
                return true;
            }

            return false;
        }
    }

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
                        textLength: selection.toString().length
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

        // For click: no additional data needed (element info is enough)
        collector.report('click', e.target, {});
    }, true);

    // Monitor right-click (context menu)
    document.addEventListener('contextmenu', function(e) {
        collector.report('contextmenu', e.target, {
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
    
    // Monitor copy events (user-initiated Ctrl+C or right-click copy)
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
                copyMethod: 'user_selection'  // User manually selected and copied
            });
        }
    });

    // Hook Clipboard API to capture programmatic clipboard writes
    // This captures when websites use navigator.clipboard.writeText() (e.g., "Copy Email" buttons)
    if (navigator.clipboard && navigator.clipboard.writeText) {
        const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
        
        navigator.clipboard.writeText = async function(text) {
            // Call original function first
            const result = await originalWriteText(text);
            
            // Report the clipboard write
            // Use document.activeElement or last clicked element as context
            const targetElement = document.activeElement || document.body;
            
            collector.report('clipboard_write', targetElement, {
                copiedText: text.slice(0, 200),
                textLength: text.length,
                copyMethod: 'api_call'  // Programmatically written via clipboard API
            });
            
            return result;
        };
    }

    // Monitor paste events (when user pastes content)
    document.addEventListener('paste', function(e) {
        const targetElement = e.target;
        
        // Read clipboard content
        const clipboardData = e.clipboardData || window.clipboardData;
        const pastedText = clipboardData ? clipboardData.getData('text') : '';
        
        collector.report('paste_action', targetElement, {
            pastedText: pastedText.slice(0, 200),
            textLength: pastedText.length,
            inputType: targetElement.tagName,
            inputName: targetElement.name || '',
            inputId: targetElement.id || ''
        });
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

            // Only report scrolls greater than 50px to reduce noise
            if (scrollDelta > 50) {
                collector.report('scroll', null, {
                    direction: scrollDirection,
                    distance: scrollDelta
                });
                lastScrollY = currentScrollY;
            }
        }, 100); // 100ms throttle
    });

    // Hover detection with DOM change monitoring
    // Only reports hover when it triggers visible DOM changes (dropdowns, tooltips, etc.)
    const hoverState = {
        element: null,
        startTime: null,
        domChanged: false,
        mutationCount: 0
    };

    // MutationObserver to detect DOM changes during hover
    const hoverMutationObserver = new MutationObserver((mutations) => {
        if (hoverState.element) {
            // Count meaningful mutations (not just text changes in unrelated elements)
            let meaningfulMutations = 0;
            mutations.forEach(mutation => {
                // Attribute changes (display, class, style) are most relevant for hover effects
                if (mutation.type === 'attributes') {
                    const attrName = mutation.attributeName;
                    if (['style', 'class', 'hidden', 'aria-expanded', 'aria-hidden'].includes(attrName)) {
                        meaningfulMutations++;
                    }
                }
                // New elements added (dropdowns, tooltips)
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    meaningfulMutations += mutation.addedNodes.length;
                }
            });

            if (meaningfulMutations > 0) {
                hoverState.domChanged = true;
                hoverState.mutationCount += meaningfulMutations;
            }
        }
    });

    // Start observing DOM for hover-related changes
    function startHoverObserver() {
        if (!document.body) {
            setTimeout(startHoverObserver, 100);
            return;
        }
        hoverMutationObserver.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class', 'hidden', 'aria-expanded', 'aria-hidden']
        });
        console.log('👆 Hover mutation observer initialized');
    }

    // Minimum hover duration to be considered intentional (ms)
    const MIN_HOVER_DURATION = 200;

    document.addEventListener('mouseenter', function(e) {
        // Reset hover state for new element
        hoverState.element = e.target;
        hoverState.startTime = Date.now();
        hoverState.domChanged = false;
        hoverState.mutationCount = 0;
    }, true);

    document.addEventListener('mouseleave', function(e) {
        if (hoverState.element === e.target && hoverState.startTime) {
            const duration = Date.now() - hoverState.startTime;

            // TEMPORARILY DISABLED: hover events are causing confusion in workflow generation
            // because click → hover → navigate pattern breaks the "click followed by navigate" rule
            // TODO: Re-enable when workflow generation can handle hover events properly
            /*
            // Only report if:
            // 1. DOM changed during hover (triggered dropdown, tooltip, etc.)
            // 2. Hover lasted at least MIN_HOVER_DURATION ms
            if (hoverState.domChanged && duration >= MIN_HOVER_DURATION) {
                collector.report('hover', e.target, {
                    duration_ms: duration,
                    triggered_dom_change: true,
                    mutation_count: hoverState.mutationCount
                });
            }
            */

            // Reset state
            hoverState.element = null;
            hoverState.startTime = null;
            hoverState.domChanged = false;
            hoverState.mutationCount = 0;
        }
    }, true);

    // Initialize hover observer when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startHoverObserver);
    } else {
        startHoverObserver();
    }

    // Initialize DataLoadDetector after DOM is ready
    let detector;

    function initializeDataLoadDetector() {
        if (!document.body) {
            console.warn("⏳ DataLoadDetector: document.body not ready, waiting...");
            setTimeout(initializeDataLoadDetector, 100);
            return;
        }

        try {
            detector = new DataLoadDetector();
            console.log("🔍 DataLoadDetector initialized");
        } catch (e) {
            console.warn("Failed to initialize DataLoadDetector:", e);
        }
    }

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeDataLoadDetector);
    } else {
        // DOM is already loaded
        initializeDataLoadDetector();
    }

})();