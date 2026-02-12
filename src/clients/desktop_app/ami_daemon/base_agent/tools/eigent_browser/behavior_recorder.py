"""
BehaviorRecorder - User behavior recording using ref-based element identification.

Records user actions in the same format as ActionExecutor expects:
  - click: {"type": "click", "ref": "e42", "text": "Submit", "role": "button"}
  - type: {"type": "type", "ref": "e15", "text": "hello", "role": "textbox", "value": "..."}
  - navigate: {"type": "navigate", "url": "https://..."}
  - scroll: {"type": "scroll", "direction": "down", "amount": 300}
  - dataload: {"type": "dataload", "request_url": "https://api.example.com/data"}
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

from src.common.timestamp_utils import get_current_timestamp

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)


class BehaviorRecorder:
    """Records user behavior using the ref-based element system.

    This recorder captures user interactions and stores them in a format
    compatible with ActionExecutor, making recorded operations directly
    replayable.
    """

    def __init__(self, enable_snapshot_capture: bool = True):
        """Initialize behavior recorder.

        Args:
            enable_snapshot_capture: Whether to capture page snapshots on navigation.
        """
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._is_recording = False
        self._enable_snapshot_capture = enable_snapshot_capture

        # Operation storage
        self.operations: List[Dict[str, Any]] = []
        self.snapshots: Dict[str, Dict[str, Any]] = {}  # URL hash -> snapshot

        # Tab tracking
        self._monitored_tabs: Set[str] = set()
        self._tab_pages: Dict[str, Any] = {}
        self._context_page_handler: Optional[Callable[[Any], None]] = None
        self._fallback_tab_counter: int = 0
        self._original_register_new_page: Optional[Callable[..., Any]] = None

        # Navigation deduplication
        self._last_nav_url: Optional[str] = None
        self._last_nav_time: Optional[datetime] = None
        self._nav_dedup_seconds = 2

        # Browser session reference
        self._browser_session: Optional[Any] = None

        # Optional callback for real-time operation events
        self._operation_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # Dataload detection - only track after scroll events
        self._recent_dataload_urls: Set[str] = set()
        self._dataload_cleanup_task: Optional[asyncio.Task] = None
        self._last_scroll_time: Optional[datetime] = None
        self._dataload_window_seconds = 3  # Only record dataload within 3s after scroll

        # Background task tracking for proper cleanup
        self._background_tasks: Set[asyncio.Task] = set()

    def set_operation_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback for real-time operation events."""
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
        self.operations.clear()
        self.snapshots.clear()
        self._monitored_tabs.clear()
        self._tab_pages.clear()
        self._fallback_tab_counter = 0

        logger.info(f"🎯 Starting behavior recording - Session: {self.session_id}")

        # Setup recording for all existing tabs
        await self._setup_all_tabs()

        # Hook into tab creation
        self._hook_new_tab_creation()
        self._hook_context_page_creation()

        # Start dataload URL cleanup task
        self._dataload_cleanup_task = asyncio.create_task(self._cleanup_dataload_urls())

    async def stop_recording(self) -> Dict[str, Any]:
        """Stop recording and return results.

        Returns:
            Dict with operations and snapshots.
        """
        if not self._is_recording:
            logger.warning("No recording in progress")
            return {"operations": [], "snapshots": {}}

        self._is_recording = False
        logger.info(f"🛑 Stopping recording - {len(self.operations)} operations")

        result = {
            "session_id": self.session_id,
            "operations": self.operations.copy(),
            "operations_count": len(self.operations),
            "snapshots": self.snapshots.copy(),
        }

        # Restore browser session hooks
        if self._browser_session and self._original_register_new_page:
            try:
                self._browser_session._register_new_page = self._original_register_new_page
            except Exception as e:
                logger.debug(f"Failed to restore _register_new_page hook: {e}")
        self._original_register_new_page = None

        # Remove context page listener
        if (
            self._browser_session
            and self._context_page_handler
            and getattr(self._browser_session, "_context", None)
        ):
            try:
                self._browser_session._context.remove_listener(
                    "page",
                    self._context_page_handler,
                )
            except Exception as e:
                logger.debug(f"Failed to remove context page listener: {e}")
        self._context_page_handler = None

        # Cleanup
        self._monitored_tabs.clear()
        self._tab_pages.clear()
        self._browser_session = None
        self._recent_dataload_urls.clear()

        # Cancel cleanup task
        if self._dataload_cleanup_task:
            self._dataload_cleanup_task.cancel()
            try:
                await self._dataload_cleanup_task
            except asyncio.CancelledError:
                pass
            self._dataload_cleanup_task = None

        # Cancel all background tasks
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        return result

    def get_operations(self) -> List[Dict[str, Any]]:
        """Get current list of recorded operations."""
        return self.operations.copy()

    def get_operations_count(self) -> int:
        """Get count of recorded operations."""
        return len(self.operations)

    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._is_recording

    # ------------------------------------------------------------------
    # Tab Setup
    # ------------------------------------------------------------------

    async def _setup_all_tabs(self) -> None:
        """Setup recording for all existing tabs."""
        if not self._browser_session:
            return

        pages = self._browser_session._pages
        for tab_id, page in pages.items():
            if tab_id not in self._monitored_tabs:
                await self._setup_for_tab(tab_id, page)

    async def _setup_for_tab(self, tab_id: str, page: "Page") -> None:
        """Setup recording for a specific tab."""
        if tab_id in self._monitored_tabs:
            return

        # Avoid duplicate setup when multiple hooks observe the same page.
        for existing_page in self._tab_pages.values():
            if existing_page is page:
                return

        if page.is_closed():
            logger.debug(f"Tab {tab_id} is closed, skipping")
            return

        try:
            logger.debug(f"Setting up recording for tab {tab_id}...")

            # Create CDP session
            cdp_session = await page.context.new_cdp_session(page)

            # Enable required domains
            await cdp_session.send("Runtime.enable")
            await cdp_session.send("Page.enable")

            # Add binding for JS -> Python communication
            await cdp_session.send(
                "Runtime.addBinding", {"name": "reportUserBehavior"}
            )

            # Register event handlers
            cdp_session.on(
                "Runtime.bindingCalled",
                lambda event: self._handle_binding_event(event, tab_id),
            )
            cdp_session.on(
                "Page.frameNavigated",
                lambda event: self._handle_navigation(event, tab_id),
            )

            # Inject tracking script
            script = self._get_tracker_script()
            await cdp_session.send(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": script, "runImmediately": True},
            )

            # Inject immediately for current page
            try:
                await page.evaluate(script)
            except Exception as e:
                logger.debug(f"Could not inject script immediately: {e}")

            # Setup network response listener for dataload detection
            page.on("response", lambda response: self._handle_response(response, tab_id))

            self._monitored_tabs.add(tab_id)
            self._tab_pages[tab_id] = page

            # In shared-browser mode, setup may happen after initial load.
            # Record current URL so popup navigations are not missed.
            self._record_initial_navigation(tab_id, page)
            logger.info(f"✅ Recording setup complete for tab {tab_id}")

        except Exception as e:
            logger.error(f"Failed to setup recording for tab {tab_id}: {e}")

    def _hook_new_tab_creation(self) -> None:
        """Hook into new tab creation for auto-setup."""
        if not self._browser_session:
            return

        if self._original_register_new_page is not None:
            return

        original_register = self._browser_session._register_new_page
        self._original_register_new_page = original_register

        async def recording_aware_register(tab_id: str, page: "Page") -> None:
            await original_register(tab_id, page)
            if self._is_recording and tab_id not in self._monitored_tabs:
                await asyncio.sleep(0.3)
                await self._setup_for_tab(tab_id, page)

        self._browser_session._register_new_page = recording_aware_register

    def _hook_context_page_creation(self) -> None:
        """Hook into context-level page events for shared-browser popup capture."""
        if not self._browser_session:
            return

        context = getattr(self._browser_session, "_context", None)
        if not context or self._context_page_handler:
            return

        def handle_new_page(page: "Page") -> None:
            if not self._is_recording:
                return
            self._create_background_task(self._handle_context_new_page(page))

        context.on("page", handle_new_page)
        self._context_page_handler = handle_new_page

    async def _handle_context_new_page(self, page: "Page") -> None:
        """Auto-setup recorder for popup/new-tab pages opened during recording."""
        if not self._is_recording:
            return

        try:
            # Give browser session a moment to register this page first.
            await asyncio.sleep(0.2)

            if page.is_closed():
                return

            # Skip if already monitored by page identity.
            for existing_page in self._tab_pages.values():
                if existing_page is page:
                    return

            opener = None
            try:
                opener = await page.opener()
            except Exception:
                opener = None

            # Only track pages opened from already-monitored tabs.
            if opener is None:
                return
            opener_tab_id = self._find_tab_id_by_page(opener)
            if not opener_tab_id or opener_tab_id not in self._monitored_tabs:
                return

            tab_id = self._find_tab_id_by_page(page)
            if not tab_id:
                self._fallback_tab_counter += 1
                tab_id = f"auto-tab-{self._fallback_tab_counter:03d}"

            await self._setup_for_tab(tab_id, page)
        except Exception as e:
            logger.debug(f"Failed to auto-setup new page recording: {e}")

    def _find_tab_id_by_page(self, page: "Page") -> Optional[str]:
        """Find tab ID for a Playwright page from known tab registries."""
        if self._browser_session:
            for tab_id, known_page in self._browser_session._pages.items():
                if known_page is page:
                    return tab_id

        for tab_id, known_page in self._tab_pages.items():
            if known_page is page:
                return tab_id

        return None

    def _record_initial_navigation(self, tab_id: str, page: "Page") -> None:
        """Record current URL as initial navigation for late-attached tabs."""
        try:
            url = page.url
        except Exception:
            return

        if not url or url in ["about:blank", "chrome://newtab/", "chrome://new-tab-page/"]:
            return

        self._handle_navigation({"frame": {"url": url}}, tab_id)

    # ------------------------------------------------------------------
    # Event Handling
    # ------------------------------------------------------------------

    def _create_background_task(self, coro) -> asyncio.Task:
        """Create and track a background task for proper cleanup."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _handle_binding_event(self, event: Dict[str, Any], tab_id: str) -> None:
        """Handle CDP binding event from JavaScript."""
        if event.get("name") != "reportUserBehavior":
            return

        payload = event.get("payload", "")
        self._create_background_task(self._process_operation(payload, tab_id))

    async def _process_operation(self, payload: str, tab_id: str) -> None:
        """Process operation data from JavaScript."""
        try:
            data = json.loads(payload)

            # Validate required fields
            if "type" not in data:
                logger.warning("Invalid operation: missing type")
                return

            # Navigation deduplication
            if data["type"] == "navigate":
                nav_url = data.get("url", "")
                now = datetime.now()

                if self._last_nav_url and self._last_nav_time:
                    time_diff = (now - self._last_nav_time).total_seconds()
                    if (
                        nav_url == self._last_nav_url
                        and time_diff < self._nav_dedup_seconds
                    ):
                        logger.debug(f"Duplicate navigate filtered: {nav_url}")
                        return

                self._last_nav_url = nav_url
                self._last_nav_time = now

            # Track scroll time for dataload detection
            if data["type"] == "scroll":
                self._last_scroll_time = datetime.now()

            # Add tab_id
            data["tab_id"] = tab_id

            # Store operation
            self.operations.append(data)

            # Log operation
            self._log_operation(data)

            # Call callback if set
            if self._operation_callback:
                try:
                    self._operation_callback(data)
                except Exception as e:
                    logger.warning(f"Operation callback failed: {e}")

            # Capture snapshot for navigation
            if self._enable_snapshot_capture and data["type"] == "navigate":
                url = data.get("url", "")
                if url and url not in ["about:blank", "chrome://newtab/"]:
                    self._create_background_task(self._capture_snapshot(url, tab_id))

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse operation data: {e}")
        except Exception as e:
            logger.error(f"Error processing operation: {e}")

    def _handle_navigation(self, event: Dict[str, Any], tab_id: str) -> None:
        """Handle CDP navigation event."""
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
            "timestamp": get_current_timestamp(),
            "url": url,
            "tab_id": tab_id,
        }

        # Deduplicate
        now = datetime.now()
        if self._last_nav_url and self._last_nav_time:
            time_diff = (now - self._last_nav_time).total_seconds()
            if url == self._last_nav_url and time_diff < self._nav_dedup_seconds:
                return

        self._last_nav_url = url
        self._last_nav_time = now

        self.operations.append(nav_data)
        self._log_operation(nav_data)

        # Capture snapshot
        if self._enable_snapshot_capture and url not in self.snapshots:
            self._create_background_task(self._capture_snapshot(url, tab_id))

    # ------------------------------------------------------------------
    # Dataload Detection (Network-based)
    # ------------------------------------------------------------------

    def _handle_response(self, response: "Response", tab_id: str) -> None:
        """Handle network response for dataload detection."""
        if not self._is_recording:
            return

        self._create_background_task(self._process_response(response, tab_id))

    async def _process_response(self, response: "Response", tab_id: str) -> None:
        """Process network response to detect data loading.

        Only records dataload if it happens within a few seconds after a scroll event.
        This filters out navigation-triggered requests and focuses on infinite scroll.
        """
        try:
            # Only record dataload if there was a recent scroll
            if not self._last_scroll_time:
                return

            time_since_scroll = (datetime.now() - self._last_scroll_time).total_seconds()
            if time_since_scroll > self._dataload_window_seconds:
                return

            request = response.request

            # Only track XHR/Fetch requests (not images, scripts, etc.)
            resource_type = request.resource_type
            if resource_type not in ("xhr", "fetch"):
                return

            # Only track successful responses
            if response.status < 200 or response.status >= 300:
                return

            # Check content-type for JSON data
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            # Get request URL (without query params for deduplication)
            request_url = request.url
            url_base = request_url.split("?")[0]

            # Deduplicate - skip if we've seen this URL recently
            if url_base in self._recent_dataload_urls:
                return

            self._recent_dataload_urls.add(url_base)

            # Record dataload operation
            data = {
                "type": "dataload",
                "timestamp": get_current_timestamp(),
                "url": response.frame.url if response.frame else "",
                "request_url": request_url,
                "method": request.method,
                "status": response.status,
                "tab_id": tab_id,
            }

            self.operations.append(data)
            self._log_operation(data)

            # Call callback if set
            if self._operation_callback:
                try:
                    self._operation_callback(data)
                except Exception as e:
                    logger.warning(f"Operation callback failed: {e}")

        except Exception as e:
            logger.debug(f"Error processing response: {e}")

    async def _cleanup_dataload_urls(self) -> None:
        """Periodically clean up recent dataload URLs to allow re-detection."""
        try:
            while self._is_recording:
                await asyncio.sleep(10)  # Clean up every 10 seconds
                self._recent_dataload_urls.clear()
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Snapshot Capture
    # ------------------------------------------------------------------

    async def _capture_snapshot(self, url: str, tab_id: str) -> None:
        """Capture page snapshot for a URL."""
        if not self._browser_session or not self._enable_snapshot_capture:
            return

        # Generate URL hash for storage
        import hashlib

        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]

        if url_hash in self.snapshots:
            logger.debug(f"Snapshot already captured for: {url}")
            return

        try:
            # Wait for page to stabilize
            await asyncio.sleep(1.0)

            # Get page from recorder-tracked tabs first, then session registry.
            page = self._tab_pages.get(tab_id)
            if (not page or page.is_closed()) and self._browser_session:
                page = self._browser_session._pages.get(tab_id)
            if not page or page.is_closed():
                return

            # Use HybridBrowserSession's snapshot
            if (
                self._browser_session.snapshot
                and self._browser_session._current_tab_id == tab_id
            ):
                snapshot_result = await self._browser_session.snapshot.get_full_result()
                if snapshot_result:
                    snapshot_text = snapshot_result.get("snapshotText", "")

                    self.snapshots[url_hash] = {
                        "url": url,
                        "snapshot_text": snapshot_text,
                        "captured_at": get_current_timestamp(),
                    }
                    logger.info(f"📸 Snapshot captured for: {url[:60]}...")
                    return

            # Fallback: simple extraction
            dom_content = await page.evaluate(
                """
                () => ({
                    title: document.title,
                    url: window.location.href
                })
            """
            )

            self.snapshots[url_hash] = {
                "url": url,
                "simple": dom_content,
                "captured_at": get_current_timestamp(),
            }
            logger.info(f"📸 Simple snapshot captured for: {url[:60]}...")

        except Exception as e:
            logger.warning(f"Failed to capture snapshot for {url}: {e}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_operation(self, data: Dict[str, Any]) -> None:
        """Log operation to console."""
        op_type = data.get("type", "unknown").upper()
        ref = data.get("ref", "")
        text = data.get("text", "")[:30] if data.get("text") else ""

        # Format timestamp
        ts = data.get("timestamp", "")
        if isinstance(ts, str) and "T" in ts:
            time_str = ts.split("T")[-1][:8]
        else:
            time_str = datetime.now().strftime("%H:%M:%S")

        # Build log message
        parts = [f"[{time_str}] 🔥 {op_type}"]

        if ref:
            parts.append(f"  ref={ref}")
        if text:
            parts.append(f"  text=\"{text}\"")
        if data.get("value"):
            parts.append(f"  value=\"{data['value'][:30]}\"")
        if data.get("url") and op_type == "NAVIGATE":
            parts.append(f"  url={data['url'][:50]}")
        if data.get("request_url") and op_type == "DATALOAD":
            parts.append(f"  request={data['request_url'][:60]}")

        print("\n".join(parts))
        print("-" * 50)

    # ------------------------------------------------------------------
    # Tracker Script
    # ------------------------------------------------------------------

    def _get_tracker_script(self) -> str:
        """Get JavaScript tracking script."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            script_path = Path(sys._MEIPASS) / "base_agent" / "tools" / "eigent_browser" / "scripts" / "behavior_tracker.js"
        else:
            script_path = Path(__file__).parent / "scripts" / "behavior_tracker.js"
        if script_path.exists():
            try:
                return script_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not load behavior_tracker.js: {e}")

        # Minimal fallback
        logger.warning("Using minimal fallback tracker script")
        return """
        (function() {
            if (window._behaviorTrackerInitialized) return;
            window._behaviorTrackerInitialized = true;
            console.log("🎯 Behavior Tracker (fallback) initialized");

            function report(type, data) {
                if (window.reportUserBehavior) {
                    const payload = {
                        type: type,
                        timestamp: new Date().toISOString(),
                        url: location.href,
                        ...data
                    };
                    window.reportUserBehavior(JSON.stringify(payload));
                }
            }

            document.addEventListener('click', e => {
                const ref = e.target.getAttribute('aria-ref');
                if (ref) {
                    report('click', { ref: ref, text: e.target.textContent?.slice(0, 100) });
                }
            }, true);

            let currentUrl = location.href;
            setInterval(() => {
                if (location.href !== currentUrl) {
                    const fromUrl = currentUrl;
                    currentUrl = location.href;
                    report('navigate', { url: currentUrl, from_url: fromUrl });
                }
            }, 500);
        })();
        """
