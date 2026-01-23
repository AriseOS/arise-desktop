"""
BrowserToolkit - Browser automation tools for agents.

Wraps the existing HybridBrowserSession to provide Tool-calling compatible
browser operations. Ported from CAMEL-AI/Eigent project architecture.

All methods are async to work properly in async execution contexts.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

if TYPE_CHECKING:
    from ..eigent_browser.browser_session import HybridBrowserSession

logger = logging.getLogger(__name__)


class BrowserToolkit(BaseToolkit):
    """A toolkit for browser automation.

    Provides tools for web navigation, interaction, and content extraction.
    Each tool returns a page snapshot after execution for LLM context.

    All methods are async for proper integration with async agent loops.
    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "browser_agent"

    def __init__(
        self,
        session: Optional["HybridBrowserSession"] = None,
        timeout: Optional[float] = 30.0,
        return_snapshot: bool = True,
    ) -> None:
        """Initialize the BrowserToolkit.

        Args:
            session: An existing HybridBrowserSession instance.
                If not provided, tools will return errors until set.
            timeout: Default timeout for browser operations.
            return_snapshot: Whether to return page snapshot after each action.
        """
        super().__init__(timeout=timeout)
        self._session = session
        self._return_snapshot = return_snapshot
        logger.info(f"BrowserToolkit initialized (session={'set' if session else 'None'})")

    def set_session(self, session: "HybridBrowserSession") -> None:
        """Set or update the browser session.

        Args:
            session: The HybridBrowserSession instance to use.
        """
        self._session = session
        logger.info("Browser session updated")

    def _ensure_session(self) -> bool:
        """Check if session is available."""
        if self._session is None:
            logger.error("Browser session not set")
            return False
        return True

    async def _get_snapshot(self) -> str:
        """Get current page snapshot if enabled."""
        if not self._return_snapshot or not self._session:
            return ""
        try:
            snapshot = await self._session.get_snapshot()
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
        if not self._session:
            return ""
        try:
            page = await self._session.get_page()
            url = page.url
            title = await page.title()
            return f"**Current Page:** {title}\n**URL:** {url}"
        except Exception as e:
            logger.debug(f"Failed to get page context: {e}")
            return ""

    async def _wait_for_page_stability(self, timeout_ms: int = 1500) -> None:
        """Wait for page to become stable after an action.

        This is important after click/type actions that may trigger:
        - Page navigation
        - New tab opening
        - AJAX content loading

        Following Eigent's pattern for page stability.
        """
        if not self._session:
            return

        try:
            page = await self._session.get_page()
            # Wait for network to be idle (no pending requests)
            await page.wait_for_load_state('domcontentloaded', timeout=timeout_ms)
        except Exception as e:
            logger.debug(f"Page stability wait interrupted: {e}")

    async def _get_tab_info_summary(self) -> str:
        """Get a summary of tab information for action results.

        Returns tab count and current tab info so LLM knows about tab changes.
        """
        if not self._session:
            return ""

        try:
            tab_info = await self._session.get_tab_info()
            current_tab_id = await self._session.get_current_tab_id()

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

    async def _build_action_result(
        self,
        result_message: str,
        include_snapshot: bool = True,
        include_page_context: bool = True,
        include_tab_info: bool = True,
        wait_for_stability: bool = False,
    ) -> str:
        """Build a standardized action result with page context and snapshot.

        Following Eigent's pattern, every browser action result includes:
        1. The action result message
        2. Tab information (if multiple tabs)
        3. Current page context (URL and title)
        4. Page snapshot (interactive elements)

        Args:
            result_message: The main result message from the action.
            include_snapshot: Whether to include the page snapshot.
            include_page_context: Whether to include page URL/title.
            include_tab_info: Whether to include tab information.
            wait_for_stability: Whether to wait for page stability first.

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
            snapshot = await self._get_snapshot()
            if snapshot:
                parts.append(snapshot)

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
            await self._session.visit(url)
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
            # Get element description before clicking (for debugging)
            element_desc = ""
            if ref:
                try:
                    before_snapshot = await self._session.get_snapshot()
                    # Parse snapshot to find the element description
                    # Format: - link "Text" [ref=e17] or - button "Text" [ref=e17]
                    import re
                    pattern = rf'- (\w+) "([^"]*)"[^\[]*\[ref={ref}\]'
                    match = re.search(pattern, before_snapshot)
                    if match:
                        element_type, element_text_found = match.groups()
                        element_desc = f'{element_type} "{element_text_found}"'
                        logger.info(f"[Click] Clicking {element_desc} (ref={ref})")
                except Exception as e:
                    logger.debug(f"Could not get element description: {e}")

            action = {"type": "click"}
            if ref:
                action["ref"] = ref
            if element_text:
                action["text"] = element_text
            if selector:
                action["selector"] = selector

            result = await self._session.exec_action(action)

            if result.get("success"):
                # Extract details about the click result
                details = result.get("details", {})
                new_tab_created = details.get("new_tab_created", False)
                new_tab_index = details.get("new_tab_index")
                click_method = details.get("click_method", "unknown")

                # Build informative click message
                if new_tab_created and new_tab_index:
                    click_info = f"Clicked {element_desc}, opened new tab (now on tab {new_tab_index})" if element_desc else f"Clicked, opened new tab (now on tab {new_tab_index})"
                    logger.info(f"[Click] New tab created: {new_tab_index}, auto-switched")
                else:
                    click_info = f"Clicked {element_desc}" if element_desc else "Clicked successfully"

                # Wait for page stability and include tab info in result
                # This ensures LLM sees the new page content after navigation/tab switch
                return await self._build_action_result(
                    click_info,
                    wait_for_stability=True,
                    include_tab_info=True,
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
            action = {"type": "type", "text": input_text}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector
            if clear_first:
                action["clear"] = True

            result = await self._session.exec_action(action)

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
            action = {"type": "enter"}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector

            result = await self._session.exec_action(action)

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
            await self._session.exec_action({"type": "back"})
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
            await self._session.exec_action({"type": "forward"})
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
            action = {
                "type": "scroll",
                "direction": direction,
                "amount": amount,
            }
            await self._session.exec_action(action)
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
            action = {"type": "select", "value": value}
            if ref:
                action["ref"] = ref
            if selector:
                action["selector"] = selector

            result = await self._session.exec_action(action)

            if result.get("success"):
                return await self._build_action_result(f"Selected '{value}' successfully")
            else:
                return await self._build_action_result(f"Select failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"browser_select error: {e}")
            return f"Error selecting option: {e}"

    @listen_toolkit(
        inputs=lambda self, include_url=False: "Getting page snapshot",
        return_msg=lambda r: "Got snapshot" if r and not r.startswith("Error") else r[:100]
    )
    async def browser_get_page_snapshot(self, include_url: bool = False) -> str:
        """Get the current page snapshot without performing any action.

        Use this to see the current state of the page, including:
        - Page URL and title (if include_url=True)
        - Interactive elements with [ref=eN] markers
        - Page structure

        Args:
            include_url: If True, includes the current page URL at the top of the snapshot.
                Useful for loop iterations to track which page you're on.

        Returns:
            The current page snapshot, optionally prefixed with URL info.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            snapshot = await self._session.get_snapshot()

            if include_url:
                page = await self._session.get_page()
                url = page.url
                title = await page.title()
                return f"**Current Page:**\n- URL: {url}\n- Title: {title}\n\n{snapshot}"

            return snapshot
        except Exception as e:
            logger.error(f"browser_get_page_snapshot error: {e}")
            return f"Error getting snapshot: {e}"

    @listen_toolkit(
        inputs=lambda self: "Getting page info",
        return_msg=lambda r: r[:100] if r else "Got page info"
    )
    async def browser_get_page_info(self) -> str:
        """Get basic information about the current page (URL, title).

        This is a lightweight call that doesn't capture the full DOM snapshot.
        Useful for loop iterations to quickly check which page you're on.

        Returns:
            Page URL and title.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            page = await self._session.get_page()
            url = page.url
            title = await page.title()
            return f"URL: {url}\nTitle: {title}"
        except Exception as e:
            logger.error(f"browser_get_page_info error: {e}")
            return f"Error getting page info: {e}"

    async def _format_tab_info(self) -> str:
        """Format tab information for display."""
        try:
            tab_info = await self._session.get_tab_info()
            if not tab_info:
                return "No tabs open."

            current_tab_idx = None
            lines = [f"**Open Tabs ({len(tab_info)} total):**"]
            for i, tab in enumerate(tab_info):
                is_current = tab.get("is_current", False)
                if is_current:
                    current_tab_idx = i
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
            tab_id: The tab ID to switch to (e.g., "tab_1", "tab_2").

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            success = await self._session.switch_to_tab(tab_id)
            if not success:
                return f"Error: Failed to switch to tab '{tab_id}'. Use browser_get_tab_info to see available tabs."

            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            snapshot = await self._get_snapshot()

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

        Args:
            url: Optional URL to navigate to in the new tab.

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            tab_id = await self._session.create_new_tab(url)
            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            snapshot = await self._get_snapshot()

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
            tab_id: The tab ID to close (e.g., "tab_1", "tab_2").

        Returns:
            Result message with current page info (URL, title), tab list, and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            success = await self._session.close_tab(tab_id)
            if not success:
                return f"Error: Failed to close tab '{tab_id}'. Use browser_get_tab_info to see available tabs."

            page_context = await self._get_page_context()
            tab_info = await self._format_tab_info()
            snapshot = await self._get_snapshot()

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

    @listen_toolkit(
        inputs=lambda self: "Viewing console logs",
        return_msg=lambda r: f"Got {r.count(chr(10))} log entries" if "Console logs" in r else r[:100]
    )
    async def browser_console_view(self) -> str:
        """View current page console logs.

        Returns console messages that have been logged by the webpage,
        useful for debugging or extracting dynamically generated data.

        Returns:
            Formatted string with console log messages.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            logs = await self._session.get_console_logs()
            if not logs:
                return "No console messages captured."

            # Format logs for display
            output = "Console logs:\n\n"
            log_list = list(logs) if hasattr(logs, '__iter__') else [logs]
            for i, log in enumerate(log_list[-50:], 1):  # Last 50 logs
                if hasattr(log, 'type') and hasattr(log, 'text'):
                    output += f"{i}. [{log.type}] {log.text}\n"
                elif isinstance(log, dict):
                    log_type = log.get('type', 'log')
                    log_text = log.get('text', str(log))
                    output += f"{i}. [{log_type}] {log_text}\n"
                else:
                    output += f"{i}. {str(log)}\n"
            return output
        except Exception as e:
            logger.error(f"browser_console_view error: {e}")
            return f"Error viewing console: {e}"

    @listen_toolkit(
        inputs=lambda self, code: f"Executing JS: {code[:50]}{'...' if len(code) > 50 else ''}",
        return_msg=lambda r: "JS executed" if "successfully" in r.lower() else r[:100]
    )
    async def browser_console_exec(self, code: str) -> str:
        """Execute JavaScript code in the browser console.

        Run custom JavaScript code in the context of the current page.
        Useful for extracting data, manipulating the page, or debugging.

        Args:
            code: JavaScript code to execute in the browser console.

        Returns:
            Result message with JS result, current page info (URL, title), and page snapshot.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            page = await self._session.get_page()
            result = await page.evaluate(code)

            # Format the result
            if result is None:
                result_str = "(no return value)"
            elif isinstance(result, (dict, list)):
                import json
                result_str = json.dumps(result, indent=2, ensure_ascii=False)
            else:
                result_str = str(result)

            result_msg = f"JavaScript executed successfully.\n\nResult:\n{result_str}"
            return await self._build_action_result(result_msg)
        except Exception as e:
            logger.error(f"browser_console_exec error: {e}")
            return f"JavaScript execution error: {e}"

    @listen_toolkit(
        inputs=lambda self, keys: f"Pressing keys: {keys}",
        return_msg=lambda r: "Keys pressed" if "successfully" in r.lower() else r[:100]
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
            # Build the key combination string for Playwright
            # Playwright expects format like "Control+a" or "Shift+Tab"
            key_combo = "+".join(keys)

            page = await self._session.get_page()
            await page.keyboard.press(key_combo)

            return await self._build_action_result(f"Pressed keys: {key_combo}")
        except Exception as e:
            logger.error(f"browser_press_key error: {e}")
            return f"Error pressing keys: {e}"

    @listen_toolkit(
        inputs=lambda self, x, y, click_type="click": f"Mouse {click_type} at ({x}, {y})",
        return_msg=lambda r: "Mouse action done" if "successfully" in r.lower() or "Mouse" in r else r[:100]
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
            page = await self._session.get_page()

            # Move mouse to position
            await page.mouse.move(x, y)

            # Perform the click action
            if click_type == "click":
                await page.mouse.click(x, y)
            elif click_type == "dblclick":
                await page.mouse.dblclick(x, y)
            elif click_type == "right_click":
                await page.mouse.click(x, y, button="right")

            return await self._build_action_result(
                f"Mouse {click_type} at coordinates ({x}, {y})"
            )
        except Exception as e:
            logger.error(f"browser_mouse_control error: {e}")
            return f"Error with mouse control: {e}"

    @listen_toolkit(
        inputs=lambda self, refs: f"Getting URLs for refs: {refs}",
        return_msg=lambda r: f"Found {r.count('URL:')} links" if "URL:" in r else r[:100]
    )
    async def browser_get_page_links(self, refs: List[str]) -> str:
        """Get the destination URLs for a list of link elements.

        This is useful to know where a link goes before clicking it.
        Only works for anchor (<a>) elements with href attributes.

        Args:
            refs: List of ref IDs for link elements (e.g., ["e1", "e5", "e12"]).

        Returns:
            List of links with their text, ref, and destination URL.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        if not refs or not isinstance(refs, list):
            return "Error: refs must be a non-empty list of ref IDs"

        try:
            page = await self._session.get_page()

            # Get link information for each ref
            links_info = []
            for ref in refs:
                try:
                    # Use JavaScript to find the element and get its href
                    link_data = await page.evaluate(f"""
                        (() => {{
                            const elements = document.querySelectorAll('[data-ref="{ref}"], [ref="{ref}"]');
                            for (const el of elements) {{
                                if (el.tagName === 'A' && el.href) {{
                                    return {{
                                        ref: "{ref}",
                                        text: el.textContent?.trim() || '',
                                        url: el.href
                                    }};
                                }}
                            }}
                            // Try finding by aria-label or other attributes
                            const allLinks = document.querySelectorAll('a[href]');
                            // This is a fallback - in practice, the snapshot ref system should work
                            return null;
                        }})()
                    """)

                    if link_data:
                        links_info.append(link_data)
                    else:
                        links_info.append({
                            "ref": ref,
                            "text": "(not found or not a link)",
                            "url": None
                        })
                except Exception as e:
                    links_info.append({
                        "ref": ref,
                        "text": f"(error: {e})",
                        "url": None
                    })

            # Format output
            if not links_info:
                return "No links found for the provided refs."

            lines = ["**Link URLs:**"]
            for link in links_info:
                ref = link.get("ref", "?")
                text = link.get("text", "")[:50]
                url = link.get("url", "N/A")
                lines.append(f"- [{ref}] \"{text}\"")
                lines.append(f"  URL: {url}")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"browser_get_page_links error: {e}")
            return f"Error getting page links: {e}"

    @listen_toolkit(
        inputs=lambda self, message="Please complete the required action": f"Waiting for user: {message[:50]}",
        return_msg=lambda r: "User action completed" if "completed" in r.lower() else r[:100]
    )
    async def browser_wait_user(
        self,
        message: str = "Please complete the required action (e.g., solve CAPTCHA, login)",
        timeout_seconds: int = 300,
    ) -> str:
        """Pause execution and wait for human intervention.

        Use this when encountering situations that require manual user action:
        - CAPTCHA challenges
        - Two-factor authentication
        - Manual login required
        - Complex verification steps

        The agent will pause and wait for the user to complete the action
        in the browser, then continue.

        Args:
            message: Message to display to the user explaining what action is needed.
            timeout_seconds: Maximum time to wait in seconds (default: 300 = 5 minutes).

        Returns:
            Result message with current page info and updated page snapshot after user action.
        """
        if not self._ensure_session():
            return "Error: Browser session not initialized"

        try:
            # Notify that we're waiting for user action
            logger.info(f"[Wait User] {message}")

            # Use the human toolkit if available to notify the user
            # For now, we'll use a simple polling approach
            import asyncio

            # Get initial page state
            page = await self._session.get_page()
            initial_url = page.url

            # Wait and poll for page changes or timeout
            # In a real implementation, this would integrate with the human_toolkit
            # to send a notification to the frontend
            wait_interval = 2  # Check every 2 seconds
            elapsed = 0

            while elapsed < timeout_seconds:
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

                # Check if the page has changed (user took action)
                current_url = page.url
                if current_url != initial_url:
                    logger.info(f"[Wait User] Page changed from {initial_url} to {current_url}")
                    break

            if elapsed >= timeout_seconds:
                return await self._build_action_result(
                    f"Wait timed out after {timeout_seconds} seconds. User action may not have completed."
                )

            return await self._build_action_result(
                f"User action completed. Page changed from {initial_url} to {current_url}"
            )
        except Exception as e:
            logger.error(f"browser_wait_user error: {e}")
            return f"Error waiting for user: {e}"

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            # Navigation
            FunctionTool(self.browser_visit_page),
            FunctionTool(self.browser_back),
            FunctionTool(self.browser_forward),
            FunctionTool(self.browser_scroll),
            # Interaction
            FunctionTool(self.browser_click),
            FunctionTool(self.browser_type),
            FunctionTool(self.browser_enter),
            FunctionTool(self.browser_select),
            FunctionTool(self.browser_press_key),
            FunctionTool(self.browser_mouse_control),
            # Page info
            FunctionTool(self.browser_get_page_snapshot),
            FunctionTool(self.browser_get_page_info),
            FunctionTool(self.browser_get_page_links),
            # Tab management
            FunctionTool(self.browser_get_tab_info),
            FunctionTool(self.browser_new_tab),
            FunctionTool(self.browser_switch_tab),
            FunctionTool(self.browser_close_tab),
            # Console
            FunctionTool(self.browser_console_view),
            FunctionTool(self.browser_console_exec),
            # User interaction
            FunctionTool(self.browser_wait_user),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Browser Toolkit"
