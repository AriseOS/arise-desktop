"""Local file system storage management"""

import json
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


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

    def save_recording(self, user_id: str, session_id: str, recording_data: dict):
        """Save recording data to local file

        Args:
            recording_data: Output from RecordingSession.to_file_format()
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id
        recording_path.mkdir(parents=True, exist_ok=True)

        file_path = recording_path / "operations.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(recording_data, f, indent=2, ensure_ascii=False)

    def get_recording(self, user_id: str, session_id: str) -> dict:
        """Read recording data from local file"""
        file_path = self._user_path(user_id) / "recordings" / session_id / "operations.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # === MetaFlow Management ===

    def save_metaflow(
        self,
        user_id: str,
        metaflow_id: str,
        metaflow_yaml: str,
        task_description: Optional[str] = None
    ):
        """Save MetaFlow YAML to local file"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        metaflow_path.mkdir(parents=True, exist_ok=True)

        # Save MetaFlow YAML
        yaml_file = metaflow_path / "metaflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)

        # Save task description if provided
        if task_description:
            desc_file = metaflow_path / "task_description.txt"
            with open(desc_file, 'w', encoding='utf-8') as f:
                f.write(task_description)

    def get_metaflow(self, user_id: str, metaflow_id: str) -> str:
        """Read MetaFlow YAML from local file"""
        file_path = self._user_path(user_id) / "metaflows" / metaflow_id / "metaflow.yaml"
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def list_metaflows(self, user_id: str) -> List[str]:
        """List all MetaFlow IDs for user"""
        metaflows_path = self._user_path(user_id) / "metaflows"
        if not metaflows_path.exists():
            return []

        return [d.name for d in metaflows_path.iterdir() if d.is_dir()]

    # === Workflow Management ===

    def save_workflow(self, user_id: str, workflow_name: str, yaml_content: str):
        """Save workflow YAML to local file"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        workflow_path.mkdir(parents=True, exist_ok=True)

        file_path = workflow_path / "workflow.yaml"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

    def get_workflow(self, user_id: str, workflow_name: str) -> str:
        """Read workflow YAML from local file"""
        file_path = self._user_path(user_id) / "workflows" / workflow_name / "workflow.yaml"
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def workflow_exists(self, user_id: str, workflow_name: str) -> bool:
        """Check if workflow exists locally"""
        file_path = self._user_path(user_id) / "workflows" / workflow_name / "workflow.yaml"
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
                            name = data.get('name', workflow_id)
                            description = data.get('description', '')
                except Exception:
                    # Use defaults if parsing fails
                    pass

            local_workflows[workflow_id] = {
                'agent_id': workflow_id,
                'name': name,
                'description': description,
                'created_at': created_at,
                'is_downloaded': True,
                'source': 'local'
            }

        return local_workflows

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
