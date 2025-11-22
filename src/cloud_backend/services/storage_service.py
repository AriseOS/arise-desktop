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
        user_query: str
    ) -> str:
        """
        Save MetaFlow to server filesystem

        Args:
            user_id: User ID
            metaflow_id: MetaFlow ID
            metaflow_yaml: MetaFlow YAML content
            user_query: User's query/request

        Returns:
            metaflow.yaml file path
        """
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        metaflow_path.mkdir(parents=True, exist_ok=True)

        # Save metaflow.yaml
        yaml_file = metaflow_path / "metaflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)

        # Save metadata.json
        metadata = {
            "metaflow_id": metaflow_id,
            "user_query": user_query,
            "workflow_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        metadata_file = metaflow_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"MetaFlow saved: {metaflow_id}")
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
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at")
        }

    def update_metaflow_yaml(self, user_id: str, metaflow_id: str, metaflow_yaml: str):
        """Update MetaFlow YAML content"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        yaml_file = metaflow_path / "metaflow.yaml"

        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)

        # Update timestamp in metadata
        metadata_file = metaflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        logger.info(f"MetaFlow updated: {metaflow_id}")

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
                        "created_at": metaflow.get("created_at"),
                        "updated_at": metaflow.get("updated_at")
                    })

        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    # ===== Workflow 管理 =====
    
    def save_workflow(
        self,
        user_id: str,
        workflow_id: str,
        workflow_yaml: str,
        workflow_name: str
    ) -> str:
        """
        Save Workflow to server filesystem

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            workflow_yaml: Workflow YAML content
            workflow_name: Display name for the workflow

        Returns:
            workflow.yaml file path
        """
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        workflow_path.mkdir(parents=True, exist_ok=True)

        # Save workflow.yaml
        yaml_file = workflow_path / "workflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        # Save metadata.json
        metadata = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        metadata_file = workflow_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Workflow saved: {workflow_id} ({workflow_name})")
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
