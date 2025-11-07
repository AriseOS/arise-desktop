"""
Storage Manager - 本地文件系统管理 (Local Backend)

统一存储路径：~/.ami 

目录结构：
~/.ami
├── users/{user_id}/
│   ├── recordings/          # 临时录制数据
│   │   └── {session_id}/
│   │       └── operations.json
│   ├── workflows/           # Workflow YAML 缓存
│   │   └── {workflow_name}/
│   │       ├── workflow.yaml
│   │       ├── metadata.json
│   │       └── executions/
│   │           └── {execution_id}/
│   │               └── result.json
│   └── cache/               # 其他缓存
└── logs/                    # 日志
"""

from pathlib import Path
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class StorageManager:
    """本地文件系统管理器"""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        初始化存储管理器
        
        Args:
            base_path: 基础路径（可选）
                默认：~/.ami 
        """
        if base_path:
            self.base_path = Path(base_path).expanduser()
        else:
            # macOS 标准路径
            self.base_path = Path.home() / ".ami"
        
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Storage initialized: {self.base_path}")
    
    def _user_path(self, user_id: str) -> Path:
        """获取用户目录"""
        path = self.base_path / "users" / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # ===== 录制数据管理 =====
    
    def save_recording(
        self, 
        user_id: str, 
        session_id: str, 
        operations: List[Dict]
    ):
        """
        保存录制数据
        
        Args:
            user_id: 用户 ID
            session_id: 录制会话 ID
            operations: 操作列表
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id
        recording_path.mkdir(parents=True, exist_ok=True)
        
        file_path = recording_path / "operations.json"
        with open(file_path, 'w') as f:
            json.dump({
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "operations_count": len(operations),
                "operations": operations
            }, f, indent=2)
        
        logger.info(f"Recording saved: {session_id} ({len(operations)} ops)")
    
    def get_recording(self, user_id: str, session_id: str) -> Optional[List[Dict]]:
        """
        读取录制数据
        
        Returns:
            操作列表，如果不存在返回 None
        """
        file_path = self._user_path(user_id) / "recordings" / session_id / "operations.json"
        
        if not file_path.exists():
            logger.warning(f"Recording not found: {session_id}")
            return None
        
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get("operations", [])
    
    def delete_recording(self, user_id: str, session_id: str):
        """删除录制数据（上传成功后）"""
        recording_path = self._user_path(user_id) / "recordings" / session_id
        
        if recording_path.exists():
            import shutil
            shutil.rmtree(recording_path)
            logger.info(f"Recording deleted: {session_id}")
    
    # ===== Workflow 管理 =====
    
    def save_workflow(
        self,
        user_id: str,
        workflow_name: str,
        workflow_yaml: str,
        metadata: Optional[Dict] = None
    ):
        """
        保存 Workflow YAML
        
        Args:
            user_id: 用户 ID
            workflow_name: Workflow 名称
            workflow_yaml: YAML 内容
            metadata: 元数据（可选）
        """
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        workflow_path.mkdir(parents=True, exist_ok=True)
        
        # 保存 YAML
        yaml_file = workflow_path / "workflow.yaml"
        with open(yaml_file, 'w') as f:
            f.write(workflow_yaml)
        
        # 保存元数据
        if metadata is None:
            metadata = {}
        
        metadata.update({
            "workflow_name": workflow_name,
            "cached_at": datetime.now(timezone.utc).isoformat()
        })
        
        metadata_file = workflow_path / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Workflow saved: {workflow_name}")
    
    def get_workflow(self, user_id: str, workflow_name: str) -> Optional[str]:
        """
        读取 Workflow YAML
        
        Returns:
            YAML 内容，如果不存在返回 None
        """
        file_path = self._user_path(user_id) / "workflows" / workflow_name / "workflow.yaml"
        
        if not file_path.exists():
            logger.warning(f"Workflow not found: {workflow_name}")
            return None
        
        with open(file_path, 'r') as f:
            return f.read()
    
    def list_workflows(self, user_id: str) -> List[Dict]:
        """
        列出所有 Workflow
        
        Returns:
            [{"name": "...", "cached_at": "...", ...}, ...]
        """
        workflows_path = self._user_path(user_id) / "workflows"
        
        if not workflows_path.exists():
            return []
        
        workflows = []
        for workflow_dir in workflows_path.iterdir():
            if not workflow_dir.is_dir():
                continue
            
            metadata_file = workflow_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    workflows.append(metadata)
            else:
                # 没有元数据，只返回名称
                workflows.append({"workflow_name": workflow_dir.name})
        
        return workflows
    
    def delete_workflow(self, user_id: str, workflow_name: str):
        """删除 Workflow"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        
        if workflow_path.exists():
            import shutil
            shutil.rmtree(workflow_path)
            logger.info(f"Workflow deleted: {workflow_name}")
    
    # ===== 执行历史管理 =====
    
    def save_execution_result(
        self,
        user_id: str,
        workflow_name: str,
        execution_id: str,
        result: Dict
    ):
        """
        保存执行结果
        
        Args:
            user_id: 用户 ID
            workflow_name: Workflow 名称
            execution_id: 执行 ID
            result: 执行结果
        """
        exec_path = (
            self._user_path(user_id) / 
            "workflows" / workflow_name / 
            "executions" / execution_id
        )
        exec_path.mkdir(parents=True, exist_ok=True)
        
        result_file = exec_path / "result.json"
        with open(result_file, 'w') as f:
            json.dump({
                "execution_id": execution_id,
                "workflow_name": workflow_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **result
            }, f, indent=2)
        
        logger.info(f"Execution result saved: {execution_id}")
    
    def get_execution_history(
        self,
        user_id: str,
        workflow_name: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        获取执行历史
        
        Args:
            user_id: 用户 ID
            workflow_name: Workflow 名称
            limit: 最多返回多少条
            
        Returns:
            [{execution_id, status, timestamp, ...}, ...]
        """
        exec_base_path = (
            self._user_path(user_id) / 
            "workflows" / workflow_name / 
            "executions"
        )
        
        if not exec_base_path.exists():
            return []
        
        history = []
        for exec_dir in sorted(exec_base_path.iterdir(), reverse=True):
            if not exec_dir.is_dir():
                continue
            
            result_file = exec_dir / "result.json"
            if result_file.exists():
                with open(result_file, 'r') as f:
                    history.append(json.load(f))
            
            if len(history) >= limit:
                break
        
        return history
    
    # ===== 工具方法 =====
    
    def get_storage_stats(self, user_id: str) -> Dict:
        """
        获取存储统计信息
        
        Returns:
            {
                "workflows_count": 10,
                "recordings_count": 5,
                "total_size_mb": 15.2
            }
        """
        user_path = self._user_path(user_id)
        
        def get_dir_size(path: Path) -> int:
            """计算目录大小（字节）"""
            total = 0
            if path.exists():
                for item in path.rglob('*'):
                    if item.is_file():
                        total += item.stat().st_size
            return total
        
        workflows_path = user_path / "workflows"
        recordings_path = user_path / "recordings"
        
        workflows_count = len(list(workflows_path.iterdir())) if workflows_path.exists() else 0
        recordings_count = len(list(recordings_path.iterdir())) if recordings_path.exists() else 0
        total_size = get_dir_size(user_path)
        
        return {
            "workflows_count": workflows_count,
            "recordings_count": recordings_count,
            "total_size_mb": round(total_size / 1024 / 1024, 2)
        }
