"""Browser lifecycle management with health monitoring"""
import asyncio
import logging
import psutil
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from src.clients.desktop_app.ami_daemon.services.browser_state import BrowserState
from src.clients.desktop_app.ami_daemon.services.browser_window_manager import BrowserWindowManager

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage browser lifecycle with on-demand startup and health monitoring"""

    def __init__(self, config_service=None):
        """Initialize browser manager

        Args:
            config_service: Configuration service for user data directory
        """
        self.config_service = config_service
        self.state = BrowserState.NOT_STARTED

        # Browser session components
        self.session_manager = None
        # Track all managed sessions (not just 'global')
        # Key: session_id, Value: dict with session_info and metadata
        self._managed_sessions: Dict[str, Dict[str, Any]] = {}

        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 5  # Check every 5 seconds
        self._last_health_check: Optional[datetime] = None

        # Window management
        self.window_manager = BrowserWindowManager(config_service=config_service)

        # Event callbacks
        self._status_callbacks: list[Callable] = []

    @property
    def global_session(self):
        """Get global session (backward compatibility)

        Returns:
            BrowserSessionInfo or None
        """
        if "global" in self._managed_sessions:
            return self._managed_sessions["global"].get("session_info")
        return None

    async def start_browser(self, headless: bool = False) -> Dict[str, Any]:
        """Start browser for recording (creates 'global' session)

        This is a convenience method for backward compatibility.
        New code should use start_browser_for_recording() instead.

        Args:
            headless: Whether to run browser in headless mode

        Returns:
            Dict with status, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        return await self.start_browser_for_recording(headless=headless)

    async def start_browser_for_recording(self, headless: bool = False) -> Dict[str, Any]:
        """Start browser for recording scenario

        Args:
            headless: Whether to run browser in headless mode

        Returns:
            Dict with status, session_id, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        return await self._ensure_session(
            session_id="global",
            headless=headless,
            keep_alive=True,
            arrange_windows=not headless
        )

    async def start_browser_for_workflow(
        self,
        workflow_id: str,
        headless: bool = False
    ) -> Dict[str, Any]:
        """Start browser for workflow execution

        Args:
            workflow_id: Unique workflow identifier
            headless: Whether to run browser in headless mode

        Returns:
            Dict with status, session_id, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        session_id = f"workflow_{workflow_id}"
        return await self._ensure_session(
            session_id=session_id,
            headless=headless,
            keep_alive=True,
            arrange_windows=not headless
        )

    async def _ensure_session(
        self,
        session_id: str,
        headless: bool = False,
        keep_alive: bool = True,
        arrange_windows: bool = True
    ) -> Dict[str, Any]:
        """Ensure browser session exists and is managed

        Args:
            session_id: Session identifier
            headless: Whether to run browser in headless mode
            keep_alive: Whether to keep session alive
            arrange_windows: Whether to arrange windows side-by-side

        Returns:
            Dict with status, session_id, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        # Check if session already exists
        if session_id in self._managed_sessions:
            logger.info(f"Browser session already exists: {session_id}")
            existing = self._managed_sessions[session_id]
            return {
                "status": "already_running",
                "session_id": session_id,
                "pid": existing.get("pid"),
                "state": self.state.value
            }

        logger.info(f"Starting browser session: {session_id} (headless={headless})...")

        # Update state if this is the first session
        if self.state == BrowserState.NOT_STARTED:
            self.state = BrowserState.STARTING
            self._notify_status_change("starting")

        try:
            # Import here to avoid circular dependency
            from src.clients.desktop_app.ami_daemon.base_app.base_app.base_agent.tools.browser_session_manager import (
                BrowserSessionManager
            )

            # Get or create session manager instance
            if not self.session_manager:
                self.session_manager = await BrowserSessionManager.get_instance()

            # Create browser session
            session_info = await self.session_manager.get_or_create_session(
                session_id=session_id,
                config_service=self.config_service,
                headless=headless,
                keep_alive=keep_alive
            )

            # Get browser PID
            browser_pid = await self._get_browser_pid_from_session(session_info)

            # Track this session
            self._managed_sessions[session_id] = {
                "session_info": session_info,
                "pid": browser_pid,
                "headless": headless,
                "created_at": datetime.now()
            }

            # Start health check if not already running
            if not self._health_check_task or self._health_check_task.done():
                self._start_health_check()

            # Update global state
            if self.state == BrowserState.STARTING:
                self.state = BrowserState.RUNNING
                self._last_health_check = datetime.now()
                self._notify_status_change("running")

            logger.info(f"✅ Browser session started: {session_id} (PID: {browser_pid})")

            return {
                "status": "started",
                "session_id": session_id,
                "pid": browser_pid,
                "state": self.state.value
            }

        except Exception as e:
            logger.error(f"❌ Failed to start browser session {session_id}: {e}")

            # Only update global state to ERROR if no other sessions are running
            if not self._managed_sessions:
                self.state = BrowserState.ERROR
                self._notify_status_change("error")

            # Cleanup failed session
            await self._cleanup_failed_session(session_id)

            raise RuntimeError(f"Failed to start browser session {session_id}: {e}")

    def get_session(self, session_id: str) -> Optional[Any]:
        """Get browser session by ID

        Args:
            session_id: Session identifier

        Returns:
            BrowserSessionInfo object or None if not found
        """
        managed = self._managed_sessions.get(session_id)
        if managed:
            return managed.get("session_info")
        return None

    def get_all_sessions(self) -> Dict[str, Any]:
        """Get all managed browser sessions

        Returns:
            Dict mapping session_id to session metadata
        """
        result = {}
        for session_id, managed in self._managed_sessions.items():
            result[session_id] = {
                "pid": managed.get("pid"),
                "headless": managed.get("headless"),
                "created_at": managed.get("created_at").isoformat() if managed.get("created_at") else None
            }
        return result

    async def stop_browser(self, force: bool = False) -> Dict[str, Any]:
        """Stop all browser sessions gracefully

        Args:
            force: If True, force close even if tasks are running

        Returns:
            Dict with status

        Raises:
            RuntimeError: If browser fails to stop
        """
        if self.state == BrowserState.STOPPED or self.state == BrowserState.NOT_STARTED:
            logger.info("Browser already stopped")
            return {"status": "already_stopped", "state": self.state.value}

        if self.state == BrowserState.STOPPING:
            logger.warning("Browser is already stopping")
            return {"status": "stopping", "state": self.state.value}

        logger.info(f"Stopping all browser sessions ({len(self._managed_sessions)} sessions)...")
        self.state = BrowserState.STOPPING
        self._notify_status_change("stopping")

        try:
            # Stop health check task
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
                logger.debug("Health check task stopped")

            # Close all managed sessions
            if self.session_manager:
                session_ids = list(self._managed_sessions.keys())
                for session_id in session_ids:
                    try:
                        await self.session_manager.close_session(session_id, force=True)
                        logger.debug(f"Browser session closed: {session_id}")
                    except Exception as e:
                        logger.error(f"Error closing session {session_id}: {e}")

            # Clear all references
            self._managed_sessions.clear()
            self._last_health_check = None

            # Update state
            self.state = BrowserState.STOPPED
            self._notify_status_change("stopped")

            logger.info("✅ All browser sessions stopped successfully")

            return {"status": "stopped", "state": self.state.value}

        except Exception as e:
            logger.error(f"❌ Failed to stop browser: {e}")
            self.state = BrowserState.ERROR
            self._notify_status_change("error")
            raise RuntimeError(f"Failed to stop browser: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current browser status

        Returns:
            Dict with detailed status information including all sessions
        """
        return {
            "state": self.state.value,
            "is_running": self.state == BrowserState.RUNNING,
            "total_sessions": len(self._managed_sessions),
            "sessions": self.get_all_sessions(),
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
            "health_monitoring": self._health_check_task is not None and not self._health_check_task.done()
        }

    def is_ready(self) -> bool:
        """Check if browser is ready for use

        Returns:
            True if browser is running and has at least one session
        """
        return self.state == BrowserState.RUNNING and len(self._managed_sessions) > 0

    def subscribe_status_change(self, callback: Callable[[str], None]):
        """Subscribe to browser status change events

        Args:
            callback: Function to call when status changes
                     callback(new_state: str)
        """
        self._status_callbacks.append(callback)

    def _notify_status_change(self, new_state: str):
        """Notify all subscribers of status change

        Args:
            new_state: New browser state
        """
        for callback in self._status_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    async def _get_browser_pid_from_session(self, session_info) -> Optional[int]:
        """Get browser process PID from session info

        Args:
            session_info: BrowserSessionInfo object

        Returns:
            Browser PID or None if not found
        """
        try:
            if not session_info:
                return None

            # Get CDP URL from browser session
            session = session_info.session
            cdp_url = session.cdp_url

            if not cdp_url:
                logger.warning("No CDP URL available")
                return None

            # Extract port from CDP URL (e.g., "ws://localhost:60288/devtools/...")
            # Format: ws://host:port/path
            parts = cdp_url.split(':')
            if len(parts) >= 3:
                port_str = parts[2].split('/')[0]
                cdp_port = int(port_str)
                logger.debug(f"Looking for browser process on CDP port {cdp_port}")

                # Find process listening on this port
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        proc_name = proc.info['name'].lower()
                        if 'chrome' in proc_name or 'chromium' in proc_name:
                            # Check if this process is listening on our CDP port
                            connections = proc.connections()
                            for conn in connections:
                                if hasattr(conn, 'laddr') and hasattr(conn.laddr, 'port'):
                                    if conn.laddr.port == cdp_port:
                                        logger.info(f"Found browser process: PID={proc.info['pid']}, Name={proc.info['name']}")
                                        return proc.info['pid']
                    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                        continue

            logger.warning(f"Could not find browser process for CDP URL: {cdp_url}")
            return None

        except Exception as e:
            logger.warning(f"Could not get browser PID: {e}")
            return None

    async def _cleanup_failed_session(self, session_id: str):
        """Cleanup resources after failed session start

        Args:
            session_id: Session identifier to cleanup
        """
        try:
            if self.session_manager:
                await self.session_manager.close_session(session_id, force=True)
        except Exception as e:
            logger.debug(f"Error during session cleanup: {e}")

        # Remove from managed sessions if it exists
        if session_id in self._managed_sessions:
            del self._managed_sessions[session_id]

    def _start_health_check(self):
        """Start background health check task"""
        if self._health_check_task and not self._health_check_task.done():
            logger.debug("Health check already running")
            return

        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.debug("Health check task started")

    async def _health_check_loop(self):
        """Continuous health monitoring loop"""
        logger.info("🏥 Health check loop started")

        while True:
            try:
                await asyncio.sleep(self._health_check_interval)

                # Skip health check if not in running state
                if self.state != BrowserState.RUNNING:
                    continue

                # Check CDP connection
                is_alive = await self._check_cdp_alive()

                if is_alive:
                    # Update last check time
                    self._last_health_check = datetime.now()
                    logger.debug("✓ Browser health check passed")
                else:
                    logger.warning("❌ Browser health check failed - connection lost")
                    await self._handle_connection_lost()

            except asyncio.CancelledError:
                logger.info("🛑 Health check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                # Continue checking despite errors
                await asyncio.sleep(self._health_check_interval)

    async def _check_cdp_alive(self) -> bool:
        """Check if any CDP connection is alive

        Returns:
            True if at least one browser session is responsive, False otherwise
        """
        if not self._managed_sessions:
            return False

        # Check all managed sessions
        any_alive = False
        for session_id, managed in list(self._managed_sessions.items()):
            session_info = managed.get("session_info")
            if not session_info:
                continue

            try:
                session = session_info.session

                # Get CDP session
                cdp_session = await session.get_or_create_cdp_session(focus=False)

                # Send a lightweight CDP command to verify connection
                result = await asyncio.wait_for(
                    cdp_session.cdp_client.send.Browser.getVersion(
                        session_id=cdp_session.session_id
                    ),
                    timeout=3.0
                )

                if result is not None:
                    any_alive = True
                    logger.debug(f"✓ Session {session_id} health check passed")
                else:
                    logger.warning(f"✗ Session {session_id} health check failed")

            except asyncio.TimeoutError:
                logger.debug(f"CDP health check timed out for session {session_id}")
            except Exception as e:
                logger.debug(f"CDP health check failed for session {session_id}: {type(e).__name__}: {e}")

        return any_alive

    async def _handle_connection_lost(self):
        """Handle CDP connection loss for all sessions

        This method determines whether browser sessions were:
        1. Closed by user (process does not exist)
        2. Crashed or connection issue (process exists but unresponsive)
        """
        logger.warning("🔴 Handling connection loss for all sessions...")

        # Check each managed session
        all_closed = True
        for session_id, managed in list(self._managed_sessions.items()):
            pid = managed.get("pid")
            process_exists = self._check_process_exists(pid)

            if not process_exists:
                # Session was closed by user or crashed
                logger.info(f"🔴 Browser session {session_id} was closed (PID {pid} not found)")
                # Remove from managed sessions
                del self._managed_sessions[session_id]
            else:
                # Process exists but connection lost
                logger.warning(f"⚠️ Browser session {session_id} process exists but CDP connection lost (PID {pid})")
                all_closed = False

        # Update global state based on remaining sessions
        if not self._managed_sessions:
            # All sessions closed
            logger.info("🔴 All browser sessions closed")
            self.state = BrowserState.STOPPED

            # Stop health check
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()

            # Notify listeners
            self._notify_status_change("closed_by_user")
        elif not all_closed:
            # Some sessions have connection issues
            logger.warning("⚠️ Some browser sessions have connection issues")
            self.state = BrowserState.ERROR
            self._notify_status_change("connection_error")

    def _check_process_exists(self, pid: Optional[int]) -> bool:
        """Check if a process with given PID exists

        Args:
            pid: Process ID to check

        Returns:
            True if process exists, False otherwise
        """
        if pid is None:
            return False

        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False


    async def cleanup(self):
        """Cleanup all browser resources

        This should be called when shutting down the application
        """
        logger.info("Cleaning up browser manager...")

        # Stop browser if running
        if self.state == BrowserState.RUNNING or self.state == BrowserState.STARTING:
            try:
                await self.stop_browser(force=True)
            except Exception as e:
                logger.error(f"Error stopping browser during cleanup: {e}")

        # Final cleanup
        if self.session_manager:
            try:
                await self.session_manager.close_all_sessions()
            except Exception as e:
                logger.error(f"Error closing all sessions: {e}")

        logger.info("✅ Browser manager cleanup complete")
