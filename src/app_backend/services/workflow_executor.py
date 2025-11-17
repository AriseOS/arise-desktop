"""Workflow execution engine"""

import uuid
import yaml
from datetime import datetime
from typing import Dict, Optional

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

        # Create task
        task = ExecutionTask(
            task_id=task_id,
            workflow_name=workflow_name,
            user_id=user_id,
            status="running",
            progress=0,
            current_step=0,
            total_steps=0,
            message="Starting execution",
            started_at=datetime.now()
        )
        self.tasks[task_id] = task

        # Load workflow YAML
        workflow_yaml = self.storage.get_workflow(user_id, workflow_name)

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
            "error": task.error
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

            # Get total steps
            task.total_steps = len(workflow_dict.get('steps', []))

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

            # Execute workflow
            result = await agent.run_workflow(workflow, input_data=inputs or {})

            # Update task
            task.status = "completed" if result.success else "failed"
            task.progress = 100
            task.completed_at = datetime.now()
            task.result = result.final_result
            task.error = result.error if not result.success else None
            task.message = "Execution completed" if result.success else f"Failed: {result.error}"

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
