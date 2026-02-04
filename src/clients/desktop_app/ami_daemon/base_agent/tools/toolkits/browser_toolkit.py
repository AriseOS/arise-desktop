"""
BrowserToolkit - Browser automation tools for agents.

Wraps the existing HybridBrowserSession to provide Tool-calling compatible
browser operations. Ported from CAMEL-AI/Eigent project architecture.

All methods are async to work properly in async execution contexts.
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...events.action_types import ScreenshotData

if TYPE_CHECKING:
    from ..eigent_browser.browser_session import HybridBrowserSession

logger = logging.getLogger(__name__)


class BrowserPageClosedError(Exception):
    """Raised when the browser page was closed and had to be recovered.

    This exception carries a user-friendly message that should be returned
    to the Agent so it knows to re-navigate to the target page.
    """
    pass


class BrowserToolkit(BaseToolkit):
    """A toolkit for browser automation.

    Provides tools for web navigation, interaction, and content extraction.
    Each tool returns a page snapshot after execution for LLM context.

    All methods are async for proper integration with async agent loops.
    Uses @listen_toolkit for automatic event emission on public methods.

    Session Management:
        Uses session_id for on-demand browser session creation.
        Session is created when the first browser tool is called, using
        HybridBrowserSession's singleton mechanism. Multiple toolkit instances
        with the same session_id share the same browser instance, making this
        clone-safe for CAMEL's agent pooling.

    Tool Filtering:
        Use `enabled_tools` parameter to control which tools are exposed to the LLM.
        This reduces request payload size and focuses the LLM on relevant actions.

        Example:
            toolkit = BrowserToolkit(
                session_id="task_123",
                headless=False,
                enabled_tools=[
                    "browser_visit_page",
                    "browser_click",
                    "browser_type",
                    "browser_enter",
                    "browser_get_page_snapshot",
                ])
    """

    # Agent name for event tracking
    agent_name: str = "browser_agent"

    # Default tools to enable (matches Eigent's enabled_tools for browser_agent)
    DEFAULT_ENABLED_TOOLS = [
        "browser_visit_page",
        "browser_click",
        "browser_type",
        "browser_back",
        "browser_forward",
        "browser_select",
        "browser_switch_tab",
        "browser_enter",
        "browser_get_page_snapshot",
        "browser_scroll",
    ]

    # All available tools
    ALL_TOOLS = [
        "browser_visit_page",
        "browser_back",
        "browser_forward",
        "browser_scroll",
        "browser_click",
        "browser_type",
        "browser_enter",
        "browser_select",
        "browser_press_key",
        "browser_mouse_control",
        "browser_get_page_snapshot",
        "browser_get_tab_info",
        "browser_switch_tab",
        "browser_new_tab",
        "browser_close_tab",
    ]

    def __init__(
        self,
        session_id: str,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        timeout: Optional[float] = 30.0,
        return_snapshot: bool = True,
        enabled_tools: Optional[List[str]] = None,
        agent: Optional[Any] = None,  # ListenChatAgent for URL change notifications
    ) -> None:
        """Initialize the BrowserToolkit.

        Args:
            session_id: Session identifier for browser session management.
                Same session_id across multiple toolkit instances/clones will share
                the same browser session via HybridBrowserSession's singleton mechanism.
            headless: Whether to run browser in headless mode.
            user_data_dir: Browser user data directory.
            timeout: Default timeout for browser operations.
            return_snapshot: Whether to return page snapshot after each action.
            enabled_tools: List of tool names to enable. If None, uses DEFAULT_ENABLED_TOOLS.
                Only tools in this list will be returned by get_tools().
            agent: Optional ListenChatAgent for URL change notifications.
                When provided, BrowserToolkit will call agent.set_current_url()
                after each browser action to enable IntentSequence cache management.
        """
        super().__init__(timeout=timeout)
        self._return_snapshot = return_snapshot

        # Session configuration (session retrieved on-demand via singleton)
        self._session_id = session_id
        self._headless = headless
        self._user_data_dir = user_data_dir

        # Agent reference for URL change notifications (IntentSequence cache)
        self._agent = agent

        # Set enabled tools
        if enabled_tools is None:
            self._enabled_tools = self.DEFAULT_ENABLED_TOOLS.copy()
        else:
            # Validate tool names
            invalid_tools = [t for t in enabled_tools if t not in self.ALL_TOOLS]
            if invalid_tools:
                logger.warning(f"Unknown tool names will be ignored: {invalid_tools}")
            self._enabled_tools = [t for t in enabled_tools if t in self.ALL_TOOLS]

        logger.info(f"BrowserToolkit initialized (session_id={session_id}, enabled_tools={len(self._enabled_tools)})")

    def set_agent(self, agent: Any) -> None:
        """Set the agent reference for URL change notifications.

        This enables IntentSequence cache management in ListenChatAgent.
        Should be called when the toolkit is registered with an agent.

        Args:
            agent: ListenChatAgent instance with set_current_url() method.
        """
        self._agent = agent
        logger.debug(f"BrowserToolkit: agent reference set for URL notifications")

    async def _notify_url_change(self) -> None:
        """Notify the agent of current URL for IntentSequence cache management.

        Called after each browser action to enable:
        - Cache invalidation when URL changes
        - Page operations cache injection
        """
        if not self._agent or not hasattr(self._agent, 'set_current_url'):
            return

        try:
            session = await self._get_session_with_page()
            page = await session.get_page()
            current_url = page.url
            self._agent.set_current_url(current_url)
            logger.debug(f"BrowserToolkit: notified agent of URL: {current_url[:50]}...")
        except Exception as e:
            logger.debug(f"BrowserToolkit: URL notification failed: {e}")

    async def _get_session(self) -> "HybridBrowserSession":
        """Get browser session using HybridBrowserSession's singleton mechanism.

        Each call creates a new HybridBrowserSession instance, but ensure_browser()
        returns the singleton for this session_id. This approach is clone-safe because
        we don't cache session references - each toolkit instance independently
        retrieves the shared session via the singleton registry.

        Note: This returns the session even if _page is closed. Methods that need
        a valid page should call _ensure_valid_page() separately.

        Returns:
            HybridBrowserSession instance (the actual singleton, not a copy).
        """
        from ..eigent_browser.browser_session import HybridBrowserSession

        # Create session instance - HybridBrowserSession's ensure_browser() handles
        # singleton lookup/creation internally via _get_or_create_instance()
        session = HybridBrowserSession(
            session_id=self._session_id,
            headless=self._headless,
            user_data_dir=self._user_data_dir,
            stealth=True,
        )
        await session.ensure_browser()

        # Return the actual singleton instance, not a copy
        # This ensures that any updates to _page are reflected globally
        singleton = await HybridBrowserSession._get_or_create_instance(session)
        return singleton

    async def _ensure_valid_page(self, session: "HybridBrowserSession") -> Tuple[bool, Optional[str]]:
        """Ensure session has a valid (non-closed) page.

        If current _page is closed, tries to switch to another valid page in _pages.
        If no valid pages exist, creates a new one.
        If browser/context is closed, restarts the browser (lazy mode).

        Uses retry logic to handle race conditions where user closes tabs quickly.

        Args:
            session: The browser session to check/fix.

        Returns:
            Tuple of (success, recovery_message):
            - success: True if a valid page is available
            - recovery_message: If not None, indicates page was recovered and Agent
              should be notified to re-navigate. None means page was already valid.
        """
        max_retries = 3
        browser_was_restarted = False
        page_was_recovered = False

        for attempt in range(max_retries):
            # Check if browser/context is still valid
            browser_valid = (
                session._browser is not None
                and session._context is not None
                and session._browser.is_connected()
            )
            if not browser_valid:
                logger.info("Browser/context is closed, restarting browser (lazy mode)")
                try:
                    await self._restart_browser(session)
                    browser_was_restarted = True
                except Exception as e:
                    logger.error(f"Failed to restart browser: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    return (False, None)

            # Check if current page is valid
            if session._page and not session._page.is_closed():
                # Page is valid - check if we had to recover
                if browser_was_restarted or page_was_recovered:
                    return (True, "The browser page was closed unexpectedly. A new page has been created. Please use browser_visit_page to navigate to your target URL.")
                return (True, None)

            # Try to find another valid page in _pages
            found_valid = False
            for tab_id, page in list(session._pages.items()):
                if not page.is_closed():
                    logger.info(f"Current page was closed, switching to existing tab {tab_id}")
                    session._page = page
                    session._current_tab_id = tab_id

                    # Re-initialize snapshot and executor with the existing page
                    from ..eigent_browser.page_snapshot import PageSnapshot
                    from ..eigent_browser.action_executor import ActionExecutor
                    session.snapshot = PageSnapshot(page)
                    session.executor = ActionExecutor(
                        page,
                        session,
                        default_timeout=session._default_timeout,
                        short_timeout=session._short_timeout,
                    )
                    found_valid = True
                    page_was_recovered = True
                    break

            if found_valid:
                # Verify the page is still valid after switching
                if session._page and not session._page.is_closed():
                    return (True, "Your previous browser tab was closed. Switched to another existing tab. Please check if this is the correct page or use browser_visit_page to navigate to your target URL.")
                else:
                    logger.warning(f"Switched page was closed immediately, retrying (attempt {attempt + 1}/{max_retries})")
                    continue

            # No valid pages exist - try to create a new one
            if session._context:
                logger.info("All pages closed, creating new page in existing context")
                try:
                    # Create new page - _on_new_page event will auto-register it
                    new_page = await session._context.new_page()

                    # Wait a moment for the event handler to register the page
                    await asyncio.sleep(0.1)

                    # Verify page is still valid (user might have closed it already)
                    if new_page.is_closed():
                        logger.warning(f"New page was closed immediately, retrying (attempt {attempt + 1}/{max_retries})")
                        continue

                    # Find the newly registered page in _pages
                    for tab_id, registered_page in session._pages.items():
                        if registered_page is new_page:
                            session._page = new_page
                            session._current_tab_id = tab_id

                            # Re-initialize snapshot and executor
                            from ..eigent_browser.page_snapshot import PageSnapshot
                            from ..eigent_browser.action_executor import ActionExecutor
                            session.snapshot = PageSnapshot(new_page)
                            session.executor = ActionExecutor(
                                new_page,
                                session,
                                default_timeout=session._default_timeout,
                                short_timeout=session._short_timeout,
                            )

                            new_page.set_default_navigation_timeout(session._navigation_timeout)
                            new_page.set_default_timeout(session._navigation_timeout)
                            page_was_recovered = True
                            return (True, "The browser page was closed. A new blank page has been created. Please use browser_visit_page to navigate to your target URL.")

                    logger.error("New page was not registered by event handler")
                except Exception as e:
                    logger.error(f"Failed to create new page: {e}")
                    # Context might be invalid, mark for restart and retry
                    session._context = None
                    continue

        logger.error(f"Failed to get valid page after {max_retries} attempts")
        return (False, None)

    async def _restart_browser(self, session: "HybridBrowserSession") -> None:
        """Restart browser when it's been closed.

        This implements lazy mode - browser is only restarted when needed.
        """
        from ..eigent_browser.browser_session import HybridBrowserSession

        logger.info("Restarting browser...")

        # Clear old state
        session._page = None
        session._pages = {}
        session._console_logs = {}
        session._context = None
        session._browser = None
        if session._playwright:
            try:
                await session._playwright.stop()
            except Exception:
                pass
        session._playwright = None
        session._browser_launcher = None
        session._tab_groups = {}

        # Re-initialize browser
        await session._ensure_browser_inner()

        # Update lock file if this is daemon session
        if session is HybridBrowserSession._daemon_session:
            await HybridBrowserSession._write_lock_file(session)

        logger.info("Browser restarted successfully")

    async def _get_session_with_page(self) -> "HybridBrowserSession":
        """Get browser session and ensure it has a valid page.

        This is a convenience method for operations that require a valid page.
        It combines _get_session() and _ensure_valid_page().

        Returns:
            HybridBrowserSession instance with a valid page.

        Raises:
            BrowserPageClosedError: If page was closed and had to be recovered.
            RuntimeError: If session cannot be created or no valid page available.
        """
        session = await self._get_session()
        page_was_recovered, recovery_message = await self._ensure_valid_page(session)
        if not page_was_recovered and not (session._page and not session._page.is_closed()):
            raise RuntimeError("Could not get a valid browser page")
        if recovery_message:
            raise BrowserPageClosedError(recovery_message)
        return session

    def _ensure_session(self) -> bool:
        """Check if session can be created (always True since session_id is required)."""
        return True

    async def _get_snapshot(self, force_refresh: bool = False) -> str:
        """Get current page snapshot if enabled.

        Args:
            force_refresh: If True, forces re-injection of aria-ref attributes.
                          Use after switching tabs or when refs may be stale.
        """
        if not self._return_snapshot:
            return ""
        try:
            session = await self._get_session_with_page()
        except Exception:
            return ""
        try:
            snapshot = await session.get_snapshot(force_refresh=force_refresh)
            return snapshot
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            return f"[Snapshot unavailable: {e}]"

    async def _get_page_context(self) -> str:
        """Get current page context (URL and title).

        This provides essential context about the current page state,
        following Eigent's pattern of including page info in every action result.

        Returns:
            Formatted string with current page URL and title.
        """
        try:
            session = await self._get_session_with_page()
        except Exception:
            return ""
        try:
            page = await session.get_page()
            url = page.url
            title = await page.title()
            return f"**Current Page:** {title}\n**URL:** {url}"
        except Exception as e:
            logger.debug(f"Failed to get page context: {e}")
            return ""

    async def get_page_title(self) -> str:
        """Get current page title.

        Returns:
            Page title string, or empty string if unavailable.
        """
        try:
            session = await self._get_session_with_page()
        except Exception:
            return ""
        try:
            page = await session.get_page()
            return await page.title()
        except Exception as e:
            logger.debug(f"Failed to get page title: {e}")
            return ""

    async def _wait_for_page_stability(self, timeout_ms: Optional[int] = None) -> None:
        """Wait for page to become stable after an action.

        This is important after click/type actions that may trigger:
        - Page navigation
        - New tab opening
        - AJAX content loading
        - SPA re-rendering

        Following Eigent's pattern for page stability:
        1. First wait for DOM content loaded
        2. Then try to wait for network idle (SPA apps need this)

        Args:
            timeout_ms: Timeout in milliseconds. If None, uses session's network_idle_timeout.
        """
        try:
            session = await self._get_session_with_page()
        except Exception:
            return

        # Use session's configured timeout if not specified
        if timeout_ms is None:
            timeout_ms = getattr(session, '_network_idle_timeout', None) or 5000

        try:
            page = await session.get_page()

            # Step 1: Wait for DOM content to be loaded
            await page.wait_for_load_state('domcontentloaded', timeout=timeout_ms)
            logger.debug("DOM content loaded")

            # Step 2: Try to wait for network idle (important for SPA)
            # This gives time for React/Vue/etc to finish rendering
            try:
                await page.wait_for_load_state('networkidle', timeout=timeout_ms)
                logger.debug("Network idle achieved")
            except Exception:
                # Network idle timeout is acceptable - SPA might keep connections open
                logger.debug(f"Network idle timeout after {timeout_ms}ms - continuing anyway")

        except Exception as e:
            logger.debug(f"Page stability wait interrupted: {e}")

    async def _get_tab_info_summary(self) -> str:
        """Get a summary of tab information for action results.

        Returns tab count and current tab info so LLM knows about tab changes.
        """
        session = await self._get_session()
        if not session:
            return ""

        try:
            tab_info = await session.get_tab_info()
            current_tab_id = await session.get_current_tab_id()

            if not tab_info:
                return ""

            total_tabs = len(tab_info)
            if total_tabs == 1:
                return ""  # Don't clutter output for single tab

            # Find current tab info
            current_tab = None
            for tab in tab_info:
                if tab.get("tab_id") == current_tab_id:
                    current_tab = tab
                    break

            current_title = current_tab.get("title", "Unknown")[:50] if current_tab else "Unknown"
            return f"**Tabs:** {total_tabs} open (current: {current_tab_id} - {current_title})"
        except Exception as e:
            logger.debug(f"Failed to get tab info: {e}")
            return ""

    async def _send_screenshot_event(self) -> None:
        """Capture and send screenshot to frontend via SSE.

        Following Eigent's pattern of sending browser screenshots for
        real-time display in the BrowserTab component.
        """
        if not hasattr(self, '_task_state') or self._task_state is None:
            return

        try:
            session = await self._get_session_with_page()
        except Exception:
            return

        try:
            page = await session.get_page()
            url = page.url
            title = await page.title()
            tab_id = await session.get_current_tab_id()

            # Capture screenshot as PNG bytes
            screenshot_bytes = await page.screenshot(type='jpeg', quality=80)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            screenshot_data_uri = f"data:image/jpeg;base64,{screenshot_base64}"

            # Send screenshot event to frontend
            state = self._task_state
            if hasattr(state, 'put_event'):
                await state.put_event(ScreenshotData(
                    task_id=getattr(state, 'task_id', None),
                    screenshot=screenshot_data_uri,
                    url=url,
                    page_title=title,
                    tab_id=tab_id,
                ))
                logger.debug(f"Screenshot event sent for {url}")

        except Exception as e:
            logger.warning(f"Failed to send screenshot event: {e}")

    async def _build_action_result(
        self,
        result_message: str,
        include_snapshot: bool = True,
        include_page_context: bool = True,
        include_tab_info: bool = True,
        wait_for_stability: bool = False,
        force_refresh: bool = False,
    ) -> str:
        """Build a standardized action result with page context and snapshot.

        Following Eigent's pattern, every browser action result includes:
        1. The action result message
        2. Tab information (if multiple tabs)
        3. Current page context (URL and title)
        4. Page snapshot (interactive elements)

        Additionally, sends a screenshot event to the frontend for BrowserTab display.

        Args:
            result_message: The main result message from the action.
            include_snapshot: Whether to include the page snapshot.
            include_page_context: Whether to include page URL/title.
            include_tab_info: Whether to include tab information.
            wait_for_stability: Whether to wait for page stability first.
            force_refresh: Whether to force re-injection of aria-ref attributes.
                          Use when switching tabs or after tab creation.

        Returns:
            Formatted result string with all components.
        """
        # Wait for page stability if requested (important after click/type)
        if wait_for_stability:
            await self._wait_for_page_stability()

        parts = [result_message]

        # Add tab info (important for LLM to know about tab changes)
        if include_tab_info:
            tab_info = await self._get_tab_info_summary()
            if tab_info:
                parts.append(tab_info)

        # Add page context (URL and title)
        if include_page_context:
            page_context = await self._get_page_context()
            if page_context:
                parts.append(page_context)

        # Add snapshot
        if include_snapshot:
            snapshot = await self._get_snapshot(force_refresh=force_refresh)
            if snapshot:
                parts.append(snapshot)

        # Send screenshot event to frontend for BrowserTab display
        # This is async but we don't wait for it to complete
        try:
            await self._send_screenshot_event()
        except Exception as e:
            logger.debug(f"Screenshot event send failed (non-critical): {e}")

        # Notify agent of URL change for IntentSequence cache management
        try:
            await self._notify_url_change()
        except Exception as e:
            logger.debug(f"URL change notification failed (non-critical): {e}")

        return "\n\n".join(parts)

    @listen_toolkit(
        inputs=lambda self, url: f"Visiting: {url[:80]}{'...' if len(url) > 80 else ''}",
        return_msg=lambda r: "Page loaded" if "Navigated to" in r else r[:100]
    )
    async def browser_visit_page(self, url: str) -> str:
        """Navigate to a URL and return the page snapshot.

        Use this to open a new webpage. The snapshot shows interactive elements
        with [ref=eN] markers that can be used with other browser tools.

        Args:
            url: The URL to navigate to.

        Returns:
            Result message with current page info (URL, title) and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            await session.visit(url)
            return await self._build_action_result(f"Navigated to {url}")
        except Exception as e:
            logger.error(f"browser_visit_page error: {e}")
            return f"Error visiting page: {e}"

    @listen_toolkit(
        inputs=lambda self, ref=None, element_text=None, selector=None: f"Clicking: {ref or element_text or selector}",
        return_msg=lambda r: "Clicked" if "successfully" in r.lower() or "Clicked" in r else r[:100]
    )
    async def browser_click(
        self,
        ref: Optional[str] = None,
        element_text: Optional[str] = None,
        selector: Optional[str] = None,
    ) -> str:
        """Click an element on the page.

        Provide one of: ref (from snapshot), element_text content, or CSS selector.
        If the click opens a new tab, the browser automatically switches to it.

        Args:
            ref: Element reference from snapshot (e.g., "e1", "e2").
            element_text: Visible text content of the element to click (e.g., "Submit", "Login").
            selector: CSS selector for the element.

        Returns:
            Result message with current page info (URL, title), tab info, and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if not (ref or element_text or selector):
            return "Error: Must provide ref, element_text, or selector"

        try:
            session = await self._get_session_with_page()
            action = {"type": "click"}
            if ref:
                action["ref"] = ref
            if element_text:
                action["text"] = element_text
            if selector:
                action["selector"] = selector

            result = await session.exec_action(action)

            if result.get("success"):
                details = result.get("details", {})
                new_tab_created = details.get("new_tab_created", False)
                new_tab_index = details.get("new_tab_index")

                if new_tab_created and new_tab_index:
                    click_info = f"Clicked, opened new tab (now on tab {new_tab_index})"
                else:
                    click_info = "Clicked successfully"

                return await self._build_action_result(
                    click_info,
                    wait_for_stability=True,
                    include_tab_info=True,
                    force_refresh=new_tab_created,
                )
            else:
                return await self._build_action_result(
                    f"Click failed: {result.get('message')}",
                    wait_for_stability=False,
                )
        except Exception as e:
            logger.error(f"browser_click error: {e}")
            return f"Error clicking element: {e}"

    @listen_toolkit(
        inputs=lambda self, input_text, ref=None, selector=None, **kw: f"Typing into {ref or selector}: {input_text[:30]}{'...' if len(input_text) > 30 else ''}",
        return_msg=lambda r: "Typed" if "successfully" in r.lower() else r[:100]
    )
    async def browser_type(
        self,
        input_text: str,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        clear_first: bool = True,
    ) -> str:
        """Type text into an input element.

        Args:
            input_text: The text content to type into the input field.
            ref: Element reference from snapshot (e.g., "e1").
            selector: CSS selector for the input element.
            clear_first: Whether to clear existing text before typing.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if not (ref or selector):
            return "Error: Must provide ref or selector"

        try:
            session = await self._get_session_with_page()
            action = {"type": "type", "text": input_text}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector
            if clear_first:
                action["clear"] = True

            result = await session.exec_action(action)

            if result.get("success"):
                return await self._build_action_result("Typed text successfully")
            else:
                return await self._build_action_result(f"Type failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_type error: {e}")
            return f"Error typing text: {e}"

    @listen_toolkit(
        inputs=lambda self, ref=None, selector=None: f"Pressing Enter{' on ' + (ref or selector) if ref or selector else ''}",
        return_msg=lambda r: "Enter pressed" if "successfully" in r.lower() else r[:100]
    )
    async def browser_enter(
        self,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
    ) -> str:
        """Press Enter key, optionally on a specific element.

        Args:
            ref: Element reference from snapshot.
            selector: CSS selector for the element.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            action = {"type": "enter"}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector

            result = await session.exec_action(action)

            if result.get("success"):
                return await self._build_action_result("Pressed Enter successfully")
            else:
                return await self._build_action_result(f"Enter failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_enter error: {e}")
            return f"Error pressing Enter: {e}"

    @listen_toolkit(
        inputs=lambda self: "Navigating back",
        return_msg=lambda r: "Went back" if "back" in r.lower() else r[:100]
    )
    async def browser_back(self) -> str:
        """Navigate back in browser history.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            await session.exec_action({"type": "back"})
            return await self._build_action_result("Navigated back")
        except Exception as e:
            logger.error(f"browser_back error: {e}")
            return f"Error navigating back: {e}"

    @listen_toolkit(
        inputs=lambda self: "Navigating forward",
        return_msg=lambda r: "Went forward" if "forward" in r.lower() else r[:100]
    )
    async def browser_forward(self) -> str:
        """Navigate forward in browser history.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            await session.exec_action({"type": "forward"})
            return await self._build_action_result("Navigated forward")
        except Exception as e:
            logger.error(f"browser_forward error: {e}")
            return f"Error navigating forward: {e}"

    @listen_toolkit(
        inputs=lambda self, direction="down", amount=300: f"Scrolling {direction} {amount}px",
        return_msg=lambda r: "Scrolled" if "scrolled" in r.lower() else r[:100]
    )
    async def browser_scroll(
        self,
        direction: str = "down",
        amount: int = 300,
    ) -> str:
        """Scroll the page.

        Args:
            direction: Scroll direction ("up" or "down").
            amount: Scroll amount in pixels.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            action = {
                "type": "scroll",
                "direction": direction,
                "amount": amount,
            }
            await session.exec_action(action)
            return await self._build_action_result(f"Scrolled {direction} by {amount}px")
        except Exception as e:
            logger.error(f"browser_scroll error: {e}")
            return f"Error scrolling: {e}"

    @listen_toolkit(
        inputs=lambda self, value, ref=None, selector=None: f"Selecting '{value}' from {ref or selector}",
        return_msg=lambda r: "Selected" if "successfully" in r.lower() else r[:100]
    )
    async def browser_select(
        self,
        value: str,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
    ) -> str:
        """Select an option from a dropdown.

        Args:
            value: The value to select.
            ref: Element reference from snapshot.
            selector: CSS selector for the select element.

        Returns:
            Result message with current page info (URL, title) and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if not (ref or selector):
            return "Error: Must provide ref or selector"

        try:
            session = await self._get_session_with_page()
            action = {"type": "select", "value": value}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector

            result = await session.exec_action(action)

            if result.get("success"):
                return await self._build_action_result(f"Selected '{value}' successfully")
            else:
                return await self._build_action_result(f"Select failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_select error: {e}")
            return f"Error selecting option: {e}"

    @listen_toolkit(
        inputs=lambda self, include_links=False: "Getting page snapshot",
        return_msg=lambda r: "Got snapshot" if r and not r.startswith("Error") else r[:100]
    )
    async def browser_get_page_snapshot(
        self,
        include_links: bool = False,
    ) -> str:
        """Get the current page snapshot without performing any action.

        Always includes the current page URL and title at the top.

        Use this to see the current state of the page, including:
        - Page URL and title
        - Interactive elements with [ref=eN] markers
        - Page structure
        - All links with their href URLs (if include_links=True)

        Args:
            include_links: If True, appends a list of all links on the page
                with their actual href URLs. Useful for extracting navigation
                targets to save in notes for later use.

        Returns:
            The current page snapshot with URL info and optionally a links list.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session_with_page()
            # Always get page URL and title
            page = await session.get_page()
            url = page.url
            title = await page.title()
            header = f"**Current Page:**\n- URL: {url}\n- Title: {title}\n\n"

            if include_links:
                # Get full result with elements map to extract links
                full_result = await session.get_snapshot_with_elements()
                snapshot = full_result.get("snapshotText", "")
                elements = full_result.get("elements", {})

                # Extract links from elements map
                links = []
                for ref, elem_info in elements.items():
                    href = elem_info.get("href")
                    if href:
                        name = elem_info.get("name", "")
                        role = elem_info.get("role", "")
                        links.append({
                            "ref": ref,
                            "name": name,
                            "href": href,
                            "role": role,
                        })

                # Build links section
                links_section = ""
                if links:
                    links_section = "\n\n**Page Links:**\n"
                    for link in links:
                        links_section += f"- [{link['ref']}] \"{link['name']}\" -> {link['href']}\n"

                # Format snapshot text
                if isinstance(snapshot, str) and snapshot.startswith("- Page Snapshot"):
                    formatted_snapshot = snapshot
                else:
                    formatted_snapshot = f"- Page Snapshot\n```yaml\n{snapshot}\n```"

                return header + formatted_snapshot + links_section
            else:
                snapshot = await session.get_snapshot()
                return header + snapshot
        except Exception as e:
            logger.error(f"browser_get_page_snapshot error: {e}")
            return f"Error getting snapshot: {e}"

    async def _format_tab_info(self) -> str:
        """Format tab information for display."""
        try:
            session = await self._get_session()
            if not session:
                return "No session available."

            tab_info = await session.get_tab_info()
            if not tab_info:
                return "No tabs open."

            lines = [f"**Open Tabs ({len(tab_info)} total):**"]
            for tab in tab_info:
                is_current = tab.get("is_current", False)
                marker = "→ " if is_current else "  "
                tab_id = tab.get("tab_id", "unknown")
                title = tab.get("title", "Untitled")[:50]
                url = tab.get("url", "")
                lines.append(f"{marker}[{tab_id}] {title}")
                lines.append(f"       URL: {url}")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error formatting tab info: {e}")
            return f"[Tab info unavailable: {e}]"

    @listen_toolkit(
        inputs=lambda self, keys: f"Pressing keys: {keys}",
        return_msg=lambda r: "Keys pressed" if "Pressed" in r else r[:100]
    )
    async def browser_press_key(self, keys: List[str]) -> str:
        """Press key or key combinations.

        Supports single key press or combination of keys. For combinations,
        provide multiple keys in the list (e.g., ["Control", "c"] for Ctrl+C).

        Common keys: Enter, Escape, Tab, Backspace, Delete, ArrowUp, ArrowDown,
        ArrowLeft, ArrowRight, Home, End, PageUp, PageDown, F1-F12,
        Control, Shift, Alt, Meta (Command on Mac).

        Args:
            keys: List of keys to press. For combinations, all keys are pressed
                together. Examples:
                - ["Enter"] - Press Enter
                - ["Escape"] - Press Escape
                - ["Control", "a"] - Select all (Ctrl+A)
                - ["Control", "c"] - Copy (Ctrl+C)
                - ["Control", "v"] - Paste (Ctrl+V)
                - ["Shift", "Tab"] - Shift+Tab

        Returns:
            Result message with current page info and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if not keys or not isinstance(keys, list):
            return "Error: keys must be a non-empty list of strings"

        try:
            session = await self._get_session_with_page()
            action = {"type": "press_key", "keys": keys}
            result = await session.exec_action(action)

            if result.get("success"):
                key_combo = "+".join(keys)
                return await self._build_action_result(f"Pressed keys: {key_combo}")
            else:
                return await self._build_action_result(f"Press key failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_press_key error: {e}")
            return f"Error pressing keys: {e}"

    @listen_toolkit(
        inputs=lambda self, x, y, click_type="click": f"Mouse {click_type} at ({x}, {y})",
        return_msg=lambda r: "Mouse action done" if "performed" in r.lower() or "Mouse" in r else r[:100]
    )
    async def browser_mouse_control(
        self,
        x: float,
        y: float,
        click_type: str = "click",
    ) -> str:
        """Control the mouse to interact with browser using x, y coordinates.

        Use this when you cannot locate an element by ref or selector.
        Coordinates are relative to the viewport (visible area).

        Args:
            x: X-coordinate for the mouse action (pixels from left).
            y: Y-coordinate for the mouse action (pixels from top).
            click_type: Type of click action. Options:
                - "click" (default): Single left click
                - "dblclick": Double click
                - "right_click": Right click (context menu)

        Returns:
            Result message with current page info and updated page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if click_type not in ("click", "dblclick", "right_click"):
            return f"Error: click_type must be 'click', 'dblclick', or 'right_click', got '{click_type}'"

        try:
            session = await self._get_session_with_page()
            action = {
                "type": "mouse_control",
                "control": click_type,
                "x": x,
                "y": y,
            }
            result = await session.exec_action(action)

            if result.get("success"):
                return await self._build_action_result(
                    f"Mouse {click_type} at coordinates ({x}, {y})"
                )
            else:
                return await self._build_action_result(f"Mouse control failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_mouse_control error: {e}")
            return f"Error with mouse control: {e}"

    @listen_toolkit(
        inputs=lambda self: "Getting tab info",
        return_msg=lambda r: r.split('\n')[0] if r else "Got tab info"
    )
    async def browser_get_tab_info(self) -> str:
        """Get information about all open browser tabs.

        Use this to see all open tabs, their IDs, titles, and URLs.
        The current active tab is marked with an arrow (→).
        Use the tab_id with browser_switch_tab or browser_close_tab.

        Returns:
            List of all open tabs with their IDs, titles, and URLs.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            return await self._format_tab_info()
        except Exception as e:
            logger.error(f"browser_get_tab_info error: {e}")
            return f"Error getting tab info: {e}"

    @listen_toolkit(
        inputs=lambda self, tab_id: f"Switching to tab: {tab_id}",
        return_msg=lambda r: "Tab switched" if "Switched" in r else r[:100]
    )
    async def browser_switch_tab(
        self,
        tab_id: str,
    ) -> str:
        """Switch to a different browser tab by its ID.

        Use browser_get_tab_info first to see available tabs and their IDs.

        Args:
            tab_id: The tab ID to switch to (e.g., "tab-001", "tab-002").

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session()
            success = await session.switch_to_tab(tab_id)
            if not success:
                return f"Error: Failed to switch to tab '{tab_id}'. Use browser_get_tab_info to see available tabs."

            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            # Force refresh to re-inject aria-ref attributes on the new tab
            # This is critical because each tab has its own window object
            snapshot = await self._get_snapshot(force_refresh=True)

            parts = [f"Switched to tab '{tab_id}'"]
            if page_context:
                parts.append(page_context)
            parts.append(tab_info)
            if snapshot:
                parts.append(snapshot)

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"browser_switch_tab error: {e}")
            return f"Error switching tab: {e}"

    @listen_toolkit(
        inputs=lambda self, url=None: f"Opening new tab{': ' + url[:50] if url else ''}",
        return_msg=lambda r: "New tab opened" if "Opened" in r else r[:100]
    )
    async def browser_new_tab(
        self,
        url: Optional[str] = None,
    ) -> str:
        """Open a new browser tab, optionally navigating to a URL.

        Creates a new tab and switches to it. If a URL is provided, navigates to that URL.
        This is useful for opening links in new tabs while keeping the original page.

        Bug #19 fix: Uses Tab Group to organize tabs by task (session_id).

        Args:
            url: Optional URL to navigate to in the new tab.

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session()

            # Bug #19 fix: Use create_tab_in_group to auto-organize tabs by task
            # session_id is used as task_id for Tab Group management
            tab_id, page = await session.create_tab_in_group(
                task_id=self._session_id,
                url=url
            )

            # Switch to the new tab
            await session.switch_to_tab(tab_id)

            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            # Force refresh because new tab has its own window object
            snapshot = await self._get_snapshot(force_refresh=True)

            if url:
                result_msg = f"Opened new tab '{tab_id}' and navigated to {url}"
            else:
                result_msg = f"Opened new tab '{tab_id}'"

            parts = [result_msg]
            if page_context:
                parts.append(page_context)
            parts.append(tab_info)
            if snapshot:
                parts.append(snapshot)

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"browser_new_tab error: {e}")
            return f"Error opening new tab: {e}"

    @listen_toolkit(
        inputs=lambda self, tab_id: f"Closing tab: {tab_id}",
        return_msg=lambda r: "Tab closed" if "Closed" in r else r[:100]
    )
    async def browser_close_tab(
        self,
        tab_id: str,
    ) -> str:
        """Close a browser tab by its ID.

        Use browser_get_tab_info first to see available tabs and their IDs.
        After closing, the browser will automatically switch to another tab if available.

        Args:
            tab_id: The tab ID to close (e.g., "tab-001", "tab-002").

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            session = await self._get_session()
            success = await session.close_tab(tab_id)
            if not success:
                return f"Error: Failed to close tab '{tab_id}'. Use browser_get_tab_info to see available tabs."

            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            # Force refresh because we might have switched to a different tab
            snapshot = await self._get_snapshot(force_refresh=True)

            parts = [f"Closed tab '{tab_id}'"]
            if page_context:
                parts.append(page_context)
            parts.append(tab_info)
            if snapshot:
                parts.append(snapshot)
            else:
                parts.append("No active tab remaining.")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"browser_close_tab error: {e}")
            return f"Error closing tab: {e}"

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for enabled tools only.

        Only returns tools that are in the `enabled_tools` list.
        This reduces the request payload size sent to the LLM.

        Returns:
            List of FunctionTool objects for enabled tools.
        """
        # Map tool names to their methods
        tool_map = {
            "browser_visit_page": self.browser_visit_page,
            "browser_back": self.browser_back,
            "browser_forward": self.browser_forward,
            "browser_scroll": self.browser_scroll,
            "browser_click": self.browser_click,
            "browser_type": self.browser_type,
            "browser_enter": self.browser_enter,
            "browser_select": self.browser_select,
            "browser_press_key": self.browser_press_key,
            "browser_mouse_control": self.browser_mouse_control,
            "browser_get_page_snapshot": self.browser_get_page_snapshot,
            "browser_get_tab_info": self.browser_get_tab_info,
            "browser_switch_tab": self.browser_switch_tab,
            "browser_new_tab": self.browser_new_tab,
            "browser_close_tab": self.browser_close_tab,
        }

        # Return only enabled tools
        enabled_tools = []
        for tool_name in self._enabled_tools:
            if tool_name in tool_map:
                enabled_tools.append(FunctionTool(tool_map[tool_name]))

        logger.info(f"Returning {len(enabled_tools)} enabled browser tools")
        return enabled_tools

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Browser Toolkit"
