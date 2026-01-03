"""
Script Pre-generation Service

Generates scripts (find_element.py, extraction_script.py) for workflow steps
using DOM snapshots captured during recording.

This service runs asynchronously after workflow generation to pre-populate
the workflow directory with cached scripts, eliminating the need to generate
them during first execution.
"""

import asyncio
import hashlib
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from src.common.script_generation import (
    BrowserScriptGenerator,
    ScraperScriptGenerator,
    BrowserTask,
    ScraperRequirement,
    ScriptGenerationResult,
)

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

logger = logging.getLogger(__name__)


class ScriptPregenerationService:
    """
    Pre-generates scripts for workflow steps using recorded DOM snapshots.

    This service:
    1. Parses workflow YAML to identify steps that need scripts
    2. Matches step URLs to DOM snapshots from recording
    3. Generates scripts using BrowserScriptGenerator / ScraperScriptGenerator
    4. Saves scripts to workflow directory structure

    Usage:
        service = ScriptPregenerationService(
            config_service=config_service,
            api_key="sk-...",
            base_url="https://api.anthropic.com"
        )

        result = await service.pregenerate_scripts(
            workflow_yaml=workflow_yaml,
            dom_snapshots={"https://...": {...}},
            workflow_dir=Path("/path/to/workflow")
        )
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """Initialize service

        Args:
            config_service: Configuration service
            api_key: API key for Claude Agent SDK
            base_url: API base URL
        """
        self.config_service = config_service
        self.api_key = api_key
        self.base_url = base_url

        self.browser_generator = BrowserScriptGenerator(config_service)
        self.scraper_generator = ScraperScriptGenerator(config_service)

    async def pregenerate_scripts(
        self,
        workflow_yaml: str,
        dom_snapshots: Dict[str, Dict],
        workflow_dir: Path,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Pre-generate scripts for all applicable workflow steps

        Args:
            workflow_yaml: Workflow YAML content
            dom_snapshots: URL -> DOM dict mapping from recording
            workflow_dir: Directory to save scripts
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with generation results:
            {
                "success": bool,
                "total_steps": int,
                "generated": int,
                "skipped": int,
                "failed": int,
                "details": [...]
            }
        """
        logger.info(f"Starting script pre-generation for workflow")
        logger.info(f"  DOM snapshots: {len(dom_snapshots)} URLs")
        logger.info(f"  Workflow dir: {workflow_dir}")

        # Parse workflow
        try:
            workflow = yaml.safe_load(workflow_yaml)
        except Exception as e:
            logger.error(f"Failed to parse workflow YAML: {e}")
            return {
                "success": False,
                "error": f"Failed to parse workflow: {e}",
                "total_steps": 0,
                "generated": 0,
                "skipped": 0,
                "failed": 0,
                "details": []
            }

        # Extract steps that need scripts
        steps_to_process = self._extract_scriptable_steps(workflow)
        logger.info(f"Found {len(steps_to_process)} steps that may need scripts")

        if not steps_to_process:
            return {
                "success": True,
                "total_steps": 0,
                "generated": 0,
                "skipped": 0,
                "failed": 0,
                "details": []
            }

        # Process each step
        results = {
            "success": True,
            "total_steps": len(steps_to_process),
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "details": []
        }

        for i, step_info in enumerate(steps_to_process):
            step_id = step_info["id"]
            step_type = step_info["type"]
            step_inputs = step_info.get("inputs", {})

            if progress_callback:
                await progress_callback(
                    "info",
                    f"Processing step {i+1}/{len(steps_to_process)}: {step_id}",
                    {"step_id": step_id, "step_type": step_type}
                )

            # Find matching DOM snapshot
            dom_dict = self._find_matching_dom(step_info, dom_snapshots)

            if not dom_dict:
                logger.warning(f"No DOM snapshot found for step {step_id}")
                results["skipped"] += 1
                results["details"].append({
                    "step_id": step_id,
                    "status": "skipped",
                    "reason": "No matching DOM snapshot"
                })
                continue

            # Generate script based on step type
            try:
                if step_type == "browser_agent":
                    result = await self._generate_browser_script(
                        step_id, step_inputs, dom_dict, workflow_dir
                    )
                elif step_type == "scraper_agent":
                    result = await self._generate_scraper_script(
                        step_id, step_inputs, dom_dict, workflow_dir
                    )
                else:
                    results["skipped"] += 1
                    results["details"].append({
                        "step_id": step_id,
                        "status": "skipped",
                        "reason": f"Unknown step type: {step_type}"
                    })
                    continue

                if result.success:
                    results["generated"] += 1
                    results["details"].append({
                        "step_id": step_id,
                        "status": "generated",
                        "script_path": str(result.script_path),
                        "turns": result.turns
                    })
                    logger.info(f"Generated script for step {step_id}")
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "step_id": step_id,
                        "status": "failed",
                        "error": result.error
                    })
                    logger.error(f"Failed to generate script for {step_id}: {result.error}")

            except Exception as e:
                logger.error(f"Exception generating script for {step_id}: {e}")
                results["failed"] += 1
                results["details"].append({
                    "step_id": step_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Overall success if no failures
        results["success"] = results["failed"] == 0

        logger.info(f"Script pre-generation complete: "
                   f"generated={results['generated']}, "
                   f"skipped={results['skipped']}, "
                   f"failed={results['failed']}")

        return results

    def _extract_scriptable_steps(self, workflow: Dict) -> List[Dict]:
        """Extract steps that need script generation

        Returns list of step info dicts with:
        - id: step ID
        - type: agent type (browser_agent, scraper_agent)
        - inputs: step inputs
        - url: target URL if available
        """
        steps = []

        def process_step(step: Dict):
            # Skip control flow steps
            if any(k in step for k in ["foreach", "if", "while"]):
                # Process nested steps
                for key in ["do", "then", "else", "steps"]:
                    if key in step:
                        nested = step[key]
                        if isinstance(nested, list):
                            for s in nested:
                                process_step(s)
                return

            # Get agent type
            agent = step.get("agent") or step.get("agent_type")
            if not agent:
                return

            # Only process browser_agent and scraper_agent
            if agent not in ["browser_agent", "scraper_agent"]:
                return

            step_id = step.get("id", "unknown")
            inputs = step.get("inputs", {})

            # For browser_agent, check if it needs a script (click/fill operations)
            if agent == "browser_agent":
                operation = inputs.get("operation", "navigate")
                if operation not in ["click", "fill", "type"]:
                    return  # Only click/fill need scripts

            # For scraper_agent, always needs script in script mode
            if agent == "scraper_agent":
                method = inputs.get("extraction_method", "script")
                if method != "script":
                    return

            # Extract URL for DOM matching
            url = None
            if "target_url" in inputs:
                url = inputs["target_url"]
            elif "url" in inputs:
                url = inputs["url"]

            steps.append({
                "id": step_id,
                "type": agent,
                "inputs": inputs,
                "url": url
            })

        # Process all workflow steps
        for step in workflow.get("steps", []):
            process_step(step)

        return steps

    def _find_matching_dom(
        self,
        step_info: Dict,
        dom_snapshots: Dict[str, Dict]
    ) -> Optional[Dict]:
        """Find DOM snapshot that matches the step's URL

        Matching strategy:
        1. Exact URL match
        2. URL without query params match
        3. Same domain match (fallback)
        """
        step_url = step_info.get("url")

        if not step_url:
            # If no URL in step, use the first/latest DOM snapshot
            if dom_snapshots:
                return list(dom_snapshots.values())[-1]
            return None

        # Remove variable references for matching
        if "{{" in step_url:
            # Can't match variable URLs directly
            # Fall back to first available snapshot
            if dom_snapshots:
                return list(dom_snapshots.values())[0]
            return None

        # Exact match
        if step_url in dom_snapshots:
            return dom_snapshots[step_url]

        # URL without query params
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(step_url)
        base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

        for url, dom in dom_snapshots.items():
            parsed_snap = urlparse(url)
            snap_base = urlunparse((parsed_snap.scheme, parsed_snap.netloc, parsed_snap.path, "", "", ""))
            if base_url == snap_base:
                return dom

        # Same domain fallback
        for url, dom in dom_snapshots.items():
            if urlparse(url).netloc == parsed.netloc:
                return dom

        return None

    async def _generate_browser_script(
        self,
        step_id: str,
        inputs: Dict,
        dom_dict: Dict,
        workflow_dir: Path
    ) -> ScriptGenerationResult:
        """Generate find_element.py for browser_agent step"""

        # Build task from inputs
        operation = inputs.get("operation", "click")
        task_desc = inputs.get("task") or inputs.get("description") or f"{operation} element"

        # Get xpath hints
        xpath_hints = inputs.get("xpath_hints", {})
        if isinstance(xpath_hints, list):
            # Convert list to dict
            xpath_hints = {"target": xpath_hints[0]} if xpath_hints else {}

        text = inputs.get("text") or inputs.get("value")

        task = BrowserTask(
            task=task_desc,
            operation=operation,
            xpath_hints=xpath_hints,
            text=text
        )

        # Generate script key for directory naming
        script_key = self._generate_script_key("browser", task_desc, xpath_hints)

        # Create working directory
        working_dir = workflow_dir / step_id / f"browser_script_{script_key}"
        working_dir.mkdir(parents=True, exist_ok=True)

        # Generate script
        result = await self.browser_generator.generate(
            task=task,
            dom_dict=dom_dict,
            working_dir=working_dir,
            api_key=self.api_key,
            base_url=self.base_url
        )

        return result

    async def _generate_scraper_script(
        self,
        step_id: str,
        inputs: Dict,
        dom_dict: Dict,
        workflow_dir: Path
    ) -> ScriptGenerationResult:
        """Generate extraction_script.py for scraper_agent step"""

        # Build requirement from inputs
        data_req = inputs.get("data_requirements", {})

        user_description = data_req.get("user_description", "Extract data")
        output_format = data_req.get("output_format", {})
        xpath_hints = data_req.get("xpath_hints", {})
        sample_data = data_req.get("sample_data", [])

        requirement = ScraperRequirement(
            user_description=user_description,
            output_format=output_format,
            xpath_hints=xpath_hints,
            sample_data=sample_data
        )

        # Generate script key for directory naming
        script_key = self._generate_script_key("scraper", user_description, output_format)

        # Create working directory
        working_dir = workflow_dir / step_id / f"scraper_script_{script_key}"
        working_dir.mkdir(parents=True, exist_ok=True)

        # Generate script
        result = await self.scraper_generator.generate(
            requirement=requirement,
            dom_dict=dom_dict,
            working_dir=working_dir,
            api_key=self.api_key,
            base_url=self.base_url
        )

        return result

    def _generate_script_key(
        self,
        script_type: str,
        description: str,
        extra: Dict
    ) -> str:
        """Generate a unique key for script caching"""
        content = f"{script_type}:{description}:{json.dumps(extra, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()[:8]
