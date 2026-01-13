"""Cloud Backend API client"""
import logging
import httpx
from typing import List, Optional, Dict, Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class CloudClient:
    """Client for calling Cloud Backend APIs

    Note: All Cloud Backend APIs are sync (no timeout limit)
    Workflow generation may take 30-60s

    Phase 4: Forwards X-Ami-API-Key header to Cloud Backend for API Proxy integration
    """

    def __init__(self, api_url: str, token: Optional[str] = None, user_api_key: Optional[str] = None):
        """Initialize Cloud API client

        Args:
            api_url: Cloud Backend URL (e.g., https://api.ami.com)
            token: User JWT token (optional for MVP)
            user_api_key: User's Ami API key for API Proxy (ami_xxxxx format)
        """
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.user_api_key = user_api_key

        # Build base headers (only static headers)
        # Note: Dynamic headers (like X-Ami-API-Key) must be passed per-request
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Create HTTP client
        # Note: httpx automatically uses system HTTP_PROXY/HTTPS_PROXY if set
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers=headers,
            timeout=None,  # No timeout for long-running operations
        )

        logger.info(f"CloudClient initialized for {self.api_url}")

        if user_api_key:
            logger.info(f"CloudClient initialized with API key: {user_api_key[:10]}...")

    def set_user_api_key(self, api_key: Optional[str]):
        """Update user API key for subsequent requests

        Note: The API key is stored and will be sent as X-Ami-API-Key header
        in each request that requires it.

        Args:
            api_key: User's Ami API key (ami_xxxxx format)
        """
        self.user_api_key = api_key
        if api_key:
            logger.info(f"API key updated: {api_key[:10]}...")
        else:
            logger.info("API key cleared")

    async def check_version(self, version: str, platform: str) -> Dict[str, Any]:
        """Check if app version is compatible with Cloud Backend

        Args:
            version: App version string (e.g., "0.0.1")
            platform: Platform identifier (e.g., "macos-arm64", "windows-x64")

        Returns:
            dict with:
                - compatible: bool - whether version is allowed
                - minimum_version: str - minimum required version
                - update_url: str - download URL if update needed
                - message: str - user-facing message if update needed
        """
        try:
            response = await self.client.post(
                "/api/v1/app/version-check",
                json={"version": version, "platform": platform},
                timeout=10.0  # Short timeout for version check
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Version check result: {result}")
            return result
        except Exception as e:
            logger.error(f"Version check failed: {e}")
            # On error, allow startup (fail open) but log warning
            return {
                "compatible": True,
                "minimum_version": "unknown",
                "error": str(e)
            }

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
            Recording dict with workflow_id if linked
        """
        logger.info(f"Fetching recording {recording_id} from Cloud")

        response = await self.client.get(
            f"/api/v1/recordings/{recording_id}",
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
        recording_id: Optional[str] = None,
        dom_snapshots: Optional[Dict[str, dict]] = None
    ) -> str:
        """Upload recording data to Cloud Backend

        Args:
            operations: List of operation dictionaries
            task_description: User's description of what they did
            user_query: User's description of what they want to do
            user_id: User ID (default: "default_user")
            recording_id: Optional recording ID (use App Backend's session_id to keep IDs in sync)
            dom_snapshots: Optional URL -> DOM dict mapping for pre-generating scripts

        Returns:
            recording_id: Cloud Backend recording ID
        """
        payload = {
            "user_id": user_id,
            "user_api_key": self.user_api_key,
            "task_description": task_description,
            "user_query": user_query,
            "operations": operations,
            "recording_id": recording_id
        }

        # Include DOM snapshots if provided
        if dom_snapshots:
            payload["dom_snapshots"] = dom_snapshots
            logger.info(f"Uploading recording with {len(dom_snapshots)} DOM snapshots")

        response = await self.client.post(
            "/api/v1/recordings",
            json=payload
        )
        response.raise_for_status()
        return response.json()["recording_id"]

    async def update_recording_metadata(
        self,
        recording_id: str,
        user_id: str,
        workflow_id: Optional[str] = None,
        task_description: Optional[str] = None,
        user_query: Optional[str] = None,
        updated_at: Optional[str] = None
    ) -> bool:
        """Update recording metadata in Cloud Backend (for sync)

        Args:
            recording_id: Recording ID
            user_id: User ID
            workflow_id: Workflow ID (None to clear)
            task_description: Task description
            user_query: User query
            updated_at: Timestamp for sync

        Returns:
            True if successful
        """
        payload = {}
        if workflow_id is not None or workflow_id == "":
            # Include workflow_id even if None (to clear it)
            payload["workflow_id"] = workflow_id if workflow_id != "" else None
        if task_description is not None:
            payload["task_description"] = task_description
        if user_query is not None:
            payload["user_query"] = user_query
        if updated_at is not None:
            payload["updated_at"] = updated_at

        logger.info(f"Updating recording metadata in Cloud: {recording_id}")
        response = await self.client.patch(
            f"/api/v1/recordings/{recording_id}",
            params={"user_id": user_id},
            json=payload
        )
        response.raise_for_status()
        return True

    async def update_workflow(
        self,
        workflow_id: str,
        workflow_yaml: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Update Workflow YAML content

        Args:
            workflow_id: Workflow ID
            workflow_yaml: New YAML content
            user_id: User ID (default: "default_user")

        Returns:
            {"success": True}
        """
        logger.info(f"Updating Workflow {workflow_id}")

        response = await self.client.put(
            f"/api/v1/workflows/{workflow_id}",
            json={
                "user_id": user_id,
                "workflow_yaml": workflow_yaml
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_workflow(
        self,
        workflow_id: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Get Workflow detail from Cloud Backend

        Args:
            workflow_id: Workflow ID
            user_id: User ID (default: "default_user")

        Returns:
            Workflow dict with source_recording_id, etc.
        """
        logger.info(f"Fetching Workflow {workflow_id} from Cloud")

        response = await self.client.get(
            f"/api/v1/workflows/{workflow_id}",
            params={"user_id": user_id}
        )
        response.raise_for_status()
        return response.json()

    async def list_recordings(
        self,
        user_id: str = "default_user"
    ) -> List[Dict[str, Any]]:
        """List all recordings for user from Cloud Backend

        Args:
            user_id: User ID

        Returns:
            List of recording dicts with:
            - recording_id: recording ID
            - task_description: task description
            - created_at: creation timestamp
            - workflow_id: associated workflow ID (if any)
        """
        logger.info(f"Fetching recording list from Cloud for user: {user_id}")

        try:
            response = await self.client.get(
                "/api/v1/recordings",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            recordings = response.json()

            logger.info(f"Fetched {len(recordings)} recordings from Cloud")
            return recordings

        except Exception as e:
            logger.warning(f"Failed to fetch recordings from Cloud: {e}")
            return []

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
                f"/api/v1/users/{user_id}/workflows"
            )
            response.raise_for_status()
            result = response.json()

            workflows = result.get("workflows", [])
            logger.info(f"Fetched {len(workflows)} workflows from Cloud")
            return workflows

        except Exception as e:
            logger.warning(f"Failed to fetch workflows from Cloud: {e}")
            return []

    async def delete_workflow(
        self,
        workflow_id: str,
        user_id: str = "default_user"
    ) -> bool:
        """Delete workflow from Cloud Backend

        Args:
            workflow_id: Workflow ID to delete
            user_id: User ID (default: "default_user")

        Returns:
            True if deleted successfully, False otherwise
        """
        logger.info(f"Deleting workflow from Cloud: {workflow_id}")

        try:
            response = await self.client.delete(
                f"/api/v1/workflows/{workflow_id}",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            logger.info(f"Workflow deleted from Cloud: {workflow_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to delete workflow from Cloud: {e}")
            return False

    async def delete_recording(
        self,
        recording_id: str,
        user_id: str = "default_user"
    ) -> bool:
        """Delete recording from Cloud Backend

        Args:
            recording_id: Recording ID to delete
            user_id: User ID

        Returns:
            True if deleted successfully, False otherwise
        """
        logger.info(f"Deleting recording from Cloud: {recording_id}")

        try:
            response = await self.client.delete(
                f"/api/v1/recordings/{recording_id}",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            logger.info(f"Recording deleted from Cloud: {recording_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to delete recording from Cloud: {e}")
            return False

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
                "/api/v1/executions/report",
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

            # Build request headers
            headers = {}
            if self.user_api_key:
                headers["X-Ami-API-Key"] = self.user_api_key
                logger.info(f"Sending request with API key: {self.user_api_key[:10]}...")
            else:
                logger.warning("No user API key set, request will fail")

            response = await self.client.post(
                "/api/v1/recordings/analyze",
                json={
                    "operations": operations,
                    "user_id": user_id
                },
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

            logger.info("Analysis successful")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Analysis failed: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Analysis error: {type(e).__name__}: {e}")
            logger.error(f"Request URL: {self.client.base_url}/api/v1/recordings/analyze")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    # ===== Intent Builder Agent APIs (SSE Streaming) =====

    async def start_intent_builder_session(
        self,
        user_id: str,
        user_query: str,
        task_description: Optional[str] = None,
        workflow_id: Optional[str] = None,
        current_workflow_yaml: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start a new Intent Builder Agent session

        Args:
            user_id: User ID
            user_query: User's query/request
            task_description: Optional additional context
            workflow_id: Optional Workflow ID being modified
            current_workflow_yaml: Current Workflow content for context

        Returns:
            dict: {"session_id": "..."}
        """
        logger.info(f"Starting Intent Builder session for user: {user_id}")

        # Build request headers
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key
            logger.info(f"Sending request with API key: {self.user_api_key[:10]}...")
        else:
            logger.warning("No user API key set, request may fail")

        response = await self.client.post(
            "/api/v1/intent-builder/sessions",
            json={
                "user_id": user_id,
                "user_query": user_query,
                "task_description": task_description,
                "workflow_id": workflow_id,
                "current_workflow_yaml": current_workflow_yaml
            },
            headers=headers
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
            f"/api/v1/intent-builder/sessions/{session_id}/stream"
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
            f"/api/v1/intent-builder/sessions/{session_id}/chat",
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
            f"/api/v1/intent-builder/sessions/{session_id}/state"
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
            f"/api/v1/intent-builder/sessions/{session_id}"
        )
        response.raise_for_status()
        return response.json()

    async def report_workflow_execution_to_proxy(
        self,
        api_proxy_url: str,
        workflow_id: str,
        status: str,
        execution_time_ms: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Report workflow execution to API Proxy for quota tracking

        Args:
            api_proxy_url: API Proxy base URL (e.g., http://localhost:8080)
            workflow_id: Workflow ID
            status: 'success' or 'failed'
            execution_time_ms: Execution time in milliseconds
            metadata: Optional execution metadata

        Returns:
            dict with quota_status:
                {
                    "success": true,
                    "quota_status": {
                        "current_usage": 45,
                        "monthly_limit": 100,
                        "remaining": 55,
                        "percentage_used": 45,
                        "warnings": []
                    }
                }
        """
        if not self.user_api_key:
            logger.warning("No user API key set, cannot report to API Proxy")
            return {"success": False, "error": "No API key"}

        try:
            logger.info(f"Reporting workflow execution to API Proxy: {workflow_id} ({status})")

            # Create separate client for API Proxy
            async with httpx.AsyncClient(
                base_url=api_proxy_url.rstrip('/'),
                headers={"x-api-key": self.user_api_key},
                timeout=10.0  # Short timeout for reporting
            ) as proxy_client:
                response = await proxy_client.post(
                    "/api/stats/workflow-execution",
                    json={
                        "workflow_id": workflow_id,
                        "status": status,
                        "execution_time_ms": execution_time_ms,
                        "metadata": metadata or {}
                    }
                )
                response.raise_for_status()
                result = response.json()

                logger.info(f"Workflow execution reported: {result.get('quota_status', {})}")
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to report to API Proxy: {e.response.status_code} {e.response.text}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Error reporting to API Proxy: {e}")
            return {"success": False, "error": str(e)}

    async def get_quota_status_from_proxy(self, api_proxy_url: str) -> Optional[Dict[str, Any]]:
        """Get user's quota status from API Proxy

        Args:
            api_proxy_url: API Proxy base URL

        Returns:
            dict with quota information or None if failed
        """
        if not self.user_api_key:
            logger.warning("No user API key set, cannot get quota status")
            return None

        try:
            logger.info("Fetching quota status from API Proxy")

            async with httpx.AsyncClient(
                base_url=api_proxy_url.rstrip('/'),
                headers={"x-api-key": self.user_api_key},
                timeout=5.0
            ) as proxy_client:
                response = await proxy_client.get("/api/stats/quota")
                response.raise_for_status()
                result = response.json()

                logger.info(f"Quota status retrieved: {result.get('quota', {})}")
                return result

        except Exception as e:
            logger.error(f"Failed to get quota status: {e}")
            return None

    # ============================================================================
    # Workflow Resource Sync Methods
    # ============================================================================

    async def get_workflow_metadata(
        self,
        workflow_id: str,
        user_id: str = "default_user"
    ) -> Optional[Dict[str, Any]]:
        """Get workflow metadata from Cloud Backend

        Args:
            workflow_id: Workflow ID
            user_id: User ID

        Returns:
            metadata.json content or None if not found
        """
        try:
            logger.info(f"[CloudClient] Getting metadata for workflow {workflow_id}")
            response = await self.client.get(
                f"/api/v1/workflows/{workflow_id}/metadata",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"[CloudClient] Metadata not found for workflow {workflow_id}")
                return None
            logger.error(f"[CloudClient] Failed to get metadata: {e}")
            raise
        except Exception as e:
            logger.error(f"[CloudClient] Failed to get metadata: {e}")
            raise

    async def save_workflow_metadata(
        self,
        workflow_id: str,
        metadata: Dict[str, Any],
        user_id: str = "default_user"
    ) -> bool:
        """Save workflow metadata to Cloud Backend

        Args:
            workflow_id: Workflow ID
            metadata: metadata.json content
            user_id: User ID

        Returns:
            True if successful
        """
        try:
            logger.info(f"[CloudClient] Saving metadata for workflow {workflow_id}")
            response = await self.client.put(
                f"/api/v1/workflows/{workflow_id}/metadata",
                params={"user_id": user_id},
                json=metadata
            )
            response.raise_for_status()
            result = response.json()
            return result.get("success", False)
        except Exception as e:
            logger.error(f"[CloudClient] Failed to save metadata: {e}")
            raise

    async def download_workflow_file(
        self,
        workflow_id: str,
        file_path: str,
        user_id: str = "default_user"
    ) -> bytes:
        """Download a single file from Cloud Backend

        Args:
            workflow_id: Workflow ID
            file_path: Relative path like "extract-daily-link/extraction_script.py"
            user_id: User ID

        Returns:
            File bytes
        """
        try:
            logger.debug(f"[CloudClient] Downloading file {file_path} from workflow {workflow_id}")
            response = await self.client.get(
                f"/api/v1/workflows/{workflow_id}/files",
                params={
                    "user_id": user_id,
                    "path": file_path
                }
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"[CloudClient] Failed to download file {file_path}: {e}")
            raise

    async def upload_workflow_file(
        self,
        workflow_id: str,
        file_path: str,
        content: bytes,
        user_id: str = "default_user"
    ) -> bool:
        """Upload a single file to Cloud Backend

        Args:
            workflow_id: Workflow ID
            file_path: Relative path like "extract-daily-link/extraction_script.py"
            content: File bytes
            user_id: User ID

        Returns:
            True if successful
        """
        try:
            logger.debug(f"[CloudClient] Uploading file {file_path} to workflow {workflow_id} ({len(content)} bytes)")

            # Create multipart form data with file
            files = {
                'file': (file_path.split('/')[-1], content, 'application/octet-stream')
            }

            response = await self.client.put(
                f"/api/v1/workflows/{workflow_id}/files",
                params={
                    "user_id": user_id,
                    "path": file_path
                },
                files=files
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                logger.debug(f"[CloudClient] Uploaded {file_path} ({result.get('size')} bytes)")

            return result.get("success", False)
        except Exception as e:
            logger.error(f"[CloudClient] Failed to upload file {file_path}: {e}")
            raise

    async def upload_execution_log(
        self,
        log_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Upload workflow execution log to Cloud Backend.

        Args:
            log_data: Execution log data from WorkflowHistoryManager.get_run_for_upload()
                Contains: type, task_id, user_id, device_id, workflow_id, workflow_name,
                         meta, logs, workflow_yaml, device_info
            user_id: User ID (required)

        Returns:
            dict: {"success": True, "task_id": "..."}
        """
        try:
            logger.info(f"Uploading execution log: {log_data.get('task_id')}")

            # Build request headers
            headers = {}
            if self.user_api_key:
                headers["X-Ami-API-Key"] = self.user_api_key

            response = await self.client.post(
                "/api/v1/logs/workflow",
                json={
                    "user_id": user_id,
                    **log_data
                },
                headers=headers,
                timeout=30.0  # Reasonable timeout for log upload
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"Execution log uploaded: {result.get('task_id')}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to upload execution log: {e.response.status_code} {e.response.text}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Error uploading execution log: {e}")
            return {"success": False, "error": str(e)}

    async def generate_script(
        self,
        workflow_id: str,
        step_id: str,
        script_type: str,
        page_url: str,
        user_id: str = "default_user",
        dom_data: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Request cloud to generate script for workflow step

        This is used when a script doesn't exist locally. The cloud:
        - Reads step config (data_requirements/task) from workflow YAML
        - Uses dom_data uploaded by client (current page DOM)

        Args:
            workflow_id: Workflow ID
            step_id: Step ID (e.g., "extract-product-list")
            script_type: "scraper" or "browser"
            page_url: Current page URL (for absolute URL conversion)
            user_id: User ID
            dom_data: DOM dictionary - required for both scraper and browser scripts
            api_key: API key for Claude Agent SDK (script generation)

        Returns:
            dict with:
                - success: bool
                - script_path: relative path in workflow (e.g., "step-id/extraction_script.py")
                - script_content: the generated script content
                - turns: number of LLM turns used
                - error: error message if failed
        """
        try:
            logger.info(f"[CloudClient] Requesting script generation: workflow={workflow_id}, step={step_id}, type={script_type}")

            # Build request headers
            # X-Api-Key is for Claude Agent SDK (script generation)
            headers = {"X-User-Id": user_id}
            # Prefer explicit api_key parameter, fallback to instance api_key
            effective_api_key = api_key or self.user_api_key
            if effective_api_key:
                headers["X-Api-Key"] = effective_api_key

            # Build request payload - minimal data, cloud has the rest
            payload = {
                "step_id": step_id,
                "script_type": script_type,
                "page_url": page_url
            }
            # Include dom_data for both scraper and browser scripts
            if dom_data:
                payload["dom_data"] = dom_data

            response = await self.client.post(
                f"/api/v1/workflows/{workflow_id}/generate-script",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                logger.info(f"[CloudClient] Script generated: {result.get('script_path')} (turns={result.get('turns')})")
            else:
                logger.warning(f"[CloudClient] Script generation failed: {result.get('error')}")

            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"[CloudClient] Script generation failed: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"[CloudClient] Script generation error: {e}")
            return {"success": False, "error": str(e)}

    async def generate_script_stream(
        self,
        workflow_id: str,
        step_id: str,
        script_type: str,
        page_url: str,
        user_id: str = "default_user",
        dom_data: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """Request cloud to generate script with SSE streaming progress

        Args:
            workflow_id: Workflow ID
            step_id: Step ID
            script_type: "scraper" or "browser"
            page_url: Current page URL
            user_id: User ID
            dom_data: DOM dictionary
            api_key: API key for Claude Agent SDK
            progress_callback: Async callback for progress updates
                Signature: async def callback(level: str, message: str, data: dict)

        Returns:
            dict with script_path, script_content, turns
        """
        import json

        try:
            logger.info(f"[CloudClient] Requesting script generation (stream): workflow={workflow_id}, step={step_id}, type={script_type}")

            headers = {"X-User-Id": user_id}
            effective_api_key = api_key or self.user_api_key
            if effective_api_key:
                headers["X-Api-Key"] = effective_api_key

            payload = {
                "step_id": step_id,
                "script_type": script_type,
                "page_url": page_url
            }
            if dom_data:
                payload["dom_data"] = dom_data

            # Use streaming request
            async with self.client.stream(
                "POST",
                f"/api/v1/workflows/{workflow_id}/generate-script-stream",
                json=payload,
                headers=headers,
                timeout=300.0  # 5 minutes timeout for script generation
            ) as response:
                response.raise_for_status()

                result = None
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Parse SSE event
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                            event_type = event.get("type")

                            if event_type == "progress":
                                # Forward progress to callback
                                if progress_callback:
                                    await progress_callback(
                                        event.get("level", "info"),
                                        event.get("message", ""),
                                        {
                                            "turn": event.get("turn", 0),
                                            "tool_name": event.get("tool_name")
                                        }
                                    )
                                logger.debug(f"[CloudClient] Progress: {event.get('message')}")

                            elif event_type == "complete":
                                result = {
                                    "success": True,
                                    "script_path": event.get("script_path"),
                                    "script_content": event.get("script_content"),
                                    "turns": event.get("turns", 0)
                                }
                                logger.info(f"[CloudClient] Script generated: {result.get('script_path')} (turns={result.get('turns')})")

                            elif event_type == "error":
                                error_msg = event.get("message", "Unknown error")
                                logger.error(f"[CloudClient] Script generation error: {error_msg}")
                                return {"success": False, "error": error_msg}

                        except json.JSONDecodeError:
                            logger.warning(f"[CloudClient] Failed to parse SSE event: {data_str}")

                    elif line.startswith(": keepalive"):
                        # Ignore keepalive comments
                        pass

                if result:
                    return result
                else:
                    return {"success": False, "error": "No completion event received"}

        except httpx.HTTPStatusError as e:
            # For streaming response, we can't access response.text directly
            error_msg = f"HTTP {e.response.status_code}"
            logger.error(f"[CloudClient] Script generation failed: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"[CloudClient] Script generation error: {e}")
            return {"success": False, "error": str(e)}

    async def upload_diagnostic(
        self,
        diagnostic_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Upload diagnostic package to Cloud Backend.

        Args:
            diagnostic_data: Diagnostic data containing:
                - type: "diagnostic"
                - device_id: Device identifier
                - app_version: App version
                - system_logs: Recent system log entries
                - recent_executions: Recent workflow execution summaries
                - device_info: OS, version, etc.
                - user_description: User's description of the issue (optional)
            user_id: User ID (required)

        Returns:
            dict: {"success": True, "diagnostic_id": "DIAG-..."}
        """
        try:
            logger.info("Uploading diagnostic package...")

            # Build request headers
            headers = {}
            if self.user_api_key:
                headers["X-Ami-API-Key"] = self.user_api_key

            response = await self.client.post(
                "/api/v1/logs/diagnostic",
                json={
                    "user_id": user_id,
                    **diagnostic_data
                },
                headers=headers,
                timeout=60.0  # Longer timeout for diagnostic upload
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"Diagnostic uploaded: {result.get('diagnostic_id')}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to upload diagnostic: {e.response.status_code} {e.response.text}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Error uploading diagnostic: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
