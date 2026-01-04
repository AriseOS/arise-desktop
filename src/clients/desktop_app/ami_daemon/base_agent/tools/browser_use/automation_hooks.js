/**
 * Automation Hooks - JavaScript injected during browser automation
 *
 * This script is injected into every page to enable automation capabilities
 * that would otherwise be blocked by browser security restrictions.
 *
 * Features:
 * - Clipboard interception: Capture clipboard writes even when page is not focused
 */
(function() {
    // Prevent multiple initialization
    if (window.__automationHooksInstalled) return;
    window.__automationHooksInstalled = true;

    console.log('[AutomationHooks] Initializing...');

    // ============================================================
    // Clipboard Interception
    // ============================================================
    // Hook navigator.clipboard.writeText to capture clipboard content
    // before the actual write (which may fail if page is not focused)

    if (navigator.clipboard && navigator.clipboard.writeText) {
        const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);

        navigator.clipboard.writeText = async function(text) {
            // Save content BEFORE calling original (in case it fails)
            window.__interceptedClipboard = text;
            window.__interceptedClipboardTime = Date.now();

            console.log('[AutomationHooks] Clipboard write intercepted:',
                text.length, 'chars, preview:', text.substring(0, 50) + '...');

            // Try original write (may fail if not focused, but we already have the content)
            try {
                return await originalWriteText(text);
            } catch (e) {
                console.warn('[AutomationHooks] Original clipboard.writeText failed:', e.message);
                // Return resolved promise to prevent site errors
                return Promise.resolve();
            }
        };
    }

    // Also hook document.execCommand('copy') as fallback method
    if (document.execCommand) {
        const originalExecCommand = document.execCommand.bind(document);

        document.execCommand = function(command, ...args) {
            if (command === 'copy') {
                const selection = window.getSelection();
                if (selection && selection.toString()) {
                    window.__interceptedClipboard = selection.toString();
                    window.__interceptedClipboardTime = Date.now();

                    console.log('[AutomationHooks] execCommand copy intercepted:',
                        window.__interceptedClipboard.length, 'chars');
                }
            }
            return originalExecCommand(command, ...args);
        };
    }

    console.log('[AutomationHooks] Installed successfully');
})();
