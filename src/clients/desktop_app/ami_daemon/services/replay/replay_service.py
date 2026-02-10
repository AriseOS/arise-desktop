"""
Replay Service - Main orchestrator for recording replay.

This service manages the complete replay lifecycle:
1. Load recording data from storage
2. Initialize browser session
3. Execute operations step-by-step
4. Generate replay report
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.replay.replay_executor import ReplayExecutor

logger = logging.getLogger(__name__)


class ReplayService:
    """Service for replaying recorded user sessions."""

    def __init__(self, storage_manager: StorageManager):
        """Initialize replay service.

        Args:
            storage_manager: Storage manager for loading recordings.
        """
        self.storage = storage_manager
        self.current_replay_id: Optional[str] = None
        self.replay_start_time: Optional[datetime] = None

    async def replay_recording(
        self,
        session_id: str,
        user_id: str,
        browser_session: Any,  # HybridBrowserSession instance
        wait_between_operations: float = 0.5,
        stop_on_error: bool = False,
        start_from_index: int = 0,
        end_at_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """Replay a recorded session.

        Args:
            session_id: Recording session ID to replay.
            user_id: User ID who owns the recording.
            browser_session: Active HybridBrowserSession instance.
            wait_between_operations: Seconds to wait between operations (default 0.5).
            stop_on_error: Stop replay if an operation fails (default False).
            start_from_index: Start replay from this operation index (default 0).
            end_at_index: Stop replay at this operation index (default None = end).

        Returns:
            Replay report dict with execution results.
        """
        self.current_replay_id = f"replay_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.replay_start_time = datetime.now()

        logger.info(f"Starting replay: {self.current_replay_id}")
        logger.info(f"Recording session: {session_id}")
        logger.info(f"User: {user_id}")

        try:
            # 1. Load recording
            recording = self._load_recording(session_id, user_id)
            operations = recording.get("operations", [])

            if not operations:
                raise ValueError("Recording contains no operations")

            logger.info(f"Loaded {len(operations)} operations")

            # Apply index range
            operations_to_replay = operations[start_from_index:end_at_index]
            logger.info(f"Replaying operations {start_from_index} to {end_at_index or len(operations)}")

            # 2. Get Playwright page from browser session
            page = await self._get_page_from_session(browser_session)

            # 3. Initialize executor
            executor = ReplayExecutor(page)

            # 4. Execute operations
            for i, operation in enumerate(operations_to_replay):
                actual_index = start_from_index + i

                result = await executor.execute_operation(
                    operation,
                    index=actual_index,
                    wait_after=wait_between_operations
                )

                # Stop on error if requested
                if stop_on_error and result["status"] == "failed":
                    logger.warning(f"Stopping replay due to error at operation {actual_index}")
                    break

            # 5. Generate report
            execution_summary = executor.get_execution_summary()
            replay_report = self._generate_replay_report(
                recording,
                execution_summary,
                start_from_index,
                end_at_index
            )

            logger.info(f"Replay completed: {replay_report['execution_summary']['success_rate']*100:.1f}% success")
            return replay_report

        except Exception as e:
            logger.error(f"Replay failed: {e}", exc_info=True)
            return {
                "replay_id": self.current_replay_id,
                "status": "failed",
                "error": str(e),
                "started_at": self.replay_start_time.isoformat() if self.replay_start_time else None
            }

    async def replay_single_operation(
        self,
        session_id: str,
        user_id: str,
        operation_index: int,
        browser_session: Any
    ) -> Dict[str, Any]:
        """Replay a single operation from a recording.

        Useful for debugging or testing specific operations.

        Args:
            session_id: Recording session ID.
            user_id: User ID.
            operation_index: Index of operation to replay.
            browser_session: Active browser session.

        Returns:
            Operation execution result.
        """
        logger.info(f"Replaying single operation at index {operation_index}")

        recording = self._load_recording(session_id, user_id)
        operations = recording.get("operations", [])

        if operation_index < 0 or operation_index >= len(operations):
            raise ValueError(f"Invalid operation index: {operation_index}")

        operation = operations[operation_index]
        page = await self._get_page_from_session(browser_session)
        executor = ReplayExecutor(page)

        result = await executor.execute_operation(operation, operation_index)
        return result

    def _load_recording(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Load recording data from storage.

        Args:
            session_id: Recording session ID.
            user_id: User ID.

        Returns:
            Recording data dict.
        """
        try:
            recording = self.storage.get_recording(user_id, session_id)
            logger.info(f"Loaded recording: {session_id}")
            logger.info(f"  Operations: {recording.get('operations_count', 0)}")
            logger.info(f"  Created: {recording.get('timestamp', 'unknown')}")
            return recording
        except Exception as e:
            logger.error(f"Failed to load recording {session_id}: {e}")
            raise

    async def _get_page_from_session(self, browser_session: Any) -> Any:
        """Extract Playwright page from browser session.

        Args:
            browser_session: HybridBrowserSession instance.

        Returns:
            Playwright Page instance.
        """
        # HybridBrowserSession has an async get_page() method
        if hasattr(browser_session, 'get_page'):
            return await browser_session.get_page()
        else:
            raise AttributeError("Browser session does not have get_page() method")

    def _generate_replay_report(
        self,
        recording: Dict[str, Any],
        execution_summary: Dict[str, Any],
        start_index: int,
        end_index: Optional[int]
    ) -> Dict[str, Any]:
        """Generate comprehensive replay report.

        Args:
            recording: Original recording data.
            execution_summary: Execution results from ReplayExecutor.
            start_index: Starting operation index.
            end_index: Ending operation index.

        Returns:
            Replay report dict.
        """
        replay_end_time = datetime.now()
        duration = (replay_end_time - self.replay_start_time).total_seconds() if self.replay_start_time else 0

        return {
            "replay_id": self.current_replay_id,
            "status": "completed",
            "recording_session_id": recording.get("session_id"),
            "recording_created_at": recording.get("timestamp"),
            "task_metadata": recording.get("task_metadata", {}),
            "replay_range": {
                "start_index": start_index,
                "end_index": end_index or recording.get("operations_count", 0)
            },
            "execution_summary": {
                "total_operations": execution_summary["total_operations"],
                "successful": execution_summary["successful"],
                "failed": execution_summary["failed"],
                "skipped": execution_summary["skipped"],
                "success_rate": execution_summary["success_rate"]
            },
            "timing": {
                "started_at": self.replay_start_time.isoformat() if self.replay_start_time else None,
                "ended_at": replay_end_time.isoformat(),
                "duration_seconds": duration
            },
            "operation_results": execution_summary["execution_log"]
        }

    def get_recording_preview(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Get preview of recording without replaying.

        Useful for UI to show recording details before replay.

        Args:
            session_id: Recording session ID.
            user_id: User ID.

        Returns:
            Recording preview dict.
        """
        recording = self._load_recording(session_id, user_id)

        operations = recording.get("operations", [])
        operation_summary = {}
        for op in operations:
            op_type = op.get("type", "unknown")
            operation_summary[op_type] = operation_summary.get(op_type, 0) + 1

        return {
            "session_id": recording.get("session_id"),
            "created_at": recording.get("timestamp"),
            "ended_at": recording.get("ended_at"),
            "operations_count": recording.get("operations_count", 0),
            "operation_summary": operation_summary,
            "task_metadata": recording.get("task_metadata", {}),
            "operations": [
                {
                    "index": i,
                    "type": op.get("type"),
                    "url": op.get("url"),
                    "timestamp": op.get("timestamp")
                }
                for i, op in enumerate(operations)
            ]
        }
