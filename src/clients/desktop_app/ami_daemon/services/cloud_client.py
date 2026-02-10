"""Cloud Backend API client"""
import logging
import os
import httpx
from typing import List, Optional, Dict, Any, Callable, Awaitable

logger = logging.getLogger(__name__)


def _get_proxy_from_env() -> Optional[str]:
    """Get proxy from environment variables only (ignore system proxy settings).

    This explicitly reads from environment variables and ignores system-level
    proxy settings (e.g., macOS System Preferences) to ensure predictable behavior.

    Returns:
        Proxy URL string or None if not set
    """
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )


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
        # Note: We explicitly get proxy from env vars only, ignoring system proxy
        # settings (e.g., Clash modifying macOS System Preferences)
        proxy = _get_proxy_from_env()
        if proxy:
            logger.info(f"Using proxy from environment: {proxy}")

        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers=headers,
            timeout=None,  # No timeout for long-running operations
            proxy=proxy,  # None disables auto-detection, explicit URL enables proxy
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
                timeout=10.0,  # Short timeout for reporting
                proxy=_get_proxy_from_env(),
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
                timeout=5.0,
                proxy=_get_proxy_from_env(),
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

    # ============================================================================
    # Tavily API Methods
    # ============================================================================

    async def tavily_search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        topic: Optional[str] = None,
        days: Optional[int] = None,
        time_range: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_answer: Optional[bool] = None,
        include_raw_content: Optional[bool] = None,
        include_images: Optional[bool] = None,
        country: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call Cloud Backend Tavily search API

        Args:
            query: Search query
            max_results: Number of results to return (default: 10)
            search_depth: "basic", "advanced", "fast", "ultra-fast"
            topic: "general", "news", "finance"
            days: Limit to past N days
            time_range: "day", "week", "month", "year"
            include_domains: Only include results from these domains
            exclude_domains: Exclude results from these domains
            include_answer: Include LLM-generated answer
            include_raw_content: Include raw page content
            include_images: Include image results
            country: Country code for localized results

        Returns:
            dict with:
                - results: List of search results
                - query: Original query
                - total: Number of results
                - answer: (optional) LLM-generated answer
                - images: (optional) Image results
        """
        if not self.user_api_key:
            raise ValueError("User API key is required for Tavily search")

        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }

        # Optional parameters - only include if set
        if topic:
            payload["topic"] = topic
        if days is not None:
            payload["days"] = days
        if time_range:
            payload["time_range"] = time_range
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        if include_answer is not None:
            payload["include_answer"] = include_answer
        if include_raw_content is not None:
            payload["include_raw_content"] = include_raw_content
        if include_images is not None:
            payload["include_images"] = include_images
        if country:
            payload["country"] = country

        logger.info(f"[CloudClient] Tavily search: {query[:50]}... (depth={search_depth}, topic={topic}, days={days})")

        response = await self.client.post(
            "/api/v1/tavily/search",
            json=payload,
            headers={"X-Ami-API-Key": self.user_api_key},
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()

    async def tavily_research(
        self,
        query: str,
        stream: bool = False,
        model: Optional[str] = None,
        citation_format: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Call Cloud Backend Tavily research API

        Args:
            query: Research topic
            stream: Enable streaming for progress updates
            model: "mini", "pro", "auto"
            citation_format: "numbered", "mla", "apa", "chicago"
            progress_callback: Async callback for progress updates (if streaming)
                Signature: async def callback(level: str, message: str, data: dict)

        Returns:
            dict with:
                - report/content: Research report content
                - sources: List of sources used
        """
        import json as json_lib

        if not self.user_api_key:
            raise ValueError("User API key is required for Tavily research")

        payload = {
            "query": query,
            "stream": stream,
        }

        # Optional parameters
        if model:
            payload["model"] = model
        if citation_format:
            payload["citation_format"] = citation_format

        logger.info(f"[CloudClient] Tavily research: {query[:50]}... (stream={stream}, model={model})")

        if stream:
            # Streaming response
            result = {"report": "", "sources": []}
            async with self.client.stream(
                "POST",
                "/api/v1/tavily/research",
                json=payload,
                headers={"X-Ami-API-Key": self.user_api_key},
                timeout=300.0
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Ignore SSE comments (keepalive, etc.)
                    if line.startswith(":"):
                        continue

                    # Parse SSE event
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json_lib.loads(data_str)
                            event_type = event.get("type")

                            if event_type == "progress" and progress_callback:
                                await progress_callback(
                                    event.get("level", "info"),
                                    event.get("message", ""),
                                    event.get("data", {})
                                )
                            elif event_type == "error":
                                error_msg = event.get("message", "Unknown error")
                                logger.error(f"[CloudClient] Tavily research error: {error_msg}")
                                raise Exception(f"Tavily research failed: {error_msg}")
                            elif event_type == "result":
                                result = event.get("data", result)
                            elif event_type == "complete":
                                if "report" in event:
                                    result["report"] = event["report"]
                                if "sources" in event:
                                    result["sources"] = event["sources"]
                                if "data" in event:
                                    result = event.get("data", result)

                        except json_lib.JSONDecodeError:
                            # Raw text chunk - append to report
                            result["report"] += data_str

            return result
        else:
            # Non-streaming response
            response = await self.client.post(
                "/api/v1/tavily/research",
                json=payload,
                headers={"X-Ami-API-Key": self.user_api_key},
                timeout=300.0
            )
            response.raise_for_status()
            return response.json()

    # ============================================================================
    # Memory API Methods
    # ============================================================================

    async def add_to_memory(
        self,
        user_id: str,
        recording_id: Optional[str] = None,
        operations: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        generate_embeddings: bool = True
    ) -> Dict[str, Any]:
        """Add recording to user's workflow memory

        Args:
            user_id: User ID
            recording_id: Recording ID to load operations from (optional)
            operations: Direct operations array (optional)
            session_id: Session identifier (optional)
            generate_embeddings: Whether to generate embeddings for semantic search

        Returns:
            dict with:
                - success: bool
                - states_added: int
                - states_merged: int
                - page_instances_added: int
                - intent_sequences_added: int
                - actions_added: int
                - processing_time_ms: int
        """
        if not recording_id and not operations:
            raise ValueError("Either recording_id or operations must be provided")

        payload = {
            "user_id": user_id,
            "generate_embeddings": generate_embeddings,
        }
        if recording_id:
            payload["recording_id"] = recording_id
        if operations:
            payload["operations"] = operations
        if session_id:
            payload["session_id"] = session_id

        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key

        logger.info(f"[CloudClient] Adding to memory for user {user_id}")

        response = await self.client.post(
            "/api/v1/memory/add",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Memory add result: {result.get('states_added')} added, "
                   f"{result.get('states_merged')} merged")
        return result

    async def query_memory(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
        min_score: float = 0.5,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query user's workflow memory using natural language

        The system uses a unified query interface that supports:
        - Task queries: Complete workflow retrieval (default)
        - Navigation queries: Find path between two states
        - Action queries: Find available actions in current state

        Args:
            user_id: User ID
            query: Natural language query describing the task
            top_k: Number of results to return (default: 3)
            min_score: Minimum similarity score (0.0-1.0) - currently unused by server
            domain: Filter by domain (optional) - currently unused by server

        Returns:
            dict with:
                - success: bool
                - query_type: "task" | "navigation" | "action"
                - states: list of State dicts (for task/navigation)
                - actions: list of Action dicts (for task/navigation)
                - intent_sequences: list (for action queries)
                - cognitive_phrase: dict (for task queries, if found)
                - execution_plan: list (for task queries, if found)
                - metadata: dict with query metadata
        """
        if not self.user_api_key:
            raise ValueError("User API key is required for memory query")

        payload = {
            "user_id": user_id,
            "target": query,
            "top_k": top_k,
        }

        logger.info(f"[CloudClient] Querying memory for user {user_id}: {query[:50]}...")

        response = await self.client.post(
            "/api/v1/memory/query",
            json=payload,
            headers={"X-Ami-API-Key": self.user_api_key}
        )
        response.raise_for_status()
        result = response.json()

        query_type = result.get('query_type', 'unknown')
        states_count = len(result.get('states', []))
        actions_count = len(result.get('actions', []))
        logger.info(f"[CloudClient] Memory query result: type={query_type}, states={states_count}, actions={actions_count}")
        return result

    async def get_memory_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get user's workflow memory statistics

        Args:
            user_id: User ID

        Returns:
            dict with:
                - success: bool
                - user_id: str
                - stats: dict with counts and domains
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key

        logger.info(f"[CloudClient] Getting memory stats for user {user_id}")

        response = await self.client.get(
            "/api/v1/memory/stats",
            params={"user_id": user_id},
            headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def clear_memory(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Clear user's workflow memory

        Args:
            user_id: User ID

        Returns:
            dict with:
                - success: bool
                - deleted_states: int
                - deleted_actions: int
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key

        logger.info(f"[CloudClient] Clearing memory for user {user_id}")

        response = await self.client.delete(
            "/api/v1/memory",
            params={"user_id": user_id},
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Memory cleared: {result.get('deleted_states')} states, "
                   f"{result.get('deleted_actions')} actions")
        return result

    # ============================================================================
    # CognitivePhrase APIs
    # ============================================================================

    async def list_cognitive_phrases(
        self,
        limit: int = 50,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all cognitive phrases from memory

        Args:
            limit: Maximum number of phrases to return
            user_id: Optional user ID filter

        Returns:
            dict with:
                - success: bool
                - phrases: list of phrase objects
                - total: int
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key
        if user_id:
            headers["X-User-Id"] = user_id

        logger.info(f"[CloudClient] Listing cognitive phrases (limit={limit})")

        response = await self.client.get(
            "/api/v1/memory/phrases",
            params={"limit": limit},
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Found {result.get('total', 0)} cognitive phrases")
        return result

    async def get_cognitive_phrase(
        self,
        phrase_id: str,
        user_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a single cognitive phrase with full details

        Args:
            phrase_id: CognitivePhrase ID
            user_id: User ID for private memory routing
            source: "public" to read from public memory

        Returns:
            dict with:
                - success: bool
                - phrase: phrase object
                - states: list of state objects
                - intent_sequences: list of intent sequence objects
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key
        if user_id:
            headers["X-User-Id"] = user_id

        params = {}
        if source:
            params["source"] = source

        logger.info(f"[CloudClient] Getting cognitive phrase: {phrase_id} (source={source})")

        response = await self.client.get(
            f"/api/v1/memory/phrases/{phrase_id}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def delete_cognitive_phrase(
        self,
        phrase_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a cognitive phrase from memory

        Args:
            phrase_id: CognitivePhrase ID to delete
            user_id: User ID for private memory routing

        Returns:
            dict with:
                - success: bool
                - message: str
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key
        if user_id:
            headers["X-User-Id"] = user_id

        logger.info(f"[CloudClient] Deleting cognitive phrase: {phrase_id}")

        response = await self.client.delete(
            f"/api/v1/memory/phrases/{phrase_id}",
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Cognitive phrase deleted: {phrase_id}")
        return result

    async def list_public_phrases(
        self,
        limit: int = 50,
        sort: str = "popular",
    ) -> Dict[str, Any]:
        """List cognitive phrases from public (community) memory.

        Args:
            limit: Maximum number of phrases to return
            sort: Sort order - "popular" or "recent"

        Returns:
            dict with success, phrases list, and total count
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key

        logger.info(f"[CloudClient] Listing public phrases (limit={limit}, sort={sort})")

        response = await self.client.get(
            "/api/v1/memory/phrases/public",
            params={"limit": limit, "sort": sort},
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Found {result.get('total', 0)} public phrases")
        return result

    async def publish_phrase(
        self,
        user_id: str,
        phrase_id: str,
    ) -> Dict[str, Any]:
        """Publish a cognitive phrase from private memory to public memory.

        Args:
            user_id: User who owns the phrase
            phrase_id: CognitivePhrase ID to publish

        Returns:
            dict with success and public_phrase_id
        """
        headers = {}
        if self.user_api_key:
            headers["X-Ami-API-Key"] = self.user_api_key

        logger.info(f"[CloudClient] Publishing phrase {phrase_id} for user {user_id}")

        response = await self.client.post(
            "/api/v1/memory/share",
            json={"user_id": user_id, "phrase_id": phrase_id},
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()

        logger.info(f"[CloudClient] Phrase published: public_id={result.get('public_phrase_id')}")
        return result

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
