"""Workflow execution engine"""

import logging
import uuid
import yaml
from datetime import datetime
from typing import Dict, Optional, Callable, Awaitable

from src.clients.desktop_app.ami_daemon.models.execution import ExecutionTask
from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.browser_manager import BrowserManager
from src.clients.desktop_app.ami_daemon.services.workflow_history import WorkflowHistoryManager
from src.clients.desktop_app.ami_daemon.services.cloud_client import CloudClient

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Execute workflows using BaseAgent"""

    def __init__(
        self,
        storage_manager: StorageManager,
        browser_manager: BrowserManager,
        history_manager: Optional[WorkflowHistoryManager] = None,
        cloud_client: Optional[CloudClient] = None,
        auto_upload_logs: bool = True,
    ):
        """Initialize workflow executor

        Args:
            storage_manager: Storage manager for workflows
            browser_manager: Browser manager for automation
            history_manager: Optional history manager for execution logging
            cloud_client: Optional cloud client for log upload
            auto_upload_logs: Whether to automatically upload logs after execution
        """
        self.storage = storage_manager
        self.browser = browser_manager
        self.history = history_manager
        self.cloud_client = cloud_client
        self.auto_upload_logs = auto_upload_logs
        self.tasks: Dict[str, ExecutionTask] = {}
        self.progress_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
        # Map task_id to (user_id, workflow_id, execution_id) for history tracking
        self._task_context: Dict[str, tuple[str, str, str]] = {}

    def set_progress_callback(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Set callback for progress updates

        Args:
            callback: Async function that takes (task_id, progress_data) and sends updates
        """
        self.progress_callback = callback

    async def execute_workflow_async(
        self,
        user_id: str,
        workflow_id: str,
        inputs: Optional[dict] = None,
        user_api_key: Optional[str] = None
    ) -> Dict[str, str]:
        """Execute workflow asynchronously

        Args:
            user_id: User ID
            workflow_id: Workflow ID (currently uses workflow name as identifier)
            inputs: Input parameters (optional)
            user_api_key: User's Ami API key for LLM calls via API Proxy (optional)

        Returns:
            Dict with task_id and status
        """
        task_id = f"task_{workflow_id}_{uuid.uuid4().hex[:8]}"

        # Load workflow YAML early to extract steps info
        workflow_yaml = self.storage.get_workflow(user_id, workflow_id)

        # Parse YAML to extract steps info immediately
        workflow_dict = yaml.safe_load(workflow_yaml)
        steps_config = workflow_dict.get('steps', [])
        total_steps = len(steps_config)

        # Build steps info for timeline
        steps_info = []
        for i, step in enumerate(steps_config):
            steps_info.append({
                "id": i,
                "name": step.get('name', f'Step {i+1}'),
                "type": step.get('agent_type', 'unknown'),
                "status": "pending"
            })

        # Create task with steps info
        task = ExecutionTask(
            task_id=task_id,
            workflow_name=workflow_id,
            user_id=user_id,
            status="running",
            progress=0,
            current_step=-1,  # -1 means not started yet
            total_steps=total_steps,
            message="Initializing workflow...",
            started_at=datetime.now(),
            steps=steps_info
        )
        self.tasks[task_id] = task

        # Create history run if history manager is available
        execution_id = None
        if self.history:
            try:
                execution_id = self.history.create_run(
                    user_id=user_id,
                    workflow_id=workflow_id,
                    workflow_name=workflow_id,
                    workflow_yaml=workflow_yaml,
                    total_steps=total_steps,
                )
                # Store context for history tracking: (user_id, workflow_id, execution_id)
                self._task_context[task_id] = (user_id, workflow_id, execution_id)
                logger.info(f"Created history run {execution_id} for task {task_id}")
            except Exception as e:
                logger.error(f"Failed to create history run: {e}")

        # Send initial progress update immediately
        await self._send_progress_update(task_id, {
            "type": "progress_update",
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "current_step": -1,
            "total_steps": total_steps,
            "steps": steps_info,
            "message": "Initializing workflow...",
            "timestamp": datetime.now().isoformat()
        })

        # Execute in background
        import asyncio
        asyncio.create_task(
            self._execute_workflow(task_id, user_id, workflow_yaml, inputs, user_api_key)
        )

        return {"task_id": task_id, "status": "running"}

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Get task execution status"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        # Ensure result is JSON-serializable
        result_data = None
        if task.result is not None:
            if isinstance(task.result, dict):
                result_data = task.result
            else:
                # Convert non-dict results to dict
                result_data = {"value": str(task.result)}

        return {
            "task_id": task.task_id,
            "status": task.status,
            "progress": task.progress,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "message": task.message,
            "result": result_data,
            "error": task.error,
            "steps": task.steps  # Include steps info
        }

    async def _execute_workflow(
        self,
        task_id: str,
        user_id: str,
        workflow_yaml: str,
        inputs: Optional[dict],
        user_api_key: Optional[str] = None
    ):
        """Internal execution logic (runs in background)"""
        task = self.tasks[task_id]

        try:
            # Parse YAML
            workflow_dict = yaml.safe_load(workflow_yaml)

            # Use the actual workflow name for script organization
            if 'name' not in workflow_dict:
                workflow_dict['name'] = task.workflow_name

            # Use steps_info from task (already built in execute_workflow_async)
            steps_info = task.steps

            # Create BaseAgent
            from src.clients.desktop_app.ami_daemon.base_app.base_app.base_agent.core.base_agent import BaseAgent
            from src.clients.desktop_app.ami_daemon.base_app.base_app.base_agent.core.schemas import Workflow
            from src.clients.desktop_app.ami_daemon.core.config_service import get_config
            import logging
            logger = logging.getLogger(__name__)

            # Get config service for BaseAgent
            config_service = get_config()

            # Start browser through BrowserManager before creating BaseAgent
            logger.info(f"Starting browser for workflow {task_id}...")
            try:
                browser_result = await self.browser.start_browser_for_workflow(
                    workflow_id=task_id,
                    headless=False  # Show browser during workflow execution
                )
                logger.info(f"✅ Browser started for workflow: {browser_result}")
            except Exception as e:
                logger.error(f"Failed to start browser for workflow: {e}")
                raise

            # Build provider config - only if user provides API key
            provider_config = None
            if user_api_key:
                # User provided API key - use API Proxy
                llm_provider = config_service.get('llm.provider', 'anthropic')
                llm_model = config_service.get('llm.model', 'claude-3-5-sonnet-20241022')
                proxy_url = config_service.get('llm.proxy_url', 'https://api.ariseos.com/api')

                provider_config = {
                    'type': llm_provider,
                    'model_name': llm_model,
                    'api_key': user_api_key,
                    'base_url': proxy_url
                }
                logger.info(f"Using user API key with API Proxy: {proxy_url}")
            else:
                # No user API key - let BaseAgent auto-load from config_service
                logger.info("No user API key provided, BaseAgent will use config_service defaults")

            agent = BaseAgent(
                user_id=user_id,
                config_service=config_service,
                provider_config=provider_config,
                browser_manager=self.browser,  # Pass BrowserManager reference
                browser_session_id=f"workflow_{task_id}"  # Specify session ID
            )

            # Convert to Workflow object
            workflow = Workflow(**workflow_dict)

            # Set up progress callback to track step execution
            step_start_times = {}

            # Get context for history logging: (user_id, workflow_id, execution_id)
            history_context = self._task_context.get(task_id)

            async def step_progress_callback(step_index: int, step_name: str, step_status: str, step_result=None):
                """Callback for step progress updates"""
                task.current_step = step_index
                task.progress = int(((step_index + 1) / task.total_steps) * 100) if task.total_steps > 0 else 0

                # Calculate step duration if completed
                step_duration = None
                step_duration_ms = None
                if step_status == "completed" and step_index in step_start_times:
                    step_duration = (datetime.now() - step_start_times[step_index]).total_seconds()
                    step_duration_ms = int(step_duration * 1000)
                elif step_status == "in_progress":
                    step_start_times[step_index] = datetime.now()

                # Update steps_info with current step status
                for i, step in enumerate(steps_info):
                    if i < step_index:
                        step["status"] = "completed"
                    elif i == step_index:
                        step["status"] = step_status
                        if step_duration is not None:
                            step["duration"] = step_duration
                    else:
                        step["status"] = "pending"

                # Log to workflow history (not to app.log)
                if history_context and self.history:
                    try:
                        ctx_user_id, ctx_workflow_id, ctx_execution_id = history_context
                        # Get step type from steps_info
                        step_type = steps_info[step_index].get("type", "unknown") if step_index < len(steps_info) else "unknown"
                        self.history.log_step(
                            user_id=ctx_user_id,
                            workflow_id=ctx_workflow_id,
                            execution_id=ctx_execution_id,
                            step_index=step_index,
                            action=step_type,
                            status=step_status,
                            target=step_name,
                            duration_ms=step_duration_ms,
                            message=f"Step {step_index + 1}: {step_name}",
                            metadata={"result": str(step_result)[:500] if step_result else None},
                        )
                    except Exception as e:
                        logger.error(f"Failed to log step to history: {e}")

                await self._send_progress_update(task_id, {
                    "type": "progress_update",
                    "task_id": task_id,
                    "status": "running",
                    "progress": task.progress,
                    "current_step": step_index,
                    "total_steps": task.total_steps,
                    "steps": steps_info,  # Send complete steps list
                    "step_info": {
                        "name": step_name,
                        "status": step_status,
                        "result": str(step_result) if step_result else None,
                        "duration": step_duration
                    },
                    "message": f"Step {step_index + 1}/{task.total_steps}: {step_name}",
                    "timestamp": datetime.now().isoformat()
                })

            async def log_callback(level: str, message: str, metadata: dict = None):
                """Callback for detailed execution logs"""
                await self._send_progress_update(task_id, {
                    "type": "progress_update",
                    "task_id": task_id,
                    "status": "running",
                    "progress": task.progress,
                    "current_step": task.current_step,
                    "total_steps": task.total_steps,
                    "log": {
                        "level": level,
                        "message": message,
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "metadata": metadata or {}
                    },
                    "timestamp": datetime.now().isoformat()
                })

            # Execute workflow with real-time callbacks
            result = await agent.run_workflow(
                workflow,
                input_data=inputs or {},
                step_callback=step_progress_callback,
                log_callback=log_callback
            )

            # Update task
            task.status = "completed" if result.success else "failed"
            task.progress = 100
            task.completed_at = datetime.now()
            task.result = result.final_result
            task.error = result.error if not result.success else None
            task.message = "Execution completed" if result.success else f"Failed: {result.error}"

            # Send final progress update (include workflow_yaml for feedback context)
            await self._send_progress_update(task_id, {
                "type": "progress_update",
                "task_id": task_id,
                "status": task.status,
                "progress": 100,
                "current_step": task.total_steps - 1,  # Last step index (0-based)
                "total_steps": task.total_steps,
                "message": task.message,
                "result": {
                    **(task.result if isinstance(task.result, dict) else {"value": task.result}),
                    "workflow_yaml": workflow_yaml,  # Include workflow YAML for feedback system
                    "workflow_name": task.workflow_name,
                    "steps": task.steps  # Include steps info for scraper step lookup
                },
                "error": task.error,
                "timestamp": datetime.now().isoformat()
            })

            # Send completion log to Execution Logs
            if result.success:
                await log_callback(
                    "success",
                    f"✅ Workflow completed successfully",
                    {"result": task.result}
                )
            else:
                await log_callback(
                    "error",
                    f"❌ Workflow failed: {result.error}",
                    {"error": result.error}
                )

            # Save result
            execution_id = str(uuid.uuid4())
            self.storage.save_execution_result(
                user_id,
                task.workflow_name,
                execution_id,
                {
                    "task_id": task_id,
                    "status": task.status,
                    "result": task.result,
                    "error": task.error,
                    "started_at": task.started_at.isoformat(),
                    "completed_at": task.completed_at.isoformat()
                }
            )

            # Update workflow history status
            if history_context and self.history:
                try:
                    ctx_user_id, ctx_workflow_id, ctx_execution_id = history_context
                    steps_completed = sum(1 for s in steps_info if s.get("status") == "completed")
                    self.history.update_run_status(
                        user_id=ctx_user_id,
                        workflow_id=ctx_workflow_id,
                        execution_id=ctx_execution_id,
                        status=task.status,
                        steps_completed=steps_completed,
                        error_summary=task.error,
                    )

                    # Auto-upload execution log to cloud
                    if self.auto_upload_logs and self.cloud_client:
                        await self._upload_execution_log(
                            ctx_user_id, ctx_workflow_id, ctx_execution_id
                        )
                except Exception as e:
                    logger.error(f"Failed to update history run status: {e}")

        except Exception as e:
            task.status = "failed"
            task.progress = 0
            task.error = str(e)
            task.message = f"Execution failed: {e}"
            task.completed_at = datetime.now()

            # Update workflow history with failure
            if history_context and self.history:
                try:
                    ctx_user_id, ctx_workflow_id, ctx_execution_id = history_context
                    steps_completed = sum(1 for s in steps_info if s.get("status") == "completed")
                    self.history.update_run_status(
                        user_id=ctx_user_id,
                        workflow_id=ctx_workflow_id,
                        execution_id=ctx_execution_id,
                        status="failed",
                        steps_completed=steps_completed,
                        error_summary=str(e),
                    )

                    # Auto-upload execution log to cloud (even for failures)
                    if self.auto_upload_logs and self.cloud_client:
                        await self._upload_execution_log(
                            ctx_user_id, ctx_workflow_id, ctx_execution_id
                        )
                except Exception as he:
                    logger.error(f"Failed to update history run status: {he}")

            # Send error progress update (include workflow_yaml for feedback context)
            await self._send_progress_update(task_id, {
                "type": "progress_update",
                "task_id": task_id,
                "status": "failed",
                "progress": 0,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "message": task.message,
                "result": {
                    "workflow_yaml": workflow_yaml,  # Include workflow YAML for feedback system
                    "workflow_name": task.workflow_name,
                    "steps": task.steps  # Include steps info for scraper step lookup
                },
                "error": task.error,
                "timestamp": datetime.now().isoformat()
            })

    async def _send_progress_update(self, task_id: str, data: dict):
        """Send progress update via callback if set"""
        if self.progress_callback:
            try:
                await self.progress_callback(task_id, data)
            except Exception as e:
                # Log error but don't fail execution
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send progress update: {e}")

    async def _upload_execution_log(
        self, user_id: str, workflow_id: str, execution_id: str
    ):
        """Upload execution log to cloud (fire-and-forget).

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            execution_id: Execution ID
        """
        if not self.history or not self.cloud_client:
            return

        try:
            # Get log data for upload
            log_data = self.history.get_run_for_upload(user_id, workflow_id, execution_id)
            if not log_data:
                logger.warning(f"No log data found for execution {execution_id}")
                return

            # Upload to cloud
            result = await self.cloud_client.upload_execution_log(log_data, user_id)

            if result.get("success"):
                # Mark as uploaded in local history
                self.history.mark_as_uploaded(user_id, workflow_id, execution_id)
                logger.info(f"Execution log uploaded: {execution_id}")
            else:
                logger.warning(f"Failed to upload execution log: {result.get('error')}")

        except Exception as e:
            # Fire-and-forget: don't fail the workflow execution
            logger.error(f"Error uploading execution log: {e}")
