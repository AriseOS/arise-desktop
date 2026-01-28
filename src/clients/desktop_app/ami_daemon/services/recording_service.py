"""
RecordingService - User behavior recording service using HybridBrowserSession.

This service manages the recording lifecycle and provides a clean API for:
- Starting/stopping recording sessions
- Accessing recorded operations
- Capturing page snapshots
- Saving recordings to storage (YAML format)

Recording format uses ref-based element identification compatible with ActionExecutor:
  - click: {type: click, ref: e42, text: Submit, role: button}
  - type: {type: type, ref: e15, value: hello, role: textbox}
  - navigate: {type: navigate, url: https://...}
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class RecordingService:
    """Recording service using HybridBrowserSession.

    This service provides recording capabilities using HybridBrowserSession
    with BehaviorRecorder for capturing user interactions in a format
    compatible with ActionExecutor for replay.
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
        """Subscribe to recording status changes."""
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
        """
        if self._is_recording:
            raise RuntimeError("Recording already in progress")

        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.behavior_recorder import (
            BehaviorRecorder,
        )
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import (
            HybridBrowserSession,
        )

        # Generate session ID
        self.current_session_id = (
            f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.current_user_id = user_id
        self.recording_start_time = datetime.now()
        self.task_metadata = metadata or {}

        logger.info(f"Starting recording session: {self.current_session_id}")

        try:
            # Get user data directory for browser state persistence
            user_data_dir = self._get_browser_data_dir(user_id)

            # Create browser session
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
            self._behavior_recorder = BehaviorRecorder(enable_snapshot_capture=True)

            # Start recording
            await self._behavior_recorder.start_recording(self._browser_session)
            logger.info("Behavior recorder started")

            # Navigate to starting URL
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
            snapshots = recording_result.get("snapshots", {})

            logger.info(
                f"Captured {len(operations)} operations, {len(snapshots)} snapshots"
            )

            # Prepare recording data
            recording_data = {
                "session_id": self.current_session_id,
                "created_at": (
                    self.recording_start_time.isoformat()
                    if self.recording_start_time
                    else None
                ),
                "ended_at": datetime.now().isoformat(),
                "operations_count": len(operations),
                "task_metadata": self.task_metadata,
                "operations": operations,
            }

            # Save to local storage (YAML format)
            if not self.current_user_id:
                raise RuntimeError("User ID not set for current recording session")

            self.storage.save_recording(
                user_id=self.current_user_id,
                session_id=self.current_session_id,
                recording_data=recording_data,
            )

            # Save snapshots (YAML format)
            if snapshots:
                self._save_snapshots(snapshots)

            recording_path = (
                self.storage._user_path(self.current_user_id)
                / "recordings"
                / self.current_session_id
            )

            result = {
                "session_id": self.current_session_id,
                "operations_count": len(operations),
                "local_file_path": str(recording_path / "recording.yaml"),
                "snapshot_count": len(snapshots),
            }

            # Cleanup and close browser
            session_id = self.current_session_id
            await self._cleanup(close_browser=True)

            self._notify_status_change("stopped")
            logger.info(
                f"Recording stopped: {session_id}, {len(operations)} operations saved"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            await self._cleanup()
            raise

    def _save_snapshots(self, snapshots: Dict[str, Dict]) -> None:
        """Save page snapshots to YAML files.

        Args:
            snapshots: URL hash -> snapshot data mapping.
        """
        if not self.current_user_id or not self.current_session_id:
            return

        for url_hash, snapshot_data in snapshots.items():
            try:
                self.storage.save_snapshot(
                    user_id=self.current_user_id,
                    session_id=self.current_session_id,
                    url_hash=url_hash,
                    snapshot_data=snapshot_data,
                )
                logger.debug(f"Saved snapshot: {url_hash}")
            except Exception as e:
                logger.warning(f"Failed to save snapshot {url_hash}: {e}")

        logger.info(f"Saved {len(snapshots)} snapshots")

    async def _cleanup(self, close_browser: bool = True):
        """Clean up recording state."""
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
        """Get current recorded operations."""
        if self._behavior_recorder:
            return self._behavior_recorder.get_operations()
        return []

    def get_operations_count(self) -> int:
        """Get count of recorded operations."""
        if self._behavior_recorder:
            return self._behavior_recorder.get_operations_count()
        return 0

    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._is_recording

    def get_browser_session(self) -> Optional[Any]:
        """Get the underlying browser session."""
        return self._browser_session

    def _get_browser_data_dir(self, user_id: str) -> str:
        """Get browser data directory for user."""
        base_path = Path.home() / ".ami" / "users" / user_id / "browser_data"
        base_path.mkdir(parents=True, exist_ok=True)
        return str(base_path)

    async def close_browser(self) -> None:
        """Close the browser session."""
        if self._browser_session:
            try:
                await self._browser_session.close()
                logger.info("Browser session closed")
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")
            finally:
                self._browser_session = None
