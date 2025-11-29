"""
Storage Service - 服务器本地文件系统管理 (Cloud Backend)

存储路径：
- 开发环境：~/ami-server
- 生产环境：/var/lib/ami-server/（或通过环境变量 STORAGE_PATH 配置）

目录结构：
~/ami-server/
├── users/{user_id}/
│   ├── recordings/              # 录制数据
│   │   └── {recording_id}/
│   │       ├── operations.json
│   │       └── metadata.json    # 包含 metaflow_id 关联
│   ├── metaflows/               # MetaFlows
│   │   └── {metaflow_id}/
│   │       ├── metaflow.yaml
│   │       └── metadata.json    # 包含关联信息
│   ├── workflows/               # Workflows
│   │   └── {workflow_id}/
│   │       ├── workflow.yaml
│   │       └── metadata.json    # 包含关联信息
│   └── intent_builder/          # Agent 工作目录
│       └── {session_id}/
└── logs/

关联关系 (1:1:1):
Recording → MetaFlow → Workflow
"""

from pathlib import Path
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class StorageService:
    """服务器本地文件系统管理器"""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize Cloud Backend storage service

        Args:
            base_path: Base path (optional)
                Development: ~/ami-server (default)
                Production: /var/lib/ami-server/ (via STORAGE_PATH env var)

        Note:
            Cloud Backend uses ~/ami-server (server-side data)
            App Backend uses ~/.ami (local client data)
        """
        if base_path:
            self.base_path = Path(base_path).expanduser()
        else:
            # Default path for Cloud Backend (server-side storage)
            default_path = os.getenv("STORAGE_PATH", "~/ami-server")
            self.base_path = Path(default_path).expanduser()

        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Cloud Backend Storage initialized: {self.base_path}")
    
    def _user_path(self, user_id: str) -> Path:
        """获取用户目录"""
        path = self.base_path / "users" / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user_intent_graph_path(self, user_id: str) -> str:
        """Get path to user's Intent Memory Graph file"""
        return str(self._user_path(user_id) / "intent_graph.json")

    def get_user_intent_builder_path(self, user_id: str, session_id: str) -> Path:
        """Get working directory for Intent Builder Agent session"""
        path = self._user_path(user_id) / "intent_builder" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_session_info(self, user_id: str, session_id: str, timeout_minutes: int = 30) -> Optional[Dict]:
        """
        Get session information including age and expiry time

        Args:
            user_id: User ID
            session_id: Session ID
            timeout_minutes: Session timeout in minutes

        Returns:
            Dict with session info, or None if session doesn't exist
        """
        import time

        session_path = self._user_path(user_id) / "intent_builder" / session_id
        if not session_path.exists():
            return None

        try:
            last_modified = session_path.stat().st_mtime
            current_time = time.time()
            age_seconds = current_time - last_modified
            age_minutes = age_seconds / 60
            timeout_seconds = timeout_minutes * 60

            # Calculate expiry
            minutes_until_expiry = timeout_minutes - age_minutes
            is_expired = age_seconds > timeout_seconds

            return {
                "session_id": session_id,
                "user_id": user_id,
                "working_dir": str(session_path),
                "last_active_at": datetime.fromtimestamp(last_modified, timezone.utc).isoformat(),
                "age_minutes": round(age_minutes, 2),
                "minutes_until_expiry": round(max(0, minutes_until_expiry), 2),
                "status": "expired" if is_expired else "active"
            }
        except Exception as e:
            logger.error(f"Failed to get session info: {e}")
            return None

    def cleanup_expired_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Clean up expired Intent Builder sessions across all users

        Args:
            timeout_minutes: Session timeout in minutes (default: 30)

        Returns:
            Number of sessions cleaned up
        """
        import shutil
        import time

        cleaned_count = 0
        current_time = time.time()
        timeout_seconds = timeout_minutes * 60

        users_dir = self.base_path / "users"
        if not users_dir.exists():
            return 0

        # Scan all users
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue

            intent_builder_dir = user_dir / "intent_builder"
            if not intent_builder_dir.exists():
                continue

            # Scan all sessions for this user
            for session_dir in intent_builder_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                try:
                    # Check directory last modified time
                    last_modified = session_dir.stat().st_mtime
                    age_seconds = current_time - last_modified

                    if age_seconds > timeout_seconds:
                        # Session expired, delete it
                        shutil.rmtree(session_dir)
                        cleaned_count += 1
                        logger.info(f"🗑️  Cleaned expired session: {session_dir.name} (age: {age_seconds/60:.1f} min)")
                except Exception as e:
                    logger.error(f"Failed to cleanup session {session_dir}: {e}")

        if cleaned_count > 0:
            logger.info(f"✅ Session cleanup complete: {cleaned_count} sessions removed")
        else:
            logger.debug(f"✅ Session cleanup complete: no expired sessions")

        return cleaned_count

    # ===== Recording 管理 =====
    
    def save_recording(
        self,
        user_id: str,
        recording_id: str,
        operations: List[Dict],
        task_description: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> str:
        """
        Save recording data to server filesystem

        Args:
            task_description: User's description of what they did
            user_query: User's description of what they want to do

        Returns:
            File path
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        recording_path.mkdir(parents=True, exist_ok=True)

        file_path = recording_path / "operations.json"
        data = {
            "recording_id": recording_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "operations_count": len(operations),
            "operations": operations
        }

        if task_description:
            data["task_description"] = task_description

        if user_query:
            data["user_query"] = user_query

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Recording saved: {recording_id} ({len(operations)} ops)")
        if task_description:
            logger.info(f"  Task: {task_description}")
        if user_query:
            logger.info(f"  User query: {user_query}")
        return str(file_path)

    def update_recording(
        self,
        user_id: str,
        recording_id: str,
        task_description: Optional[str] = None,
        user_query: Optional[str] = None
    ):
        """Update recording with task_description and/or user_query

        Args:
            user_id: User ID
            recording_id: Recording ID
            task_description: Task description to update (optional)
            user_query: User query to update (optional)
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        file_path = recording_path / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return

        # Read existing data
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Update fields
        if task_description is not None:
            data["task_description"] = task_description
            logger.info(f"Updated task_description for {recording_id}")

        if user_query is not None:
            data["user_query"] = user_query
            logger.info(f"Updated user_query for {recording_id}")

        # Save back
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_recording(self, user_id: str, recording_id: str) -> Optional[Dict]:
        """读取录制数据"""
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        file_path = recording_path / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return None

        with open(file_path, 'r') as f:
            data = json.load(f)

        # Load metadata if exists
        metadata_path = recording_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                data["metaflow_id"] = metadata.get("metaflow_id")

        return data

    def update_recording_metaflow(self, user_id: str, recording_id: str, metaflow_id: str):
        """Update recording with associated metaflow_id"""
        recording_path = self._user_path(user_id) / "recordings" / recording_id

        # Ensure recording directory exists
        if not recording_path.exists():
            logger.warning(f"Recording directory not found: {recording_path}")
            recording_path.mkdir(parents=True, exist_ok=True)

        metadata_path = recording_path / "metadata.json"

        metadata = {}
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

        metadata["metaflow_id"] = metaflow_id
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Recording {recording_id} linked to MetaFlow {metaflow_id}")

    def list_recordings(self, user_id: str) -> List[Dict]:
        """List all recordings for user with metadata"""
        recordings_path = self._user_path(user_id) / "recordings"

        if not recordings_path.exists():
            return []

        result = []
        for recording_dir in recordings_path.iterdir():
            if recording_dir.is_dir():
                recording_id = recording_dir.name
                recording = self.get_recording(user_id, recording_id)
                if recording:
                    result.append({
                        "recording_id": recording_id,
                        "task_description": recording.get("task_description"),
                        "created_at": recording.get("created_at"),
                        "operations_count": recording.get("operations_count"),
                        "metaflow_id": recording.get("metaflow_id")
                    })

        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    # ===== MetaFlow 管理 =====

    def save_metaflow(
        self,
        user_id: str,
        metaflow_id: str,
        metaflow_yaml: str,
        user_query: str,
        recording_id: str = None,
        source_type: str = "from_recording"
    ) -> str:
        """
        Save MetaFlow to server filesystem

        Args:
            user_id: User ID
            metaflow_id: MetaFlow ID
            metaflow_yaml: MetaFlow YAML content
            user_query: User's query/request
            recording_id: Source recording ID (for reverse traceability)
            source_type: How this metaflow was generated (from_recording, from_intent_graph)

        Returns:
            metaflow.yaml file path
        """
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        metaflow_path.mkdir(parents=True, exist_ok=True)

        # Save metaflow.yaml
        yaml_file = metaflow_path / "metaflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)

        # Save metadata.json with source information for reverse traceability
        metadata = {
            "metaflow_id": metaflow_id,
            "user_query": user_query,
            "workflow_id": None,
            "source_recording_id": recording_id,  # 反向追溯：记录来源recording
            "source_type": source_type,           # 反向追溯：记录生成方式
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        metadata_file = metaflow_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"MetaFlow saved: {metaflow_id}")
        if recording_id:
            logger.info(f"  Source recording: {recording_id}")
        return str(yaml_file)

    def get_metaflow(self, user_id: str, metaflow_id: str) -> Optional[Dict]:
        """Read MetaFlow data with metadata"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        yaml_file = metaflow_path / "metaflow.yaml"

        if not yaml_file.exists():
            logger.warning(f"MetaFlow not found: {metaflow_id}")
            return None

        with open(yaml_file, 'r', encoding='utf-8') as f:
            metaflow_yaml = f.read()

        # Load metadata
        metadata = {}
        metadata_file = metaflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "user_query": metadata.get("user_query"),
            "workflow_id": metadata.get("workflow_id"),
            "source_recording_id": metadata.get("source_recording_id"),  # 反向追溯信息
            "source_type": metadata.get("source_type"),                  # 反向追溯信息
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at")
        }

    def update_metaflow_yaml(self, user_id: str, metaflow_id: str, metaflow_yaml: str):
        """Update MetaFlow YAML content"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        yaml_file = metaflow_path / "metaflow.yaml"

        logger.info(f"📝 Updating MetaFlow: {metaflow_id}")
        logger.info(f"📍 Target file: {yaml_file}")
        logger.info(f"📏 New content length: {len(metaflow_yaml)} characters")

        # Read old content for comparison
        if yaml_file.exists():
            with open(yaml_file, 'r', encoding='utf-8') as f:
                old_yaml = f.read()
            logger.info(f"📏 Old content length: {len(old_yaml)} characters")
            if old_yaml == metaflow_yaml:
                logger.warning(f"⚠️  New content is IDENTICAL to old content!")
            else:
                logger.info(f"✓ Content has changed")
        else:
            logger.info(f"ℹ️  File does not exist yet, creating new file")

        # Write new content
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)
        logger.info(f"✓ File written successfully")

        # Verify write
        with open(yaml_file, 'r', encoding='utf-8') as f:
            verified_content = f.read()
        if verified_content == metaflow_yaml:
            logger.info(f"✓ File write verified: content matches")
        else:
            logger.error(f"❌ File write verification FAILED: content mismatch!")
            logger.error(f"   Expected length: {len(metaflow_yaml)}, Got: {len(verified_content)}")

        # Update timestamp in metadata
        metadata_file = metaflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        logger.info(f"✅ MetaFlow updated successfully: {metaflow_id}")

    def update_metaflow_workflow(self, user_id: str, metaflow_id: str, workflow_id: str):
        """Update MetaFlow with associated workflow_id"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        metadata_file = metaflow_path / "metadata.json"

        if not metadata_file.exists():
            logger.warning(f"MetaFlow metadata not found: {metaflow_id}")
            return

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata["workflow_id"] = workflow_id
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"MetaFlow {metaflow_id} linked to Workflow {workflow_id}")

    def list_metaflows(self, user_id: str) -> List[Dict]:
        """List all MetaFlows for user"""
        metaflows_path = self._user_path(user_id) / "metaflows"

        if not metaflows_path.exists():
            return []

        result = []
        for metaflow_dir in metaflows_path.iterdir():
            if metaflow_dir.is_dir():
                metaflow_id = metaflow_dir.name
                metaflow = self.get_metaflow(user_id, metaflow_id)
                if metaflow:
                    result.append({
                        "metaflow_id": metaflow_id,
                        "user_query": metaflow.get("user_query"),
                        "workflow_id": metaflow.get("workflow_id"),
                        "source_recording_id": metaflow.get("source_recording_id"),  # 反向追溯信息
                        "source_type": metaflow.get("source_type"),                  # 反向追溯信息
                        "created_at": metaflow.get("created_at"),
                        "updated_at": metaflow.get("updated_at")
                    })

        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    def metaflow_exists(self, user_id: str, metaflow_id: str) -> bool:
        """Check if MetaFlow exists"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        return (metaflow_path / "metaflow.yaml").exists()

    def delete_metaflow(self, user_id: str, metaflow_id: str) -> bool:
        """Delete MetaFlow directory completely

        Returns:
            True if deleted, False if not found
        """
        import shutil
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id

        if not metaflow_path.exists():
            logger.warning(f"MetaFlow not found for deletion: {metaflow_id}")
            return False

        shutil.rmtree(metaflow_path)
        logger.info(f"MetaFlow deleted: {metaflow_id}")
        return True

    # ===== Workflow 管理 =====
    
    def save_workflow(
        self,
        user_id: str,
        workflow_id: str,
        workflow_yaml: str,
        workflow_name: str,
        metaflow_id: str = None,
        source_recording_id: str = None
    ) -> str:
        """
        Save Workflow to server filesystem

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            workflow_yaml: Workflow YAML content
            workflow_name: Display name for the workflow
            metaflow_id: Source metaflow ID (for reverse traceability)
            source_recording_id: Original recording ID (optional, for convenience)

        Returns:
            workflow.yaml file path
        """
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        workflow_path.mkdir(parents=True, exist_ok=True)

        # Save workflow.yaml
        yaml_file = workflow_path / "workflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        # Save metadata.json with source information for reverse traceability
        metadata = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "source_metaflow_id": metaflow_id,    # 反向追溯：记录来源metaflow
            "source_recording_id": source_recording_id,  # 反向追溯：记录原始recording（可选）
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        metadata_file = workflow_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Workflow saved: {workflow_id} ({workflow_name})")
        if metaflow_id:
            logger.info(f"  Source metaflow: {metaflow_id}")
        return str(yaml_file)

    def get_workflow(self, user_id: str, workflow_id: str) -> Optional[Dict]:
        """Read Workflow data with metadata"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        yaml_file = workflow_path / "workflow.yaml"

        if not yaml_file.exists():
            logger.warning(f"Workflow not found: {workflow_id}")
            return None

        with open(yaml_file, 'r', encoding='utf-8') as f:
            workflow_yaml = f.read()

        # Load metadata
        metadata = {}
        metadata_file = workflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

        return {
            "workflow_id": workflow_id,
            "workflow_name": metadata.get("workflow_name", workflow_id),
            "workflow_yaml": workflow_yaml,
            "source_metaflow_id": metadata.get("source_metaflow_id"),      # 反向追溯信息
            "source_recording_id": metadata.get("source_recording_id"),    # 反向追溯信息
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at")
        }

    def update_workflow_yaml(self, user_id: str, workflow_id: str, workflow_yaml: str):
        """Update Workflow YAML content"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        yaml_file = workflow_path / "workflow.yaml"

        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        # Update timestamp in metadata
        metadata_file = workflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        logger.info(f"Workflow updated: {workflow_id}")

    def list_workflows(self, user_id: str) -> List[Dict]:
        """List all Workflows for user with metadata"""
        workflows_path = self._user_path(user_id) / "workflows"

        if not workflows_path.exists():
            return []

        result = []
        for workflow_dir in workflows_path.iterdir():
            if workflow_dir.is_dir():
                workflow_id = workflow_dir.name
                workflow = self.get_workflow(user_id, workflow_id)
                if workflow:
                    result.append({
                        "workflow_id": workflow_id,
                        "workflow_name": workflow.get("workflow_name"),
                        "created_at": workflow.get("created_at"),
                        "updated_at": workflow.get("updated_at")
                    })

        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    def workflow_exists(self, user_id: str, workflow_id: str) -> bool:
        """Check if Workflow exists"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        return (workflow_path / "workflow.yaml").exists()

    def delete_workflow(self, user_id: str, workflow_id: str) -> bool:
        """Delete Workflow directory completely

        Returns:
            True if deleted, False if not found
        """
        import shutil
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id

        if not workflow_path.exists():
            logger.warning(f"Workflow not found for deletion: {workflow_id}")
            return False

        shutil.rmtree(workflow_path)
        logger.info(f"Workflow deleted: {workflow_id}")
        return True
