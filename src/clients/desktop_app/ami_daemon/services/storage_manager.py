"""Local file system storage management"""

import json
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.common.timestamp_utils import get_current_timestamp


class StorageManager:
    """Manage local file storage for recordings, workflows, and execution results"""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage manager

        Args:
            base_path: Base storage path (e.g., ~/.ami)
        """
        self.base_path = Path(base_path) if base_path else Path.home() / ".ami"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _user_path(self, user_id: str) -> Path:
        """Get user directory path"""
        path = self.base_path / "users" / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    # === Recording Management ===

    def save_recording(self, user_id: str, session_id: str, recording_data: dict, update_timestamp: bool = True):
        """Save recording data to local file

        Args:
            recording_data: Output from RecordingSession.to_file_format()
            update_timestamp: Whether to update the updated_at timestamp (default True)
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id
        recording_path.mkdir(parents=True, exist_ok=True)

        # Update timestamp on save
        if update_timestamp:
            recording_data["updated_at"] = get_current_timestamp()

        file_path = recording_path / "operations.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(recording_data, f, indent=2, ensure_ascii=False)

    def get_recording(self, user_id: str, session_id: str) -> dict:
        """Read recording data from local file

        Also loads DOM snapshots if available (for script pre-generation).

        Returns:
            Recording dict with optional 'dom_snapshots' field containing
            URL -> DOM dict mapping
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id
        file_path = recording_path / "operations.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Load DOM snapshots if available
        dom_dir = recording_path / "dom_snapshots"
        if dom_dir.exists():
            dom_snapshots = {}
            for dom_file in dom_dir.glob("*.json"):
                try:
                    with open(dom_file, 'r', encoding='utf-8') as f:
                        dom_data = json.load(f)
                        url = dom_data.get("url")
                        dom_dict = dom_data.get("dom")
                        if url and dom_dict:
                            dom_snapshots[url] = dom_dict
                except Exception:
                    # Skip corrupted DOM snapshot files
                    continue

            if dom_snapshots:
                data["dom_snapshots"] = dom_snapshots

        return data

    def update_recording_metadata(self, user_id: str, session_id: str, task_description: str = None, user_query: str = None, name: str = None, workflow_id: str = None):
        """Update recording metadata with task_description, user_query, name and workflow_id

        Args:
            user_id: User ID
            session_id: Session ID
            task_description: Task description (what user did)
            user_query: User query (what user wants to achieve)
            name: Short name/title (optional)
            workflow_id: Associated workflow ID (optional, can be None to clear)
        """
        # Read existing recording
        recording_data = self.get_recording(user_id, session_id)

        # Update task_metadata
        if "task_metadata" not in recording_data:
            recording_data["task_metadata"] = {}

        if task_description is not None:
            recording_data["task_metadata"]["task_description"] = task_description
        if user_query is not None:
            recording_data["task_metadata"]["user_query"] = user_query
        if name is not None:
            recording_data["task_metadata"]["name"] = name

        # Update workflow_id at root level (can be set to None to clear)
        if workflow_id is not None:
            recording_data["workflow_id"] = workflow_id
        elif "workflow_id" in recording_data and workflow_id is None:
            # Explicitly clear workflow_id when passed as None
            pass  # Keep existing behavior, only clear when explicitly requested via clear_workflow_id

        # Save back (exclude dom_snapshots - they are stored separately)
        save_data = {k: v for k, v in recording_data.items() if k != 'dom_snapshots'}
        self.save_recording(user_id, session_id, save_data)

    def clear_recording_workflow_id(self, user_id: str, session_id: str):
        """Clear the workflow_id from a recording (when workflow is deleted)"""
        recording_data = self.get_recording(user_id, session_id)
        if "workflow_id" in recording_data:
            del recording_data["workflow_id"]
            save_data = {k: v for k, v in recording_data.items() if k != 'dom_snapshots'}
            self.save_recording(user_id, session_id, save_data)

    def update_recording_from_cloud(self, user_id: str, session_id: str, cloud_data: dict):
        """Update local recording with cloud data (for sync)

        Only updates metadata fields, not operations.
        Preserves local operations and DOM snapshots.

        Args:
            user_id: User ID
            session_id: Session ID
            cloud_data: Recording data from cloud with updated_at, workflow_id, task_description, etc.
        """
        recording_data = self.get_recording(user_id, session_id)

        # Update metadata fields from cloud
        if cloud_data.get("workflow_id"):
            recording_data["workflow_id"] = cloud_data["workflow_id"]
        elif "workflow_id" in cloud_data and cloud_data["workflow_id"] is None:
            # Explicitly cleared on cloud
            recording_data.pop("workflow_id", None)

        if cloud_data.get("task_description"):
            if "task_metadata" not in recording_data:
                recording_data["task_metadata"] = {}
            recording_data["task_metadata"]["task_description"] = cloud_data["task_description"]

        if cloud_data.get("user_query"):
            if "task_metadata" not in recording_data:
                recording_data["task_metadata"] = {}
            recording_data["task_metadata"]["user_query"] = cloud_data["user_query"]

        # Use cloud's updated_at to keep them in sync
        if cloud_data.get("updated_at"):
            recording_data["updated_at"] = cloud_data["updated_at"]

        # Save without auto-updating timestamp (use cloud's timestamp)
        save_data = {k: v for k, v in recording_data.items() if k != 'dom_snapshots'}
        self.save_recording(user_id, session_id, save_data, update_timestamp=False)

    def list_recordings(self, user_id: str) -> List[Dict[str, Any]]:
        """List all recordings for user with metadata

        Returns:
            List of recording info dicts with session_id, task_metadata, etc.
        """
        recordings_path = self._user_path(user_id) / "recordings"
        if not recordings_path.exists():
            return []

        recordings = []
        for session_dir in recordings_path.iterdir():
            if not session_dir.is_dir():
                continue

            operations_file = session_dir / "operations.json"
            if not operations_file.exists():
                continue

            try:
                with open(operations_file, 'r', encoding='utf-8') as f:
                    recording_data = json.load(f)

                # Extract metadata
                task_metadata = recording_data.get("task_metadata", {})
                operations = recording_data.get("operations", [])

                # Get file creation time
                created_at = datetime.fromtimestamp(operations_file.stat().st_ctime).isoformat()

                # Count actions (click, input, etc.)
                action_count = sum(1 for op in operations if op.get("type") in ["click", "input", "type", "navigate"])

                # Count DOM snapshots
                dom_count = 0
                dom_dir = session_dir / "dom_snapshots"
                if dom_dir.exists():
                    dom_count = sum(1 for f in dom_dir.glob("*.json") if f.name != "url_index.json")

                recordings.append({
                    "session_id": session_dir.name,
                    "task_metadata": task_metadata,
                    "created_at": created_at,
                    "action_count": action_count,
                    "dom_count": dom_count
                })
            except Exception as e:
                # Skip corrupted recordings
                continue

        # Sort by created_at descending (newest first)
        recordings.sort(key=lambda x: x["created_at"], reverse=True)
        return recordings

    def delete_recording(self, user_id: str, session_id: str) -> bool:
        """Delete a recording

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            True if deleted successfully, False if not found
        """
        import shutil

        recording_path = self._user_path(user_id) / "recordings" / session_id
        if not recording_path.exists():
            return False

        shutil.rmtree(recording_path)
        return True

    def get_recording_detail(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed recording information including parsed operations

        Returns:
            Recording detail dict with operations timeline and task_metadata
        """
        try:
            recording_data = self.get_recording(user_id, session_id)

            metadata = recording_data.get("metadata", {})
            operations = recording_data.get("operations", [])

            # Count actions
            action_count = 0
            for op in operations:
                op_type = op.get("type", "unknown")
                if op_type in ["navigate", "click", "input", "type"]:
                    action_count += 1

            # Get file creation time
            operations_file = self._user_path(user_id) / "recordings" / session_id / "operations.json"
            created_at = datetime.fromtimestamp(operations_file.stat().st_ctime).isoformat()

            # Extract task_metadata from recording data
            task_metadata = recording_data.get("task_metadata", {})

            return {
                "session_id": session_id,
                "created_at": created_at,
                "updated_at": recording_data.get("updated_at"),
                "action_count": action_count,
                "task_metadata": task_metadata,
                "workflow_id": recording_data.get("workflow_id"),
                "operations": operations,
                "dom_snapshots": recording_data.get("dom_snapshots", {})
            }
        except Exception as e:
            return None

    # === Workflow Management ===

    def save_workflow(self, user_id: str, workflow_name: str, yaml_content: str):
        """Save workflow YAML to local file"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        workflow_path.mkdir(parents=True, exist_ok=True)

        file_path = workflow_path / "workflow.yaml"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

    def get_workflow(self, user_id: str, workflow_id: str) -> str:
        """Read workflow YAML from local file"""
        file_path = self._user_path(user_id) / "workflows" / workflow_id / "workflow.yaml"
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def get_workflow_metadata(self, user_id: str, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Read workflow metadata.json from local file

        Returns:
            Dict with metadata fields or None if not found:
            {
                'workflow_id': 'workflow_xxx',
                'workflow_name': 'human-readable-name',
                'source_recording_id': 'session_xxx',
                'created_at': '2025-01-05T18:02:30Z',
                'updated_at': '2025-01-05T18:07:50Z',
                'resources': {...}
            }
        """
        file_path = self._user_path(user_id) / "workflows" / workflow_id / "metadata.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def workflow_exists(self, user_id: str, workflow_id: str) -> bool:
        """Check if workflow exists locally"""
        file_path = self._user_path(user_id) / "workflows" / workflow_id / "workflow.yaml"
        return file_path.exists()

    def list_workflows(self, user_id: str) -> List[str]:
        """List all workflow names for user"""
        workflows_path = self._user_path(user_id) / "workflows"
        if not workflows_path.exists():
            return []

        return [d.name for d in workflows_path.iterdir() if d.is_dir()]

    def get_local_workflows_info(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about local workflows

        Returns:
            Dict mapping workflow_id to workflow info:
            {
                'workflow_xxx': {
                    'agent_id': 'workflow_xxx',
                    'name': 'Workflow Name',
                    'description': 'Description',
                    'created_at': '2025-01-09T10:30:00',
                    'is_downloaded': True,
                    'source': 'local'
                }
            }
        """
        workflows_path = self._user_path(user_id) / "workflows"
        if not workflows_path.exists():
            return {}

        local_workflows = {}

        for workflow_dir in workflows_path.iterdir():
            if not workflow_dir.is_dir():
                continue

            workflow_id = workflow_dir.name
            workflow_file = workflow_dir / "workflow.yaml"

            # Default values
            name = workflow_id
            description = ""
            created_at = None

            # Get file creation time
            if workflow_file.exists():
                try:
                    created_at = datetime.fromtimestamp(
                        workflow_file.stat().st_ctime
                    ).isoformat()
                except Exception:
                    pass

                # Parse YAML to get name and description
                try:
                    with open(workflow_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            # Get name and description from metadata section
                            metadata = data.get('metadata', {})
                            name = metadata.get('name', workflow_id)
                            description = metadata.get('description', '')
                except Exception:
                    # Use defaults if parsing fails
                    pass

            # Get last execution time
            last_run = None
            last_exec = self.get_workflow_last_execution(user_id, workflow_id)
            if last_exec:
                last_run = last_exec.get('timestamp')

            local_workflows[workflow_id] = {
                'agent_id': workflow_id,
                'name': name,
                'description': description,
                'created_at': created_at,
                'last_run': last_run,
                'is_downloaded': True,
                'source': 'local'
            }

        return local_workflows

    def delete_workflow(self, user_id: str, workflow_name: str) -> bool:
        """Delete a workflow and all its execution history

        Args:
            user_id: User ID
            workflow_name: Workflow name/ID

        Returns:
            True if deleted successfully, False if not found
        """
        import shutil

        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        if not workflow_path.exists():
            return False

        shutil.rmtree(workflow_path)
        return True

    def get_workflow_last_execution(self, user_id: str, workflow_name: str) -> Optional[Dict[str, Any]]:
        """Get the most recent execution result for a workflow

        Returns:
            Dict with execution info (timestamp, status, etc.) or None if no executions
        """
        exec_path = self._user_path(user_id) / "workflows" / workflow_name / "executions"
        if not exec_path.exists():
            return None

        # Get most recent execution directory
        exec_dirs = sorted(exec_path.iterdir(), reverse=True)
        if not exec_dirs:
            return None

        for exec_dir in exec_dirs:
            if exec_dir.is_dir():
                result_file = exec_dir / "result.json"
                if result_file.exists():
                    try:
                        with open(result_file, 'r', encoding='utf-8') as f:
                            result = json.load(f)
                            return {
                                "execution_id": exec_dir.name,
                                "timestamp": result.get("completed_at") or result.get("timestamp", ""),
                                "status": result.get("status", "unknown"),
                                "error": result.get("error")
                            }
                    except Exception:
                        continue

        return None

    # === Execution Results ===

    def save_execution_result(
        self,
        user_id: str,
        workflow_name: str,
        execution_id: str,
        result: dict
    ):
        """Save execution result"""
        exec_path = (
            self._user_path(user_id) /
            "workflows" / workflow_name /
            "executions" / execution_id
        )
        exec_path.mkdir(parents=True, exist_ok=True)

        file_path = exec_path / "result.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    def get_execution_results(
        self,
        user_id: str,
        workflow_name: str,
        limit: int = 10
    ) -> List[dict]:
        """Get execution history for workflow"""
        exec_path = self._user_path(user_id) / "workflows" / workflow_name / "executions"
        if not exec_path.exists():
            return []

        results = []
        for exec_dir in sorted(exec_path.iterdir(), reverse=True)[:limit]:
            if exec_dir.is_dir():
                result_file = exec_dir / "result.json"
                if result_file.exists():
                    with open(result_file, 'r', encoding='utf-8') as f:
                        results.append(json.load(f))

        return results
