"""Browser lifecycle management with health monitoring"""
import asyncio
import logging
import psutil
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from src.app_backend.services.browser_state import BrowserState
from src.app_backend.services.browser_window_manager import BrowserWindowManager

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
        self.global_session = None
        self._browser_pid: Optional[int] = None

        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 5  # Check every 5 seconds
        self._last_health_check: Optional[datetime] = None

        # Window management
        self.window_manager = BrowserWindowManager(config_service=config_service)

        # Event callbacks
        self._status_callbacks: list[Callable] = []

    async def start_browser(self, headless: bool = False) -> Dict[str, Any]:
        """Start browser on demand

        Args:
            headless: Whether to run browser in headless mode

        Returns:
            Dict with status, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        if self.state == BrowserState.RUNNING:
            logger.info("Browser already running")
            return {
                "status": "already_running",
                "pid": self._browser_pid,
                "state": self.state.value
            }

        if self.state == BrowserState.STARTING:
            logger.warning("Browser is already starting")
            return {
                "status": "starting",
                "state": self.state.value
            }

        logger.info(f"Starting browser (headless={headless})...")
        self.state = BrowserState.STARTING
        self._notify_status_change("starting")

        try:
            # Import here to avoid circular dependency
            from src.clients.base_app.base_app.base_agent.tools.browser_session_manager import (
                BrowserSessionManager
            )

            # Get or create session manager instance
            self.session_manager = await BrowserSessionManager.get_instance()

            # Create browser session
            self.global_session = await self.session_manager.get_or_create_session(
                session_id="global",
                config_service=self.config_service,
                headless=headless,
                keep_alive=True
            )

            # Get browser PID
            self._browser_pid = await self._get_browser_pid()

            # Start health check
            self._start_health_check()

            # Update state
            self.state = BrowserState.RUNNING
            self._last_health_check = datetime.now()
            self._notify_status_change("running")

            logger.info(f"✅ Browser started successfully (PID: {self._browser_pid})")

            # Arrange windows if not headless
            window_result = {"arranged": False}
            if not headless and self._browser_pid:
                # Wait for browser window to be ready
                await asyncio.sleep(1.5)

                # Arrange windows side by side
                window_result = self.window_manager.arrange_windows(
                    browser_pid=self._browser_pid,
                    app_name="Ami"
                )

            return {
                "status": "started",
                "pid": self._browser_pid,
                "state": self.state.value,
                "windows_arranged": window_result.get("success", False)
            }

        except Exception as e:
            logger.error(f"❌ Failed to start browser: {e}")
            self.state = BrowserState.ERROR
            self._notify_status_change("error")

            # Cleanup on failure
            await self._cleanup_failed_start()

            raise RuntimeError(f"Failed to start browser: {e}")

    async def stop_browser(self, force: bool = False) -> Dict[str, Any]:
        """Stop browser gracefully

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

        logger.info("Stopping browser...")
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

            # Close browser session
            if self.session_manager and self.global_session:
                await self.session_manager.close_session("global", force=True)
                logger.debug("Browser session closed")

            # Clear references
            self.global_session = None
            self._browser_pid = None
            self._last_health_check = None

            # Update state
            self.state = BrowserState.STOPPED
            self._notify_status_change("stopped")

            logger.info("✅ Browser stopped successfully")

            return {"status": "stopped", "state": self.state.value}

        except Exception as e:
            logger.error(f"❌ Failed to stop browser: {e}")
            self.state = BrowserState.ERROR
            self._notify_status_change("error")
            raise RuntimeError(f"Failed to stop browser: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current browser status

        Returns:
            Dict with detailed status information
        """
        return {
            "state": self.state.value,
            "pid": self._browser_pid,
            "is_running": self.state == BrowserState.RUNNING,
            "session_exists": self.global_session is not None,
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
            "health_monitoring": self._health_check_task is not None and not self._health_check_task.done()
        }

    def is_ready(self) -> bool:
        """Check if browser is ready for use

        Returns:
            True if browser is running and healthy
        """
        return self.state == BrowserState.RUNNING and self.global_session is not None

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

    async def _get_browser_pid(self) -> Optional[int]:
        """Get browser process PID by finding process listening on CDP port

        Returns:
            Browser PID or None if not found
        """
        try:
            if not self.global_session:
                return None

            # Get CDP URL from browser session
            session = self.global_session.session
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
        """Check if CDP connection is alive

        Returns:
            True if browser is responsive, False otherwise
        """
        if not self.global_session:
            return False

        try:
            session = self.global_session.session

            # Get CDP session
            cdp_session = await session.get_or_create_cdp_session(focus=False)

            # Send a lightweight CDP command to verify connection
            result = await asyncio.wait_for(
                cdp_session.cdp_client.send.Browser.getVersion(
                    session_id=cdp_session.session_id
                ),
                timeout=3.0
            )

            return result is not None

        except asyncio.TimeoutError:
            logger.debug("CDP health check timed out")
            return False
        except Exception as e:
            logger.debug(f"CDP health check failed: {type(e).__name__}: {e}")
            return False

    async def _handle_connection_lost(self):
        """Handle CDP connection loss

        This method determines whether the browser was:
        1. Closed by user (process does not exist)
        2. Crashed or connection issue (process exists but unresponsive)
        """
        logger.warning("🔴 Handling connection loss...")

        # Check if browser process still exists
        process_exists = self._check_process_exists(self._browser_pid)

        if not process_exists:
            # User manually closed the browser
            logger.info("🔴 Browser was closed by user (process not found)")
            self.state = BrowserState.STOPPED
            self._browser_pid = None
            self.global_session = None

            # Stop health check
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()

            # Notify listeners
            self._notify_status_change("closed_by_user")

        else:
            # Process exists but connection lost - might be crash or temporary issue
            logger.warning("⚠️ Browser process exists but CDP connection lost")
            # For now, mark as error state
            # In future, could attempt reconnection
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

    async def _cleanup_failed_start(self):
        """Cleanup resources after failed browser start"""
        try:
            if self.session_manager:
                await self.session_manager.close_session("global", force=True)
        except Exception as e:
            logger.debug(f"Error during cleanup: {e}")

        self.global_session = None
        self._browser_pid = None

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
