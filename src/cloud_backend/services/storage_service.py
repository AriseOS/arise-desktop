"""
Storage Service - 服务器本地文件系统管理 (Cloud Backend)

存储路径：
- 开发环境：~/.ami
- 生产环境：/var/lib/ami/（或通过环境变量 STORAGE_PATH 配置）

目录结构：
~/.ami/
├── users/{user_id}/
│   ├── recordings/              # 录制数据
│   │   └── {recording_id}/
│   │       ├── operations.json
│   │       └── intent_graph_status.json  # {status, intent_graph_id}
│   ├── intent_graphs/           # Intent Memory Graphs
│   │   └── {graph_id}/
│   │       ├── graph.json       # Intent Memory Graph 序列化
│   │       └── metadata.json    # 元数据
│   ├── metaflows/               # MetaFlows
│   │   └── {metaflow_id}/
│   │       ├── metaflow.yaml
│   │       ├── source_graph_id.txt
│   │       └── task_description.txt
│   └── workflows/               # Workflows
│       └── {workflow_name}/
│           ├── workflow.yaml
│           ├── metaflow.yaml
│           └── intent_graph.json
└── logs/
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
        file_path = self._user_path(user_id) / "recordings" / recording_id / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return None

        with open(file_path, 'r') as f:
            return json.load(f)

    # ===== MetaFlow 管理 =====

    def save_metaflow(
        self,
        user_id: str,
        metaflow_id: str,
        metaflow_yaml: str,
        task_description: str
    ) -> str:
        """
        Save MetaFlow to server filesystem

        Returns:
            metaflow.yaml file path
        """
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        metaflow_path.mkdir(parents=True, exist_ok=True)

        # Save metaflow.yaml
        yaml_file = metaflow_path / "metaflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(metaflow_yaml)

        # Save task_description.txt
        task_file = metaflow_path / "task_description.txt"
        with open(task_file, 'w', encoding='utf-8') as f:
            f.write(task_description)

        logger.info(f"MetaFlow saved: {metaflow_id}")
        return str(yaml_file)

    def get_metaflow(self, user_id: str, metaflow_id: str) -> Optional[Dict]:
        """Read MetaFlow data"""
        metaflow_path = self._user_path(user_id) / "metaflows" / metaflow_id
        yaml_file = metaflow_path / "metaflow.yaml"

        if not yaml_file.exists():
            logger.warning(f"MetaFlow not found: {metaflow_id}")
            return None

        with open(yaml_file, 'r', encoding='utf-8') as f:
            metaflow_yaml = f.read()

        # Load task_description if exists
        task_description = None
        task_file = metaflow_path / "task_description.txt"
        if task_file.exists():
            with open(task_file, 'r', encoding='utf-8') as f:
                task_description = f.read()

        return {
            "metaflow_yaml": metaflow_yaml,
            "task_description": task_description
        }

    # ===== Workflow 管理 =====
    
    def save_workflow(
        self,
        user_id: str,
        workflow_name: str,
        workflow_yaml: str,
        metaflow_yaml: Optional[str] = None,
        intent_graph: Optional[Dict] = None
    ) -> str:
        """
        保存 Workflow 到服务器文件系统
        
        Returns:
            workflow.yaml 文件路径
        """
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        workflow_path.mkdir(parents=True, exist_ok=True)
        
        # 保存 workflow.yaml
        yaml_file = workflow_path / "workflow.yaml"
        with open(yaml_file, 'w') as f:
            f.write(workflow_yaml)
        
        # 保存 metaflow.yaml（如果有）
        if metaflow_yaml:
            metaflow_file = workflow_path / "metaflow.yaml"
            with open(metaflow_file, 'w') as f:
                f.write(metaflow_yaml)
        
        # 保存 intent_graph.json（如果有）
        if intent_graph:
            graph_file = workflow_path / "intent_graph.json"
            with open(graph_file, 'w') as f:
                json.dump(intent_graph, f, indent=2)
        
        logger.info(f"Workflow saved: {workflow_name}")
        return str(yaml_file)
    
    def get_workflow(self, user_id: str, workflow_name: str) -> Optional[str]:
        """读取 Workflow YAML"""
        file_path = self._user_path(user_id) / "workflows" / workflow_name / "workflow.yaml"
        
        if not file_path.exists():
            logger.warning(f"Workflow not found: {workflow_name}")
            return None
        
        with open(file_path, 'r') as f:
            return f.read()
    
    def list_workflows(self, user_id: str) -> List[str]:
        """列出用户的所有 Workflow"""
        workflows_path = self._user_path(user_id) / "workflows"
        
        if not workflows_path.exists():
            return []
        
        return [d.name for d in workflows_path.iterdir() if d.is_dir()]
