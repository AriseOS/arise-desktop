"""
Cloud Client - 调用 Cloud Backend API 的客户端

负责与云端通信：
- 用户认证
- 上传录制数据
- 触发 Workflow 生成
- 下载 Workflow
- 上报执行统计
"""

import httpx
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class CloudClient:
    """调用 Cloud Backend API 的客户端"""
    
    def __init__(self, base_url: str, token: Optional[str] = None):
        """
        初始化 Cloud Client
        
        Args:
            base_url: Cloud Backend URL (如 https://api.ami.com)
            token: JWT Token（可选，登录后获得）
        """
        self.base_url = base_url
        self.token = token
        
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=120.0  # Workflow 生成需要时间
        )
    
    async def login(self, username: str, password: str) -> Dict:
        """
        用户登录
        
        Returns:
            {"token": "...", "user_id": ...}
        """
        try:
            response = await self.client.post(
                "/api/auth/login",
                json={"username": username, "password": password}
            )
            response.raise_for_status()
            data = response.json()
            
            # 更新 token
            self.token = data["token"]
            self.client.headers["Authorization"] = f"Bearer {self.token}"
            
            logger.info(f"User logged in: {username}")
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Login failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Login error: {e}")
            raise
    
    async def upload_recording(self, operations: List[Dict]) -> str:
        """
        上传录制数据
        
        Args:
            operations: 操作列表
            
        Returns:
            recording_id
        """
        try:
            response = await self.client.post(
                "/api/recordings/upload",
                json={"operations": operations}
            )
            response.raise_for_status()
            data = response.json()
            
            recording_id = data["recording_id"]
            logger.info(f"Recording uploaded: {recording_id}")
            return recording_id
            
        except Exception as e:
            logger.error(f"Upload recording failed: {e}")
            raise
    
    async def generate_workflow(self, recording_id: str) -> str:
        """
        触发 Workflow 生成（同步，30-60 秒）
        
        Args:
            recording_id: 录制 ID
            
        Returns:
            workflow_name
        """
        try:
            logger.info(f"Generating workflow for recording: {recording_id}")
            
            response = await self.client.post(
                f"/api/recordings/{recording_id}/generate"
            )
            response.raise_for_status()
            data = response.json()
            
            workflow_name = data["workflow_name"]
            logger.info(f"Workflow generated: {workflow_name}")
            return workflow_name
            
        except Exception as e:
            logger.error(f"Generate workflow failed: {e}")
            raise
    
    async def download_workflow(self, workflow_name: str) -> str:
        """
        下载 Workflow YAML
        
        Args:
            workflow_name: Workflow 名称
            
        Returns:
            workflow.yaml 内容（字符串）
        """
        try:
            response = await self.client.get(
                f"/api/workflows/{workflow_name}/download"
            )
            response.raise_for_status()
            data = response.json()
            
            workflow_yaml = data["yaml"]
            logger.info(f"Workflow downloaded: {workflow_name}")
            return workflow_yaml
            
        except Exception as e:
            logger.error(f"Download workflow failed: {e}")
            raise
    
    async def list_workflows(self) -> List[Dict]:
        """
        获取 Workflow 列表
        
        Returns:
            [{"name": "...", "created_at": "...", ...}, ...]
        """
        try:
            response = await self.client.get("/api/workflows")
            response.raise_for_status()
            workflows = response.json()
            
            logger.info(f"Found {len(workflows)} workflows")
            return workflows
            
        except Exception as e:
            logger.error(f"List workflows failed: {e}")
            raise
    
    async def report_execution(
        self,
        workflow_name: str,
        status: str,
        duration: float,
        error: Optional[str] = None
    ):
        """
        上报执行统计
        
        Args:
            workflow_name: Workflow 名称
            status: 状态（success/failed）
            duration: 执行时长（秒）
            error: 错误信息（可选）
        """
        try:
            await self.client.post(
                "/api/executions/report",
                json={
                    "workflow_name": workflow_name,
                    "status": status,
                    "duration": duration,
                    "error": error
                }
            )
            logger.info(f"Execution reported: {workflow_name} - {status}")
            
        except Exception as e:
            # 上报失败不影响主流程，只记录日志
            logger.warning(f"Report execution failed: {e}")
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
