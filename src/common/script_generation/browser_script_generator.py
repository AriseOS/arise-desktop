"""Browser Script Generator

Generates find_element.py scripts for browser automation operations (click, fill, scroll).
Uses Claude Agent SDK to create scripts that find target elements in DOM.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Awaitable

from .types import ScriptGenerationResult, ScriptType, BrowserTask
from .templates import (
    BROWSER_TEST_OPERATION,
    BROWSER_FIND_ELEMENT_TEMPLATE,
    BROWSER_AGENT_PROMPT,
)
from src.cloud_backend.services.skills import SkillManager

logger = logging.getLogger(__name__)


class BrowserScriptGenerator:
    """Generates find_element.py scripts for browser operations

    This generator creates Python scripts that find target elements in a DOM structure.
    It uses Claude Agent SDK to iteratively generate and test the script.

    Usage:
        generator = BrowserScriptGenerator(config_service)
        result = await generator.generate(
            task=BrowserTask(task="Click login", operation="click", xpath_hints={...}),
            dom_dict={...},
            working_dir=Path("/tmp/workspace"),
            api_key="sk-..."
        )
    """

    def __init__(self, config_service=None):
        """Initialize generator

        Args:
            config_service: Configuration service (optional, for default paths)
        """
        self.config_service = config_service

    async def generate(
        self,
        task: BrowserTask,
        dom_dict: Dict[str, Any],
        working_dir: Path,
        api_key: str,
        base_url: Optional[str] = None,
        page_url: Optional[str] = None,
        feedback: str = "",
        progress_callback: Optional[Callable[[str, str, Dict], Awaitable[None]]] = None
    ) -> ScriptGenerationResult:
        """Generate find_element.py script

        Args:
            task: Browser task description
            dom_dict: DOM dictionary (from DOMExtractor.extract_dom_dict())
            working_dir: Working directory for script generation
            api_key: API key for Claude Agent SDK
            base_url: Optional base URL for API
            page_url: Optional page URL for DOM wrapper
            feedback: Feedback from previous attempt (for retries)
            progress_callback: Optional async callback for progress updates
                Signature: async def callback(level: str, message: str, data: dict)

        Returns:
            ScriptGenerationResult with generated script
        """
        from src.common.llm import ClaudeAgentProvider
        import shutil

        try:
            # Ensure working directory exists
            working_dir = Path(working_dir)
            working_dir.mkdir(parents=True, exist_ok=True)

            # Copy skills to working directory for Claude Agent to use
            SkillManager.prepare_browser_skills(working_dir)

            # Save input files
            await self._save_input_files(working_dir, task, dom_dict, page_url)

            # Build prompt
            prompt = self._build_prompt(working_dir, task, feedback)

            # Initialize Claude Agent Provider
            claude_provider = ClaudeAgentProvider(
                config_service=self.config_service,
                api_key=api_key,
                base_url=base_url
            )

            # Run Claude Agent SDK with streaming
            logger.info(f"Starting Claude Agent for find_element.py...")

            progress_id = f"browser_script_{task.task[:20]}"
            if progress_callback:
                await progress_callback(
                    "info",
                    f"Generating element finder script for: {task.task}",
                    {"update_id": progress_id, "task": task.task, "operation": task.operation}
                )

            task_completed = False
            task_error = None
            final_turn = 0

            async for event in claude_provider.run_task_stream(
                prompt=prompt,
                working_dir=working_dir
            ):
                if event.turn:
                    final_turn = event.turn

                # Forward progress to callback
                if progress_callback:
                    await self._handle_progress_event(
                        event, progress_id, progress_callback
                    )

                if event.type == "complete":
                    task_completed = True
                    logger.info(f"Claude Agent completed in {final_turn} turns")
                elif event.type == "error":
                    task_error = event.content
                    logger.error(f"Claude Agent error: {event.content}")

            # Check result
            if task_error:
                return ScriptGenerationResult(
                    success=False,
                    script_type=ScriptType.BROWSER_FIND_ELEMENT,
                    working_dir=working_dir,
                    error=task_error,
                    turns=final_turn
                )

            if not task_completed:
                return ScriptGenerationResult(
                    success=False,
                    script_type=ScriptType.BROWSER_FIND_ELEMENT,
                    working_dir=working_dir,
                    error=f"Claude Agent did not complete ({final_turn} turns)",
                    turns=final_turn
                )

            # Read generated script
            script_file = working_dir / "find_element.py"
            if not script_file.exists():
                return ScriptGenerationResult(
                    success=False,
                    script_type=ScriptType.BROWSER_FIND_ELEMENT,
                    working_dir=working_dir,
                    error="find_element.py not created",
                    turns=final_turn
                )

            script_content = script_file.read_text(encoding='utf-8')

            # Send completion callback
            if progress_callback:
                await progress_callback(
                    "success",
                    f"Element finder script generated ({final_turn} turns)",
                    {
                        "update_id": progress_id,
                        "completed": True,
                        "script_path": str(script_file)
                    }
                )

            return ScriptGenerationResult(
                success=True,
                script_type=ScriptType.BROWSER_FIND_ELEMENT,
                script_content=script_content,
                script_path=script_file,
                working_dir=working_dir,
                turns=final_turn,
                metadata={"task": task.to_dict()}
            )

        except Exception as e:
            logger.error(f"Browser script generation failed: {e}")
            return ScriptGenerationResult(
                success=False,
                script_type=ScriptType.BROWSER_FIND_ELEMENT,
                working_dir=working_dir,
                error=str(e)
            )

    async def _save_input_files(
        self,
        working_dir: Path,
        task: BrowserTask,
        dom_dict: Dict[str, Any],
        page_url: Optional[str] = None
    ) -> None:
        """Save input files for Claude Agent

        DOM format (wrapped): {"url": "...", "dom": {...}}
        """
        # Save task.json
        task_file = working_dir / "task.json"
        task_file.write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        # Save dom_data.json in wrapped format: {"url": ..., "dom": {...}}
        wrapped_dom = {
            "url": page_url or "unknown",
            "dom": dom_dict
        }
        dom_file = working_dir / "dom_data.json"
        dom_file.write_text(
            json.dumps(wrapped_dom, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        # Save templates
        template_file = working_dir / "find_element_template.py"
        template_file.write_text(BROWSER_FIND_ELEMENT_TEMPLATE, encoding='utf-8')

        test_file = working_dir / "test_operation.py"
        test_file.write_text(BROWSER_TEST_OPERATION, encoding='utf-8')

        logger.info(f"Input files saved to {working_dir}")

    def _build_prompt(
        self,
        working_dir: Path,
        task: BrowserTask,
        feedback: str = ""
    ) -> str:
        """Build Claude Agent prompt"""
        # Build task details with xpath hints
        task_details = f"""
