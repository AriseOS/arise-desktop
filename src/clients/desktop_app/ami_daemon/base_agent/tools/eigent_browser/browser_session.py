"""
HybridBrowserSession - Lightweight wrapper around Playwright for browsing with multi-tab support.

V3 Upgrade: Unified browser management with Daemon lifecycle integration.
- Auto start/restart browser
- Health check monitoring
- Lock file management
- Existing browser reconnection
- Internal Tab Group management

Ported from CAMEL-AI/Eigent project.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Tuple

import logging

from .action_executor import ActionExecutor
from .config_loader import ConfigLoader
from .page_snapshot import PageSnapshot

if TYPE_CHECKING:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        ConsoleMessage,
        Page,
        Playwright,
    )

logger = logging.getLogger(__name__)

# Lock file name

# Tab Group colors
TAB_GROUP_COLORS = ["blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange", "grey"]


@dataclass
class TabGroup:
    """A task's tab collection for Chrome Tab Group management"""

    task_id: str
    title: str  # Default "task-{task_id[:8]}"
    color: str  # Chrome Tab Group color
    chrome_group_id: Optional[int] = None  # Chrome internal Group ID
    created_at: datetime = field(default_factory=datetime.now)

    # tab_id -> Page
    tabs: Dict[str, "Page"] = field(default_factory=dict)
    current_tab_id: Optional[str] = None
    # Bug #6 fix: Use field() to make _tab_counter an instance attribute
    _tab_counter: int = field(default=0)

    def add_tab(self, page: "Page") -> str:
        """Add a tab and return tab_id"""
        self._tab_counter += 1
        tab_id = f"{self.task_id}-tab-{self._tab_counter:03d}"
        self.tabs[tab_id] = page
        if self.current_tab_id is None:
            self.current_tab_id = tab_id
        return tab_id

    @property
    def current_tab(self) -> Optional["Page"]:
        if self.current_tab_id and self.current_tab_id in self.tabs:
            return self.tabs[self.current_tab_id]
        return None


class TabIdGenerator:
    """Monotonically increasing tab ID generator."""

    _counter: int = 0
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def generate_tab_id(cls) -> str:
        """Generate a monotonically increasing tab ID."""
        async with cls._lock:
            cls._counter += 1
            return f"tab-{cls._counter:03d}"


