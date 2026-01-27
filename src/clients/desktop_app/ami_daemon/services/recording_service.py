"""
RecordingService - User behavior recording service using HybridBrowserSession.

This service manages the recording lifecycle and provides a clean API for:
- Starting/stopping recording sessions
- Accessing recorded operations
- Capturing DOM snapshots
- Saving recordings to storage

This replaces the old CDPRecorder that used browser-use's BrowserSession.
Now it uses HybridBrowserSession with integrated BehaviorRecorder.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class RecordingService:
    """Recording service using HybridBrowserSession.

    This service provides the same API as the old CDPRecorder but uses
    HybridBrowserSession internally, which has better anti-detection
    capabilities and unified browser control.
    """

    def __init__(self, storage_manager: StorageManager):
        """Initialize recording service.

        Args:
            storage_manager: Storage manager for saving recordings.
        """
        self.storage = storage_manager

        # Recording state
        self.current_session_id: Optional[str] = None
        self.current_user_id: Optional[str] = None
        self.recording_start_time: Optional[datetime] = None
        self.task_metadata: Dict[str, Any] = {}
        self._is_recording = False

        # Browser session and recorder
        self._browser_session: Optional[Any] = None
        self._behavior_recorder: Optional[Any] = None

        # Status change callback
        self._status_callbacks: List[Callable[[str], None]] = []

    def subscribe_status_change(self, callback: Callable[[str], None]):
        """Subscribe to recording status changes.

        Args:
            callback: Function called with status string.
        """
        self._status_callbacks.append(callback)

    def _notify_status_change(self, status: str):
        """Notify subscribers of status change."""
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")

    async def start_recording(
        self,
        url: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        headless: bool = False,
    ) -> Dict[str, Any]:
        """Start a new recording session.

        Args:
            url: Starting URL to navigate to.
            user_id: User ID for multi-user support.
            metadata: Optional task metadata.
            headless: Whether to run browser in headless mode.

        Returns:
            Dict with session_id, status, and url.

        Raises:
            RuntimeError: If recording fails to start.
        """
        if self._is_recording:
            raise RuntimeError("Recording already in progress")

        # Import here to avoid circular dependencies
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import (
            HybridBrowserSession,
        )
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.behavior_recorder import (
            BehaviorRecorder,
        )

        # Generate session ID
        self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_user_id = user_id
        self.recording_start_time = datetime.now()
        self.task_metadata = metadata or {}

        logger.info(f"Starting recording session: {self.current_session_id}")

        try:
            # Get user data directory for browser state persistence
            user_data_dir = self._get_browser_data_dir(user_id)

            # Create browser session with unique session_id to avoid conflicts
            self._browser_session = HybridBrowserSession(
                headless=headless,
                stealth=True,
                user_data_dir=user_data_dir,
                session_id=f"recording_{self.current_session_id}",
            )

            # Ensure browser is started
            await self._browser_session.ensure_browser()
            logger.info("Browser session initialized")

            # Create behavior recorder
            self._behavior_recorder = BehaviorRecorder(enable_dom_capture=True)

            # Start recording
            await self._behavior_recorder.start_recording(self._browser_session)
            logger.info("Behavior recorder started")

            # Navigate to starting URL (skip about:blank)
            if url and url != "about:blank":
                await self._browser_session.visit(url)
                logger.info(f"Navigated to: {url}")

            self._is_recording = True
            self._notify_status_change("recording")

            return {
                "session_id": self.current_session_id,
                "status": "recording",
                "url": url,
            }

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            await self._cleanup()
            raise RuntimeError(f"Failed to start recording: {e}")

    async def stop_recording(self) -> Dict[str, Any]:
        """Stop recording and save results.

        Returns:
            Dict with session_id, operations_count, and file path.

        Raises:
            RuntimeError: If no recording is active.
        """
        if not self._is_recording or not self.current_session_id:
            raise RuntimeError("No active recording session")

        logger.info(f"Stopping recording session: {self.current_session_id}")

        try:
            # Stop behavior recorder and get results
            recording_result = {}
            if self._behavior_recorder:
                recording_result = await self._behavior_recorder.stop_recording()

            operations = recording_result.get("operations", [])
            dom_snapshots = recording_result.get("dom_snapshots", {})

            logger.info(f"Captured {len(operations)} operations, {len(dom_snapshots)} DOM snapshots")

            # Build URL to dom_id mapping
            url_to_dom_id = {}
            for url in dom_snapshots.keys():
                url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
                url_to_dom_id[url] = url_hash

            # Add dom_id to each operation
            for op in operations:
                op_url = op.get("url", "")
                op["dom_id"] = url_to_dom_id.get(op_url)

            # Prepare recording data
            recording_data = {
                "session_id": self.current_session_id,
                "timestamp": self.recording_start_time.isoformat() if self.recording_start_time else None,
                "ended_at": datetime.now().isoformat(),
                "operations_count": len(operations),
                "task_metadata": self.task_metadata,
                "operations": operations,
            }

            # Save to local storage
            if not self.current_user_id:
                raise RuntimeError("User ID not set for current recording session")

            self.storage.save_recording(
                user_id=self.current_user_id,
                session_id=self.current_session_id,
                recording_data=recording_data,
            )

            # Save DOM snapshots
            recording_path = self.storage._user_path(self.current_user_id) / "recordings" / self.current_session_id
            if dom_snapshots:
                self._save_dom_snapshots(recording_path, dom_snapshots)

            result = {
                "session_id": self.current_session_id,
                "operations_count": len(operations),
                "local_file_path": str(recording_path / "operations.json"),
                "dom_snapshots_count": len(dom_snapshots),
            }

            # Cleanup (but don't close browser - keep it open)
            session_id = self.current_session_id
            await self._cleanup(close_browser=False)

            self._notify_status_change("stopped")
            logger.info(f"Recording stopped: {session_id}, {len(operations)} operations saved")

            return result

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            await self._cleanup()
            raise

    async def _cleanup(self, close_browser: bool = True):
        """Clean up recording state.

        Args:
            close_browser: Whether to close the browser session.
        """
        self._is_recording = False

        if close_browser and self._browser_session:
            try:
                await self._browser_session.close()
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")

        self._browser_session = None
        self._behavior_recorder = None
        self.current_session_id = None
        self.current_user_id = None
        self.recording_start_time = None
        self.task_metadata = {}

    def get_operations(self) -> List[Dict[str, Any]]:
        """Get current recorded operations.

        Returns:
            List of operation dicts.
        """
        if self._behavior_recorder:
            return self._behavior_recorder.get_operations()
        return []

    def get_operations_count(self) -> int:
        """Get count of recorded operations.

        Returns:
            Number of operations.
        """
        if self._behavior_recorder:
            return self._behavior_recorder.get_operations_count()
        return 0

    def is_recording(self) -> bool:
        """Check if recording is active.

        Returns:
            True if recording is in progress.
        """
        return self._is_recording

    def get_browser_session(self) -> Optional[Any]:
        """Get the underlying browser session.

        Returns:
            HybridBrowserSession instance or None.
        """
        return self._browser_session

    def _get_browser_data_dir(self, user_id: str) -> str:
        """Get browser data directory for user.

        Args:
            user_id: User identifier.

        Returns:
            Path to browser data directory.
        """
        base_path = Path.home() / ".ami" / "users" / user_id / "browser_data"
        base_path.mkdir(parents=True, exist_ok=True)
        return str(base_path)

    def _save_dom_snapshots(self, recording_path: Path, dom_snapshots: Dict[str, Dict]) -> None:
        """Save DOM snapshots to recording directory.

        Format matches cloud backend storage:
        recording_path/dom_snapshots/{url_hash}.json
        recording_path/dom_snapshots/url_index.json

        Args:
            recording_path: Path to recording directory.
            dom_snapshots: URL -> DOM dict mapping.
        """
        dom_dir = recording_path / "dom_snapshots"
        dom_dir.mkdir(parents=True, exist_ok=True)

        url_index = []

        for url, dom_dict in dom_snapshots.items():
            # Use MD5 hash of URL for filename
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            dom_filename = f"{url_hash}.json"
            dom_file = dom_dir / dom_filename
            captured_at = dom_dict.get("captured_at", datetime.now().isoformat())

            dom_data = {
                "url": url,
                "dom": dom_dict,
                "captured_at": captured_at,
            }

            try:
                with open(dom_file, "w", encoding="utf-8") as f:
                    json.dump(dom_data, f, indent=2, ensure_ascii=False)
                logger.debug(f"Saved DOM snapshot for {url} -> {dom_filename}")

                url_index.append({
                    "url": url,
                    "file": dom_filename,
                    "captured_at": captured_at,
                })
            except Exception as e:
                logger.warning(f"Failed to save DOM snapshot for {url}: {e}")

        # Save URL index file
        index_file = dom_dir / "url_index.json"
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(url_index, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved URL index with {len(url_index)} entries")
        except Exception as e:
            logger.warning(f"Failed to save URL index: {e}")

        logger.info(f"Saved {len(dom_snapshots)} DOM snapshots to {dom_dir}")

    async def close_browser(self) -> None:
        """Close the browser session.

        Call this when recording is done and browser should be closed.
        """
        if self._browser_session:
            try:
                await self._browser_session.close()
                logger.info("Browser session closed")
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")
            finally:
                self._browser_session = None
