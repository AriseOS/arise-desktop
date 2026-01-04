"""CDP-based recording service"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.browser_manager import BrowserManager

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
        from src.clients.desktop_app.ami_daemon.base_agent.tools.browser_use.user_behavior.monitor import (
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

        # Enable DOM capture for script pre-generation
        self.monitor.enable_dom_capture(True)
        logger.info("DOM capture enabled for recording")

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

        # Get DOM snapshots BEFORE stopping monitoring
        dom_snapshots = {}
        if self.monitor:
            dom_snapshots = self.monitor.get_dom_snapshots()
            logger.info(f"Captured {len(dom_snapshots)} DOM snapshots during recording")
            self.monitor._is_monitoring = False

        # Build URL to dom_id mapping
        url_to_dom_id = {}
        for url in dom_snapshots.keys():
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            url_to_dom_id[url] = url_hash

        # Add dom_id to each operation
        for op in self.operations:
            op_url = op.get("url", "")
            op["dom_id"] = url_to_dom_id.get(op_url)  # None if no DOM for this URL

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

        # Save DOM snapshots to separate files (for script pre-generation)
        recording_path = self.storage._user_path(self.current_user_id) / "recordings" / self.current_session_id
        if dom_snapshots:
            self._save_dom_snapshots(recording_path, dom_snapshots)

        result = {
            "session_id": self.current_session_id,
            "operations_count": len(self.operations),
            "local_file_path": str(recording_path / "operations.json"),
            "dom_snapshots_count": len(dom_snapshots)
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

    def _save_dom_snapshots(self, recording_path: Path, dom_snapshots: Dict[str, dict]) -> None:
        """Save DOM snapshots to recording directory

        Format matches cloud backend storage:
        recording_path/dom_snapshots/{url_hash}.json
        recording_path/dom_snapshots/url_index.json (URL -> file mapping)

        Each DOM file contains: {"url": "...", "dom": {...}}
        url_index.json contains: [{"url": "...", "file": "xxx.json", "captured_at": "..."}]

        Args:
            recording_path: Path to recording directory
            dom_snapshots: URL -> DOM dict mapping
        """
        dom_dir = recording_path / "dom_snapshots"
        dom_dir.mkdir(parents=True, exist_ok=True)

        # Build URL index for easy lookup
        url_index = []

        for url, dom_dict in dom_snapshots.items():
            # Use MD5 hash of URL for filename (same as cloud backend)
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            dom_filename = f"{url_hash}.json"
            dom_file = dom_dir / dom_filename
            captured_at = datetime.now().isoformat()

            dom_data = {
                "url": url,
                "dom": dom_dict,
                "captured_at": captured_at
            }

            try:
                with open(dom_file, 'w', encoding='utf-8') as f:
                    json.dump(dom_data, f, ensure_ascii=False)
                logger.debug(f"Saved DOM snapshot for {url} -> {dom_filename}")

                # Add to URL index
                url_index.append({
                    "url": url,
                    "file": dom_filename,
                    "captured_at": captured_at
                })
            except Exception as e:
                logger.warning(f"Failed to save DOM snapshot for {url}: {e}")

        # Save URL index file
        index_file = dom_dir / "url_index.json"
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(url_index, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved URL index with {len(url_index)} entries")
        except Exception as e:
            logger.warning(f"Failed to save URL index: {e}")

        logger.info(f"Saved {len(dom_snapshots)} DOM snapshots to {dom_dir}")

    def get_operations_count(self) -> int:
        """Get current operations count"""
        return len(self.operations)
