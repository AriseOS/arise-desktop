"""CDP-based recording service"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.services.browser_manager import BrowserManager


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
        self.operations: List[Dict[str, Any]] = []
        self.monitor = None
        self.recording_start_time = None
        self.task_metadata: Dict[str, Any] = {}

    async def start_recording(self, url: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start CDP recording session

        Args:
            url: Starting URL to navigate to
            metadata: Task metadata including user's natural language description

        Returns:
            Session info with session_id and status
        """
        # Create session ID
        self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        self.storage.save_recording(
            user_id="default_user",  # MVP: single user
            session_id=self.current_session_id,
            recording_data=recording_data
        )

        result = {
            "session_id": self.current_session_id,
            "operations_count": len(self.operations),
            "local_file_path": str(
                self.storage._user_path("default_user") / "recordings" /
                self.current_session_id / "operations.json"
            )
        }

        # Cleanup
        session_id = self.current_session_id
        self.current_session_id = None
        self.operations = []
        self.monitor = None
        self.recording_start_time = None
        self.task_metadata = {}

        # Note: Browser session remains open (persistent)

        return result

    def get_operations_count(self) -> int:
        """Get current operations count"""
        return len(self.operations)
