"""
Workflow Service - Workflow generation and execution management
"""
import asyncio
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path so we can import from src
backend_dir = Path(__file__).parent
project_root = str(backend_dir.parent.parent.parent.parent)
sys.path.insert(0, project_root)

from storage_service import storage_service
from src.intent_builder.core.metaflow import MetaFlow
from src.intent_builder.generators.workflow_generator import WorkflowGenerator
from src.common.llm import AnthropicProvider

logger = logging.getLogger(__name__)


class WorkflowService:
    """Handles workflow operations: generation, execution, and management"""

    def __init__(self, llm_provider=None):
        """Initialize workflow service

        Args:
            llm_provider: LLM provider instance, if None will use AnthropicProvider
        """
        self.llm_provider = llm_provider or AnthropicProvider()
        self.storage = storage_service

    async def generate_workflow(self, user_id: int, session_id: str) -> Dict:
        """Generate workflow from MetaFlow

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            Dict with keys: success, workflow_name, workflow_yaml, overwritten

        Raises:
            ValueError: If metaflow not found or generation fails
        """
        logger.info(f"Generating workflow for session {session_id}")

        # 1. Read metaflow
        metaflow_yaml = self.storage.get_learning_metaflow(user_id, session_id)
        if not metaflow_yaml:
            raise ValueError(f"MetaFlow not found for session: {session_id}")

        # 2. Get session metadata
        session = self.storage.get_learning_session(user_id, session_id)
        if not session:
            raise ValueError(f"Session metadata not found: {session_id}")

        # 3. Parse MetaFlow
        metaflow = MetaFlow.from_yaml(metaflow_yaml)

        # 4. Call WorkflowGenerator
        generator = WorkflowGenerator(self.llm_provider)
        workflow_yaml = await generator.generate(metaflow)

        # 5. Generate workflow name from title
        title = session.get("title", "workflow")
        workflow_name = self._title_to_workflow_name(title)

        # 6. Save workflow
        result = self.storage.save_workflow(
            user_id=user_id,
            workflow_name=workflow_name,
            workflow_yaml=workflow_yaml,
            source_session_id=session_id,
            description=session.get("description", "")
        )

        logger.info(f"Generated workflow '{workflow_name}' for session {session_id}")

        return {
            "success": True,
            "workflow_name": workflow_name,
            "workflow_yaml": workflow_yaml,
            "overwritten": result["overwritten"]
        }

    def _title_to_workflow_name(self, title: str) -> str:
        """Convert title to workflow name

        Args:
            title: Recording title

        Returns:
            workflow_name: lowercase with hyphens, no special chars
        """
        # Convert to lowercase
        name = title.lower()

        # Replace spaces with hyphens
        name = name.replace(" ", "-")

        # Remove special characters (keep letters, numbers, hyphens, underscores, Chinese)
        name = re.sub(r'[^a-z0-9\-_\u4e00-\u9fff]', '', name)

        # Collapse multiple hyphens
        name = re.sub(r'-+', '-', name)

        # Remove leading/trailing hyphens
        name = name.strip('-')

        # Limit length
        name = name[:100]

        return name or "untitled-workflow"

    async def execute_workflow(self, user_id: int, workflow_name: str) -> Dict:
        """Execute a workflow asynchronously

        Args:
            user_id: User ID
            workflow_name: Workflow name to execute

        Returns:
            Dict with keys: success, task_id, workflow_name, status, started_at

        Raises:
            ValueError: If workflow not found
        """
        logger.info(f"Executing workflow '{workflow_name}' for user {user_id}")

        # 1. Read workflow
        workflow_data = self.storage.get_workflow(user_id, workflow_name)
        if not workflow_data:
            raise ValueError(f"Workflow not found: {workflow_name}")

        # 2. Generate task_id
        task_id = f"task_{workflow_name}_{uuid.uuid4().hex[:8]}"

        # 3. Create initial execution record
        execution_data = {
            "task_id": task_id,
            "workflow_name": workflow_name,
            "status": "running",
            "progress": 0,
            "current_step": None,
            "result": None,
            "execution_time_ms": None,
            "error_message": None,
            "failed_step": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None
        }
        self.storage.save_execution(user_id, workflow_name, task_id, execution_data)

        # 4. Update workflow execution statistics
        self.storage.update_workflow_execution_stats(user_id, workflow_name)

        # 5. Start async execution
        asyncio.create_task(
            self._run_workflow_async(user_id, workflow_name, task_id, workflow_data["workflow_yaml"])
        )

        logger.info(f"Started workflow execution with task_id: {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "workflow_name": workflow_name,
            "status": "running",
            "started_at": execution_data["started_at"]
        }

    async def _run_workflow_async(
        self,
        user_id: int,
        workflow_name: str,
        task_id: str,
        workflow_yaml: str
    ):
        """Execute workflow in background (async task)

        Args:
            user_id: User ID
            workflow_name: Workflow name
            task_id: Task ID for tracking
            workflow_yaml: Workflow YAML content
        """
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"Running workflow async: task_id={task_id}")

            # Import BaseAgent components
            from src.base_app.base_app.base_agent.core.base_agent import BaseAgent
            from src.base_app.base_app.base_agent.core.schemas import AgentConfig
            from src.base_app.base_app.server.core.config_service import ConfigService
            import yaml

            # Initialize config service
            config_service = ConfigService()

            # Get LLM config
            llm_provider = config_service.get('agent.llm.provider', 'openai')
            llm_model = config_service.get('agent.llm.model', 'gpt-4o')
            api_key = config_service.get('agent.llm.api_key')

            # Create BaseAgent config
            agent_config = AgentConfig(
                name=f"workflow-{workflow_name}",
                llm_provider=llm_provider,
                llm_model=llm_model,
                api_key=api_key or ""
            )

            # Create provider config
            provider_config = {
                'type': llm_provider,
                'api_key': api_key if api_key else None,
                'model_name': llm_model
            }

            # Create BaseAgent instance with user_id for memory isolation
            base_agent = BaseAgent(
                agent_config,
                config_service=config_service,
                provider_config=provider_config,
                user_id=str(user_id)
            )

            # Initialize BaseAgent
            await base_agent.initialize()

            # Load workflow using workflow_loader
            from src.base_app.base_app.base_agent.workflows.workflow_loader import load_workflow
            import tempfile
            
            # Write workflow YAML to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(workflow_yaml)
                temp_workflow_path = f.name
            
            try:
                # Load workflow from the temporary file
                workflow = load_workflow(temp_workflow_path)
                
                # Force workflow to use global browser session
                original_workflow_name = workflow.name
                workflow.name = "global"  # Force use global session
                logger.info(f"Forcing workflow '{original_workflow_name}' to use global browser session")
            finally:
                # Clean up temporary file
                import os
                if os.path.exists(temp_workflow_path):
                    os.unlink(temp_workflow_path)

            # Execute workflow
            result = await base_agent.run_workflow(
                workflow=workflow,
                input_data={}
            )

            # Calculate execution time
            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Update execution record - success
            execution_data = self.storage.get_execution(user_id, workflow_name, task_id)
            execution_data.update({
                "status": "completed",
                "progress": 100,
                "result": {
                    "success": result.success,
                    "data": str(result.final_result) if hasattr(result, 'final_result') else None
                },
                "execution_time_ms": execution_time_ms,
                "completed_at": end_time.isoformat()
            })
            self.storage.save_execution(user_id, workflow_name, task_id, execution_data)

            logger.info(f"Workflow execution completed: task_id={task_id}, success={result.success}")

            # Cleanup old executions (keep only 50 most recent)
            self.storage.cleanup_old_executions(user_id, workflow_name, keep_count=50)

        except Exception as e:
            logger.error(f"Workflow execution failed: task_id={task_id}, error={str(e)}")

            # Update execution record - failed
            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            execution_data = self.storage.get_execution(user_id, workflow_name, task_id)
            execution_data.update({
                "status": "failed",
                "error_message": str(e),
                "execution_time_ms": execution_time_ms,
                "completed_at": end_time.isoformat()
            })
            self.storage.save_execution(user_id, workflow_name, task_id, execution_data)

    def get_execution_status(self, user_id: int, task_id: str, workflow_name: str = None) -> Optional[Dict]:
        """Get execution status by task_id

        Args:
            user_id: User ID
            task_id: Task ID
            workflow_name: Optional workflow name (if known, for faster lookup)

        Returns:
            Execution data dict or None if not found
        """
        if workflow_name:
            return self.storage.get_execution(user_id, workflow_name, task_id)

        # If workflow_name not provided, search all workflows
        workflows = self.storage.list_workflows(user_id)
        for workflow in workflows:
            execution = self.storage.get_execution(user_id, workflow["workflow_name"], task_id)
            if execution:
                return execution

        return None

    def list_executions(self, user_id: int, workflow_name: str, limit: int = 50) -> List[Dict]:
        """List execution history for a workflow

        Args:
            user_id: User ID
            workflow_name: Workflow name
            limit: Maximum number of executions to return

        Returns:
            List of execution data dicts
        """
        return self.storage.list_executions(user_id, workflow_name, limit)

    def get_workflow(self, user_id: int, workflow_name: str) -> Optional[Dict]:
        """Get workflow details

        Args:
            user_id: User ID
            workflow_name: Workflow name

        Returns:
            Workflow data dict or None if not found
        """
        return self.storage.get_workflow(user_id, workflow_name)

    def list_workflows(self, user_id: int) -> List[Dict]:
        """List all workflows for a user

        Args:
            user_id: User ID

        Returns:
            List of workflow metadata dicts
        """
        return self.storage.list_workflows(user_id)

    def delete_workflow(self, user_id: int, workflow_name: str) -> bool:
        """Delete a workflow

        Args:
            user_id: User ID
            workflow_name: Workflow name

        Returns:
            True if deleted, False if not found
        """
        return self.storage.delete_workflow(user_id, workflow_name)


# Global instance
workflow_service = WorkflowService()
