"""
EigentBrowserAgent - Browser automation agent ported from CAMEL-AI/Eigent project.

This agent uses LLM-guided browser automation with snapshot-based page understanding.
It follows the ReAct pattern: Observe (snapshot) -> Think (plan) -> Act (execute).
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.eigent_browser.browser_session import HybridBrowserSession
from ..tools.eigent_browser.action_executor import ActionExecutor

logger = logging.getLogger(__name__)


def _get_browser_data_dir() -> Optional[str]:
    """Get browser data directory for Quick Task.

    Uses a separate subdirectory from AMI's main browser_data to avoid
    conflicts when both Quick Task and AMI recording are running.

    Note: Chrome doesn't allow two processes to use the same user_data_dir,
    so Quick Task uses ~/.ami/browser_data_quicktask/ instead of
    ~/.ami/browser_data/ (which is used by AMI's browser-use).
    """
    try:
        from pathlib import Path

        # Use a separate directory for Quick Task to avoid conflicts
        # with AMI's browser-use sessions
        quicktask_path = Path.home() / ".ami" / "browser_data_quicktask"
        quicktask_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Quick Task browser_data: {quicktask_path}")
        return str(quicktask_path)
    except Exception as e:
        logger.warning(f"Failed to create quicktask browser_data dir: {e}")
        return None


# System prompt ported from Eigent's PlaywrightLLMAgent
EIGENT_SYSTEM_PROMPT = """
You are a web automation assistant.

Analyse the page snapshot and create a short high-level plan, then output the FIRST action to start with.

Return a JSON object in *exactly* this shape:
Action format json_object examples:
{
  "plan": ["Step 1", "Step 2"],
  "action": {
    "type": "click",
    "ref": "e1"
  }
}

If task is already complete:
{
  "plan": [],
  "action": {
    "type": "finish",
    "ref": null,
    "summary": "Task was already completed. Summary of what was found..."
  }
}

Available action types:
- 'click': {"type": "click", "ref": "e1"} or {"type": "click", "text": "Button Text"} or {"type": "click", "selector": "button"}
- 'type': {"type": "type", "ref": "e1", "text": "search text"} or {"type": "type", "selector": "input", "text": "search text"}
- 'select': {"type": "select", "ref": "e1", "value": "option"} or {"type": "select", "selector": "select", "value": "option"}
- 'wait': {"type": "wait", "timeout": 2000} or {"type": "wait", "selector": "#element"}
- 'scroll': {"type": "scroll", "direction": "down", "amount": 300}
- 'enter': {"type": "enter", "ref": "e1"} or {"type": "enter", "selector": "input[name=q]"} or {"type": "enter"}
- 'navigate': {"type": "navigate", "url": "https://example.com"}
- 'back': {"type": "back"}
- 'forward': {"type": "forward"}
- 'finish': {"type": "finish", "ref": null, "summary": "task completion summary"}

IMPORTANT:
- For 'click': Use 'ref' from snapshot, or 'text' for visible text, or 'selector' for CSS selectors
- For 'type'/'select': Use 'ref' from snapshot or 'selector' for CSS selectors
- Only use 'ref' values that exist in the snapshot (e.g., ref=e1, ref=e2, etc.)
- Use 'finish' when the task is completed successfully with a summary of what was accomplished
- Use 'enter' to press the Enter key (optionally focus an element first)
- Use 'navigate' to open a new URL before interacting further
- click can choose radio, checkbox...
"""


class EigentBrowserAgent(BaseStepAgent):
    """
    Eigent Browser Agent - LLM-guided browser automation.

    This agent uses the Eigent/CAMEL approach:
    1. Capture page snapshot (DOM -> text representation)
    2. Send snapshot + task to LLM
    3. LLM returns plan + next action
    4. Execute action
    5. Repeat until task is complete or max_steps reached
    """

    INPUT_SCHEMA = InputSchema(
        description="Eigent browser agent that uses LLM-guided browser automation",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Task description in natural language"
            ),
            "start_url": FieldSchema(
                type="str",
                required=False,
                default="https://www.google.com",
                description="Starting URL for the browser"
            ),
            "max_steps": FieldSchema(
                type="int",
                required=False,
                default=15,
                description="Maximum number of steps the agent can take"
            ),
            "headless": FieldSchema(
                type="bool",
                required=False,
                default=False,
                description="Whether to run browser in headless mode"
            ),
        },
        examples=[
            {
                "task": "Go to google.com and search for 'Python tutorials'",
                "start_url": "https://www.google.com",
                "max_steps": 10
            },
            {
                "task": "Navigate to GitHub and find the trending repositories",
                "start_url": "https://github.com",
                "max_steps": 15
            }
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="eigent_browser_agent",
            description="Eigent Browser Agent - LLM-guided browser automation ported from CAMEL-AI/Eigent",
            version="1.0.0",
            tags=["browser", "eigent", "autonomous", "web"],
        )
        super().__init__(metadata)
        self._session: Optional[HybridBrowserSession] = None
        self._llm_client = None
        self._llm_model: str = "claude-sonnet-4-5-20250929"
        self._llm_base_url: Optional[str] = None
        self.action_history: List[Dict[str, Any]] = []
        self._progress_callback: Optional[Callable] = None
        self._current_plan: List[str] = []

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates.

        The callback will be called with (event: str, data: dict).
        Events: plan_generated, step_started, step_completed, step_failed
        """
        self._progress_callback = callback

    async def _notify_progress(self, event: str, data: Dict[str, Any]):
        """Notify progress to callback if set."""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(event, data)
                else:
                    self._progress_callback(event, data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize the agent with LLM client.

        LLM calls go through Claude Relay Service (CRS) when base_url is configured.
        The api_key should be the user's Ami API key (ami_xxxxx format).
        """
        try:
            # Get LLM config from context
            llm_api_key = None
            llm_base_url = None

            if context.agent_instance and hasattr(context.agent_instance, 'provider'):
                provider = context.agent_instance.provider
                if hasattr(provider, 'api_key') and provider.api_key:
                    llm_api_key = provider.api_key
                    logger.info("EigentBrowserAgent got API key from provider")
                if hasattr(provider, 'model_name') and provider.model_name:
                    self._llm_model = provider.model_name
                    logger.info(f"EigentBrowserAgent using model: {self._llm_model}")
                if hasattr(provider, 'base_url') and provider.base_url:
                    llm_base_url = provider.base_url
                    self._llm_base_url = llm_base_url
                    logger.info(f"EigentBrowserAgent using base_url (CRS): {llm_base_url}")

            # Initialize Anthropic client
            import anthropic
            import os

            client_kwargs = {}

            if llm_api_key:
                client_kwargs["api_key"] = llm_api_key

            if llm_base_url:
                # Use CRS (Claude Relay Service) proxy
                client_kwargs["base_url"] = llm_base_url
                logger.info(f"EigentBrowserAgent using CRS proxy: {llm_base_url}")

            if client_kwargs:
                self._llm_client = anthropic.Anthropic(**client_kwargs)
            else:
                # Fallback to env var (ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL)
                self._llm_client = anthropic.Anthropic()

            logger.info(f"EigentBrowserAgent initialized with model: {self._llm_model}")
            self.is_initialized = True
            return True

        except Exception as e:
            import traceback
            logger.error(f"EigentBrowserAgent initialization failed: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data."""
        if isinstance(input_data, (dict, AgentInput)):
            return True
        return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the browser automation task."""
        try:
            # Parse input
            task = ""
            start_url = "https://www.google.com"
            max_steps = 15
            headless = False

            if isinstance(input_data, AgentInput):
                if input_data.data:
                    task = input_data.data.get("task", "")
                    start_url = input_data.data.get("start_url", start_url)
                    max_steps = input_data.data.get("max_steps", max_steps)
                    headless = input_data.data.get("headless", headless)
            elif isinstance(input_data, dict):
                task = input_data.get("task", "")
                start_url = input_data.get("start_url", start_url)
                max_steps = input_data.get("max_steps", max_steps)
                headless = input_data.get("headless", headless)

            if not task:
                return AgentOutput(
                    success=False,
                    message="Missing task description",
                    data={}
                )

            logger.info(f"EigentBrowserAgent executing task: {task[:100]}...")

            # Get browser data directory for login state persistence
            browser_data_dir = _get_browser_data_dir()
            if browser_data_dir:
                logger.info(f"EigentBrowserAgent using browser_data: {browser_data_dir}")
            else:
                logger.warning("EigentBrowserAgent: No browser_data_dir, login state won't persist")

            # Initialize browser session with user_data_dir for login state persistence
            self._session = HybridBrowserSession(
                headless=headless,
                stealth=True,
                user_data_dir=browser_data_dir,
            )

            # Navigate to start URL
            logger.info(f"Navigating to: {start_url}")
            await self._session.visit(start_url)

            # Process the command
            result = await self._process_command(task, max_steps)

            return AgentOutput(
                success=True,
                data={
                    "result": result,
                    "task": task,
                    "start_url": start_url,
                    "steps_taken": len(self.action_history),
                    "action_history": self.action_history,
                },
                message=f"Task completed: {task[:100]}"
            )

        except Exception as e:
            import traceback
            error_msg = f"EigentBrowserAgent execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return AgentOutput(
                success=False,
                message=error_msg,
                data={"action_history": self.action_history}
            )

    async def _process_command(self, prompt: str, max_steps: int = 15) -> str:
        """Process a command using LLM-guided browser automation."""
        # Get initial full snapshot
        full_snapshot = await self._session.get_snapshot()
        logger.info("Initial snapshot captured")
        logger.debug(f"Full snapshot:\n{full_snapshot}")

        # Get initial plan from LLM
        plan_resp = self._llm_call(prompt, full_snapshot or "", is_initial=True)
        plan = plan_resp.get("plan", [])
        action = plan_resp.get("action")
        self._current_plan = plan

        logger.info(f"Plan generated: {json.dumps(plan, ensure_ascii=False)}")

        # Notify plan generated
        await self._notify_progress("plan_generated", {
            "plan": plan,
            "first_action": action,
        })

        steps = 0
        final_summary = ""

        while action and steps < max_steps:
            if action.get("type") == "finish":
                final_summary = action.get("summary", "Task completed")
                logger.info(f"Task finished: {final_summary}")
                break

            # Notify step started
            await self._notify_progress("step_started", {
                "step": steps + 1,
                "max_steps": max_steps,
                "action": action,
                "action_type": action.get("type"),
            })

            # Execute the action
            result = await self._run_action(action)
            logger.debug(f"Executed action: {action} | Result: {result}")

            # Parse result
            success = False
            result_for_history = ""

            if isinstance(result, str):
                success = "Error" not in result
                result_for_history = result
            elif isinstance(result, dict):
                success = result.get('success', False)
                result_for_history = result.get('message', str(result))
            else:
                success = False
                result_for_history = str(result)

            action_record = {
                "action": action,
                "result": result_for_history,
                "success": success,
            }
            self.action_history.append(action_record)

            # Notify step completed or failed
            if success:
                await self._notify_progress("step_completed", {
                    "step": steps + 1,
                    "max_steps": max_steps,
                    "action": action,
                    "result": result_for_history,
                    "action_history": self.action_history.copy(),
                })
            else:
                await self._notify_progress("step_failed", {
                    "step": steps + 1,
                    "max_steps": max_steps,
                    "action": action,
                    "error": result_for_history,
                    "action_history": self.action_history.copy(),
                })

            # Get diff snapshot
            diff_snapshot = await self._session.get_snapshot(
                force_refresh=ActionExecutor.should_update_snapshot(action),
                diff_only=True,
            )

            # Update full snapshot if page changed
            if self._session.snapshot:
                meta = self._session.snapshot.last_info
                if meta["is_diff"] and not diff_snapshot.startswith("- Page Snapshot (no structural changes)"):
                    full_snapshot = self._session.snapshot.snapshot_data or ""

            # Get next action from LLM
            action = self._llm_call(
                prompt,
                full_snapshot or "",
                is_initial=False,
                history=self.action_history,
            ).get("action")
            steps += 1

        logger.info(f"Process completed with {steps} steps")
        return final_summary or f"Task processing completed after {steps} steps"

    def _llm_call(
        self,
        prompt: str,
        snapshot: str,
        is_initial: bool,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call the LLM to get plan & next action."""
        # Build user message
        if is_initial:
            user_content = f"Snapshot:\n{snapshot}\n\nTask: {prompt}"
        else:
            hist_lines = [
                f"{i + 1}. {'✅' if h['success'] else '❌'} {h['action']['type']} -> {h['result']}"
                for i, h in enumerate(history or [])
            ]
            user_content = (
                f"Snapshot:\n{snapshot}\n\nHistory:\n"
                + "\n".join(hist_lines)
                + f"\n\nTask: {prompt}"
            )

        # Call Anthropic API
        try:
            response = self._llm_client.messages.create(
                model=self._llm_model,
                max_tokens=2048,
                system=EIGENT_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_content}
                ]
            )
            content = response.content[0].text if response.content else "{}"
            return self._safe_parse_json(content)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._get_fallback_response(str(e))

    def _safe_parse_json(self, content: str) -> Dict[str, Any]:
        """Safely parse JSON from LLM response with multiple fallback strategies."""
        # First attempt: direct parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Second attempt: extract JSON-like block using regex
        json_pattern = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)
        json_matches = json_pattern.findall(content)

        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Third attempt: try to find and parse line by line
        lines = content.split('\n')
        json_lines = []
        in_json = False

        for line in lines:
            line = line.strip()
            if line.startswith('{'):
                in_json = True
                json_lines = [line]
            elif in_json:
                json_lines.append(line)
                if line.endswith('}'):
                    try:
                        json_text = '\n'.join(json_lines)
                        return json.loads(json_text)
                    except json.JSONDecodeError:
                        pass
                    in_json = False
                    json_lines = []

        # Fallback: return default structure
        logger.warning(f"Could not parse JSON from LLM response: {content[:200]}")
        return self._get_fallback_response("Parsing error")

    def _get_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Generate a fallback response structure."""
        return {
            "plan": [f"Could not parse response: {error_msg}"],
            "action": {
                "type": "finish",
                "ref": None,
                "summary": f"Parsing error: {error_msg}",
            },
        }

    async def _run_action(self, action: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """Execute a single action and return the result."""
        if action.get("type") == "navigate":
            url = action.get("url", "")
            try:
                await self._session.visit(url)
                return await self._session.get_snapshot(force_refresh=True)
            except Exception as exc:
                return f"Error: could not navigate to {url} - {exc}"
        return await self._session.exec_action(action)

    async def cleanup(self, context: AgentContext):
        """Clean up browser session."""
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")
            self._session = None
        self.action_history = []
