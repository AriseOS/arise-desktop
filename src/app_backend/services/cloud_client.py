"""Cloud Backend API client"""
import logging
import httpx
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class CloudClient:
    """Client for calling Cloud Backend APIs

    Note: All Cloud Backend APIs are sync (no timeout limit)
    MetaFlow and Workflow generation may take 30-60s
    """

    def __init__(self, api_url: str, token: Optional[str] = None):
        """Initialize Cloud API client

        Args:
            api_url: Cloud Backend URL (e.g., https://api.ami.com)
            token: User JWT token (optional for MVP)
        """
        self.api_url = api_url.rstrip('/')
        self.token = token

        # No timeout limit (as per requirements)
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=None  # No timeout
        )

    async def upload_recording(
        self,
        operations: List[Dict[str, Any]],
        task_description: str,
        user_query: Optional[str] = None,
        user_id: str = "default_user"
    ) -> str:
        """Upload recording data to Cloud Backend

        Args:
            operations: List of operation dictionaries
            task_description: User's description of what they did
            user_query: User's description of what they want to do (for MetaFlow generation)
            user_id: User ID (default: "default_user")

        Returns:
            recording_id: Cloud Backend recording ID
        """
        response = await self.client.post(
            "/api/recordings/upload",
            json={
                "user_id": user_id,
                "task_description": task_description,
                "user_query": user_query,
                "operations": operations
            }
        )
        response.raise_for_status()
        return response.json()["recording_id"]

    async def generate_metaflow(
        self,
        task_description: str,
        user_query: Optional[str] = None,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Generate MetaFlow from user's Intent Memory Graph

        Args:
            task_description: User's description of what they did
            user_query: User's description of what they want to do (for MetaFlow generation)
            user_id: User ID (default: "default_user")

        Returns:
            dict: {
                "metaflow_id": str,
                "metaflow_yaml": str,
                "task_description": str,
                "status": str
            }
        """
        logger.info(f"Generating MetaFlow for task: {task_description}")
        if user_query:
            logger.info(f"User query: {user_query}")

        response = await self.client.post(
            f"/api/users/{user_id}/generate_metaflow",
            json={
                "task_description": task_description,
                "user_query": user_query
            }
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"MetaFlow generated: {result.get('metaflow_id')}")
        return result

    async def generate_metaflow_from_recording(
        self,
        recording_id: str,
        task_description: str,
        user_query: Optional[str] = None,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Generate MetaFlow from a specific recording (using only that recording's intents)

        Args:
            recording_id: Recording ID
            task_description: User's description of what they did
            user_query: User's description of what they want to do (for MetaFlow generation)
            user_id: User ID (default: "default_user")

        Returns:
            dict: {
                "metaflow_id": str,
                "metaflow_yaml": str,
                "task_description": str,
                "status": str
            }
        """
        logger.info(f"Generating MetaFlow from recording: {recording_id}")
        if user_query:
            logger.info(f"User query: {user_query}")

        response = await self.client.post(
            f"/api/recordings/{recording_id}/generate_metaflow",
            json={
                "user_id": user_id,
                "task_description": task_description,
                "user_query": user_query
            }
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"MetaFlow generated from recording: {result.get('metaflow_id')}")
        return result

    async def generate_workflow(
        self,
        metaflow_id: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Generate Workflow from MetaFlow

        Args:
            metaflow_id: MetaFlow ID
            user_id: User ID (default: "default_user")

        Returns:
            dict: {
                "workflow_name": str,
                "workflow_yaml": str,
                "status": str
            }
        """
        logger.info(f"Generating Workflow from MetaFlow: {metaflow_id}")

        response = await self.client.post(
            f"/api/metaflows/{metaflow_id}/generate_workflow",
            json={"user_id": user_id}
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"Workflow generated: {result.get('workflow_name')}")
        return result

    async def list_workflows(
        self,
        user_id: str = "default_user"
    ) -> List[Dict[str, Any]]:
        """List all workflows for user from Cloud Backend

        Args:
            user_id: User ID (default: "default_user")

        Returns:
            List of workflow dicts with:
            - agent_id: workflow ID
            - name: workflow display name
            - description: workflow description
            - created_at: creation timestamp
        """
        logger.info(f"Fetching workflow list from Cloud for user: {user_id}")

        try:
            response = await self.client.get(
                f"/api/users/{user_id}/workflows"
            )
            response.raise_for_status()
            result = response.json()

            workflows = result.get("workflows", [])
            logger.info(f"Fetched {len(workflows)} workflows from Cloud")
            return workflows

        except Exception as e:
            logger.warning(f"Failed to fetch workflows from Cloud: {e}")
            return []

    async def report_execution(
        self,
        user_id: str,
        workflow_name: str,
        status: str,
        execution_time_ms: int,
        error: Optional[str] = None
    ):
        """Report execution statistics to Cloud Backend (async)"""
        try:
            await self.client.post(
                "/api/executions/report",
                json={
                    "user_id": user_id,
                    "workflow_name": workflow_name,
                    "status": status,
                    "execution_time_ms": execution_time_ms,
                    "error": error
                }
            )
        except Exception as e:
            # Fire-and-forget, don't fail if reporting fails
            logger.warning(f"Failed to report execution: {e}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
