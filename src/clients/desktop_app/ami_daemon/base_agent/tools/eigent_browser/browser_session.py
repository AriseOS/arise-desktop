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
import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Tuple

import aiohttp
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
LOCK_FILE_NAME = "ami_browser.lock"

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

    # === Class-level: Daemon lifecycle management ===
    _daemon_session: ClassVar[Optional["HybridBrowserSession"]] = None
    _health_check_task: ClassVar[Optional[asyncio.Task]] = None
    _auto_restart: ClassVar[bool] = True
    _health_check_interval: ClassVar[int] = 5  # seconds
    _restart_delay: ClassVar[float] = 1.0  # seconds
    _close_on_daemon_exit: ClassVar[bool] = True
    _daemon_config: ClassVar[Optional[Dict[str, Any]]] = None
    _browser_pid: ClassVar[Optional[int]] = None
    _cdp_url: ClassVar[Optional[str]] = None
    _ami_dir: ClassVar[Path] = Path.home() / ".ami"

    # Bug #18 fix: Restart retry tracking
    _restart_attempts: ClassVar[int] = 0
    _max_restart_attempts: ClassVar[int] = 5
    _max_restart_delay: ClassVar[float] = 30.0  # Max delay with exponential backoff

    # Shared browser resources for non-daemon mode
    # When no daemon exists, the first session to launch a browser becomes the "primary"
    # and other sessions can reuse its browser resources
    _primary_session: ClassVar[Optional["HybridBrowserSession"]] = None

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
        self._browser_launcher: Optional[Any] = None

        # Dictionary-based tab management with monotonic IDs
        self._pages: Dict[str, Page] = {}
        self._console_logs: Dict[str, Any] = {}
        self._current_tab_id: Optional[str] = None
        self.log_limit: int = ConfigLoader.get_max_log_limit() or 1000

        self.snapshot: Optional[PageSnapshot] = None
        self.executor: Optional[ActionExecutor] = None

        # Tab Group management (V3)
        self._tab_groups: Dict[str, TabGroup] = {}
        self._color_index: int = 0

        self._ensure_lock: asyncio.Lock = asyncio.Lock()

        # Load stealth config on initialization (class-level cache)
        self._stealth_script: Optional[str] = None
        self._stealth_config: Optional[Dict[str, Any]] = None
        if self._stealth:
            if self.__class__._stealth_config_cache is None:
                self.__class__._stealth_config_cache = ConfigLoader.get_browser_config().get_stealth_config()
            self._stealth_config = self.__class__._stealth_config_cache

    def _find_chrome_executable(self) -> Optional[str]:
        """Find system Chrome executable path.

        Returns path to Chrome or None if not found.
        Priority: System Chrome > Playwright bundled Chromium
        """
        import platform
        import os

        system = platform.system()

        if system == "Darwin":  # macOS
            paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ]
        elif system == "Windows":
            paths = [
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
            ]
        else:  # Linux
            paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]

        for path in paths:
            if os.path.exists(path):
                logger.info(f"Found system Chrome: {path}")
                return path

        # Fallback: let Playwright use its bundled Chromium
        logger.warning("System Chrome not found, will use Playwright bundled Chromium")
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
        new_page = await self._context.new_page()
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

    async def close_tab(self, tab_id: str) -> bool:
        """Close a specific tab by ID.

        Also removes the tab from any Tab Group it belongs to.
        """
        if tab_id not in self._pages:
            logger.warning(f"Invalid tab ID: {tab_id}")
            return False

        page = self._pages[tab_id]

        try:
            if not page.is_closed():
                await page.close()

            del self._pages[tab_id]

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

        V3: First tries to use daemon session's browser if available.
        Then tries to use primary session's browser (non-daemon mode).
        Otherwise launches new browser via subprocess + CDP.
        """
        from playwright.async_api import async_playwright
        from .browser_launcher import BrowserLauncher

        if self._page is not None:
            return

        # V3: Try to reuse daemon session's browser
        daemon = self.__class__._daemon_session
        if daemon and daemon._context and daemon._browser and daemon._browser.is_connected():
            logger.info("Reusing daemon session's browser")

            # Share browser resources
            self._playwright = daemon._playwright
            self._browser = daemon._browser
            self._context = daemon._context
            self._browser_launcher = daemon._browser_launcher

            # Bug #19 fix: Create initial page in Tab Group using session_id as task_id
            # This ensures all tabs created by this session are grouped together
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
                    self._page,
                    self,
                    default_timeout=self._default_timeout,
                    short_timeout=self._short_timeout,
                )

                logger.info(f"Browser session initialized (reusing daemon browser, Tab Group: {self._session_id})")
                return
            except Exception as e:
                # Context/browser became invalid, clear references and fall through to launch new browser
                logger.warning(f"Failed to reuse daemon browser (context may be closed): {e}")
                self._playwright = None
                self._browser = None
                self._context = None
                self._browser_launcher = None
                # Also clear daemon session's invalid state to trigger restart
                daemon._context = None
                daemon._browser = None

        # Non-daemon mode: Try to reuse primary session's browser
        primary = self.__class__._primary_session
        if primary and primary is not self and primary._context and primary._browser and primary._browser.is_connected():
            logger.info("Reusing primary session's browser (non-daemon mode)")

            # Share browser resources
            self._playwright = primary._playwright
            self._browser = primary._browser
            self._context = primary._context
            self._browser_launcher = primary._browser_launcher

            # Create a new page for this session
            try:
                self._page = await self._context.new_page()
                initial_tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(initial_tab_id, self._page)
                self._current_tab_id = initial_tab_id

                self._page.set_default_navigation_timeout(self._navigation_timeout)
                self._page.set_default_timeout(self._navigation_timeout)

                self.snapshot = PageSnapshot(self._page)
                self.executor = ActionExecutor(
                    self._page,
                    self,
                    default_timeout=self._default_timeout,
                    short_timeout=self._short_timeout,
                )

                logger.info(f"Browser session initialized (reusing primary session's browser)")
                return
            except Exception as e:
                # Context/browser became invalid, clear references and fall through to launch new browser
                logger.warning(f"Failed to reuse primary browser (context may be closed): {e}")
                self._playwright = None
                self._browser = None
                self._context = None
                self._browser_launcher = None

        # Launch browser via subprocess (no Playwright launch fingerprints)
        # Add retry mechanism for first browser startup (问题 9)
        max_retries = 3
        retry_delay = 2.0
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Creating BrowserLauncher (headless={self._headless}, user_data_dir={self._user_data_dir}, attempt {attempt + 1}/{max_retries})")
                self._browser_launcher = BrowserLauncher(
                    headless=self._headless,
                    user_data_dir=self._user_data_dir,
                    enable_stealth=self._stealth,
                )

                cdp_url = await self._browser_launcher.launch()
                logger.info(f"Browser launched via subprocess, CDP URL: {cdp_url}")

                # Connect to browser via Playwright's CDP connection
                # Bypass proxy for localhost (fixes Clash/proxy software interference with Node.js driver)
                import os
                os.environ.setdefault('NO_PROXY', '127.0.0.1,localhost')
                os.environ.setdefault('no_proxy', '127.0.0.1,localhost')

                logger.info("Starting Playwright...")
                self._playwright = await async_playwright().start()
                logger.info(f"Playwright started, connecting to CDP at {cdp_url}...")

                self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
                logger.info("Playwright connected via CDP successfully")

                # Success - break out of retry loop
                break

            except Exception as e:
                last_error = e
                logger.warning(f"Browser startup attempt {attempt + 1}/{max_retries} failed: {e}")

                # Clean up on failure
                if self._playwright:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass
                    self._playwright = None
                if self._browser_launcher:
                    try:
                        await self._browser_launcher.close()
                    except Exception:
                        pass
                    self._browser_launcher = None

                if attempt < max_retries - 1:
                    logger.info(f"Retrying browser startup in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    logger.error(f"Failed to launch browser after {max_retries} attempts")
                    raise RuntimeError(f"Failed to launch browser after {max_retries} attempts: {last_error}") from last_error

        # Get the default context (created by Chrome)
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        # Listen for new pages (tabs/popups) opened by any means (JS, target="_blank", etc.)
        self._context.on("page", self._on_new_page)

        # Get existing pages or create new one
        pages = self._context.pages
        if pages:
            self._page = pages[0]
            initial_tab_id = await TabIdGenerator.generate_tab_id()
            await self._register_new_page(initial_tab_id, pages[0])
            self._current_tab_id = initial_tab_id
            for page in pages[1:]:
                tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(tab_id, page)
        else:
            self._page = await self._context.new_page()
            initial_tab_id = await TabIdGenerator.generate_tab_id()
            await self._register_new_page(initial_tab_id, self._page)
            self._current_tab_id = initial_tab_id

        self._page.set_default_navigation_timeout(self._navigation_timeout)
        self._page.set_default_timeout(self._navigation_timeout)

        self.snapshot = PageSnapshot(self._page)
        self.executor = ActionExecutor(
            self._page,
            self,
            default_timeout=self._default_timeout,
            short_timeout=self._short_timeout,
        )

        # Register as primary session if no daemon and no primary exists
        if self.__class__._daemon_session is None and self.__class__._primary_session is None:
            self.__class__._primary_session = self
            logger.info("Registered as primary session for browser sharing")

        logger.info("Browser session initialized successfully (subprocess + CDP)")

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

    async def _close_session(self) -> None:
        """Internal session close logic with thorough cleanup.

        Closes resources in order: pages -> context -> browser -> playwright.
        Each step waits for completion to avoid Chrome crash on macOS.
        """
        try:
            # Step 1: Close all pages gracefully
            pages_to_close = list(self._pages.values())
            for page in pages_to_close:
                try:
                    if not page.is_closed():
                        await page.close()
                        await asyncio.sleep(0.1)  # Small delay between page closes
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")

            self._pages.clear()
            self._page = None

            # Wait for pages to fully close
            await asyncio.sleep(0.2)

            # Step 2: Close context
            if self._context:
                try:
                    await self._context.close()
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
                finally:
                    self._context = None

            # Step 3: Close browser gracefully
            if self._browser:
                try:
                    # Check if browser is still connected before closing
                    if self._browser.is_connected():
                        await self._browser.close()
                        # Wait for browser process to terminate gracefully
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")
                finally:
                    self._browser = None

            # Step 4: Stop playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")
                finally:
                    self._playwright = None

            # Step 5: Close browser launcher (kills subprocess)
            if self._browser_launcher:
                try:
                    await self._browser_launcher.close()
                except Exception as e:
                    logger.warning(f"Error closing browser launcher: {e}")
                finally:
                    self._browser_launcher = None

        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
        finally:
            self._page = None
            self._pages = {}
            self._current_tab_id = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._browser_launcher = None

    @classmethod
    async def close_all_sessions(cls) -> None:
        """Close all browser sessions and clean up the singleton registry."""
        logger.debug("Closing all browser sessions...")
        async with cls._instances_lock:
            instances_to_close = list(cls._instances.values())
            cls._instances.clear()

        for instance in instances_to_close:
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
    # Daemon Lifecycle Management (V3)
    # =========================================================================

    @classmethod
    async def start_daemon_session(
        cls,
        config: Optional[Dict[str, Any]] = None,
    ) -> "HybridBrowserSession":
        """Start daemon-level browser session

        Called by Daemon on startup. Initializes the global browser session:
        1. Check for existing browser, reconnect if found
        2. Otherwise launch new browser
        3. Start health check loop

        Args:
            config: Configuration dict with browser settings

        Returns:
            The daemon session instance
        """
        if cls._daemon_session is not None:
            logger.warning("Daemon session already exists, returning existing session")
            return cls._daemon_session

        logger.info("Starting daemon browser session...")

        # Store config
        cls._daemon_config = config or {}

        # Load config values
        browser_config = cls._daemon_config.get("browser", {}) if cls._daemon_config else {}
        cls._auto_restart = browser_config.get("auto_restart", True)
        cls._health_check_interval = browser_config.get("health_check_interval", 5)
        cls._restart_delay = browser_config.get("restart_delay", 1.0)
        cls._close_on_daemon_exit = browser_config.get("close_on_daemon_exit", True)

        headless = browser_config.get("headless", False)
        user_data_dir = browser_config.get("user_data_dir")

        # Create session instance
        session = cls(
            session_id="daemon",
            headless=headless,
            user_data_dir=user_data_dir,
            stealth=True,
        )

        # Check for existing browser
        existing_cdp_url = await cls._find_existing_browser()

        if existing_cdp_url:
            logger.info(f"Found existing browser, reconnecting to {existing_cdp_url}")
            try:
                await session._connect_to_existing(existing_cdp_url)
                logger.info("Reconnected to existing browser successfully")
            except Exception as e:
                logger.warning(f"Failed to reconnect to existing browser: {e}")
                logger.info("Will launch new browser instead")
                await session._cleanup_failed_connection()
                await session.ensure_browser()
        else:
            logger.info("No existing browser found, launching new browser")
            await session.ensure_browser()

        # Write lock file
        await cls._write_lock_file(session)

        # Store as daemon session
        cls._daemon_session = session

        # Register in singleton registry with special daemon key
        try:
            loop = asyncio.get_running_loop()
            loop_id = str(id(loop))
        except RuntimeError:
            import threading
            loop_id = f"sync_{threading.current_thread().ident}"

        async with cls._instances_lock:
            cls._instances[(loop_id, "daemon")] = session

        # Lazy mode: No health check - browser will be restarted when needed
        # cls._start_health_check()

        logger.info("Daemon browser session started successfully")
        return session

    @classmethod
    async def stop_daemon_session(cls, force: bool = False) -> None:
        """Stop daemon-level browser session

        Called by Daemon on shutdown.

        Args:
            force: If True, always close browser. If False, respect close_on_daemon_exit config.
        """
        logger.info("Stopping daemon browser session...")

        # Stop health check
        cls._stop_health_check()

        # Decide whether to close browser
        should_close = force or cls._close_on_daemon_exit

        if cls._daemon_session:
            if should_close:
                logger.info("Closing browser...")
                await cls._daemon_session._close_session()
                await cls._remove_lock_file()
            else:
                logger.info("Keeping browser running (close_on_daemon_exit=False)")
                # Just disconnect, don't close
                if cls._daemon_session._playwright:
                    try:
                        await cls._daemon_session._playwright.stop()
                    except Exception as e:
                        logger.warning(f"Error stopping playwright: {e}")
                    cls._daemon_session._playwright = None
                cls._daemon_session._browser = None
                cls._daemon_session._context = None

            # Clear instance references
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
        """Get the daemon-level browser session

        Returns:
            The daemon session or None if not started
        """
        return cls._daemon_session

    # =========================================================================
    # Health Check (V3)
    # =========================================================================

    @classmethod
    def _start_health_check(cls) -> None:
        """Start health check loop"""
        if cls._health_check_task and not cls._health_check_task.done():
            return  # Already running

        cls._health_check_task = asyncio.create_task(cls._health_check_loop())
        logger.debug("Health check started")

    @classmethod
    def _stop_health_check(cls) -> None:
        """Stop health check loop"""
        if cls._health_check_task:
            cls._health_check_task.cancel()
            cls._health_check_task = None
            logger.debug("Health check stopped")

    @classmethod
    async def _health_check_loop(cls) -> None:
        """Health check loop - monitors browser status"""
        logger.debug("Health check loop started")

        while True:
            try:
                await asyncio.sleep(cls._health_check_interval)

                if not cls._daemon_session:
                    continue

                # Check process alive
                if not cls._check_process_alive():
                    logger.warning("Browser process died")
                    await cls._handle_browser_closed()
                    continue

                # Check CDP connection
                if not await cls._check_cdp_alive():
                    logger.warning("CDP connection lost")
                    await cls._handle_connection_lost()
                    continue

            except asyncio.CancelledError:
                logger.debug("Health check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(1)

    @classmethod
    def _check_process_alive(cls) -> bool:
        """Check if browser process is alive"""
        if not cls._browser_pid:
            return False

        try:
            import psutil
            return psutil.pid_exists(cls._browser_pid)
        except ImportError:
            # Fallback: try os.kill with signal 0
            import os
            import signal
            try:
                os.kill(cls._browser_pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

    @classmethod
    async def _check_cdp_alive(cls) -> bool:
        """Check if CDP is responding"""
        if not cls._cdp_url:
            return False

        try:
            # Extract port from CDP URL (ws://localhost:9222/devtools/...)
            match = re.search(r':(\d+)', cls._cdp_url)
            if not match:
                return False
            port = match.group(1)
            http_url = f"http://127.0.0.1:{port}/json/version"

            # Use trust_env=False to bypass system proxy for localhost
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(http_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except Exception:
            return False

    @classmethod
    async def _handle_browser_closed(cls) -> None:
        """Handle browser being closed by user.

        Bug #18 fix: Implements retry limit with exponential backoff.
        """
        if not cls._auto_restart:
            logger.info("Browser closed, auto-restart disabled")
            return

        # Check retry limit
        cls._restart_attempts += 1
        if cls._restart_attempts > cls._max_restart_attempts:
            logger.error(f"Browser restart failed after {cls._max_restart_attempts} attempts, giving up")
            cls._restart_attempts = 0  # Reset for potential manual restart
            return

        # Calculate delay with exponential backoff
        delay = min(cls._restart_delay * (2 ** (cls._restart_attempts - 1)), cls._max_restart_delay)
        logger.info(f"Browser closed, restarting in {delay:.1f}s (attempt {cls._restart_attempts}/{cls._max_restart_attempts})...")
        await asyncio.sleep(delay)

        if cls._daemon_session:
            # Clear old state
            cls._daemon_session._page = None
            cls._daemon_session._pages = {}
            cls._daemon_session._console_logs = {}  # Bug #14 fix: Clear console logs
            cls._daemon_session._context = None
            cls._daemon_session._browser = None
            cls._daemon_session._playwright = None
            cls._daemon_session._browser_launcher = None
            cls._daemon_session._tab_groups = {}

            try:
                # Relaunch browser
                await cls._daemon_session.ensure_browser()
                await cls._write_lock_file(cls._daemon_session)
                logger.info("Browser restarted successfully")

                # Reset retry counter on success
                cls._restart_attempts = 0

            except Exception as e:
                logger.error(f"Failed to restart browser (attempt {cls._restart_attempts}): {e}")

    @classmethod
    async def _handle_connection_lost(cls) -> None:
        """Handle CDP connection lost

        Attempts to reconnect to existing browser via CDP.
        If reconnection fails, falls back to browser restart.
        """
        # Try to reconnect first
        if cls._cdp_url:
            # Bug #5 fix: Initialize playwright to None before try block
            playwright = None
            try:
                from playwright.async_api import async_playwright

                # Bug #6 fix: Close old playwright instance before creating new one
                old_playwright = None
                if cls._daemon_session:
                    old_playwright = cls._daemon_session._playwright

                # Create new playwright instance
                playwright = await async_playwright().start()
                browser = await playwright.chromium.connect_over_cdp(cls._cdp_url)

                if cls._daemon_session:
                    # Close old playwright to prevent resource leak
                    if old_playwright:
                        try:
                            await old_playwright.stop()
                            logger.debug("Closed old playwright instance")
                        except Exception as e:
                            logger.warning(f"Error closing old playwright: {e}")

                    cls._daemon_session._playwright = playwright
                    cls._daemon_session._browser = browser
                    if browser.contexts:
                        cls._daemon_session._context = browser.contexts[0]
                        # Re-register page event listener
                        cls._daemon_session._context.on("page", cls._daemon_session._on_new_page)

                logger.info("CDP connection restored")
                return
            except Exception as e:
                logger.warning(f"Failed to reconnect CDP: {e}")
                # Clean up the new playwright if connection failed
                if playwright:
                    try:
                        await playwright.stop()
                    except Exception:
                        pass

        # If reconnect fails, treat as browser closed
        await cls._handle_browser_closed()

    # =========================================================================
    # Lock File Management (V3)
    # =========================================================================

    @classmethod
    def _get_lock_file_path(cls) -> Path:
        """Get lock file path"""
        return cls._ami_dir / LOCK_FILE_NAME

    @classmethod
    async def _find_existing_browser(cls) -> Optional[str]:
        """Find existing browser instance.

        Strategy:
        1. Check lock file first (fast path)
        2. If no lock file, scan processes via pgrep (fallback for unclean shutdown)

        Returns:
            CDP URL if found, None otherwise
        """
        # Strategy 1: Lock file
        lock_file = cls._get_lock_file_path()

        if lock_file.exists():
            try:
                lock_data = json.loads(lock_file.read_text())
                pid = lock_data.get("pid")
                cdp_url = lock_data.get("cdp_url")

                if not pid or not cdp_url:
                    logger.debug("Invalid lock file data")
                    lock_file.unlink()
                else:
                    # Check if process is alive
                    process_alive = False
                    try:
                        import psutil
                        process_alive = psutil.pid_exists(pid)
                    except ImportError:
                        import os
                        try:
                            os.kill(pid, 0)
                            process_alive = True
                        except (OSError, ProcessLookupError):
                            pass

                    if not process_alive:
                        logger.debug(f"Process {pid} not found")
                        lock_file.unlink()
                    elif await cls._check_cdp_alive_url(cdp_url):
                        # Store for later use
                        cls._browser_pid = pid
                        cls._cdp_url = cdp_url
                        return cdp_url
                    else:
                        logger.debug("CDP not responding, lock file stale")
                        lock_file.unlink()

            except Exception as e:
                logger.warning(f"Error reading lock file: {e}")
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        # Strategy 2: Process scanning (non-destructive)
        # Handles case where daemon exited without cleaning up lock file
        # but Chrome is still running with CDP enabled
        browser_config = cls._daemon_config.get("browser", {}) if cls._daemon_config else {}
        user_data_dir = browser_config.get("user_data_dir")
        if not user_data_dir:
            return None

        return await cls._find_chrome_by_process(user_data_dir)

    @classmethod
    async def _find_chrome_by_process(cls, user_data_dir: str) -> Optional[str]:
        """Find existing Chrome instance by scanning processes (non-destructive).

        Only matches Chrome processes using the exact user_data_dir (e.g. ~/.ami/browser_data).
        User's personal Chrome (~/Library/Application Support/Google/Chrome) is never affected.

        This method NEVER kills processes — it only detects and returns CDP URL for reuse.

        Returns:
            CDP URL if a reusable Chrome instance is found, None otherwise.
        """
        import subprocess
        import platform

        try:
            if platform.system() not in ("Darwin", "Linux"):
                return None

            result = subprocess.run(
                ["pgrep", "-f", f"--user-data-dir={user_data_dir}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if not result.stdout.strip():
                logger.debug("No Chrome process found for this profile via pgrep")
                return None

            pids = result.stdout.strip().split("\n")
            logger.info(f"Process scan: found {len(pids)} process(es) using {user_data_dir}")

            for pid in pids:
                try:
                    pid_int = int(pid.strip())
                    cmd_result = subprocess.run(
                        ["ps", "-p", str(pid_int), "-o", "args="],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    cmdline = cmd_result.stdout.strip()

                    port_match = re.search(r"--remote-debugging-port=(\d+)", cmdline)
                    if port_match:
                        existing_port = int(port_match.group(1))
                        cdp_url = f"http://127.0.0.1:{existing_port}"

                        if await cls._check_cdp_alive_url(cdp_url):
                            logger.info(
                                f"Found existing Chrome via process scan at {cdp_url} (PID {pid_int})"
                            )
                            cls._browser_pid = pid_int
                            cls._cdp_url = cdp_url
                            return cdp_url
                        else:
                            logger.debug(f"Chrome PID {pid_int} has CDP port {existing_port} but not responding")

                except (ValueError, subprocess.TimeoutExpired):
                    continue

            logger.debug("No reusable Chrome instance found via process scan")
            return None

        except FileNotFoundError:
            logger.debug("pgrep not available")
            return None
        except Exception as e:
            logger.warning(f"Error scanning Chrome processes: {e}")
            return None

    @classmethod
    async def _check_cdp_alive_url(cls, cdp_url: str) -> bool:
        """Check if CDP at given URL is alive"""
        try:
            match = re.search(r':(\d+)', cdp_url)
            if not match:
                return False
            port = match.group(1)
            http_url = f"http://127.0.0.1:{port}/json/version"

            # Use trust_env=False to bypass system proxy for localhost
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(http_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except Exception:
            return False

    @classmethod
    async def _write_lock_file(cls, session: "HybridBrowserSession") -> None:
        """Write lock file with browser info"""
        lock_file = cls._get_lock_file_path()
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Get PID from browser launcher (supports both launched and reused browsers)
        pid = None
        if session._browser_launcher:
            pid = session._browser_launcher.browser_pid

        # Get CDP URL
        cdp_url = None
        if session._browser_launcher:
            cdp_url = session._browser_launcher.cdp_url

        if pid and cdp_url:
            cls._browser_pid = pid
            cls._cdp_url = cdp_url

            lock_data = {
                "pid": pid,
                "cdp_url": cdp_url,
                "started_at": datetime.now().isoformat()
            }
            lock_file.write_text(json.dumps(lock_data, indent=2))
            logger.debug(f"Lock file written: {lock_file}")
        else:
            logger.warning(f"Could not write lock file: pid={pid}, cdp_url={cdp_url}")

    @classmethod
    async def _remove_lock_file(cls) -> None:
        """Remove lock file"""
        lock_file = cls._get_lock_file_path()
        if lock_file.exists():
            try:
                lock_file.unlink()
                logger.debug("Lock file removed")
            except Exception as e:
                logger.warning(f"Failed to remove lock file: {e}")

        cls._browser_pid = None
        cls._cdp_url = None

    # =========================================================================
    # Reconnection (V3)
    # =========================================================================

    async def _connect_to_existing(self, cdp_url: str) -> None:
        """Reconnect to existing browser instance"""
        from playwright.async_api import async_playwright

        logger.info(f"Connecting to existing browser at {cdp_url}")

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)

            # Get existing context
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
                logger.info(f"Using existing context with {len(self._context.pages)} pages")
            else:
                self._context = await self._browser.new_context()
                logger.info("Created new context")

            # Listen for new pages
            self._context.on("page", self._on_new_page)

            # Register existing pages
            pages = self._context.pages
            if pages:
                self._page = pages[0]
                initial_tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(initial_tab_id, pages[0])
                self._current_tab_id = initial_tab_id

                for page in pages[1:]:
                    tab_id = await TabIdGenerator.generate_tab_id()
                    await self._register_new_page(tab_id, page)
            else:
                self._page = await self._context.new_page()
                initial_tab_id = await TabIdGenerator.generate_tab_id()
                await self._register_new_page(initial_tab_id, self._page)
                self._current_tab_id = initial_tab_id

            # Setup snapshot and executor
            self._page.set_default_navigation_timeout(self._navigation_timeout)
            self._page.set_default_timeout(self._navigation_timeout)
            self.snapshot = PageSnapshot(self._page)
            self.executor = ActionExecutor(
                self._page,
                self,
                default_timeout=self._default_timeout,
                short_timeout=self._short_timeout,
            )

            logger.info("Reconnected to existing browser successfully")

        except Exception as e:
            # Clean up on failure
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            raise

    async def _cleanup_failed_connection(self) -> None:
        """Clean up after failed connection attempt"""
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._pages = {}

    # =========================================================================
    # Tab Group Management (V3) - Internal tracking only
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

        # Close all pages in the group
        for tab_id, page in list(group.tabs.items()):
            try:
                if not page.is_closed():
                    await page.close()
                # Also remove from main _pages dict
                if tab_id in self._pages:
                    del self._pages[tab_id]
            except Exception as e:
                logger.warning(f"Error closing tab {tab_id}: {e}")

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

        # Create page - validate context is still connected
        if not self._context:
            raise RuntimeError("Browser context not available")
        if not self._browser or not self._browser.is_connected():
            raise RuntimeError("Browser is disconnected")

        page = await self._context.new_page()

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
            if not page.is_closed():
                await page.close()
        except Exception as e:
            logger.warning(f"Error closing tab {tab_id}: {e}")

        del group.tabs[tab_id]

        # Also remove from main _pages dict
        if tab_id in self._pages:
            del self._pages[tab_id]

        # Update current tab if needed
        if group.current_tab_id == tab_id:
            if group.tabs:
                group.current_tab_id = next(iter(group.tabs.keys()))
            else:
                group.current_tab_id = None

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
