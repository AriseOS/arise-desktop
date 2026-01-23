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


def _get_browser_data_dir(explicit_dir: Optional[str] = None) -> Optional[str]:
    """Get browser data directory for the agent.

    Uses user-level directory to preserve login sessions across tasks.

    Args:
        explicit_dir: Explicit directory path (from input_data).
            If provided, uses this directory.
            Otherwise, tries current task manager, then falls back to global.
    """
    try:
        from pathlib import Path
        from ..workspace.directory_manager import get_current_manager

        if explicit_dir:
            path = Path(explicit_dir)
        else:
            # Try to get from current task manager (user-level)
            manager = get_current_manager()
            if manager:
                path = manager.browser_data_dir
            else:
                # Fallback to global directory
                path = Path.home() / ".ami" / "browser_data_quicktask"

        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    except Exception as e:
        logger.warning(f"Failed to create browser_data dir: {e}")
        return None


# System prompt ported from Eigent's PlaywrightLLMAgent
# Updated to support memory-guided planning
EIGENT_SYSTEM_PROMPT = """
You are a web automation assistant.

Analyse the page snapshot and create a plan, then output the FIRST action to start with.
If a Reference Path is provided, your plan should follow it (see Memory Reference section below).

## Memory Reference

You may receive a "Reference Path" - this is a VERIFIED SUCCESSFUL execution path from a past workflow that actually completed successfully.

How to use the Reference Path:
1. The path is FACTUAL - it represents real actions that worked on this website
2. Analyze which parts of the path are relevant to the current task
3. If relevant parts exist, use those path segments to build your plan
4. CRITICAL: You may trim irrelevant steps from the beginning or end, but NEVER skip steps in the middle
   - Valid: Use steps 2-5 from a 7-step path (trimmed front and back)
   - Valid: Use steps 0-3 from a 7-step path (trimmed back only)
   - INVALID: Use steps 0, 1, 3, 5 (skipping step 2 and 4 breaks the flow)
5. For each plan step, indicate the corresponding path_ref or null if it's a new step not from the path

## Output Format

Return a JSON object in *exactly* this shape:

Initial response (with plan):
{
  "plan": [
    {"step": "Step description based on path step 2", "path_ref": 2},
    {"step": "Step description based on path step 3", "path_ref": 3},
    {"step": "Step description based on path step 4", "path_ref": 4},
    {"step": "Additional step not in path", "path_ref": null}
  ],
  "current_plan_step": 0,
  "action": {
    "type": "click",
    "ref": "e1"
  }
}

Note on path_ref: The example above uses path steps 2,3,4 (a continuous segment). This is valid.
Using path_ref 2,4,5 would be INVALID because it skips step 3.

Subsequent responses (action only):
{
  "current_plan_step": 1,
  "action": {
    "type": "click",
    "ref": "e1"
  }
}

Note: For subsequent responses, you may receive "Reference Intents" showing what actions worked before for the current step. Use these as hints.

If task is already complete:
{
  "plan": [],
  "current_plan_step": null,
  "action": {
    "type": "finish",
    "ref": null,
    "summary": "Task was already completed. Summary of what was found..."
  }
}

IMPORTANT: Always include "current_plan_step" to indicate which plan step you are working on. This helps track progress accurately.

## Available action types:
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

## IMPORTANT:
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
            },
            {
                "task": "Navigate to GitHub and find the trending repositories",
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
        self._current_plan: List[Dict[str, Any]] = []  # Plan steps with path_ref
        # Memory-guided planning
        self._memory_paths: List[Dict[str, Any]] = []  # Retrieved memory paths
        self._current_plan_step: int = 0  # Current execution step index

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
            headless = False
            memory_paths = []

            if isinstance(input_data, AgentInput):
                if input_data.data:
                    task = input_data.data.get("task", "")
                    headless = input_data.data.get("headless", False)
                    memory_paths = input_data.data.get("memory_paths", [])
            elif isinstance(input_data, dict):
                task = input_data.get("task", "")
                headless = input_data.get("headless", False)
                memory_paths = input_data.get("memory_paths", [])

            # Store memory paths for later use
            self._memory_paths = memory_paths
            self._current_plan_step = 0

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

            # Process the command (no start_url - LLM decides where to navigate)
            result = await self._process_command(task)

            return AgentOutput(
                success=True,
                data={
                    "result": result,
                    "task": task,
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

    def _format_memory_paths(self) -> str:
        """Format memory paths for inclusion in prompt.

        Returns:
            Formatted string describing the reference path, or empty string if no paths.
        """
        if not self._memory_paths:
            return ""

        # Use the best (first) path
        path = self._memory_paths[0]
        score = path.get("score", 0)
        steps = path.get("steps", [])

        if not steps:
            return ""

        lines = []
        lines.append(f"\n## Reference Path (similarity: {score:.2f})")
        lines.append("This is a VERIFIED SUCCESSFUL PATH from a completed task. Analyze which steps are relevant to the current task.\n")

        for i, step in enumerate(steps):
            state = step.get("state") or {}
            action = step.get("action") or {}
            intent_seq = step.get("intent_sequence") or {}

            state_desc = state.get("description", "Unknown page")
            state_url = state.get("page_url", "")
            action_desc = action.get("description", "No action")
            action_type = action.get("type", "")

            lines.append(f"Path Step {i}: {state_desc}")
            if state_url:
                lines.append(f"  URL: {state_url}")
            if action_desc and action_desc != "No action":
                lines.append(f"  Action: {action_desc} (type: {action_type})")

            # Format intents
            intents = intent_seq.get("intents", [])
            if intents:
                intent_strs = []
                for intent in intents:
                    intent_type = intent.get("type", "unknown")
                    intent_text = intent.get("text", "")
                    intent_value = intent.get("value", "")
                    if intent_text:
                        intent_strs.append(f'{intent_type} on "{intent_text}"')
                    elif intent_value:
                        intent_strs.append(f'{intent_type} value "{intent_value}"')
                    else:
                        intent_strs.append(intent_type)
                lines.append(f"  Intents: [{', '.join(intent_strs)}]")

            lines.append("")  # Blank line between steps

        return "\n".join(lines)

    def _get_current_intent_reference(self) -> str:
        """Get intent reference for current plan step based on path_ref.

        Returns:
            Formatted string with intent hints, or empty string if no reference.
        """
        if not self._memory_paths or not self._current_plan:
            return ""

        # Get current plan step
        if self._current_plan_step >= len(self._current_plan):
            return ""

        plan_step = self._current_plan[self._current_plan_step]

        # Handle both new format (dict with path_ref) and legacy format (string)
        if isinstance(plan_step, str):
            return ""

        path_ref = plan_step.get("path_ref")
        if path_ref is None:
            return ""

        # Get the referenced path step
        path = self._memory_paths[0]
        steps = path.get("steps", [])

        if path_ref >= len(steps):
            logger.warning(f"path_ref {path_ref} out of bounds (path has {len(steps)} steps)")
            return ""

        path_step = steps[path_ref]
        intent_seq = path_step.get("intent_sequence", {})
        intents = intent_seq.get("intents", [])

        if not intents:
            return ""

        # Format intents
        intent_strs = []
        for intent in intents:
            intent_type = intent.get("type", "unknown")
            intent_text = intent.get("text", "")
            intent_value = intent.get("value", "")
            if intent_text:
                intent_strs.append(f'{intent_type} on "{intent_text}"')
            elif intent_value:
                intent_strs.append(f'{intent_type} value "{intent_value}"')
            else:
                intent_strs.append(intent_type)

        step_desc = plan_step.get("step", f"Plan step {self._current_plan_step}")
        return f'\nCurrent Plan Step: "{step_desc}" (path_ref: {path_ref})\nReference Intents: [{", ".join(intent_strs)}]\n'

    def _normalize_plan(self, plan: List) -> List[Dict[str, Any]]:
        """Normalize plan to consistent format with path_ref.

        Args:
            plan: Plan from LLM response (either list of strings or list of dicts)

        Returns:
            List of dicts with 'step' and 'path_ref' keys
        """
        normalized = []
        for item in plan:
            if isinstance(item, str):
                normalized.append({"step": item, "path_ref": None})
            elif isinstance(item, dict):
                normalized.append({
                    "step": item.get("step", str(item)),
                    "path_ref": item.get("path_ref")
                })
            else:
                normalized.append({"step": str(item), "path_ref": None})
        return normalized

    async def _process_command(self, prompt: str) -> str:
        """Process a command using LLM-guided browser automation.

        The agent will keep executing until the LLM returns a 'finish' action.
        """
        # Get initial full snapshot
        full_snapshot = await self._session.get_snapshot()
        logger.info("Initial snapshot captured")
        logger.debug(f"Full snapshot:\n{full_snapshot}")

        # Format memory reference for initial plan generation
        memory_reference = self._format_memory_paths()
        if memory_reference:
            logger.info("Including memory reference in plan generation")
            logger.info(f"Memory reference content:\n{memory_reference}")

        # Get initial plan from LLM
        plan_resp = self._llm_call(
            prompt,
            full_snapshot or "",
            is_initial=True,
            memory_reference=memory_reference
        )
        plan = plan_resp.get("plan", [])
        action = plan_resp.get("action")

        # Normalize and store plan
        self._current_plan = self._normalize_plan(plan)
        # Use LLM's current_plan_step if provided, otherwise default to 0
        self._current_plan_step = plan_resp.get("current_plan_step", 0) or 0

        # Log plan with path references
        logger.info(f"Plan generated: {json.dumps(self._current_plan, ensure_ascii=False)}")

        # Notify plan generated (send normalized format)
        await self._notify_progress("plan_generated", {
            "plan": self._current_plan,
            "first_action": action,
            "memory_path_used": bool(memory_reference),
        })

        steps = 0
        final_summary = ""

        while action:
            if action.get("type") == "finish":
                final_summary = action.get("summary", "Task completed")
                logger.info(f"Task finished: {final_summary}")
                break

            # Notify step started
            await self._notify_progress("step_started", {
                "step": steps + 1,
                "action": action,
                "action_type": action.get("type"),
                "plan_step": self._current_plan_step,
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
                "plan_step": self._current_plan_step,
            }
            self.action_history.append(action_record)

            # Notify step completed or failed
            if success:
                await self._notify_progress("step_completed", {
                    "step": steps + 1,
                    "action": action,
                    "result": result_for_history,
                    "action_history": self.action_history.copy(),
                    "plan_step": self._current_plan_step,
                })
            else:
                await self._notify_progress("step_failed", {
                    "step": steps + 1,
                    "action": action,
                    "error": result_for_history,
                    "action_history": self.action_history.copy(),
                    "plan_step": self._current_plan_step,
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

            # Get intent reference for current plan step
            intent_reference = self._get_current_intent_reference()

            # Get next action from LLM
            llm_resp = self._llm_call(
                prompt,
                full_snapshot or "",
                is_initial=False,
                history=self.action_history,
                intent_reference=intent_reference,
            )
            action = llm_resp.get("action")

            # Update current_plan_step from LLM response
            if "current_plan_step" in llm_resp and llm_resp["current_plan_step"] is not None:
                self._current_plan_step = llm_resp["current_plan_step"]

            steps += 1

        logger.info(f"Process completed with {steps} steps")
        return final_summary or f"Task processing completed after {steps} steps"

    def _llm_call(
        self,
        prompt: str,
        snapshot: str,
        is_initial: bool,
        history: Optional[List[Dict[str, Any]]] = None,
        memory_reference: str = "",
        intent_reference: str = "",
    ) -> Dict[str, Any]:
        """Call the LLM to get plan & next action.

        Args:
            prompt: The task description
            snapshot: Current page snapshot
            is_initial: Whether this is the initial call (plan generation)
            history: Action history for subsequent calls
            memory_reference: Formatted memory path for plan generation
            intent_reference: Intent hints for current action generation
        """
        # Build user message
        if is_initial:
            # Initial call: include full memory reference for plan generation
            user_content = f"Snapshot:\n{snapshot}"
            if memory_reference:
                user_content += f"\n{memory_reference}"
            user_content += f"\n\nTask: {prompt}"
        else:
            # Subsequent calls: include history and optional intent reference
            hist_lines = [
                f"{i + 1}. {'✅' if h['success'] else '❌'} {h['action']['type']} -> {h['result']}"
                for i, h in enumerate(history or [])
            ]
            user_content = f"Snapshot:\n{snapshot}\n\nHistory:\n" + "\n".join(hist_lines)
            if intent_reference:
                user_content += f"\n{intent_reference}"
            user_content += f"\n\nTask: {prompt}"

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
        """Clean up browser session and reset state."""
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")
            self._session = None
        # Reset all state
        self.action_history = []
        self._current_plan = []
        self._memory_paths = []
        self._current_plan_step = 0
