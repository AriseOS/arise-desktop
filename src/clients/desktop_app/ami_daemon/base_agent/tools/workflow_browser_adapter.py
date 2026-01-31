"""
WorkflowBrowserAdapter - Adapter layer for workflow engine browser operations.

This adapter wraps HybridBrowserSession to provide a compatible interface
for workflow agents (BrowserAgent, ScraperAgent, AutonomousBrowserAgent).

Replaces the browser-use based BrowserSessionManager with eigent_browser
implementation while maintaining the same API contract for workflow agents.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .eigent_browser.browser_session import HybridBrowserSession
from .eigent_browser.action_executor import ActionExecutor
from .eigent_browser.page_snapshot import PageSnapshot

logger = logging.getLogger(__name__)


@dataclass
class WorkflowBrowserSessionInfo:
    """Browser session information for workflow agents.

    This replaces BrowserSessionInfo from browser_session_manager.py,
    providing the same interface but backed by HybridBrowserSession.
    """
    session: HybridBrowserSession
    executor: ActionExecutor
    snapshot: PageSnapshot
    created_at: datetime
    last_accessed: datetime
    reference_count: int = 0

    @property
    def controller(self):
        """Backward compatibility - return executor as 'controller'.

        This allows existing code that expects session_info.controller to work.
        The executor provides equivalent functionality to browser-use's Tools/Controller.
        """
        return self.executor


class WorkflowBrowserAdapter:
    """Adapter for workflow browser operations.

    This class provides the same interface as BrowserSessionManager but uses
    HybridBrowserSession internally. It enables a gradual migration from
    browser-use to eigent_browser.

    Key responsibilities:
    1. Session lifecycle management (create, reuse, close)
    2. Browser navigation and actions
    3. DOM extraction for LLM analysis
    4. Multi-tab support

    Usage:
        adapter = WorkflowBrowserAdapter()
        session_info = await adapter.get_or_create_session(
            session_id="workflow_123",
            config_service=config_service,
            headless=False
        )

        # Navigate
        await adapter.navigate(session_info, "https://example.com")

        # Get page snapshot for LLM
        snapshot_text = await adapter.get_page_snapshot(session_info)

        # Execute actions
        result = await adapter.click(session_info, ref="e1")
        result = await adapter.type_text(session_info, ref="e2", text="hello")
    """

    _instance: Optional["WorkflowBrowserAdapter"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._sessions: Dict[str, WorkflowBrowserSessionInfo] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._session_timeout_minutes = 30

    @classmethod
    async def get_instance(cls) -> "WorkflowBrowserAdapter":
        """Get singleton instance of the adapter."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._start_cleanup_task()
        return cls._instance

    def _start_cleanup_task(self):
        """Start periodic cleanup task for expired sessions."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._cleanup_expired_sessions()

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def _cleanup_expired_sessions(self):
        """Clean up sessions that have been idle for too long."""
        from datetime import timedelta

        now = datetime.now()
        timeout = timedelta(minutes=self._session_timeout_minutes)
        expired = []

        for session_id, info in self._sessions.items():
            if info.reference_count == 0 and (now - info.last_accessed) > timeout:
                expired.append(session_id)

        for session_id in expired:
            logger.info(f"Cleaning up expired session: {session_id}")
            await self.close_session(session_id, force=True)

    async def get_or_create_session(
        self,
        session_id: str,
        config_service=None,
        headless: bool = False,
        keep_alive: bool = True
    ) -> WorkflowBrowserSessionInfo:
        """Get existing session or create a new one.

        Args:
            session_id: Unique identifier for the session (e.g., workflow_id)
            config_service: Configuration service for browser data directory
            headless: Whether to run browser in headless mode
            keep_alive: Whether to keep session alive after use

        Returns:
            WorkflowBrowserSessionInfo with session and helper objects
        """
        # Reuse existing session
        if session_id in self._sessions:
            info = self._sessions[session_id]
            info.last_accessed = datetime.now()
            info.reference_count += 1
            logger.info(f"Reusing existing session: {session_id}, refs: {info.reference_count}")
            return info

        # Create new session
        logger.info(f"Creating new browser session: {session_id}")

        # Get browser data directory
        user_data_dir = None
        if config_service:
            user_data_dir = str(config_service.get_path("data.browser_data"))
        else:
            import tempfile
            user_data_dir = tempfile.mkdtemp(prefix="browser_data_")
            logger.warning(f"No config_service provided, using temp dir: {user_data_dir}")

        # Create HybridBrowserSession with unique session_id
        # NOTE: Do NOT add "workflow_" prefix here - caller already provides full session_id
        browser_session = HybridBrowserSession(
            headless=headless,
            user_data_dir=user_data_dir,
            stealth=True,  # Enable stealth mode for anti-detection
            session_id=session_id,
        )

        # Ensure browser is started
        await browser_session.ensure_browser()

        # Get executor and snapshot from session
        executor = browser_session.executor
        snapshot = browser_session.snapshot

        # Create session info
        info = WorkflowBrowserSessionInfo(
            session=browser_session,
            executor=executor,
            snapshot=snapshot,
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            reference_count=1,
        )

        self._sessions[session_id] = info
        logger.info(f"Browser session created: {session_id}")

        return info

    def release_session(self, session_id: str):
        """Release session reference (does not close the session).

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            info = self._sessions[session_id]
            info.reference_count = max(0, info.reference_count - 1)
            info.last_accessed = datetime.now()
            logger.info(f"Released session: {session_id}, refs: {info.reference_count}")

    async def close_session(self, session_id: str, force: bool = False):
        """Close a browser session.

        Args:
            session_id: Session identifier
            force: If True, close even if there are active references
        """
        if session_id not in self._sessions:
            logger.warning(f"Session not found: {session_id}")
            return

        info = self._sessions[session_id]

        if not force and info.reference_count > 0:
            logger.warning(f"Session has {info.reference_count} refs, not closing: {session_id}")
            return

        try:
            await info.session.close()
            logger.info(f"Browser session closed: {session_id}")
        except Exception as e:
            logger.error(f"Failed to close session {session_id}: {e}")
        finally:
            del self._sessions[session_id]

    async def close_all_sessions(self):
        """Close all browser sessions."""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id, force=True)

        if self._cleanup_task:
            self._cleanup_task.cancel()

    def get_session_info(self, session_id: str) -> Optional[WorkflowBrowserSessionInfo]:
        """Get session info without creating a new session."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> Dict[str, dict]:
        """List all sessions with their status."""
        result = {}
        for session_id, info in self._sessions.items():
            result[session_id] = {
                "created_at": info.created_at.isoformat(),
                "last_accessed": info.last_accessed.isoformat(),
                "reference_count": info.reference_count,
                "is_active": info.session is not None,
            }
        return result

    # =========================================================================
    # Browser Operations - These wrap HybridBrowserSession methods
    # =========================================================================

    async def navigate(
        self,
        session_info: WorkflowBrowserSessionInfo,
        url: str,
        wait_for_load: bool = True
    ) -> Dict[str, Any]:
        """Navigate to a URL.

        Args:
            session_info: Browser session info
            url: Target URL
            wait_for_load: Whether to wait for page load

        Returns:
            Dict with success status and message
        """
        try:
            session = session_info.session
            result = await session.visit(url)
            return {
                "success": True,
                "message": result,
                "url": url,
            }
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url,
            }

    async def click(
        self,
        session_info: WorkflowBrowserSessionInfo,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Click on an element.

        Args:
            session_info: Browser session info
            ref: Element reference (e.g., "e1")
            selector: CSS selector
            text: Text content to match

        Returns:
            Dict with success status and details
        """
        executor = session_info.executor
        return await executor.execute({
            "type": "click",
            "ref": ref,
            "selector": selector,
            "text": text,
        })

    async def type_text(
        self,
        session_info: WorkflowBrowserSessionInfo,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        text: str = ""
    ) -> Dict[str, Any]:
        """Type text into an input field.

        Args:
            session_info: Browser session info
            ref: Element reference
            selector: CSS selector
            text: Text to type

        Returns:
            Dict with success status and details
        """
        executor = session_info.executor
        return await executor.execute({
            "type": "type",
            "ref": ref,
            "selector": selector,
            "text": text,
        })

    async def scroll(
        self,
        session_info: WorkflowBrowserSessionInfo,
        direction: str = "down",
        amount: int = 300
    ) -> Dict[str, Any]:
        """Scroll the page.

        Args:
            session_info: Browser session info
            direction: "up" or "down"
            amount: Scroll amount in pixels

        Returns:
            Dict with success status and details
        """
        executor = session_info.executor
        return await executor.execute({
            "type": "scroll",
            "direction": direction,
            "amount": amount,
        })

    async def press_enter(
        self,
        session_info: WorkflowBrowserSessionInfo
    ) -> Dict[str, Any]:
        """Press Enter key.

        Args:
            session_info: Browser session info

        Returns:
            Dict with success status
        """
        executor = session_info.executor
        return await executor.execute({
            "type": "enter",
        })

    async def press_key(
        self,
        session_info: WorkflowBrowserSessionInfo,
        keys: List[str]
    ) -> Dict[str, Any]:
        """Press keyboard keys.

        Args:
            session_info: Browser session info
            keys: List of keys to press (e.g., ["Control", "c"])

        Returns:
            Dict with success status
        """
        executor = session_info.executor
        return await executor.execute({
            "type": "press_key",
            "keys": keys,
        })

    async def get_page_snapshot(
        self,
        session_info: WorkflowBrowserSessionInfo,
        viewport_limit: bool = False
    ) -> str:
        """Get page snapshot in LLM-friendly format.

        Args:
            session_info: Browser session info
            viewport_limit: If True, only include visible elements

        Returns:
            YAML-like text snapshot with element references
        """
        return await session_info.session.get_snapshot(
            viewport_limit=viewport_limit
        )

    async def get_full_snapshot_result(
        self,
        session_info: WorkflowBrowserSessionInfo,
        viewport_limit: bool = False
    ) -> Dict[str, Any]:
        """Get full snapshot result including elements map.

        Args:
            session_info: Browser session info
            viewport_limit: If True, only include visible elements

        Returns:
            Dict with snapshotText and elements map
        """
        snapshot = session_info.snapshot
        return await snapshot.get_full_result(viewport_limit=viewport_limit)

    async def get_current_url(
        self,
        session_info: WorkflowBrowserSessionInfo
    ) -> str:
        """Get current page URL.

        Args:
            session_info: Browser session info

        Returns:
            Current URL string
        """
        page = await session_info.session.get_page()
        return page.url

    async def get_page_title(
        self,
        session_info: WorkflowBrowserSessionInfo
    ) -> str:
        """Get current page title.

        Args:
            session_info: Browser session info

        Returns:
            Page title string
        """
        page = await session_info.session.get_page()
        return await page.title()

    async def evaluate_js(
        self,
        session_info: WorkflowBrowserSessionInfo,
        script: str
    ) -> Any:
        """Evaluate JavaScript in the page context.

        Args:
            session_info: Browser session info
            script: JavaScript code to execute

        Returns:
            Result of the JavaScript execution
        """
        page = await session_info.session.get_page()
        return await page.evaluate(script)

    # =========================================================================
    # Tab Management
    # =========================================================================

    async def create_new_tab(
        self,
        session_info: WorkflowBrowserSessionInfo,
        url: Optional[str] = None
    ) -> str:
        """Create a new tab.

        Args:
            session_info: Browser session info
            url: Optional URL to navigate to

        Returns:
            New tab ID
        """
        return await session_info.session.create_new_tab(url)

    async def switch_tab(
        self,
        session_info: WorkflowBrowserSessionInfo,
        tab_id: str
    ) -> bool:
        """Switch to a specific tab.

        Args:
            session_info: Browser session info
            tab_id: Tab identifier

        Returns:
            True if successful
        """
        result = await session_info.session.switch_to_tab(tab_id)

        # Update executor and snapshot after tab switch
        if result:
            session_info.executor = session_info.session.executor
            session_info.snapshot = session_info.session.snapshot

        return result

    async def close_tab(
        self,
        session_info: WorkflowBrowserSessionInfo,
        tab_id: str
    ) -> bool:
        """Close a specific tab.

        Args:
            session_info: Browser session info
            tab_id: Tab identifier

        Returns:
            True if successful
        """
        return await session_info.session.close_tab(tab_id)

    async def get_tab_info(
        self,
        session_info: WorkflowBrowserSessionInfo
    ) -> List[Dict[str, Any]]:
        """Get information about all open tabs.

        Args:
            session_info: Browser session info

        Returns:
            List of tab info dicts with tab_id, title, url, is_current
        """
        return await session_info.session.get_tab_info()

    async def get_current_tab_id(
        self,
        session_info: WorkflowBrowserSessionInfo
    ) -> Optional[str]:
        """Get current active tab ID.

        Args:
            session_info: Browser session info

        Returns:
            Current tab ID or None
        """
        return await session_info.session.get_current_tab_id()
