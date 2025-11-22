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

    async def get_recording(
        self,
        recording_id: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Get recording detail from Cloud Backend

        Args:
            recording_id: Recording ID
            user_id: User ID (default: "default_user")

        Returns:
            Recording dict with metaflow_id if linked
        """
        logger.info(f"Fetching recording {recording_id} from Cloud")

        response = await self.client.get(
            f"/api/recordings/{recording_id}",
            params={"user_id": user_id}
        )
        response.raise_for_status()
        return response.json()

    async def upload_recording(
        self,
        operations: List[Dict[str, Any]],
        task_description: str,
        user_query: Optional[str] = None,
        user_id: str = "default_user",
        recording_id: Optional[str] = None
    ) -> str:
        """Upload recording data to Cloud Backend

        Args:
            operations: List of operation dictionaries
            task_description: User's description of what they did
            user_query: User's description of what they want to do (for MetaFlow generation)
            user_id: User ID (default: "default_user")
            recording_id: Optional recording ID (use App Backend's session_id to keep IDs in sync)

        Returns:
            recording_id: Cloud Backend recording ID
        """
        response = await self.client.post(
            "/api/recordings/upload",
            json={
                "user_id": user_id,
                "task_description": task_description,
                "user_query": user_query,
                "operations": operations,
                "recording_id": recording_id
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

    async def list_metaflows(
        self,
        user_id: str = "default_user"
    ) -> List[Dict[str, Any]]:
        """List all MetaFlows for user from Cloud Backend

        Args:
            user_id: User ID (default: "default_user")

        Returns:
            List of MetaFlow dicts
        """
        logger.info(f"Fetching MetaFlow list from Cloud for user: {user_id}")

        try:
            response = await self.client.get(
                "/api/metaflows",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch metaflows from Cloud: {e}")
            return []

    async def get_metaflow(
        self,
        metaflow_id: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Get MetaFlow detail from Cloud Backend

        Args:
            metaflow_id: MetaFlow ID
            user_id: User ID (default: "default_user")

        Returns:
            MetaFlow dict with metaflow_yaml, user_query, etc.
        """
        logger.info(f"Fetching MetaFlow {metaflow_id} from Cloud")

        response = await self.client.get(
            f"/api/metaflows/{metaflow_id}",
            params={"user_id": user_id}
        )
        response.raise_for_status()
        return response.json()

    async def update_metaflow(
        self,
        metaflow_id: str,
        metaflow_yaml: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Update MetaFlow YAML content

        Args:
            metaflow_id: MetaFlow ID
            metaflow_yaml: New YAML content
            user_id: User ID (default: "default_user")

        Returns:
            {"success": True}
        """
        logger.info(f"Updating MetaFlow {metaflow_id}")

        response = await self.client.put(
            f"/api/metaflows/{metaflow_id}",
            json={
                "user_id": user_id,
                "metaflow_yaml": metaflow_yaml
            }
        )
        response.raise_for_status()
        return response.json()

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

    async def analyze_recording_operations(
        self,
        operations: List[Dict[str, Any]],
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Analyze recording operations using AI

        Args:
            operations: List of operation dictionaries
            user_id: User ID

        Returns:
            dict with:
                - task_description: What user did
                - user_query: What user wants to achieve
                - patterns: Detected patterns (loop, extraction, etc.)
        """
        try:
            logger.info(f"Analyzing {len(operations)} operations...")

            response = await self.client.post(
                "/api/analyze_recording",
                json={
                    "operations": operations,
                    "user_id": user_id
                }
            )
            response.raise_for_status()
            result = response.json()

            logger.info("Analysis successful")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Analysis failed: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            raise

    # ===== Intent Builder Agent APIs (SSE Streaming) =====

    async def start_intent_builder_session(
        self,
        user_id: str,
        user_query: str,
        task_description: Optional[str] = None,
        current_metaflow_yaml: Optional[str] = None,
        current_workflow_yaml: Optional[str] = None,
        phase: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start a new Intent Builder Agent session

        Args:
            user_id: User ID
            user_query: User's query/request
            task_description: Optional additional context
            current_metaflow_yaml: Current MetaFlow content for context
            current_workflow_yaml: Current Workflow content for context
            phase: 'metaflow' or 'workflow'

        Returns:
            dict: {"session_id": "..."}
        """
        logger.info(f"Starting Intent Builder session for user: {user_id}")

        response = await self.client.post(
            "/api/intent-builder/start",
            json={
                "user_id": user_id,
                "user_query": user_query,
                "task_description": task_description,
                "current_metaflow_yaml": current_metaflow_yaml,
                "current_workflow_yaml": current_workflow_yaml,
                "phase": phase
            }
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"Intent Builder session started: {result['session_id']}")
        return result

    async def stream_intent_builder_start(self, session_id: str):
        """Stream the initial response from Intent Builder Agent

        Yields:
            SSE event strings (e.g., "data: {...}\n\n")
        """
        logger.info(f"Streaming Intent Builder start: {session_id}")

        async with self.client.stream(
            "GET",
            f"/api/intent-builder/{session_id}/stream"
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line + "\n"

    async def stream_intent_builder_chat(self, session_id: str, message: str):
        """Stream chat response from Intent Builder Agent

        Args:
            session_id: Session ID
            message: User message

        Yields:
            SSE event strings
        """
        logger.info(f"Streaming Intent Builder chat: {session_id}")

        async with self.client.stream(
            "POST",
            f"/api/intent-builder/{session_id}/chat",
            json={"message": message}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line + "\n"

    async def get_intent_builder_state(self, session_id: str) -> Dict[str, Any]:
        """Get current state of Intent Builder session

        Args:
            session_id: Session ID

        Returns:
            State dictionary
        """
        response = await self.client.get(
            f"/api/intent-builder/{session_id}/state"
        )
        response.raise_for_status()
        return response.json()

    async def close_intent_builder_session(self, session_id: str) -> Dict[str, Any]:
        """Close and cleanup Intent Builder session

        Args:
            session_id: Session ID

        Returns:
            {"success": True}
        """
        logger.info(f"Closing Intent Builder session: {session_id}")

        response = await self.client.delete(
            f"/api/intent-builder/{session_id}"
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
