"""Workflow execution engine"""

import uuid
import yaml
from datetime import datetime
from typing import Dict, Optional, Callable, Awaitable

from src.app_backend.models.execution import ExecutionTask
from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.services.browser_manager import BrowserManager


class WorkflowExecutor:
    """Execute workflows using BaseAgent"""

    def __init__(
        self,
        storage_manager: StorageManager,
        browser_manager: BrowserManager
    ):
        """Initialize workflow executor"""
        self.storage = storage_manager
        self.browser = browser_manager
        self.tasks: Dict[str, ExecutionTask] = {}
        self.progress_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

    def set_progress_callback(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Set callback for progress updates

        Args:
            callback: Async function that takes (task_id, progress_data) and sends updates
        """
        self.progress_callback = callback

    async def execute_workflow_async(
        self,
        user_id: str,
        workflow_name: str,
        inputs: Optional[dict] = None
    ) -> Dict[str, str]:
        """Execute workflow asynchronously

        Args:
            user_id: User ID
            workflow_name: Workflow name
            inputs: Input parameters (optional)

        Returns:
            Dict with task_id and status
        """
        task_id = f"task_{workflow_name}_{uuid.uuid4().hex[:8]}"

        # Load workflow YAML early to extract steps info
        workflow_yaml = self.storage.get_workflow(user_id, workflow_name)

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
            workflow_name=workflow_name,
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
            self._execute_workflow(task_id, user_id, workflow_yaml, inputs)
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
        inputs: Optional[dict]
    ):
        """Internal execution logic (runs in background)"""
        task = self.tasks[task_id]

        try:
            # Parse YAML
            workflow_dict = yaml.safe_load(workflow_yaml)

            # Use the actual workflow name for script organization
            # Note: browser session will use 'global' (set in AgentContext.browser_session_id)
            if 'name' not in workflow_dict:
                workflow_dict['name'] = task.workflow_name

            # Use steps_info from task (already built in execute_workflow_async)
            steps_info = task.steps

            # Create BaseAgent
            from src.clients.base_app.base_app.base_agent.core.base_agent import BaseAgent
            from src.clients.base_app.base_app.base_agent.core.schemas import Workflow
            from src.app_backend.core.config_service import get_config
            import os

            # Get config service for BaseAgent
            config_service = get_config()

            # Get LLM provider configuration
            llm_provider = config_service.get('llm.provider', 'anthropic')
            llm_model = config_service.get('llm.model', 'claude-3-5-sonnet-20241022')

            # Get API key from environment
            if llm_provider == 'anthropic':
                api_key = os.environ.get('ANTHROPIC_API_KEY')
            else:
                api_key = os.environ.get('OPENAI_API_KEY')

            # Build provider config
            provider_config = {
                'type': llm_provider,
                'model_name': llm_model,
                'api_key': api_key
            }

            agent = BaseAgent(
                user_id=user_id,
                config_service=config_service,
                provider_config=provider_config
            )

            # Convert to Workflow object
            workflow = Workflow(**workflow_dict)

            # Set up progress callback to track step execution
            step_start_times = {}

            async def step_progress_callback(step_index: int, step_name: str, step_status: str, step_result=None):
                """Callback for step progress updates"""
                task.current_step = step_index
                task.progress = int(((step_index + 1) / task.total_steps) * 100) if task.total_steps > 0 else 0

                # Calculate step duration if completed
                step_duration = None
                if step_status == "completed" and step_index in step_start_times:
                    step_duration = (datetime.now() - step_start_times[step_index]).total_seconds()
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

            # Execute workflow with real-time step callback
            result = await agent.run_workflow(
                workflow,
                input_data=inputs or {},
                step_callback=step_progress_callback
            )

            # Update task
            task.status = "completed" if result.success else "failed"
            task.progress = 100
            task.completed_at = datetime.now()
            task.result = result.final_result
            task.error = result.error if not result.success else None
            task.message = "Execution completed" if result.success else f"Failed: {result.error}"

            # Send final progress update
            await self._send_progress_update(task_id, {
                "type": "progress_update",
                "task_id": task_id,
                "status": task.status,
                "progress": 100,
                "current_step": task.total_steps,
                "total_steps": task.total_steps,
                "message": task.message,
                "result": task.result,
                "error": task.error,
                "timestamp": datetime.now().isoformat()
            })

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

        except Exception as e:
            task.status = "failed"
            task.progress = 0
            task.error = str(e)
            task.message = f"Execution failed: {e}"
            task.completed_at = datetime.now()

            # Send error progress update
            await self._send_progress_update(task_id, {
                "type": "progress_update",
                "task_id": task_id,
                "status": "failed",
                "progress": 0,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "message": task.message,
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
