"""Scraper Script Generator

Generates extraction_script.py scripts for data extraction from web pages.
Uses Claude Agent SDK to create scripts that extract structured data from DOM.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Awaitable

from .types import ScriptGenerationResult, ScriptType, ScraperRequirement
from .templates import SCRAPER_AGENT_PROMPT
from src.cloud_backend.services.skills import SkillManager

logger = logging.getLogger(__name__)


class ScraperScriptGenerator:
    """Generates extraction_script.py scripts for data extraction

    This generator creates Python scripts that extract structured data from a DOM.
    It uses Claude Agent SDK to iteratively generate and test the script.

    Usage:
        generator = ScraperScriptGenerator(config_service)
        result = await generator.generate(
            requirement=ScraperRequirement(
                user_description="Extract product list",
                output_format={"name": "Product name", "price": "Price"}
            ),
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
        requirement: ScraperRequirement,
        dom_dict: Dict[str, Any],
        working_dir: Path,
        api_key: str,
        base_url: Optional[str] = None,
        page_url: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict], Awaitable[None]]] = None
    ) -> ScriptGenerationResult:
        """Generate extraction_script.py script

        Args:
            requirement: Scraper requirement specification
            dom_dict: DOM dictionary (from DOMExtractor.extract_dom_dict())
            working_dir: Working directory for script generation
            api_key: API key for Claude Agent SDK
            base_url: Optional base URL for API
            page_url: Optional page URL for absolute URL conversion in generated scripts
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
            SkillManager.prepare_scraper_skills(working_dir)

            # Copy dom_tools.py to working directory root for both:
            # 1. Claude Agent to run: python dom_tools.py ...
            # 2. Generated script to import: from dom_tools import ...
            dom_tools_src = SkillManager.get_skill_path("dom-extraction") / "tools" / "dom_tools.py"
            dom_tools_dest = working_dir / "dom_tools.py"
            if dom_tools_src and dom_tools_src.exists():
                shutil.copy2(dom_tools_src, dom_tools_dest)
                logger.info(f"Copied dom_tools.py to {dom_tools_dest}")

            # Save input files
            await self._save_input_files(working_dir, requirement, dom_dict, page_url)

            # Build prompt
            prompt = self._build_prompt(working_dir, requirement, page_url)

            # Initialize Claude Agent Provider
            claude_provider = ClaudeAgentProvider(
                config_service=self.config_service,
                api_key=api_key,
                base_url=base_url
            )

            # Run Claude Agent SDK with streaming
            logger.info(f"Starting Claude Agent for extraction_script.py...")

            progress_id = f"scraper_script_{requirement.user_description[:20]}"
            if progress_callback:
                await progress_callback(
                    "info",
                    f"Generating extraction script for: {requirement.user_description}",
                    {"update_id": progress_id}
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
                    script_type=ScriptType.SCRAPER_EXTRACTION,
                    working_dir=working_dir,
                    error=task_error,
                    turns=final_turn
                )

            if not task_completed:
                return ScriptGenerationResult(
                    success=False,
                    script_type=ScriptType.SCRAPER_EXTRACTION,
                    working_dir=working_dir,
                    error=f"Claude Agent did not complete ({final_turn} turns)",
                    turns=final_turn
                )

            # Read generated script
            script_file = working_dir / "extraction_script.py"
            if not script_file.exists():
                return ScriptGenerationResult(
                    success=False,
                    script_type=ScriptType.SCRAPER_EXTRACTION,
                    working_dir=working_dir,
                    error="extraction_script.py not created",
                    turns=final_turn
                )

            script_content = script_file.read_text(encoding='utf-8')

            # dom_tools.py was already copied to working_dir at the start

            # Wrap script with execution wrapper
            wrapped_script = self._extract_and_wrap_code(script_content)

            # Note: Keep dom_data.json in workflow directory for first execution.
            # During modification sessions, it will be overwritten with latest DOM
            # from dom_snapshots/ by copy_workflow_to_session().

            # Send completion callback
            if progress_callback:
                await progress_callback(
                    "success",
                    f"Extraction script generated ({final_turn} turns)",
                    {
                        "update_id": progress_id,
                        "completed": True,
                        "script_path": str(script_file)
                    }
                )

            return ScriptGenerationResult(
                success=True,
                script_type=ScriptType.SCRAPER_EXTRACTION,
                script_content=wrapped_script,
                script_path=script_file,
                working_dir=working_dir,
                turns=final_turn,
                metadata={"requirement": requirement.to_dict()}
            )

        except Exception as e:
            logger.error(f"Scraper script generation failed: {e}")
            return ScriptGenerationResult(
                success=False,
                script_type=ScriptType.SCRAPER_EXTRACTION,
                working_dir=working_dir,
                error=str(e)
            )

    async def _save_input_files(
        self,
        working_dir: Path,
        requirement: ScraperRequirement,
        dom_dict: Dict[str, Any],
        page_url: Optional[str] = None
    ) -> None:
        """Save input files for Claude Agent

        Saves:
        - requirement.json: Extraction requirements (permanent)
        - dom_data.json: DOM data in wrapped format (kept for first execution)

        Note: dom_data.json is kept in workflow directory for first execution.
        During modification sessions, it will be overwritten with latest DOM
        from dom_snapshots/ by copy_workflow_to_session().

        DOM format (wrapped): {"url": "...", "dom": {...}}
        """
        # Save requirement.json (permanent - describes what to extract)
        requirement_file = working_dir / "requirement.json"
        requirement_file.write_text(
            json.dumps(requirement.to_dict(), indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        # Save dom_data.json in wrapped format: {"url": ..., "dom": {...}}
        # This is the standard format used everywhere for DOM data
        wrapped_dom = {
            "url": page_url or "unknown",
            "dom": dom_dict
        }
        dom_file = working_dir / "dom_data.json"
        dom_file.write_text(
            json.dumps(wrapped_dom, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        logger.info(f"Input files saved to {working_dir}")

    def _build_prompt(
        self,
        working_dir: Path,
        requirement: ScraperRequirement,
        page_url: Optional[str] = None
    ) -> str:
        """Build Claude Agent prompt"""
        # Build field descriptions
        fields_description = "\n".join([
            f"- {name}: {desc}"
            for name, desc in requirement.output_format.items()
        ])

        # Build sample data description
        sample_description = ""
        if requirement.sample_data:
            sample_description = f"\n\nExpected output example:\n{json.dumps(requirement.sample_data, indent=2, ensure_ascii=False)}"

        # Build xpath hints
        xpath_hints_description = ""
        if requirement.xpath_hints:
            hints_list = "\n".join([
                f"- {name}: {xpath}"
                for name, xpath in requirement.xpath_hints.items()
            ])
            xpath_hints_description = f"\n\nXPath hints from user demo (reference only):\n{hints_list}"

        # Format prompt
        prompt = SCRAPER_AGENT_PROMPT.format(
            working_dir=working_dir,
            page_url=page_url or "unknown",
            user_description=requirement.user_description,
            fields_description=fields_description,
            sample_description=sample_description,
            xpath_hints_description=xpath_hints_description
        )

        return prompt

    def _extract_and_wrap_code(self, response: str) -> str:
        """Extract and wrap the extraction code

        If the response contains a code block, extract it.
        If it's already a complete script, return as-is.
        """
        # Check if already a complete script (starts with shebang or import)
        stripped = response.strip()
        if stripped.startswith("#!/") or stripped.startswith("import ") or stripped.startswith("from "):
            return stripped

        # Extract from markdown code block
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        if "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # Return as-is if no code block found
        return response

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
                    f"Generating script (turn {event.turn})\n{event.content[:150]}...",
                    {"update_id": progress_id, "turn": event.turn}
                )
            elif event.type == "tool_use":
                await callback(
                    "info",
                    f"Generating script (turn {event.turn})\nUsing {event.tool_name} tool",
                    {"update_id": progress_id, "turn": event.turn, "tool_name": event.tool_name}
                )
        except Exception as e:
            logger.warning(f"Failed to forward progress event: {e}")
