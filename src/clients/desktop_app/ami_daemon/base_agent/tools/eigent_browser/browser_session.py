"""
HybridBrowserSession - Lightweight wrapper around Playwright for browsing with multi-tab support.

Ported from CAMEL-AI/Eigent project.
"""

from __future__ import annotations

import asyncio
from collections import deque
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
    """

    # Class-level registry for singleton instances
    _instances: ClassVar[Dict[Tuple[Any, str], "HybridBrowserSession"]] = {}
    _instances_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

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
                existing_instance = cls._instances[session_key]
                logger.debug(f"Reusing existing browser session for session_id: {session_id}")
                return existing_instance

            cls._instances[session_key] = instance
            logger.debug(f"Created new browser session for session_id: {session_id}")
            return instance

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

        self._ensure_lock: asyncio.Lock = asyncio.Lock()

        # Load stealth config on initialization
        self._stealth_script: Optional[str] = None
        self._stealth_config: Optional[Dict[str, Any]] = None
        if self._stealth:
            self._stealth_config = ConfigLoader.get_browser_config().get_stealth_config()

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
            self._console_logs.pop(tab_id, None)

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
            # Check if already registered
            for existing_page in self._pages.values():
                if existing_page is page:
                    logger.debug("Page already registered, skipping")
                    return

            tab_id = await TabIdGenerator.generate_tab_id()
            await self._register_new_page(tab_id, page)
            logger.info(f"[Auto] Registered new tab {tab_id} (opened by page event). Total tabs: {len(self._pages)}")

        # Schedule the async registration
        asyncio.create_task(register())

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
        """Close a specific tab by ID."""
        if tab_id not in self._pages:
            logger.warning(f"Invalid tab ID: {tab_id}")
            return False

        page = self._pages[tab_id]

        try:
            if not page.is_closed():
                await page.close()

            del self._pages[tab_id]

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

        Uses subprocess to launch Chrome, then connects via Playwright CDP.
        This avoids Playwright's launch fingerprints.
        """
        from playwright.async_api import async_playwright
        from .browser_launcher import BrowserLauncher

        if self._page is not None:
            return

        # Launch browser via subprocess (no Playwright launch fingerprints)
        logger.info(f"Creating BrowserLauncher (headless={self._headless}, user_data_dir={self._user_data_dir})")
        self._browser_launcher = BrowserLauncher(
            headless=self._headless,
            user_data_dir=self._user_data_dir,
            enable_stealth=self._stealth,
            enable_extensions=self._stealth and not self._headless,
        )

        try:
            cdp_url = await self._browser_launcher.launch()
            logger.info(f"Browser launched via subprocess, CDP URL: {cdp_url}")
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            # Clean up launcher on failure
            if self._browser_launcher:
                try:
                    await self._browser_launcher.close()
                except Exception:
                    pass
                self._browser_launcher = None
            raise

        # Connect to browser via Playwright's CDP connection
        logger.info("Starting Playwright...")
        self._playwright = await async_playwright().start()
        logger.info(f"Playwright started, connecting to CDP at {cdp_url}...")

        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            logger.info("Playwright connected via CDP successfully")
        except Exception as e:
            logger.error(f"Failed to connect Playwright to CDP: {e}")
            # Clean up on connection failure
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
            raise

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
