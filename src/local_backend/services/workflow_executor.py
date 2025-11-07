"""
Workflow Executor - Workflow 执行引擎 (Local Backend)

负责：
- 加载 Workflow YAML
- 使用 BaseAgent 执行
- 管理执行状态
- 保存执行结果
"""

import yaml
import uuid
import asyncio
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
import sys
import logging

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.base_app.base_app.base_agent.core.base_agent import BaseAgent
from src.base_app.base_app.base_agent.core.schemas import Workflow, AgentConfig
from src.base_app.base_app.server.core.config_service import ConfigService

logger = logging.getLogger(__name__)

class WorkflowExecutor:
    """Workflow 执行引擎（BaseAgent 简化版）"""
    
    def __init__(self):
        """初始化执行器"""
        # 加载配置
        self.config_service = ConfigService()
        
        # 创建单例 BaseAgent（服务所有用户）
        agent_config = AgentConfig(
            name="WorkflowExecutor",
            llm_provider=self.config_service.get('agent.llm.provider', 'anthropic'),
            llm_model=self.config_service.get('agent.llm.model', 'claude-sonnet-4-5'),
            api_key=self.config_service.get('agent.llm.api_key')
        )
        
        self.agent = BaseAgent(
            config=agent_config,
            config_service=self.config_service,
            user_id=None  # 不绑定特定用户，通过 context 传递
        )
        
        # 任务状态管理（内存中）
        self.tasks: Dict[str, Dict] = {}
        
        logger.info("✅ Workflow Executor initialized")
    
    async def execute_workflow(
        self,
        user_id: str,
        workflow_yaml: str,
        execution_id: Optional[str] = None
    ) -> str:
        """
        执行 Workflow（异步）
        
        Args:
            user_id: 用户 ID
            workflow_yaml: Workflow YAML 内容
            execution_id: 执行 ID（可选，不指定则自动生成）
            
        Returns:
            task_id（用于查询执行状态）
        """
        if execution_id is None:
            execution_id = str(uuid.uuid4())
        
        task_id = execution_id
        
        # 初始化任务状态
        self.tasks[task_id] = {
            "task_id": task_id,
            "user_id": user_id,
            "status": "running",
            "progress": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None
        }
        
        # 异步执行
        asyncio.create_task(self._execute_workflow_async(
            task_id, user_id, workflow_yaml
        ))
        
        logger.info(f"Workflow execution started: {task_id}")
        return task_id
    
    async def _execute_workflow_async(
        self,
        task_id: str,
        user_id: str,
        workflow_yaml: str
    ):
        """
        异步执行 Workflow
        """
        try:
            # 解析 YAML
            workflow_dict = yaml.safe_load(workflow_yaml)
            
            # 强制设置 name = "global" (复用全局浏览器会话)
            workflow_dict['name'] = 'global'
            
            # 转换为 Workflow 对象
            workflow = Workflow(**workflow_dict)
            
            # 更新进度
            self.tasks[task_id]["progress"] = 10
            
            # 执行 Workflow
            result = await self.agent.run_workflow(
                workflow,
                context={"user_id": user_id}
            )
            
            # 更新任务状态
            self.tasks[task_id].update({
                "status": "completed" if result.success else "failed",
                "progress": 100,
                "result": {
                    "success": result.success,
                    "final_result": result.final_result,
                    "steps_completed": len(result.step_results) if hasattr(result, 'step_results') else 0
                },
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
            
            if not result.success:
                self.tasks[task_id]["error"] = result.error
            
            logger.info(f"Workflow execution completed: {task_id} - {result.success}")
            
        except Exception as e:
            # 执行失败
            logger.error(f"Workflow execution failed: {task_id} - {e}")
            
            self.tasks[task_id].update({
                "status": "failed",
                "progress": 0,
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """
        获取任务状态
        
        Returns:
            {
                "task_id": "...",
                "status": "running|completed|failed",
                "progress": 0-100,
                "result": {...},
                "error": "..."
            }
        """
        return self.tasks.get(task_id)
    
    def cleanup_completed_tasks(self, max_keep: int = 100):
        """
        清理已完成的任务（保留最近的 max_keep 个）
        """
        completed_tasks = [
            (task_id, task)
            for task_id, task in self.tasks.items()
            if task["status"] in ["completed", "failed"]
        ]
        
        if len(completed_tasks) > max_keep:
            # 按完成时间排序，删除最老的
            completed_tasks.sort(
                key=lambda x: x[1].get("completed_at", ""),
                reverse=True
            )
            
            for task_id, _ in completed_tasks[max_keep:]:
                del self.tasks[task_id]
            
            logger.info(f"Cleaned up {len(completed_tasks) - max_keep} old tasks")
