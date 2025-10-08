// Recorder content script - captures user operations and sends to backend
(function() {
    console.log('🎬 AgentCrafter Recorder initialized on:', window.location.href);

    let recordingSessionId = null;
    let userToken = null;

    // Listen for messages from popup to start/stop recording
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        console.log('📨 Recorder received message:', request.action);
        if (request.action === 'startRecording') {
            console.log('🎬 Starting recording with session:', request.sessionId);
            startRecording(request.sessionId, request.token);
            sendResponse({ success: true });
        } else if (request.action === 'stopRecording') {
            console.log('⏹️ Stopping recording');
            stopRecording();
            sendResponse({ success: true });
        }
        return true;
    });

    function startRecording(sessionId, token) {
        recordingSessionId = sessionId;
        userToken = token;
        console.log('🎬 Recording started:', sessionId);
        console.log('🔑 Token set:', token ? 'Yes' : 'No');

        // Inject behavior tracking script
        injectTrackingScript();
    }

    function stopRecording() {
        recordingSessionId = null;
        userToken = null;
        console.log('⏹️ Recording stopped');

        // Remove tracking script
        removeTrackingScript();
    }

    function injectTrackingScript() {
        const script = document.createElement('script');
        script.id = 'agentcrafter-tracker';
        script.src = chrome.runtime.getURL('tracking.js');

        script.onload = () => {
            console.log('✅ Tracking script injected and loaded');
        };

        script.onerror = (error) => {
            console.error('❌ Failed to load tracking script:', error);
        };

        (document.head || document.documentElement).appendChild(script);
    }

    function removeTrackingScript() {
        const script = document.getElementById('agentcrafter-tracker');
        if (script) {
            script.remove();
            console.log('🗑️ Tracking script removed');
        }
    }

    // Listen for operations from injected script
    window.addEventListener('message', async function(event) {
        // Only accept messages from same window
        if (event.source !== window) return;

        // Only accept messages from our tracker
        if (!event.data || event.data.source !== 'agentcrafter-tracker') return;

        // Only send if recording
        if (!recordingSessionId || !userToken) {
            console.warn('⚠️ Not recording or no token - ignoring operation');
            return;
        }

        const operation = event.data.operation;
        console.log('📝 Operation captured:', operation.type, 'at', operation.url);

        // Send to background script which will forward to backend
        try {
            const response = await chrome.runtime.sendMessage({
                action: 'sendOperation',
                sessionId: recordingSessionId,
                token: userToken,
                operation: operation
            });

            if (response && response.success) {
                console.log(`✅ Operation sent (total: ${response.operation_count})`);
            } else {
                console.error('❌ Failed to send operation:', response?.error || 'Unknown error');
            }
        } catch (error) {
            console.error('❌ Error sending operation:', error);
        }
    });

    console.log('🎬 Recorder ready');
})();
