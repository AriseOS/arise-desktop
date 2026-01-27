"""BrowserAgent v4.0 - LLM-based browser interaction agent

Design Change (v4.0):
- Removed script generation and caching
- All interactions executed via EigentStyleBrowserAgent (LLM tool-calling)
- Maintains backward compatibility with v3 input format

Supported Operations:
- navigate: Navigate to a URL
- click: Click on an element
- fill: Fill text into an element
- scroll: Scroll the page
- Tab operations: new_tab, switch_tab, close_tab

Input Format (backward compatible):
- target_url: URL to navigate to
- interaction_steps: List of steps with 'task' descriptions
- user_task: Alternative natural language task description
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class BrowserAgent(BaseStepAgent):
    """BrowserAgent v4.0 - LLM-based browser interaction agent

    Uses EigentStyleBrowserAgent internally for all browser operations.
    Maintains backward compatibility with v3 input format.
    """

    INPUT_SCHEMA = InputSchema(
        description="Browser interaction agent using LLM for intelligent automation",
        fields={
            "target_url": FieldSchema(
                type="str",
                required=False,
                description="URL to navigate to before interaction"
            ),
            "interaction_steps": FieldSchema(
                type="list",
                required=False,
                items_type="dict",
                description="List of interaction steps with 'task' descriptions"
            ),
            "user_task": FieldSchema(
                type="str",
                required=False,
                description="Natural language task description (alternative to interaction_steps)"
            ),
            "max_steps": FieldSchema(
                type="int",
                required=False,
                default=30,
                description="Maximum LLM steps for task execution"
            ),
        },
        examples=[
            {
                "target_url": "https://example.com/login",
                "interaction_steps": [
                    {"task": "Click the login button"},
                    {"task": "Fill username with 'admin'", "text": "admin"}
                ]
            },
            {
                "user_task": "Go to google.com and search for 'Python tutorials'"
            }
        ]
    )

    def __init__(
        self,
        config_service=None,
        metadata: Optional[AgentMetadata] = None
    ):
        if metadata is None:
            metadata = AgentMetadata(
                name="browser_agent",
                description="LLM-based browser interaction agent"
            )
        super().__init__(metadata)

        self.config_service = config_service
        self._eigent_agent = None

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize the agent."""
        try:
            self.is_initialized = True
            logger.info("BrowserAgent initialized (will use EigentStyleBrowserAgent)")
            return True
        except Exception as e:
            logger.error(f"BrowserAgent initialization failed: {e}")
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data."""
        if isinstance(input_data, dict):
            # At least one of these should be present and non-empty
            target_url = input_data.get("target_url")
            has_url = bool(target_url and str(target_url).strip())
            has_steps = bool(input_data.get("interaction_steps"))
            has_task = bool(input_data.get("user_task"))
            result = has_url or has_steps or has_task
            if not result:
                logger.warning(
                    f"BrowserAgent.validate_input failed: "
                    f"target_url={repr(target_url)}, "
                    f"interaction_steps={bool(input_data.get('interaction_steps'))}, "
                    f"user_task={bool(input_data.get('user_task'))}, "
                    f"input_keys={list(input_data.keys())}"
                )
            return result
        if isinstance(input_data, AgentInput):
            return await self.validate_input(input_data.data)
        logger.warning(f"BrowserAgent.validate_input: unknown input type {type(input_data)}")
        return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute browser interactions using EigentStyleBrowserAgent.

        Args:
            input_data: Input data (AgentInput or dict)
            context: Execution context

        Returns:
            AgentOutput with execution result
        """
        if not self.is_initialized:
            return AgentOutput(
                success=False,
                message="BrowserAgent not initialized",
                data={}
            )

        # Parse input
        if isinstance(input_data, AgentInput):
            data = input_data.data
        else:
            data = input_data

        target_url = data.get("target_url")
        interaction_steps = data.get("interaction_steps", [])
        user_task = data.get("user_task")
        max_steps = data.get("max_steps", 30)

        logger.info(f"BrowserAgent executing: url={target_url}, steps={len(interaction_steps)}, user_task={bool(user_task)}")

        try:
            # Build task description for EigentStyleBrowserAgent
            task = self._build_task_description(
                target_url=target_url,
                interaction_steps=interaction_steps,
                user_task=user_task
            )

            # Create and initialize EigentStyleBrowserAgent
            from .eigent_style_browser_agent import EigentStyleBrowserAgent

            self._eigent_agent = EigentStyleBrowserAgent()
            await self._eigent_agent.initialize(context)

            # Execute via EigentStyleBrowserAgent
            eigent_input = AgentInput(
                data={
                    "task": task,
                    "max_steps": max_steps,
                }
            )

            result = await self._eigent_agent.execute(eigent_input, context)

            # Format result for backward compatibility
            return self._format_result(result, target_url, interaction_steps)

        except Exception as e:
            import traceback
            error_msg = f"BrowserAgent execution failed: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())

            return AgentOutput(
                success=False,
                message=error_msg,
                data={"error": str(e)}
            )

    def _build_task_description(
        self,
        target_url: Optional[str],
        interaction_steps: List[Dict],
        user_task: Optional[str]
    ) -> str:
        """Build natural language task description from input.

        Converts structured input (target_url, interaction_steps) into
        a natural language task for EigentStyleBrowserAgent.
        """
        parts = []

        # Context: Workflow environment
        parts.append("You are executing a browser interaction step in a workflow.")
        parts.append("Your job is to perform browser actions and report the result.")
        parts.append("")

        # If user provided a direct task description, use it
        if user_task:
            if target_url:
                parts.append(f"1. Navigate to: {target_url}")
                parts.append(f"2. Then: {user_task}")
            else:
                parts.append(f"Task: {user_task}")
        else:
            # Build from structured input
            if target_url:
                parts.append(f"1. Navigate to: {target_url}")

            if interaction_steps:
                start_idx = 2 if target_url else 1
                parts.append(f"\n{start_idx}. Perform the following steps in order:")
                for i, step in enumerate(interaction_steps, 1):
                    step_desc = self._convert_step_to_description(step, i)
                    parts.append(f"   {step_desc}")

        if len(parts) <= 2:  # Only context lines
            parts.append("Check the current page state.")

        # Critical instructions for workflow integration
        parts.append("\n" + "=" * 50)
        parts.append("IMPORTANT - Workflow context:")
        parts.append("- If you need to extract URLs/links, call browser_get_page_snapshot(include_links=True)")
        parts.append("- Complete all steps before calling 'done'")
        parts.append("")
        parts.append("IMPORTANT - Output format:")
        parts.append("When finished, call the 'done' tool with:")
        parts.append("- success: true/false")
        parts.append("- result: A description of what was accomplished, or any extracted data")
        parts.append("=" * 50)

        return "\n".join(parts)

    def _convert_step_to_description(self, step: Dict, index: int) -> str:
        """Convert a single interaction step to natural language."""
        # Handle legacy format (action_type + parameters)
        if "action_type" in step:
            action_type = step.get("action_type", "")
            if action_type == "click":
                target = step.get("target_element", step.get("task", "the target element"))
                return f"{index}. Click on {target}"
            elif action_type == "fill":
                target = step.get("target_element", "the input field")
                text = step.get("text", step.get("fill_value", ""))
                return f"{index}. Fill '{text}' into {target}"
            elif action_type == "scroll":
                direction = step.get("direction", "down")
                return f"{index}. Scroll {direction}"
            elif action_type == "navigate":
                url = step.get("url", "")
                return f"{index}. Navigate to {url}"
            else:
                return f"{index}. {action_type}: {step}"

        # Handle new format (task description)
        task = step.get("task", "")
        text = step.get("text", "")

        # Handle tab operations
        action = step.get("action")
        if action == "new_tab":
            url = step.get("url", "")
            return f"{index}. Open a new tab and navigate to {url}"
        elif action == "switch_tab":
            tab_index = step.get("tab_index", 0)
            return f"{index}. Switch to tab {tab_index}"
        elif action == "close_tab":
            return f"{index}. Close the current tab"

        # Regular task with optional text
        if text and "fill" in task.lower():
            return f"{index}. {task} (value: '{text}')"
        elif text:
            return f"{index}. {task} with text '{text}'"
        else:
            return f"{index}. {task}"

    def _format_result(
        self,
        result: AgentOutput,
        target_url: Optional[str],
        interaction_steps: List[Dict]
    ) -> AgentOutput:
        """Format EigentStyleBrowserAgent result for backward compatibility."""
        if result.success:
            message = "Browser interactions completed successfully"
            if target_url:
                message = f"Navigated to {target_url} and completed interactions"

            return AgentOutput(
                success=True,
                message=message,
                data={
                    "result": result.data,
                    "steps_executed": len(interaction_steps) if interaction_steps else 1,
                    "current_url": result.data.get("current_url", target_url or ""),
                }
            )
        else:
            return AgentOutput(
                success=False,
                message=result.message,
                data={
                    "error": result.message,
                    "result": result.data,
                }
            )

    async def cleanup(self, context: AgentContext):
        """Cleanup resources."""
        if self._eigent_agent:
            try:
                await self._eigent_agent.cleanup(context)
            except Exception as e:
                logger.warning(f"Failed to cleanup EigentStyleBrowserAgent: {e}")
            self._eigent_agent = None
