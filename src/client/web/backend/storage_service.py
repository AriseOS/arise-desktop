"""
Storage Service - File system management for workflow learning and execution data
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path so we can import from src
backend_dir = Path(__file__).parent
project_root = str(backend_dir.parent.parent.parent.parent)
sys.path.insert(0, project_root)


class StorageService:
    """Manages file system storage for learning sessions and workflows"""

    def __init__(self, base_storage_path: str = None):
        """Initialize storage service

        Args:
            base_storage_path: Base directory for storage, defaults to ~/agentcrafter/storage/users
        """
        if base_storage_path:
            self.base_path = Path(base_storage_path).expanduser()
        else:
            self.base_path = Path.home() / "agentcrafter" / "storage" / "users"

        self.base_path.mkdir(parents=True, exist_ok=True)

    # ===== Path Management =====

    def _user_path(self, user_id: int) -> Path:
        """Get user root directory"""
        return self.base_path / str(user_id)

    def _learning_path(self, user_id: int, session_id: str = None) -> Path:
        """Get learning directory or specific session directory"""
        learning_dir = self._user_path(user_id) / "learning"
        if session_id:
            return learning_dir / session_id
        return learning_dir

    def _workflow_path(self, user_id: int, workflow_name: str = None) -> Path:
        """Get workflows directory or specific workflow directory"""
        workflows_dir = self._user_path(user_id) / "workflows"
        if workflow_name:
            return workflows_dir / workflow_name
        return workflows_dir

    def _execution_path(self, user_id: int, workflow_name: str) -> Path:
        """Get executions directory for a workflow"""
        return self._workflow_path(user_id, workflow_name) / "executions"

    # ===== File I/O Helpers =====

    def _read_json(self, path: Path) -> Optional[dict]:
        """Read JSON file"""
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return None

    def _write_json(self, path: Path, data: dict):
        """Write JSON file atomically"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_yaml(self, path: Path) -> Optional[str]:
        """Read YAML file as string"""
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return None

    def _write_yaml(self, path: Path, yaml_content: str):
        """Write YAML file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

    # ===== Learning Session Operations =====

    def save_learning_operations(
        self, 
        user_id: int, 
        session_id: str, 
        operations: List[Dict],
        title: str,
        description: str,
        started_at: str,
        stopped_at: str
    ) -> bool:
        """Save recording operations and create session metadata

        Args:
            user_id: User ID
            session_id: Recording session ID
            operations: List of recorded operations
            title: Recording title
            description: Recording description
            started_at: Session start timestamp (ISO format)
            stopped_at: Session stop timestamp (ISO format)

        Returns:
            True on success
        """
        session_dir = self._learning_path(user_id, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Save operations
        operations_path = session_dir / "operations.json"
        self._write_json(operations_path, {"operations": operations})

        # Create metadata
        metadata = {
            "session_id": session_id,
            "title": title,
            "description": description,
            "status": "stopped",
            "operations_count": len(operations),
            "workflow_generated": False,
            "generated_workflow_name": None,
            "created_at": started_at,
            "stopped_at": stopped_at
        }

        metadata_path = session_dir / "metadata.json"
        self._write_json(metadata_path, metadata)

        return True

    def save_learning_intents(self, user_id: int, session_id: str, intents: List[Dict]) -> bool:
        """Save extracted intents"""
        session_dir = self._learning_path(user_id, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        intents_path = session_dir / "intents.json"
        self._write_json(intents_path, {"intents": intents})

        # Update metadata
        self._update_session_metadata(user_id, session_id, {
            "status": "intent_extracted",
            "intents_count": len(intents)
        })

        return True

    def save_learning_metaflow(self, user_id: int, session_id: str, metaflow_yaml: str) -> bool:
        """Save generated MetaFlow YAML"""
        session_dir = self._learning_path(user_id, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        metaflow_path = session_dir / "metaflow.yaml"
        self._write_yaml(metaflow_path, metaflow_yaml)

        # Update metadata
        self._update_session_metadata(user_id, session_id, {
            "status": "metaflow_generated"
        })

        return True

    def get_learning_session(self, user_id: int, session_id: str) -> Optional[Dict]:
        """Get learning session metadata"""
        session_dir = self._learning_path(user_id, session_id)
        if not session_dir.exists():
            return None

        metadata_path = session_dir / "metadata.json"
        return self._read_json(metadata_path)

    def get_learning_operations(self, user_id: int, session_id: str) -> Optional[List[Dict]]:
        """Get recorded operations"""
        session_dir = self._learning_path(user_id, session_id)
        operations_path = session_dir / "operations.json"

        data = self._read_json(operations_path)
        if data and "operations" in data:
            return data["operations"]
        return None

    def get_learning_intents(self, user_id: int, session_id: str) -> Optional[List[Dict]]:
        """Get extracted intents"""
        session_dir = self._learning_path(user_id, session_id)
        intents_path = session_dir / "intents.json"

        data = self._read_json(intents_path)
        if data and "intents" in data:
            return data["intents"]
        return None

    def get_learning_metaflow(self, user_id: int, session_id: str) -> Optional[str]:
        """Get MetaFlow YAML"""
        session_dir = self._learning_path(user_id, session_id)
        metaflow_path = session_dir / "metaflow.yaml"
        return self._read_yaml(metaflow_path)

    def list_learning_sessions(self, user_id: int) -> List[Dict]:
        """List all learning sessions for user"""
        learning_dir = self._learning_path(user_id)
        if not learning_dir.exists():
            return []

        sessions = []
        for session_dir in learning_dir.iterdir():
            if session_dir.is_dir():
                metadata = self._read_json(session_dir / "metadata.json")
                if metadata:
                    sessions.append(metadata)

        # Sort by created_at descending
        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions

    def delete_learning_session(self, user_id: int, session_id: str) -> bool:
        """Delete a learning session"""
        session_dir = self._learning_path(user_id, session_id)
        if not session_dir.exists():
            return False

        try:
            shutil.rmtree(session_dir)
            return True
        except Exception as e:
            print(f"Error deleting session {session_id}: {e}")
            return False

    def _update_session_metadata(self, user_id: int, session_id: str, updates: Dict):
        """Update session metadata"""
        session_dir = self._learning_path(user_id, session_id)
        metadata_path = session_dir / "metadata.json"

        metadata = self._read_json(metadata_path) or {}
        metadata.update(updates)
        self._write_json(metadata_path, metadata)

    # ===== Workflow Operations =====

    def save_workflow(
        self, 
        user_id: int, 
        workflow_name: str, 
        workflow_yaml: str, 
        source_session_id: str,
        description: str
    ) -> Dict:
        """Save a workflow

        Returns:
            Dict with keys: success, overwritten, workflow_name
        """
        workflow_dir = self._workflow_path(user_id, workflow_name)
        overwritten = workflow_dir.exists()

        workflow_dir.mkdir(parents=True, exist_ok=True)

        # Save workflow YAML
        workflow_path = workflow_dir / "workflow.yaml"
        self._write_yaml(workflow_path, workflow_yaml)

        # Create or update metadata
        metadata_path = workflow_dir / "metadata.json"
        now = datetime.utcnow().isoformat()

        if overwritten:
            metadata = self._read_json(metadata_path) or {}
            metadata.update({
                "updated_at": now
            })
        else:
            metadata = {
                "workflow_name": workflow_name,
                "description": description,
                "source_session_id": source_session_id,
                "execution_count": 0,
                "last_executed_at": None,
                "created_at": now,
                "updated_at": now
            }

        self._write_json(metadata_path, metadata)

        # Update source session metadata
        self._update_session_metadata(user_id, source_session_id, {
            "status": "workflow_generated",
            "workflow_generated": True,
            "generated_workflow_name": workflow_name
        })

        return {
            "success": True,
            "overwritten": overwritten,
            "workflow_name": workflow_name
        }

    def get_workflow(self, user_id: int, workflow_name: str) -> Optional[Dict]:
        """Get workflow data including YAML and metadata"""
        workflow_dir = self._workflow_path(user_id, workflow_name)
        if not workflow_dir.exists():
            return None

        metadata = self._read_json(workflow_dir / "metadata.json")
        workflow_yaml = self._read_yaml(workflow_dir / "workflow.yaml")

        if not metadata or not workflow_yaml:
            return None

        return {
            **metadata,
            "workflow_yaml": workflow_yaml
        }

    def list_workflows(self, user_id: int) -> List[Dict]:
        """List all workflows for user"""
        workflows_dir = self._workflow_path(user_id)
        if not workflows_dir.exists():
            return []

        workflows = []
        for workflow_dir in workflows_dir.iterdir():
            if workflow_dir.is_dir():
                metadata = self._read_json(workflow_dir / "metadata.json")
                if metadata:
                    workflows.append(metadata)

        # Sort by updated_at descending
        workflows.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return workflows

    def delete_workflow(self, user_id: int, workflow_name: str) -> bool:
        """Delete a workflow and all its executions"""
        workflow_dir = self._workflow_path(user_id, workflow_name)
        if not workflow_dir.exists():
            return False

        try:
            shutil.rmtree(workflow_dir)
            return True
        except Exception as e:
            print(f"Error deleting workflow {workflow_name}: {e}")
            return False

    def update_workflow_execution_stats(self, user_id: int, workflow_name: str) -> bool:
        """Update workflow execution statistics"""
        workflow_dir = self._workflow_path(user_id, workflow_name)
        metadata_path = workflow_dir / "metadata.json"

        metadata = self._read_json(metadata_path)
        if not metadata:
            return False

        metadata["execution_count"] = metadata.get("execution_count", 0) + 1
        metadata["last_executed_at"] = datetime.utcnow().isoformat()

        self._write_json(metadata_path, metadata)
        return True

    # ===== Execution Operations =====

    def save_execution(
        self, 
        user_id: int, 
        workflow_name: str, 
        task_id: str, 
        execution_data: Dict
    ) -> bool:
        """Save execution record"""
        exec_dir = self._execution_path(user_id, workflow_name)
        exec_dir.mkdir(parents=True, exist_ok=True)

        exec_path = exec_dir / f"{task_id}.json"
        self._write_json(exec_path, execution_data)
        return True

    def get_execution(
        self, 
        user_id: int, 
        workflow_name: str, 
        task_id: str
    ) -> Optional[Dict]:
        """Get execution record"""
        exec_dir = self._execution_path(user_id, workflow_name)
        exec_path = exec_dir / f"{task_id}.json"
        return self._read_json(exec_path)

    def list_executions(
        self, 
        user_id: int, 
        workflow_name: str, 
        limit: int = 50
    ) -> List[Dict]:
        """List execution records for a workflow"""
        exec_dir = self._execution_path(user_id, workflow_name)
        if not exec_dir.exists():
            return []

        executions = []
        for exec_file in exec_dir.glob("*.json"):
            execution = self._read_json(exec_file)
            if execution:
                executions.append(execution)

        # Sort by started_at descending
        executions.sort(key=lambda x: x.get("started_at", ""), reverse=True)

        return executions[:limit]

    def cleanup_old_executions(
        self, 
        user_id: int, 
        workflow_name: str, 
        keep_count: int = 50
    ) -> int:
        """Delete old execution records, keeping only the most recent ones

        Returns:
            Number of executions deleted
        """
        exec_dir = self._execution_path(user_id, workflow_name)
        if not exec_dir.exists():
            return 0

        # Get all execution files with their timestamps
        exec_files = []
        for exec_file in exec_dir.glob("*.json"):
            execution = self._read_json(exec_file)
            if execution:
                exec_files.append((
                    exec_file,
                    execution.get("started_at", "")
                ))

        # Sort by timestamp descending
        exec_files.sort(key=lambda x: x[1], reverse=True)

        # Delete files beyond keep_count
        deleted_count = 0
        for exec_file, _ in exec_files[keep_count:]:
            try:
                exec_file.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {exec_file}: {e}")

        return deleted_count


# Global instance
storage_service = StorageService()
