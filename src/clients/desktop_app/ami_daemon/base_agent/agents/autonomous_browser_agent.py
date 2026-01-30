"""
Autonomous Browser Agent - Wrapper for EigentStyleBrowserAgent

This agent provides a simplified interface for autonomous browser operations,
delegating to EigentStyleBrowserAgent for the actual implementation.

Replaces the browser-use based implementation with eigent_browser.
"""
import logging
from typing import Any, Dict, Optional

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput

# Import from eigent_browser
from ..tools.eigent_browser.browser_session import HybridBrowserSession
from ..tools.workflow_browser_adapter import WorkflowBrowserSessionInfo

logger = logging.getLogger(__name__)


class AutonomousBrowserAgent(BaseStepAgent):
    """
    Autonomous Browser Agent

    This agent provides autonomous browser operations via natural language instructions.
    It uses EigentStyleBrowserAgent internally for tool-calling based browser automation.

    In workflow, use 'autonomous_browser_agent' type to invoke this agent.
    """

    INPUT_SCHEMA = InputSchema(
        description="Autonomous browser agent that can explore and interact with web pages using natural language instructions",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Task description in natural language"
            ),
            "max_actions": FieldSchema(
                type="int",
                required=False,
                default=20,
                description="Maximum number of actions the agent can take"
            ),
        },
        examples=[
            {
                "task": "Go to google.com and search for 'Python tutorials'",
                "max_actions": 10
            },
            {
                "task": "Navigate to the login page and fill in the credentials",
                "max_actions": 15
            }
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="autonomous_browser_agent",
            description="Autonomous browser agent using eigent_browser for web automation",
            version="2.0.0",
            tags=["browser", "autonomous", "web"],
        )
        super().__init__(metadata)

        # Browser session (HybridBrowserSession)
        self.browser_session: Optional[HybridBrowserSession] = None
        self.session_info: Optional[WorkflowBrowserSessionInfo] = None

        # LLM provider
        self.provider = None

        # Internal EigentStyleBrowserAgent instance
        self._eigent_agent = None

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize Agent"""
        try:
            # Get shared browser session from context
            self.session_info = await context.get_browser_session()
            self.browser_session = self.session_info.session
            logger.info("AutonomousBrowserAgent using shared browser session")

            # Get provider from context
            if context.agent_instance and hasattr(context.agent_instance, 'provider'):
                self.provider = context.agent_instance.provider
                logger.info(f"AutonomousBrowserAgent got provider: {type(self.provider).__name__}")
            else:
                logger.warning("AutonomousBrowserAgent: No provider in context")

            self.is_initialized = True
            return True

        except Exception as e:
            import traceback
            logger.error(f"AutonomousBrowserAgent initialization failed: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input"""
        if isinstance(input_data, (dict, AgentInput)):
            return True
        return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute task using EigentStyleBrowserAgent"""
        try:
            # Parse input
            task = ""
            max_actions = 20

            if isinstance(input_data, AgentInput):
                if input_data.data:
                    task = input_data.data.get("task", "")
                    max_actions = input_data.data.get("max_actions", 20)
            elif isinstance(input_data, dict):
                task = input_data.get("task", "")
                max_actions = input_data.get("max_actions", 20)

            logger.info(f"AutonomousBrowserAgent executing task: {task[:100] if task else 'EMPTY'}...")

            if not task:
                logger.error("Missing task description")
                return AgentOutput(
                    success=False,
                    message="Missing task description",
                    data={}
                )

            # Create and initialize EigentStyleBrowserAgent
            from .eigent_style_browser_agent import EigentStyleBrowserAgent

            self._eigent_agent = EigentStyleBrowserAgent()
            await self._eigent_agent.initialize(context)

            # Prepare input for EigentStyleBrowserAgent
            eigent_input = AgentInput(
                data={
                    "task": task,
                    "max_steps": max_actions,
                }
            )

            logger.info(f"Delegating to EigentStyleBrowserAgent with max_steps={max_actions}")

            # Execute via EigentStyleBrowserAgent
            result = await self._eigent_agent.execute(eigent_input, context)

            logger.info(f"EigentStyleBrowserAgent execution completed, success={result.success}")

            return AgentOutput(
                success=result.success,
                data={
                    "result": result.data,
                    "task": task,
                    "max_actions": max_actions
                },
                message=result.message
            )

        except Exception as e:
            import traceback
            error_msg = f"AutonomousBrowserAgent execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return AgentOutput(
                success=False,
                message=error_msg,
                data={}
            )

    async def cleanup(self, context: AgentContext, close_browser: bool = False):
        """Cleanup resources"""
        # Cleanup internal agent if created
        if self._eigent_agent:
            try:
                await self._eigent_agent.cleanup(context, close_browser=close_browser)
            except Exception as e:
                logger.warning(f"Failed to cleanup internal agent: {e}")
            self._eigent_agent = None

        # Browser session is shared and managed by context
        pass