- **Task:** {task.task}
- **Operation:** {task.operation}
- **Text (for fill):** {task.text if task.text else "N/A"}
"""
        if task.xpath_hints:
            hints_list = "\n".join([
                f"  - {name}: `{xpath}`"
                for name, xpath in task.xpath_hints.items()
            ])
            task_details += f"- **XPath Hints:**\n{hints_list}"

        prompt = BROWSER_AGENT_PROMPT.format(
            working_dir=working_dir,
            task_details=task_details
        )

        # Add feedback if this is a retry
        if feedback:
            prompt += f"""

## IMPORTANT: Previous Attempt Failed
{feedback}

Please fix find_element.py based on the error above.
"""

        return prompt

    async def _handle_progress_event(
        self,
        event,
        progress_id: str,
        callback: Callable[[str, str, Dict], Awaitable[None]]
    ) -> None:
        """Handle streaming event and forward to callback"""
        try:
            if event.type == "text":
                await callback(
                    "info",
                    f"Finding element (turn {event.turn})\n{event.content[:150]}...",
                    {"update_id": progress_id, "turn": event.turn}
                )
            elif event.type == "tool_use":
                await callback(
                    "info",
                    f"Finding element (turn {event.turn})\nUsing {event.tool_name} tool",
                    {"update_id": progress_id, "turn": event.turn, "tool_name": event.tool_name}
                )
        except Exception as e:
            logger.warning(f"Failed to forward progress event: {e}")