class HybridBrowserSession:
    """Lightweight wrapper around Playwright for browsing with multi-tab support.

    It provides multiple *Page* instances plus helper utilities (snapshot & executor).
    Multiple toolkits or agents can reuse this class without duplicating Playwright setup code.

    This class is a singleton per event-loop and session-id combination.

    V3 Upgrade: Daemon lifecycle management
    - Class-level daemon session for unified browser management
    - Health check for auto-restart on browser close
    - Lock file for existing browser detection and reconnection
    - Internal Tab Group management for task isolation
    """

    # Class-level registry for singleton instances
    _instances: ClassVar[Dict[Tuple[Any, str], "HybridBrowserSession"]] = {}
    _instances_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    # Class-level stealth config cache (avoids re-computing per instance)
    _stealth_config_cache: ClassVar[Optional[Dict[str, Any]]] = None

    # === Class-level: Daemon session (Electron CDP) ===
    _daemon_session: ClassVar[Optional["HybridBrowserSession"]] = None
    _daemon_config: ClassVar[Optional[Dict[str, Any]]] = None

    # Shared browser resources for non-daemon mode
    _primary_session: ClassVar[Optional["HybridBrowserSession"]] = None

    # Lock to prevent two sessions from claiming the same pool page concurrently
    _pool_claim_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    _initialized: bool
    _creation_params: Dict[str, Any]

    def __new__(
        cls,
        *,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        stealth: bool = False,
        session_id: Optional[str] = None,
        default_timeout: Optional[int] = None,
        short_timeout: Optional[int] = None,
        navigation_timeout: Optional[int] = None,
        network_idle_timeout: Optional[int] = None,
    ) -> "HybridBrowserSession":
        instance = super().__new__(cls)
        instance._initialized = False
        instance._session_id = session_id or "default"
        instance._creation_params = {
            "headless": headless,
            "user_data_dir": user_data_dir,
            "stealth": stealth,
            "session_id": session_id,
            "default_timeout": default_timeout,
            "short_timeout": short_timeout,
            "navigation_timeout": navigation_timeout,
            "network_idle_timeout": network_idle_timeout,
        }
        return instance

    @classmethod
    async def _get_or_create_instance(
        cls,
        instance: "HybridBrowserSession",
    ) -> "HybridBrowserSession":
        """Get or create singleton instance for the current event loop and session."""
        try:
            loop = asyncio.get_running_loop()
            loop_id = str(id(loop))
        except RuntimeError:
            import threading
            loop_id = f"sync_{threading.current_thread().ident}"

        session_id = (
            instance._session_id
            if instance._session_id is not None
            else "default"
        )
        session_key = (loop_id, session_id)

        async with cls._instances_lock:
            if session_key in cls._instances:
                return cls._instances[session_key]

            cls._instances[session_key] = instance
            logger.debug(f"Created new browser session for session_id: {session_id}")
            return instance

    @classmethod
    async def get_session(
        cls,
        session_id: str,
        *,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        stealth: bool = True,
    ) -> "HybridBrowserSession":
        """Get or create a browser session by session_id.

        Recommended entry point. Returns existing singleton if available,
        otherwise creates and initializes a new session.

        Always returns the singleton instance from the registry, not a
        throwaway copy, so that page/tab mutations are visible globally.
        """
        loop_id = str(id(asyncio.get_running_loop()))
        session_key = (loop_id, session_id)

        async with cls._instances_lock:
            if session_key in cls._instances:
                return cls._instances[session_key]

        # Not found — create, init, register via ensure_browser
        instance = cls(
            session_id=session_id,
            headless=headless,
            user_data_dir=user_data_dir,
            stealth=stealth,
        )
        await instance.ensure_browser()

        # ensure_browser → _get_or_create_instance may have registered a
        # different object as the singleton (concurrent creation race).
        # Always return the canonical singleton from the registry.
        async with cls._instances_lock:
            return cls._instances.get(session_key, instance)

    def __init__(
        self,
        *,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        stealth: bool = False,
        session_id: Optional[str] = None,
        default_timeout: Optional[int] = None,
        short_timeout: Optional[int] = None,
        navigation_timeout: Optional[int] = None,
        network_idle_timeout: Optional[int] = None,
    ):
        if self._initialized:
            return
        self._initialized = True

        self._headless = headless
        self._user_data_dir = user_data_dir
        self._stealth = stealth
        self._session_id = session_id or "default"

        self._default_timeout = default_timeout
        self._short_timeout = short_timeout
        self._navigation_timeout = ConfigLoader.get_navigation_timeout(navigation_timeout)
        self._network_idle_timeout = ConfigLoader.get_network_idle_timeout(network_idle_timeout)

        self._creation_params = {
            "headless": headless,
            "user_data_dir": user_data_dir,
            "stealth": stealth,
            "session_id": session_id,
            "default_timeout": default_timeout,
            "short_timeout": short_timeout,
            "navigation_timeout": navigation_timeout,
            "network_idle_timeout": network_idle_timeout,
        }

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        # Dictionary-based tab management with monotonic IDs
        self._pages: Dict[str, Page] = {}
        self._console_logs: Dict[str, Any] = {}
        self._current_tab_id: Optional[str] = None
        self.log_limit: int = ConfigLoader.get_max_log_limit() or 1000

        self.snapshot: Optional[PageSnapshot] = None
        self.executor: Optional[ActionExecutor] = None

        # Background tasks set to prevent GC of fire-and-forget tasks
        self._background_tasks: set = set()

        # Tab Group management (V3)
        self._tab_groups: Dict[str, TabGroup] = {}
        self._color_index: int = 0

        # WebView ID mapping: page object id → Electron view ID ("0"-"7")
        self._page_to_view_id: Dict[int, str] = {}

        self._ensure_lock: asyncio.Lock = asyncio.Lock()

        # Load stealth config on initialization (class-level cache)
        self._stealth_script: Optional[str] = None
        self._stealth_config: Optional[Dict[str, Any]] = None
        if self._stealth:
            if self.__class__._stealth_config_cache is None:
                self.__class__._stealth_config_cache = ConfigLoader.get_browser_config().get_stealth_config()
            self._stealth_config = self.__class__._stealth_config_cache

    @property
    def webview_id(self) -> Optional[str]:
        """Return the Electron WebContentsView ID for the primary page.

        Returns "0"-"7" or None if the page wasn't claimed from the pool.
        """
        if self._page is not None:
            return self._page_to_view_id.get(id(self._page))
        return None

    # ------------------------------------------------------------------
    # Multi-tab management methods
    # ------------------------------------------------------------------
    async def create_new_tab(self, url: Optional[str] = None) -> str:
        """Create a new tab and optionally navigate to a URL."""
        await self.ensure_browser()

        if self._context is None:
            raise RuntimeError("Browser context is not available")

        tab_id = await TabIdGenerator.generate_tab_id()
        new_page = await self._claim_pool_page()
        await self._register_new_page(tab_id, new_page)

        if url:
            try:
                await new_page.goto(url, timeout=self._navigation_timeout)
                await new_page.wait_for_load_state('domcontentloaded')
            except Exception as e:
                logger.warning(f"Failed to navigate new tab to {url}: {e}")

        logger.info(f"Created new tab {tab_id}, total tabs: {len(self._pages)}")
        return tab_id

    async def _register_new_page(self, tab_id: str, new_page: "Page") -> None:
        """Register a page and add console event listeners."""
        self._pages[tab_id] = new_page
        self._console_logs[tab_id] = deque(maxlen=self.log_limit)

        def handle_console_log(msg: ConsoleMessage):
            logs = self._console_logs.get(tab_id)
            if logs is not None:
                logs.append({"type": msg.type, "text": msg.text})

        new_page.on(event="console", f=handle_console_log)

        def handle_page_close(page: "Page"):
            # Clean up both _pages and _console_logs when page is closed
            self._pages.pop(tab_id, None)
            self._console_logs.pop(tab_id, None)
            logger.debug(f"Tab {tab_id} closed and removed from registry. Remaining tabs: {len(self._pages)}")

        new_page.on(event="close", f=handle_page_close)

        def handle_page_crash(page: "Page"):
            # Page crash does NOT trigger the "close" event — clean up explicitly
            self._pages.pop(tab_id, None)
            self._console_logs.pop(tab_id, None)
            logger.error(f"Tab {tab_id} crashed and removed from registry. Remaining tabs: {len(self._pages)}")

        new_page.on(event="crash", f=handle_page_crash)

    def _on_new_page(self, page: "Page") -> None:
        """Callback for context 'page' event - auto-register new tabs/popups.

        This catches all new pages opened by any means:
        - JavaScript window.open()
        - Links with target="_blank"
        - Popups
        - Force clicks on links
        """
        import asyncio
        import time
        logger.debug(f"[PAGE EVENT] Received at {time.strftime('%H:%M:%S')}, page.url={page.url}")

        async def register():
            try:
                # Check if session is still valid
                if self._context is None or self._page is None:
                    logger.debug("Session closed during page registration, skipping")
                    return

                # Check if already registered
                for existing_page in self._pages.values():
                    if existing_page is page:
                        logger.debug("Page already registered, skipping")
                        return

                tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(tab_id, page)
                logger.info(f"[Auto] Registered new tab {tab_id} (opened by page event). Total tabs: {len(self._pages)}")
            except Exception as e:
                logger.warning(f"[Auto] Failed to register new page: {e}")

        # Schedule the async registration with error callback
        def handle_task_exception(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error(f"[PAGE EVENT] Unhandled exception in page registration: {exc}")

        task = asyncio.create_task(register())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(handle_task_exception)

    async def register_page(self, new_page: "Page") -> str:
        """Register a page that was created externally (e.g., by a click)."""
        for tab_id, page in self._pages.items():
            if page is new_page:
                return tab_id

        tab_id = await TabIdGenerator.generate_tab_id()
        await self._register_new_page(tab_id, new_page)

        logger.info(f"Registered new tab {tab_id}. Total tabs: {len(self._pages)}")
        return tab_id

    async def switch_to_tab(self, tab_id: str) -> bool:
        """Switch to a specific tab by ID."""
        if tab_id not in self._pages:
            logger.warning(f"Invalid tab ID: {tab_id}")
            return False

        page = self._pages[tab_id]

        if page.is_closed():
            logger.warning(f"Tab {tab_id} is closed, removing from registry")
            del self._pages[tab_id]
            return False

        try:
            self._current_tab_id = tab_id
            self._page = page

            self.executor = ActionExecutor(
                page,
                self,
                default_timeout=self._default_timeout,
                short_timeout=self._short_timeout,
            )
            self.snapshot = PageSnapshot(page)

            logger.info(f"Switched to tab {tab_id}")
            return True

        except Exception as e:
            logger.warning(f"Error switching to tab {tab_id}: {e}")
            return False

    async def _return_page_to_pool(self, page: "Page") -> None:
        """Return a page to the Electron WebView pool for reuse.

        Instead of page.close() which permanently destroys the WebContentsView,
        navigate back to the pool marker URL (with viewId) so the page can be
        claimed again.
        """
        try:
            if not page.is_closed():
                view_id = self._page_to_view_id.pop(id(page), None)
                pool_url = f'about:blank?ami=pool&viewId={view_id}' if view_id is not None else 'about:blank?ami=pool'
                await page.goto(pool_url)
                logger.debug(f"Returned page to pool (viewId={view_id})")
        except Exception as e:
            logger.warning(f"Failed to return page to pool: {e}")

    async def close_tab(self, tab_id: str) -> bool:
        """Close a specific tab by ID.

        Also removes the tab from any Tab Group it belongs to.
        Returns the page to the Electron WebView pool instead of destroying it.
        """
        if tab_id not in self._pages:
            logger.warning(f"Invalid tab ID: {tab_id}")
            return False

        page = self._pages[tab_id]

        try:
            await self._return_page_to_pool(page)

            del self._pages[tab_id]
            self._console_logs.pop(tab_id, None)

            # Bug #14 fix: Also remove from Tab Groups
            for group in self._tab_groups.values():
                if tab_id in group.tabs:
                    del group.tabs[tab_id]
                    if group.current_tab_id == tab_id:
                        # Update group's current tab
                        if group.tabs:
                            group.current_tab_id = next(iter(group.tabs.keys()))
                        else:
                            group.current_tab_id = None
                    logger.debug(f"Removed tab {tab_id} from group {group.title}")
                    break  # A tab can only belong to one group

            if tab_id == self._current_tab_id:
                if self._pages:
                    next_tab_id = next(iter(self._pages.keys()))
                    await self.switch_to_tab(next_tab_id)
                else:
                    self._current_tab_id = None
                    self._page = None
                    self.executor = None
                    self.snapshot = None

            logger.info(f"Closed tab {tab_id}, remaining tabs: {len(self._pages)}")
            return True

        except Exception as e:
            logger.warning(f"Error closing tab {tab_id}: {e}")
            return False

    async def get_tab_info(self) -> List[Dict[str, Any]]:
        """Get information about all open tabs including IDs."""
        tab_info = []
        tabs_to_cleanup = []

        for tab_id, page in list(self._pages.items()):
            try:
                if not page.is_closed():
                    title = await page.title()
                    url = page.url
                    is_current = tab_id == self._current_tab_id
                    tab_info.append({
                        "tab_id": tab_id,
                        "title": title,
                        "url": url,
                        "is_current": is_current,
                    })
                else:
                    tabs_to_cleanup.append(tab_id)
            except Exception as e:
                logger.warning(f"Error getting info for tab {tab_id}: {e}")
                tabs_to_cleanup.append(tab_id)

        for tab_id in tabs_to_cleanup:
            if tab_id in self._pages:
                del self._pages[tab_id]

        return tab_info

    async def get_current_tab_id(self) -> Optional[str]:
        """Get the id for the current active tab."""
        if not self._current_tab_id or not self._pages:
            return None
        return self._current_tab_id

    # ------------------------------------------------------------------
    # Browser lifecycle helpers
    # ------------------------------------------------------------------
    async def ensure_browser(self) -> None:
        """Ensure browser is ready."""
        singleton_instance = await self._get_or_create_instance(self)

        if singleton_instance is not self:
            await singleton_instance.ensure_browser()
            self._playwright = singleton_instance._playwright
            self._browser = singleton_instance._browser
            self._context = singleton_instance._context
            self._page = singleton_instance._page
            self._pages = singleton_instance._pages
            self._console_logs = singleton_instance._console_logs
            self._current_tab_id = singleton_instance._current_tab_id
            self.snapshot = singleton_instance.snapshot
            self.executor = singleton_instance.executor
            return

        async with self._ensure_lock:
            await self._ensure_browser_inner()

    async def _ensure_browser_inner(self) -> None:
        """Internal browser initialization logic.

        Connects to Electron's embedded Chromium via CDP.
        BROWSER_CDP_PORT env var is set by Electron's DaemonLauncher.
        Claims a pool page (identified by 'ami=pool' marker URL).
        """
        from playwright.async_api import async_playwright
        import os

        if self._page is not None:
            # Verify the connection is still alive
            if not self._page.is_closed() and self._browser and self._browser.is_connected():
                return
            # Page or connection is dead, need to reconnect
            logger.warning("Browser connection lost, reconnecting...")
            self._page = None
            self._pages = {}
            self._current_tab_id = None
            self._context = None
            self._browser = None
            self._playwright = None

        # Reuse existing browser connection if daemon session is alive
        daemon = self.__class__._daemon_session
        if daemon and daemon._context and daemon._browser and daemon._browser.is_connected():
            logger.info("Reusing daemon session's browser")
            self._playwright = daemon._playwright
            self._browser = daemon._browser
            self._context = daemon._context

            try:
                initial_tab_id, self._page = await self.create_tab_in_group(
                    task_id=self._session_id,
                    url=None
                )
                self._current_tab_id = initial_tab_id
                self._page.set_default_navigation_timeout(self._navigation_timeout)
                self._page.set_default_timeout(self._navigation_timeout)
                self.snapshot = PageSnapshot(self._page)
                self.executor = ActionExecutor(
                    self._page, self,
                    default_timeout=self._default_timeout,
                    short_timeout=self._short_timeout,
                )
                logger.info(f"Browser session initialized (reusing daemon browser, Tab Group: {self._session_id})")
                return
            except Exception as e:
                logger.warning(f"Failed to reuse daemon browser: {e}")
                # Only clear self's references — do NOT corrupt daemon's state.
                # The failure is likely transient (e.g., pool exhaustion).
                self._playwright = None
                self._browser = None
                self._context = None

        # Reuse primary session's browser (non-daemon mode)
        primary = self.__class__._primary_session
        if primary and primary is not self and primary._context and primary._browser and primary._browser.is_connected():
            logger.info("Reusing primary session's browser")
            self._playwright = primary._playwright
            self._browser = primary._browser
            self._context = primary._context

            try:
                self._page = await self._claim_pool_page()
                initial_tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(initial_tab_id, self._page)
                self._current_tab_id = initial_tab_id
                self._page.set_default_navigation_timeout(self._navigation_timeout)
                self._page.set_default_timeout(self._navigation_timeout)
                self.snapshot = PageSnapshot(self._page)
                self.executor = ActionExecutor(
                    self._page, self,
                    default_timeout=self._default_timeout,
                    short_timeout=self._short_timeout,
                )
                logger.info("Browser session initialized (reusing primary session's browser)")
                return
            except Exception as e:
                logger.warning(f"Failed to reuse primary browser: {e}")
                self._playwright = None
                self._browser = None
                self._context = None

        # Connect to Electron's Chromium via CDP (with timeout + retry)
        cdp_port = os.environ.get('BROWSER_CDP_PORT')
        if not cdp_port:
            raise RuntimeError(
                "BROWSER_CDP_PORT env var not set. "
                "Daemon must be launched by Electron with BROWSER_CDP_PORT."
            )

        cdp_url = f'http://127.0.0.1:{cdp_port}'
        logger.info(f"Connecting to Electron CDP at {cdp_url}...")

        # Bypass proxy for localhost
        os.environ.setdefault('NO_PROXY', '127.0.0.1,localhost')
        os.environ.setdefault('no_proxy', '127.0.0.1,localhost')

        import asyncio

        self._playwright = await async_playwright().start()

        max_retries = 5
        for attempt in range(max_retries):
            try:
                self._browser = await asyncio.wait_for(
                    self._playwright.chromium.connect_over_cdp(cdp_url),
                    timeout=15,
                )
                break
            except (asyncio.TimeoutError, Exception) as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # 1s, 2s, 4s, 8s
                    logger.warning(
                        f"CDP connection attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    await self._playwright.stop()
                    self._playwright = None
                    raise RuntimeError(
                        f"Failed to connect to Electron CDP at {cdp_url} "
                        f"after {max_retries} attempts: {e}"
                    )

        logger.info("Connected to Electron via CDP")

        # Get the default context (Electron's persist:user_login partition)
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        self._context.on("page", self._on_new_page)

        # Claim a pool page (marked with 'ami=pool' in URL)
        self._page = await self._claim_pool_page()
        initial_tab_id = await TabIdGenerator.generate_tab_id()
        await self._register_new_page(initial_tab_id, self._page)
        self._current_tab_id = initial_tab_id

        self._page.set_default_navigation_timeout(self._navigation_timeout)
        self._page.set_default_timeout(self._navigation_timeout)

        self.snapshot = PageSnapshot(self._page)
        self.executor = ActionExecutor(
            self._page, self,
            default_timeout=self._default_timeout,
            short_timeout=self._short_timeout,
        )

        # Register as primary session if no daemon and no primary exists
        if self.__class__._daemon_session is None and self.__class__._primary_session is None:
            self.__class__._primary_session = self
            logger.info("Registered as primary session for browser sharing")

        logger.info("Browser session initialized (Electron CDP)")

    async def _claim_pool_page(self) -> "Page":
        """Claim an available pool page from Electron's WebView pool.

        Pool pages are identified by 'ami=pool' in their URL and include
        'viewId=N' to identify the WebContentsView slot. The viewId is
        extracted and stored in _page_to_view_id for frontend display.

        Once claimed, the page is navigated to about:blank to mark it as in-use.

        Uses a class-level lock to prevent two sessions from claiming the same
        pool page concurrently. Retries up to 3 times with 3s delay to handle
        race conditions where Electron's WebView hasn't finished loading yet.
        """
        if not self._context:
            raise RuntimeError("No browser context available")

        max_retries = 3
        for attempt in range(max_retries):
            async with self.__class__._pool_claim_lock:
                pages = self._context.pages
                for page in pages:
                    try:
                        url = page.url
                        if 'ami=pool' in url:
                            # Extract viewId from URL (e.g. about:blank?ami=pool&viewId=3)
                            view_id = None
                            if 'viewId=' in url:
                                try:
                                    view_id = url.split('viewId=')[1].split('&')[0]
                                except (IndexError, ValueError):
                                    pass
                            logger.info(f"Claiming pool page: {url} (viewId={view_id})")
                            await page.goto('about:blank')
                            if view_id is not None:
                                self._page_to_view_id[id(page)] = view_id
                            return page
                    except Exception:
                        continue

            if attempt < max_retries - 1:
                logger.info(
                    f"No pool page available (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in 3s..."
                )
                await asyncio.sleep(3)

        raise RuntimeError(
            "No pool pages available (all WebView slots are in use). "
            "Wait for a running browser task to finish before starting a new one."
        )

    async def close(self) -> None:
        """Close browser session and clean up resources."""
        if self._page is None:
            return

        try:
            logger.debug("Closing browser session...")
            await self._close_session()

            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop_id = str(id(loop))
                except RuntimeError:
                    import threading
                    loop_id = f"sync_{threading.current_thread().ident}"

                session_id = self._session_id if self._session_id is not None else "default"
                session_key = (loop_id, session_id)

                async with self._instances_lock:
                    if session_key in self._instances and self._instances[session_key] is self:
                        del self._instances[session_key]
                        logger.debug(f"Removed session {session_id} from registry")

                # Clear primary session if this is it
                if self.__class__._primary_session is self:
                    self.__class__._primary_session = None
                    logger.debug("Cleared primary session reference")

            except Exception as registry_error:
                logger.warning(f"Error cleaning up registry: {registry_error}")

            logger.debug("Browser session closed successfully")
        except Exception as e:
            logger.error(f"Error during browser session close: {e}")
        finally:
            self._page = None
            self._pages = {}
            self._current_tab_id = None
            self.snapshot = None
            self.executor = None

    def _is_connection_owner(self) -> bool:
        """Check if this session owns the Playwright/browser/context connection.

        In Electron CDP mode, only the daemon session or primary session owns
        the connection. All other sessions borrow shared references and must
        NOT close context/browser/playwright on cleanup.
        """
        return (
            self.__class__._daemon_session is self
            or self.__class__._primary_session is self
        )

    async def _close_session(self) -> None:
        """Internal session close logic with thorough cleanup.

        In Electron CDP mode, the context, browser, and playwright connection
        are shared across all sessions. Only the connection owner (daemon/primary
        session) may close them. Borrowing sessions return pages to the pool
        instead of closing them.
        """
        is_owner = self._is_connection_owner()

        try:
            # Step 1: Return all pages to pool.
            # In Electron CDP mode, pages are Electron-owned WebContentsViews.
            # We NEVER call page.close() — that would destroy the WebContentsView
            # via CDP. Instead, navigate back to the pool marker URL.
            pages_to_release = list(self._pages.values())
            for page in pages_to_release:
                try:
                    if not page.is_closed():
                        await page.goto('about:blank?ami=pool')
                        logger.debug("Returned page to pool")
                except Exception as e:
                    logger.warning(f"Error returning page to pool: {e}")

            self._pages.clear()
            self._page = None

            # Borrowers stop here — do NOT touch shared resources
            if not is_owner:
                logger.debug("Borrowing session cleaned up (pages returned to pool)")
                return

            # Owner-only cleanup below (daemon/primary session shutdown).
            # Do NOT close context — Electron owns it.
            # Only disconnect the Playwright CDP connection.
            await asyncio.sleep(0.2)

            # Step 2: Disconnect browser (drops CDP connection, does NOT close Electron)
            if self._browser:
                try:
                    if self._browser.is_connected():
                        await self._browser.close()
                        await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Error disconnecting browser: {e}")
                finally:
                    self._browser = None

            # Step 3: Stop playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")
                finally:
                    self._playwright = None

        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
        finally:
            self._page = None
            self._pages = {}
            self._current_tab_id = None
            self._context = None
            if is_owner:
                self._browser = None
                self._playwright = None

    @classmethod
    async def close_all_sessions(cls) -> None:
        """Close all browser sessions and clean up the singleton registry.

        Closes borrowing sessions first, then owners, to ensure CDP
        connection is alive while borrowers return pages to the pool.
        """
        logger.debug("Closing all browser sessions...")
        async with cls._instances_lock:
            instances_to_close = list(cls._instances.values())
            cls._instances.clear()

        # Close borrowers first, then owners
        borrowers = [i for i in instances_to_close if not i._is_connection_owner()]
        owners = [i for i in instances_to_close if i._is_connection_owner()]

        for instance in borrowers + owners:
            try:
                await instance._close_session()
            except Exception as e:
                logger.error(f"Error closing session {instance._session_id}: {e}")

        logger.debug("All browser sessions closed and registry cleared")

    @classmethod
    async def close_session_by_id(cls, session_id: str) -> bool:
        """Close a specific browser session by session_id.

        Args:
            session_id: The session identifier to close

        Returns:
            True if session was found and closed, False if not found
        """
        try:
            loop = asyncio.get_running_loop()
            loop_id = str(id(loop))
        except RuntimeError:
            import threading
            loop_id = f"sync_{threading.current_thread().ident}"

        session_key = (loop_id, session_id)

        async with cls._instances_lock:
            if session_key not in cls._instances:
                logger.debug(f"Session {session_id} not found in registry (may not have been created)")
                return False

            instance = cls._instances[session_key]
            del cls._instances[session_key]

        # Close outside the lock to avoid deadlock
        try:
            await instance._close_session()
            logger.info(f"Closed browser session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Page interaction
    # ------------------------------------------------------------------
    async def visit(self, url: str) -> str:
        """Navigate current tab to URL."""
        await self.ensure_browser()
        page = await self.get_page()

        await page.goto(url, timeout=self._navigation_timeout)
        await page.wait_for_load_state('domcontentloaded')

        try:
            await page.wait_for_load_state('networkidle', timeout=self._network_idle_timeout)
        except Exception:
            logger.debug("Network idle timeout - continuing anyway")

        return f"Navigated to {url}"

    async def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        diff_only: bool = False,
        viewport_limit: bool = False,
    ) -> str:
        """Get snapshot for current tab."""
        if not self.snapshot:
            return "<empty>"
        return await self.snapshot.capture(
            force_refresh=force_refresh,
            diff_only=diff_only,
            viewport_limit=viewport_limit,
        )

    async def get_snapshot_with_elements(
        self,
        *,
        viewport_limit: bool = False,
    ) -> Dict[str, Any]:
        """Get full snapshot result including elements map with href info.

        Returns:
            Dict with keys:
                - snapshotText: YAML-like snapshot text
                - elements: Dict mapping ref (e.g., "e1") to element info including href
                - url: Current page URL
                - metadata: Analysis metadata
        """
        if not self.snapshot:
            return {"snapshotText": "<empty>", "elements": {}}
        return await self.snapshot.get_full_result(viewport_limit=viewport_limit)

    async def exec_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action on current tab."""
        if not self.executor:
            return {
                "success": False,
                "message": "No executor available",
                "details": {},
            }
        return await self.executor.execute(action)

    async def get_page(self) -> "Page":
        """Get current active page."""
        await self.ensure_browser()
        if self._page is None:
            raise RuntimeError("No active page available")
        return self._page

    async def get_console_logs(self) -> Dict[str, Any]:
        """Get current active logs."""
        await self.ensure_browser()
        if self._current_tab_id is None:
            raise RuntimeError("No active tab available")
        logs = self._console_logs.get(self._current_tab_id, None)
        if logs is None:
            raise RuntimeError("No active logs available for the page")
        return logs

    # =========================================================================
    # Daemon Lifecycle Management (Electron CDP)
    # =========================================================================

    @classmethod
    async def start_daemon_session(
        cls,
        config: Optional[Dict[str, Any]] = None,
    ) -> "HybridBrowserSession":
        """Start daemon-level browser session.

        Called by Daemon on startup. Creates a session that will connect to
        Electron's embedded Chromium via CDP (BROWSER_CDP_PORT env var).
        No external Chrome, no lock files, no health checks needed.
        """
        if cls._daemon_session is not None:
            logger.warning("Daemon session already exists, returning existing session")
            return cls._daemon_session

        logger.info("Starting daemon browser session (Electron CDP)...")
        cls._daemon_config = config or {}

        browser_config = cls._daemon_config.get("browser", {}) if cls._daemon_config else {}
        headless = browser_config.get("headless", False)
        user_data_dir = browser_config.get("user_data_dir")

        session = cls(
            session_id="daemon",
            headless=headless,
            user_data_dir=user_data_dir,
            stealth=True,
        )

        await session.ensure_browser()

        cls._daemon_session = session

        # Register in singleton registry
        try:
            loop = asyncio.get_running_loop()
            loop_id = str(id(loop))
        except RuntimeError:
            import threading
            loop_id = f"sync_{threading.current_thread().ident}"

        async with cls._instances_lock:
            cls._instances[(loop_id, "daemon")] = session

        logger.info("Daemon browser session started (Electron CDP)")
        return session

    @classmethod
    async def stop_daemon_session(cls, force: bool = False) -> None:
        """Stop daemon-level browser session. Called by Daemon on shutdown."""
        logger.info("Stopping daemon browser session...")

        if cls._daemon_session:
            await cls._daemon_session._close_session()

            try:
                loop = asyncio.get_running_loop()
                loop_id = str(id(loop))
            except RuntimeError:
                import threading
                loop_id = f"sync_{threading.current_thread().ident}"

            async with cls._instances_lock:
                cls._instances.pop((loop_id, "daemon"), None)

            cls._daemon_session = None

        logger.info("Daemon browser session stopped")

    @classmethod
    def get_daemon_session(cls) -> Optional["HybridBrowserSession"]:
        """Get the daemon-level browser session."""
        return cls._daemon_session

    # =========================================================================
    # Tab Group Management - Internal tracking only
    # =========================================================================

    def _allocate_color(self) -> str:
        """Allocate a color for a new Tab Group"""
        color = TAB_GROUP_COLORS[self._color_index % len(TAB_GROUP_COLORS)]
        self._color_index += 1
        return color

    async def create_tab_group(self, task_id: str, title: Optional[str] = None) -> TabGroup:
        """Create a Tab Group for a task

        Args:
            task_id: Task identifier
            title: Optional display title (default: "task-{task_id[:8]}")

        Returns:
            TabGroup instance
        """
        if task_id in self._tab_groups:
            logger.debug(f"Tab Group for {task_id} already exists")
            return self._tab_groups[task_id]

        group_title = title or f"task-{task_id[:8]}"
        color = self._allocate_color()

        group = TabGroup(
            task_id=task_id,
            title=group_title,
            color=color,
        )
        self._tab_groups[task_id] = group

        logger.info(f"Created Tab Group: {group_title} (color={color})")
        return group

    def get_tab_group(self, task_id: str) -> Optional[TabGroup]:
        """Get Tab Group for a task

        Args:
            task_id: Task identifier

        Returns:
            TabGroup or None if not found
        """
        return self._tab_groups.get(task_id)

    async def close_tab_group(self, task_id: str) -> bool:
        """Close a Tab Group and all its tabs

        Args:
            task_id: Task identifier

        Returns:
            True if closed, False if not found
        """
        group = self._tab_groups.get(task_id)
        if not group:
            logger.debug(f"Tab Group for {task_id} not found")
            return False

        logger.info(f"Closing Tab Group: {group.title} ({len(group.tabs)} tabs)")

        # Return all pages in the group to the pool
        for tab_id, page in list(group.tabs.items()):
            try:
                await self._return_page_to_pool(page)
                # Also remove from main _pages dict
                self._pages.pop(tab_id, None)
                self._console_logs.pop(tab_id, None)
            except Exception as e:
                logger.warning(f"Error returning tab {tab_id} to pool: {e}")

        # Update current tab if it was in this group
        if self._current_tab_id and self._current_tab_id not in self._pages:
            if self._pages:
                next_tab = next(iter(self._pages.keys()))
                await self.switch_to_tab(next_tab)
            else:
                self._current_tab_id = None
                self._page = None
                self.snapshot = None
                self.executor = None

        # Remove from registry
        del self._tab_groups[task_id]
        logger.info(f"Tab Group {group.title} closed")
        return True

    async def create_tab_in_group(
        self,
        task_id: str,
        url: Optional[str] = None
    ) -> Tuple[str, "Page"]:
        """Create a new tab in a task's Tab Group

        This is the main method for creating tabs with Tab Group support.

        Note: This method assumes the browser is already initialized.
        Do NOT call ensure_browser() here to avoid recursive deadlock.

        Args:
            task_id: Task identifier
            url: Initial URL (optional)

        Returns:
            Tuple of (tab_id, Page)
        """
        # Don't call ensure_browser() here - caller is responsible for that
        # Calling it here causes deadlock when called from _ensure_browser_inner

        # Get or create Tab Group
        group = self._tab_groups.get(task_id)
        if not group:
            group = await self.create_tab_group(task_id)

        # Claim a pool page instead of creating a new page.
        # In Electron CDP mode, new_page() creates unmanaged pages outside
        # the WebContentsView pool, which won't have stealth injection.
        if not self._context:
            raise RuntimeError("Browser context not available")
        if not self._browser or not self._browser.is_connected():
            raise RuntimeError("Browser is disconnected")

        page = await self._claim_pool_page()

        # Navigate if URL provided
        if url:
            try:
                await page.goto(url, timeout=self._navigation_timeout)
                await page.wait_for_load_state('domcontentloaded')
            except Exception as e:
                logger.warning(f"Navigation to {url} failed: {e}")

        # Add to Tab Group
        tab_id = group.add_tab(page)

        # Also register in main _pages dict for backward compatibility
        self._pages[tab_id] = page
        self._console_logs[tab_id] = deque(maxlen=self.log_limit)

        # Add console event listener
        def handle_console_log(msg):
            logs = self._console_logs.get(tab_id)
            if logs is not None:
                logs.append({"type": msg.type, "text": msg.text})

        page.on("console", handle_console_log)

        # Bug #11 fix: Add close event handler to clean up _pages and _console_logs
        def handle_page_close(closed_page: "Page"):
            self._pages.pop(tab_id, None)
            self._console_logs.pop(tab_id, None)
            logger.debug(f"Tab {tab_id} closed and removed from registry. Remaining tabs: {len(self._pages)}")

        page.on("close", handle_page_close)

        def handle_page_crash(crashed_page: "Page"):
            self._pages.pop(tab_id, None)
            self._console_logs.pop(tab_id, None)
            logger.error(f"Tab {tab_id} crashed in group {group.title} — removed from registry. Remaining tabs: {len(self._pages)}")

        page.on("crash", handle_page_crash)

        logger.info(f"Created tab {tab_id} in group {group.title}")

        return tab_id, page

    async def switch_to_tab_in_group(self, task_id: str, tab_id: str) -> bool:
        """Switch to a specific tab within a Tab Group

        Args:
            task_id: Task identifier
            tab_id: Tab identifier within the group

        Returns:
            True if switched, False if not found
        """
        group = self._tab_groups.get(task_id)
        if not group:
            logger.warning(f"Tab Group for {task_id} not found")
            return False

        if tab_id not in group.tabs:
            logger.warning(f"Tab {tab_id} not found in group {task_id}")
            return False

        page = group.tabs[tab_id]
        if page.is_closed():
            logger.warning(f"Tab {tab_id} is closed")
            del group.tabs[tab_id]
            return False

        # Update group's current tab
        group.current_tab_id = tab_id

        # Update session's current tab
        self._current_tab_id = tab_id
        self._page = page

        # Update executor and snapshot
        self.executor = ActionExecutor(
            page,
            self,
            default_timeout=self._default_timeout,
            short_timeout=self._short_timeout,
        )
        self.snapshot = PageSnapshot(page)

        logger.debug(f"Switched to tab {tab_id} in group {task_id}")
        return True

    async def close_tab_in_group(self, task_id: str, tab_id: str) -> bool:
        """Close a specific tab within a Tab Group

        Args:
            task_id: Task identifier
            tab_id: Tab identifier

        Returns:
            True if closed, False if not found
        """
        group = self._tab_groups.get(task_id)
        if not group:
            logger.warning(f"Tab Group for {task_id} not found")
            return False

        if tab_id not in group.tabs:
            logger.warning(f"Tab {tab_id} not found in group {task_id}")
            return False

        page = group.tabs[tab_id]
        try:
            await self._return_page_to_pool(page)
        except Exception as e:
            logger.warning(f"Error returning tab {tab_id} to pool: {e}")

        del group.tabs[tab_id]

        # Also remove from main _pages dict and console logs
        self._pages.pop(tab_id, None)
        self._console_logs.pop(tab_id, None)

        # Update group's current tab if needed
        if group.current_tab_id == tab_id:
            if group.tabs:
                group.current_tab_id = next(iter(group.tabs.keys()))
            else:
                group.current_tab_id = None

        # Update session's current tab if it was the closed one
        if tab_id == self._current_tab_id:
            if self._pages:
                next_tab = next(iter(self._pages.keys()))
                await self.switch_to_tab(next_tab)
            else:
                self._current_tab_id = None
                self._page = None
                self.executor = None
                self.snapshot = None

        logger.debug(f"Closed tab {tab_id} in group {task_id}")
        return True

    def get_tab_groups_info(self) -> List[Dict[str, Any]]:
        """Get information about all Tab Groups

        Returns:
            List of Tab Group info dictionaries
        """
        info = []
        for task_id, group in self._tab_groups.items():
            tabs_info = []
            for tab_id, page in group.tabs.items():
                try:
                    tabs_info.append({
                        "tab_id": tab_id,
                        "url": page.url if not page.is_closed() else "(closed)",
                        "is_current": tab_id == group.current_tab_id,
                    })
                except Exception:
                    tabs_info.append({
                        "tab_id": tab_id,
                        "url": "(error)",
                        "is_current": tab_id == group.current_tab_id,
                    })

            info.append({
                "task_id": task_id,
                "title": group.title,
                "color": group.color,
                "chrome_group_id": group.chrome_group_id,
                "tab_count": len(group.tabs),
                "tabs": tabs_info,
            })
        return info
