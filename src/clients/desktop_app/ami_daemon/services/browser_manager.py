"""Browser lifecycle management with health monitoring

This module uses HybridBrowserSession for browser session management.
"""
import asyncio
import logging
import psutil
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from src.clients.desktop_app.ami_daemon.services.browser_state import BrowserState
from src.clients.desktop_app.ami_daemon.services.browser_window_manager import BrowserWindowManager

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage browser lifecycle with on-demand startup and health monitoring

    Uses HybridBrowserSession for browser session management.
    """

    def __init__(self, config_service=None):
        """Initialize browser manager

        Args:
            config_service: Configuration service for user data directory
        """
        self.config_service = config_service
        self.state = BrowserState.NOT_STARTED

        # Browser session - using HybridBrowserSession
        self._session = None
        self._session_id: Optional[str] = None
        self._browser_pid: Optional[int] = None

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
            HybridBrowserSession or None
        """
        return self._session

    async def start_browser(self, headless: bool = False) -> Dict[str, Any]:
        """Start browser session

        Args:
            headless: Whether to run browser in headless mode

        Returns:
            Dict with status, pid, and state

        Raises:
            RuntimeError: If browser fails to start
        """
        # Check if session already exists
        if self._session is not None:
            logger.info("Browser session already exists")
            return {
                "status": "already_running",
                "session_id": self._session_id,
                "pid": self._browser_pid,
                "state": self.state.value
            }

        logger.info(f"Starting browser session (headless={headless})...")
        self.state = BrowserState.STARTING
        self._notify_status_change("starting")

        try:
            # Import HybridBrowserSession
            from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser import (
                HybridBrowserSession
            )

            # Create browser session
            self._session = HybridBrowserSession(
                config_service=self.config_service,
                headless=headless
            )

            # Initialize browser
            await self._session.initialize()

            # Get browser PID
            self._browser_pid = await self._get_browser_pid()
            self._session_id = "global"

            # Start health check
            if not self._health_check_task or self._health_check_task.done():
                self._start_health_check()

            # Update state
            self.state = BrowserState.RUNNING
            self._last_health_check = datetime.now()
            self._notify_status_change("running")

            logger.info(f"✅ Browser session started (PID: {self._browser_pid})")

            return {
                "status": "started",
                "session_id": self._session_id,
                "pid": self._browser_pid,
                "state": self.state.value
            }

        except Exception as e:
            logger.error(f"❌ Failed to start browser session: {e}")
            self.state = BrowserState.ERROR
            self._notify_status_change("error")

            # Cleanup failed session
            await self._cleanup_failed_session()

            raise RuntimeError(f"Failed to start browser session: {e}")

    async def stop_browser(self, force: bool = False) -> Dict[str, Any]:
        """Stop browser session gracefully

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

        logger.info("Stopping browser session...")
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

            # Close session
            if self._session:
                try:
                    await self._session.close()
                    logger.debug("Browser session closed")
                except Exception as e:
                    logger.error(f"Error closing session: {e}")

            # Clear references
            self._session = None
            self._session_id = None
            self._browser_pid = None
            self._last_health_check = None

            # Update state
            self.state = BrowserState.STOPPED
            self._notify_status_change("stopped")

            logger.info("✅ Browser session stopped successfully")

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
            "is_running": self.state == BrowserState.RUNNING,
            "total_sessions": 1 if self._session else 0,
            "sessions": {
                self._session_id: {
                    "pid": self._browser_pid,
                    "headless": getattr(self._session, '_headless', False) if self._session else None
                }
            } if self._session else {},
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
            "health_monitoring": self._health_check_task is not None and not self._health_check_task.done()
        }

    def is_ready(self) -> bool:
        """Check if browser is ready for use

        Returns:
            True if browser is running
        """
        return self.state == BrowserState.RUNNING and self._session is not None

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
        """Get browser process PID

        Returns:
            Browser PID or None if not found
        """
        try:
            if not self._session:
                return None

            # Try to get PID from browser launcher (subprocess-based)
            if hasattr(self._session, '_browser_launcher') and self._session._browser_launcher:
                launcher = self._session._browser_launcher
                if hasattr(launcher, '_process') and launcher._process:
                    pid = launcher._process.pid
                    logger.info(f"Found browser process from launcher: PID={pid}")
                    return pid

            # Fallback: search for Chrome process by name
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name'].lower()
                    if 'chrome' in proc_name or 'chromium' in proc_name:
                        logger.info(f"Found browser process: PID={proc.info['pid']}, Name={proc.info['name']}")
                        return proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    continue

            logger.warning("Could not find browser process")
            return None

        except Exception as e:
            logger.warning(f"Could not get browser PID: {e}")
            return None

    async def _cleanup_failed_session(self):
        """Cleanup resources after failed session start"""
        try:
            if self._session:
                await self._session.close()
        except Exception as e:
            logger.debug(f"Error during session cleanup: {e}")

        self._session = None
        self._session_id = None
        self._browser_pid = None

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
                await asyncio.sleep(self._health_check_interval)

    async def _check_cdp_alive(self) -> bool:
        """Check if browser session is alive

        Returns:
            True if browser session is responsive, False otherwise
        """
        if not self._session:
            return False

        try:
            # Check if session has active page
            if hasattr(self._session, '_page') and self._session._page is not None:
                if not self._session._page.is_closed():
                    try:
                        url = self._session._page.url
                        logger.debug(f"✓ Health check passed (url: {url[:50]}...)")
                        return True
                    except Exception:
                        logger.warning("✗ Health check failed - page unresponsive")
                        return False
            return False

        except Exception as e:
            logger.debug(f"Health check failed: {type(e).__name__}: {e}")
            return False

    async def _handle_connection_lost(self):
        """Handle CDP connection loss"""
        logger.warning("🔴 Handling connection loss...")

        process_exists = self._check_process_exists(self._browser_pid)

        if not process_exists:
            logger.info(f"🔴 Browser was closed (PID {self._browser_pid} not found)")
            self._session = None
            self._session_id = None
            self._browser_pid = None
            self.state = BrowserState.STOPPED

            # Stop health check
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()

            self._notify_status_change("closed_by_user")
        else:
            logger.warning(f"⚠️ Browser process exists but CDP connection lost (PID {self._browser_pid})")
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

        logger.info("✅ Browser manager cleanup complete")
