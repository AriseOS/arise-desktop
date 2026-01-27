"""
BehaviorRecorder - User behavior recording for HybridBrowserSession.

This module provides user behavior recording capabilities that can be plugged into
HybridBrowserSession. It captures user interactions (clicks, inputs, navigation, etc.)
via CDP bindings and JavaScript injection.

Ported from browser_use/user_behavior/monitor.py to work with HybridBrowserSession.
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)


class BehaviorRecorder:
    """User behavior recorder for HybridBrowserSession.

    This class captures user interactions in the browser and stores them as operations.
    It can be optionally enabled on HybridBrowserSession for recording mode.

    Key features:
    - CDP binding for JavaScript -> Python communication
    - Multi-tab support (auto-setup for new tabs)
    - DOM snapshot capture
    - Operation deduplication
    """

    def __init__(self, enable_dom_capture: bool = True):
        """Initialize behavior recorder.

        Args:
            enable_dom_capture: Whether to capture DOM snapshots on navigation.
        """
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._is_recording = False
        self._enable_dom_capture = enable_dom_capture

        # Operation storage
        self.operation_list: List[Dict[str, Any]] = []
        self.dom_snapshots: Dict[str, Dict] = {}  # URL -> DOM snapshot

        # Tab tracking
        self._monitored_tabs: Set[str] = set()  # Set of tab_ids being monitored

        # Navigation deduplication
        self._last_nav_url: Optional[str] = None
        self._last_nav_time: Optional[datetime] = None
        self._nav_dedup_window_seconds = 2

        # Reference to browser session (set during start_recording)
        self._browser_session: Optional[Any] = None

        # Callback for operation events (optional)
        self._operation_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_operation_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback to be called when new operation is recorded.

        Args:
            callback: Function that receives operation dict.
        """
        self._operation_callback = callback

    async def start_recording(self, browser_session: Any) -> None:
        """Start recording user behavior.

        Args:
            browser_session: HybridBrowserSession instance.
        """
        if self._is_recording:
            logger.warning("Recording already in progress")
            return

        self._browser_session = browser_session
        self._is_recording = True
        self.operation_list.clear()
        self.dom_snapshots.clear()
        self._monitored_tabs.clear()

        logger.info(f"🎯 Starting behavior recording - Session: {self.session_id}")

        # Setup recording for all existing tabs
        await self._setup_all_tabs()

        # Hook into tab creation for auto-setup
        self._hook_new_tab_creation()

    async def stop_recording(self) -> Dict[str, Any]:
        """Stop recording and return results.

        Returns:
            Dict with operations and dom_snapshots.
        """
        if not self._is_recording:
            logger.warning("No recording in progress")
            return {"operations": [], "dom_snapshots": {}}

        self._is_recording = False
        logger.info(f"🛑 Stopping behavior recording - {len(self.operation_list)} operations captured")

        result = {
            "session_id": self.session_id,
            "operations": self.operation_list.copy(),
            "operations_count": len(self.operation_list),
            "dom_snapshots": self.dom_snapshots.copy(),
        }

        # Cleanup
        self._monitored_tabs.clear()
        self._browser_session = None

        return result

    def get_operations(self) -> List[Dict[str, Any]]:
        """Get current list of recorded operations.

        Returns:
            List of operation dicts.
        """
        return self.operation_list.copy()

    def get_operations_count(self) -> int:
        """Get count of recorded operations.

        Returns:
            Number of operations.
        """
        return len(self.operation_list)

    def is_recording(self) -> bool:
        """Check if recording is active.

        Returns:
            True if recording is in progress.
        """
        return self._is_recording

    # ------------------------------------------------------------------
    # Internal: Tab setup
    # ------------------------------------------------------------------

    async def _setup_all_tabs(self) -> None:
        """Setup recording for all existing tabs."""
        if not self._browser_session:
            return

        # Get all tabs from HybridBrowserSession
        pages = self._browser_session._pages

        for tab_id, page in pages.items():
            if tab_id not in self._monitored_tabs:
                await self._setup_for_tab(tab_id, page)

    async def _setup_for_tab(self, tab_id: str, page: "Page") -> None:
        """Setup recording for a specific tab.

        Args:
            tab_id: Tab identifier.
            page: Playwright Page instance.
        """
        if tab_id in self._monitored_tabs:
            logger.debug(f"Tab {tab_id} already monitored, skipping")
            return

        if page.is_closed():
            logger.debug(f"Tab {tab_id} is closed, skipping")
            return

        try:
            logger.debug(f"Setting up recording for tab {tab_id}...")

            # 1. Create CDP session
            cdp_session = await page.context.new_cdp_session(page)

            # 2. Enable necessary domains
            await cdp_session.send("Runtime.enable")
            await cdp_session.send("Page.enable")

            # 3. Add binding for JavaScript -> Python communication
            await cdp_session.send("Runtime.addBinding", {"name": "reportUserBehavior"})

            # 4. Register binding event handler
            cdp_session.on("Runtime.bindingCalled", lambda event: self._handle_binding_event(event, tab_id))

            # 5. Setup navigation listener for DOM capture
            cdp_session.on("Page.frameNavigated", lambda event: self._handle_navigation(event, tab_id))

            # 6. Inject tracking script
            script = self._get_tracker_script()
            await cdp_session.send("Page.addScriptToEvaluateOnNewDocument", {
                "source": script,
                "runImmediately": True,
            })

            # 7. Also inject immediately for current page
            try:
                await page.evaluate(script)
            except Exception as e:
                logger.debug(f"Could not inject script immediately (page may be navigating): {e}")

            self._monitored_tabs.add(tab_id)
            logger.info(f"✅ Recording setup complete for tab {tab_id}")

        except Exception as e:
            logger.error(f"Failed to setup recording for tab {tab_id}: {e}")

    def _hook_new_tab_creation(self) -> None:
        """Hook into new tab creation for auto-setup.

        This modifies HybridBrowserSession's tab registration to also setup recording.
        """
        if not self._browser_session:
            return

        # Store original method
        original_register = self._browser_session._register_new_page

        async def recording_aware_register(tab_id: str, page: "Page") -> None:
            """Enhanced register that also sets up recording."""
            # Call original
            await original_register(tab_id, page)

            # Setup recording for new tab
            if self._is_recording and tab_id not in self._monitored_tabs:
                # Small delay to let page initialize
                await asyncio.sleep(0.3)
                await self._setup_for_tab(tab_id, page)

        # Replace method
        self._browser_session._register_new_page = recording_aware_register
        logger.debug("Hooked into tab registration for auto-recording setup")

    # ------------------------------------------------------------------
    # Internal: Event handling
    # ------------------------------------------------------------------

    def _handle_binding_event(self, event: Dict[str, Any], tab_id: str) -> None:
        """Handle CDP binding event from JavaScript.

        Args:
            event: CDP event data.
            tab_id: Source tab identifier.
        """
        if event.get("name") != "reportUserBehavior":
            return

        payload = event.get("payload", "")

        # Schedule async processing
        asyncio.create_task(self._process_behavior_data(payload, tab_id))

    async def _process_behavior_data(self, payload: str, tab_id: str) -> None:
        """Process behavior data from JavaScript.

        Args:
            payload: JSON string of operation data.
            tab_id: Source tab identifier.
        """
        try:
            data = json.loads(payload)

            # Validate required fields
            if "type" not in data or "timestamp" not in data:
                logger.warning(f"Invalid behavior data: missing required fields")
                return

            # Navigation deduplication
            if data["type"] == "navigate":
                nav_url = data.get("url") or data.get("data", {}).get("toUrl", "")
                now = datetime.now()

                if self._last_nav_url and self._last_nav_time:
                    time_diff = (now - self._last_nav_time).total_seconds()
                    if nav_url == self._last_nav_url and time_diff < self._nav_dedup_window_seconds:
                        logger.debug(f"Duplicate navigate event filtered: {nav_url}")
                        return

                self._last_nav_url = nav_url
                self._last_nav_time = now

            # Add tab_id to data
            data["tab_id"] = tab_id

            # Store operation
            self.operation_list.append(data)

            # Log operation
            self._log_operation(data)

            # Call callback if set
            if self._operation_callback:
                try:
                    self._operation_callback(data)
                except Exception as e:
                    logger.warning(f"Operation callback failed: {e}")

            # Trigger DOM capture for navigation events
            if self._enable_dom_capture and data["type"] == "navigate":
                url = data.get("url", "")
                if url and url not in ["about:blank", "chrome://newtab/"]:
                    asyncio.create_task(self._capture_dom_snapshot(url, tab_id))

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse behavior data: {e}")
        except Exception as e:
            logger.error(f"Error processing behavior data: {e}")

    def _handle_navigation(self, event: Dict[str, Any], tab_id: str) -> None:
        """Handle CDP navigation event.

        Args:
            event: CDP Page.frameNavigated event.
            tab_id: Source tab identifier.
        """
        frame = event.get("frame", {})
        url = frame.get("url", "")
        parent_id = frame.get("parentId")

        # Only handle main frame navigation
        if parent_id is not None:
            return

        # Skip system pages
        if url in ["about:blank", "chrome://newtab/", "chrome://new-tab-page/"]:
            return

        logger.debug(f"Navigation detected in tab {tab_id}: {url}")

        # Create navigation operation
        nav_data = {
            "type": "navigate",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "page_title": "Navigated Page",
            "element": {},
            "data": {
                "navigation_type": "main_frame",
                "source": "cdp_event",
            },
            "tab_id": tab_id,
        }

        # Deduplicate
        now = datetime.now()
        if self._last_nav_url and self._last_nav_time:
            time_diff = (now - self._last_nav_time).total_seconds()
            if url == self._last_nav_url and time_diff < self._nav_dedup_window_seconds:
                return

        self._last_nav_url = url
        self._last_nav_time = now

        self.operation_list.append(nav_data)
        self._log_operation(nav_data)

        # Trigger DOM capture
        if self._enable_dom_capture and url not in self.dom_snapshots:
            asyncio.create_task(self._capture_dom_snapshot(url, tab_id))

    # ------------------------------------------------------------------
    # Internal: DOM snapshot
    # ------------------------------------------------------------------

    async def _capture_dom_snapshot(self, url: str, tab_id: str) -> None:
        """Capture DOM snapshot for a URL.

        Args:
            url: Page URL.
            tab_id: Tab identifier.
        """
        if not self._browser_session or not self._enable_dom_capture:
            return

        if url in self.dom_snapshots:
            logger.debug(f"DOM already captured for: {url}")
            return

        try:
            # Wait for page to load
            await asyncio.sleep(1.0)

            # Get page from session
            page = self._browser_session._pages.get(tab_id)
            if not page or page.is_closed():
                return

            # Use HybridBrowserSession's snapshot if available
            if self._browser_session.snapshot and self._browser_session._current_tab_id == tab_id:
                snapshot_result = await self._browser_session.snapshot.get_full_result()
                if snapshot_result:
                    self.dom_snapshots[url] = {
                        "snapshot_text": snapshot_result.get("snapshotText", ""),
                        "elements": snapshot_result.get("elements", {}),
                        "captured_at": datetime.now().isoformat(),
                    }
                    logger.info(f"📸 DOM snapshot captured for: {url[:60]}...")
                    return

            # Fallback: simple DOM extraction
            dom_content = await page.evaluate("""
                () => {
                    return {
                        title: document.title,
                        url: window.location.href,
                        body_text: document.body ? document.body.innerText.slice(0, 5000) : '',
                    };
                }
            """)

            self.dom_snapshots[url] = {
                "simple": dom_content,
                "captured_at": datetime.now().isoformat(),
            }
            logger.info(f"📸 Simple DOM snapshot captured for: {url[:60]}...")

        except Exception as e:
            logger.warning(f"Failed to capture DOM snapshot for {url}: {e}")

    # ------------------------------------------------------------------
    # Internal: Logging
    # ------------------------------------------------------------------

    def _log_operation(self, data: Dict[str, Any]) -> None:
        """Log operation to console.

        Args:
            data: Operation data dict.
        """
        op_type = data.get("type", "unknown").upper()
        url = data.get("url", "")
        element = data.get("element", {})

        # Format timestamp
        ts = data.get("timestamp", "")
        if isinstance(ts, str) and " " in ts:
            time_str = ts.split(" ")[-1]  # Get time part
        else:
            time_str = datetime.now().strftime("%H:%M:%S")

        # Build log message
        parts = [f"[{time_str}] 🔥 {op_type}"]

        if element.get("textContent"):
            text = element["textContent"][:50]
            parts.append(f"  Text: {text}")

        if data.get("data", {}).get("actualValue"):
            value = data["data"]["actualValue"][:30]
            parts.append(f"  Input: {value}")

        if url:
            try:
                from urllib.parse import urlparse
                hostname = urlparse(url).hostname or url
                parts.append(f"  URL: {hostname}")
            except:
                parts.append(f"  URL: {url[:50]}")

        print("\n".join(parts))
        print("-" * 50)

    # ------------------------------------------------------------------
    # Internal: JavaScript tracker script
    # ------------------------------------------------------------------

    def _get_tracker_script(self) -> str:
        """Get JavaScript tracking script.

        Returns:
            JavaScript code string.
        """
        # Try to load from file first
        script_path = Path(__file__).parent / "scripts" / "behavior_tracker.js"
        if script_path.exists():
            try:
                return script_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not load behavior_tracker.js: {e}")

        # Fallback to bundled script from browser_use
        browser_use_script = (
            Path(__file__).parent.parent / "browser_use" / "user_behavior" / "behavior_tracker.js"
        )
        if browser_use_script.exists():
            try:
                return browser_use_script.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not load browser_use behavior_tracker.js: {e}")

        # Minimal fallback script
        logger.warning("Using minimal fallback tracker script")
        return '''
        (function() {
            if (window._behaviorRecorderInitialized) return;
            window._behaviorRecorderInitialized = true;
            console.log("🎯 Behavior Recorder (fallback) initialized");

            const report = (type, element, data) => {
                if (window.reportUserBehavior) {
                    const payload = {
                        type,
                        timestamp: new Date().toISOString().slice(0, 19).replace('T', ' '),
                        url: location.href,
                        page_title: document.title,
                        element: element ? {
                            tagName: element.tagName,
                            id: element.id || undefined,
                            className: element.className || undefined,
                            textContent: (element.textContent || '').slice(0, 100) || undefined,
                        } : {},
                        data: data || {}
                    };
                    window.reportUserBehavior(JSON.stringify(payload));
                }
            };

            // Click events
            document.addEventListener('click', e => report('click', e.target, {
                clientX: e.clientX,
                clientY: e.clientY
            }), true);

            // Input events (debounced)
            let inputTimeout;
            document.addEventListener('input', e => {
                const el = e.target;
                if (el.type === 'password') return;
                clearTimeout(inputTimeout);
                inputTimeout = setTimeout(() => {
                    if (el.value) {
                        report('input', el, {
                            actualValue: el.value,
                            valueLength: el.value.length
                        });
                    }
                }, 1500);
            }, true);

            // Navigation (URL polling for SPA)
            let currentUrl = location.href;
            setInterval(() => {
                if (location.href !== currentUrl) {
                    report('navigate', null, {
                        fromUrl: currentUrl,
                        toUrl: location.href
                    });
                    currentUrl = location.href;
                }
            }, 500);
        })();
        '''
