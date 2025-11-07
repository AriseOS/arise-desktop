"""
Storage Service - 服务器本地文件系统管理 (Cloud Backend)

存储路径：
- 开发环境：~/.ami
- 生产环境：/var/lib/ami/（或通过环境变量 STORAGE_PATH 配置）

目录结构：
~/.ami/
├── users/{user_id}/
│   ├── recordings/          # 录制数据
│   │   └── {session_id}/
│   │       └── operations.json
│   └── workflows/           # Workflow YAML
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
        初始化存储服务
        
        Args:
            base_path: 基础路径（可选）
                开发：~/.ami
                生产：/var/lib/ami/ (通过环境变量 STORAGE_PATH 配置)
        """
        if base_path:
            self.base_path = Path(base_path).expanduser()
        else:
            # 默认路径（开发环境）
            default_path = os.getenv("STORAGE_PATH", "~/.ami")
            self.base_path = Path(default_path).expanduser()
        
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Storage initialized: {self.base_path}")
    
    def _user_path(self, user_id: str) -> Path:
        """获取用户目录"""
        path = self.base_path / "users" / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # ===== Recording 管理 =====
    
    def save_recording(
        self,
        user_id: str,
        recording_id: str,
        operations: List[Dict]
    ) -> str:
        """
        保存录制数据到服务器文件系统
        
        Returns:
            文件路径
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        recording_path.mkdir(parents=True, exist_ok=True)
        
        file_path = recording_path / "operations.json"
        with open(file_path, 'w') as f:
            json.dump({
                "recording_id": recording_id,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "operations_count": len(operations),
                "operations": operations
            }, f, indent=2)
        
        logger.info(f"Recording saved: {recording_id} ({len(operations)} ops)")
        return str(file_path)
    
    def get_recording(self, user_id: str, recording_id: str) -> Optional[Dict]:
        """读取录制数据"""
        file_path = self._user_path(user_id) / "recordings" / recording_id / "operations.json"
        
        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return None
        
        with open(file_path, 'r') as f:
            return json.load(f)
    
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
