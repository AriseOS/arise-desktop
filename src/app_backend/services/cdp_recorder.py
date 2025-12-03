"""CDP-based recording service"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.services.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


class CDPRecorder:
    """CDP-based operation recorder using SimpleUserBehaviorMonitor"""

    def __init__(
        self,
        storage_manager: StorageManager,
        browser_manager: BrowserManager
    ):
        """Initialize CDP recorder

        Args:
            storage_manager: Storage manager for saving recordings
            browser_manager: Browser manager for CDP access
        """
        self.storage = storage_manager
        self.browser = browser_manager

        # Recording state
        self.current_session_id: Optional[str] = None
        self.current_user_id: Optional[str] = None  # Track user_id for current recording
        self.operations: List[Dict[str, Any]] = []
        self.monitor = None
        self.recording_start_time = None
        self.task_metadata: Dict[str, Any] = {}
        self._is_recording = False

        # Subscribe to browser status changes
        self.browser.subscribe_status_change(self._handle_browser_status_change)

    def _handle_browser_status_change(self, new_state: str):
        """Handle browser status change events

        Args:
            new_state: New browser state (e.g., "closed_by_user", "running", "error")
        """
        logger.info(f"Browser status changed to: {new_state}")

        # If user closes browser during recording, stop recording
        if new_state == "closed_by_user" and self._is_recording:
            logger.warning("Browser was closed by user during recording. Stopping recording...")

            # We need to run stop_recording asynchronously, but this callback is synchronous
            # Schedule it to run in the event loop
            import asyncio
            try:
                # Get the running event loop
                loop = asyncio.get_event_loop()
                # Schedule stop_recording as a task
                loop.create_task(self._handle_user_close())
            except Exception as e:
                logger.error(f"Failed to schedule recording stop: {e}")

    async def _handle_user_close(self):
        """Handle user closing browser during recording"""
        try:
            if self._is_recording and self.current_session_id:
                operations_count = len(self.operations)
                await self.stop_recording()
                logger.info(f"Recording stopped due to user closing browser. {operations_count} operations saved.")
        except Exception as e:
            logger.error(f"Error stopping recording after user close: {e}")

    async def start_recording(self, url: str, user_id: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start CDP recording session

        Args:
            url: Starting URL to navigate to
            user_id: User ID for multi-user support
            metadata: Task metadata including user's natural language description

        Returns:
            Session info with session_id and status
        """
        # Create session ID
        self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_user_id = user_id  # Store user_id for later use
        self.operations = []
        self.recording_start_time = datetime.now()
        self.task_metadata = metadata or {}  # Store metadata

        # Get global browser session (BrowserSessionInfo)
        browser_session_info = self.browser.global_session

        if not browser_session_info:
            raise RuntimeError("Global browser session not initialized")

        # Initialize SimpleUserBehaviorMonitor
        from src.clients.base_app.base_app.base_agent.tools.browser_use.user_behavior.monitor import (
            SimpleUserBehaviorMonitor
        )

        self.monitor = SimpleUserBehaviorMonitor(operation_list=self.operations)

        # Navigate to starting URL first to ensure page is loaded
        await browser_session_info.session.navigate_to(url)

        # Wait for page to be fully loaded before setting up monitoring
        import asyncio
        await asyncio.sleep(2.0)

        # Setup monitoring (CDP Binding + script injection)
        # Pass the actual BrowserSession object, not BrowserSessionInfo
        await self.monitor.setup_monitoring(browser_session_info.session)

        # Mark as recording
        self._is_recording = True

        return {
            "session_id": self.current_session_id,
            "status": "recording",
            "url": url
        }

    async def stop_recording(self) -> Dict[str, Any]:
        """Stop recording session and save to local storage

        Returns:
            Session info with operations count and file path
        """
        if not self.current_session_id:
            raise RuntimeError("No active recording session")

        # Stop monitoring
        if self.monitor:
            self.monitor._is_monitoring = False

        # Prepare recording data
        recording_data = {
            "session_id": self.current_session_id,
            "timestamp": self.recording_start_time.isoformat(),
            "ended_at": datetime.now().isoformat(),
            "operations_count": len(self.operations),
            "task_metadata": self.task_metadata,  # Save task metadata
            "operations": self.operations
        }

        # Save to local storage
        if not self.current_user_id:
            raise RuntimeError("User ID not set for current recording session")

        self.storage.save_recording(
            user_id=self.current_user_id,
            session_id=self.current_session_id,
            recording_data=recording_data
        )

        result = {
            "session_id": self.current_session_id,
            "operations_count": len(self.operations),
            "local_file_path": str(
                self.storage._user_path(self.current_user_id) / "recordings" /
                self.current_session_id / "operations.json"
            )
        }

        # Cleanup
        session_id = self.current_session_id
        self.current_session_id = None
        self.current_user_id = None
        self.operations = []
        self.monitor = None
        self.recording_start_time = None
        self.task_metadata = {}
        self._is_recording = False

        # Note: Browser session remains open (persistent)

        return result

    def get_operations_count(self) -> int:
        """Get current operations count"""
        return len(self.operations)
