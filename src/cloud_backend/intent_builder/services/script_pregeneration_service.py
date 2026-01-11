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
from ..core.intent import Intent

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
        intents: Optional[List[Intent]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Pre-generate scripts for all applicable workflow steps

        Args:
            workflow_yaml: Workflow YAML content
            dom_snapshots: dom_id -> DOM dict mapping from recording
            workflow_dir: Directory to save scripts
            intents: List of Intents for xpath_hints -> dom_id matching
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
        logger.info(f"  DOM snapshots: {len(dom_snapshots)} dom_ids")
        logger.info(f"  Intents: {len(intents) if intents else 0}")
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
            dom_data = self._find_matching_dom(step_info, dom_snapshots, intents)

            if not dom_data:
                logger.warning(f"No DOM snapshot found for step {step_id}")
                results["skipped"] += 1
                results["details"].append({
                    "step_id": step_id,
                    "status": "skipped",
                    "reason": "No matching DOM snapshot"
                })
                continue

            # Extract dom_dict and page_url from dom_data
            if isinstance(dom_data, dict) and "dom" in dom_data:
                dom_dict = dom_data["dom"]
                page_url = dom_data.get("url")
            else:
                dom_dict = dom_data
                page_url = None

            # Generate script based on step type
            try:
                if step_type == "browser_agent":
                    result = await self._generate_browser_script(
                        step_id, step_inputs, dom_dict, workflow_dir
                    )
                elif step_type == "scraper_agent":
                    result = await self._generate_scraper_script(
                        step_id, step_inputs, dom_dict, workflow_dir, page_url
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
        dom_snapshots: Dict[str, Dict],
        intents: Optional[List[Intent]] = None
    ) -> Optional[Dict]:
        """Find DOM snapshot that matches the step

        Matching strategy (in order):
        1. Match xpath_hints against Intent operations' element.xpath to find dom_id
        2. Match step URL against dom_snapshots keys (if URL is not a variable)

        Args:
            step_info: Step information with inputs, url, etc.
            dom_snapshots: dom_id -> DOM dict mapping
            intents: List of Intents for xpath_hints -> dom_id matching

        Returns:
            DOM dict if found, None otherwise
        """
        step_id = step_info.get("id", "unknown")
        inputs = step_info.get("inputs", {})

        # Strategy 1: Match via xpath_hints -> Intent operations -> dom_id
        xpath_hints = self._extract_xpath_hints(inputs)
        if xpath_hints and intents:
            logger.debug(f"  Step {step_id}: Trying to match xpath_hints: {list(xpath_hints.values())[:2]}...")
            dom_id = self._find_dom_id_by_xpath_hints(xpath_hints, intents)
            if dom_id:
                if dom_id in dom_snapshots:
                    dom_data = dom_snapshots[dom_id]
                    dom_url = dom_data.get("url") if isinstance(dom_data, dict) else None
                    logger.info(f"  Step {step_id}: Matched dom_id={dom_id} via xpath_hints (url={dom_url})")
                    # Return full dom_data {url, dom} for script generation to use page_url
                    return dom_data
                else:
                    logger.warning(f"  Step {step_id}: Matched dom_id={dom_id} but not in dom_snapshots (keys: {list(dom_snapshots.keys())})")

        # Strategy 2: Match via URL (only for fixed URLs, not variables)
        step_url = step_info.get("url")
        if step_url and "{{" not in step_url:
            # Try exact URL match against dom_snapshots
            for key, dom_data in dom_snapshots.items():
                # dom_data is {"url": ..., "dom": ...}
                dom_url = dom_data.get("url") if isinstance(dom_data, dict) else None
                if dom_url == step_url:
                    logger.info(f"  Step {step_id}: Matched via URL={step_url}")
                    return dom_data

        logger.warning(f"  Step {step_id}: No matching DOM found (xpath_hints={list(xpath_hints.keys()) if xpath_hints else None}, url={step_url})")
        return None

    def _extract_xpath_hints(self, inputs: Dict) -> Dict[str, str]:
        """Extract xpath_hints from step inputs

        Handles both scraper_agent (data_requirements.xpath_hints)
        and browser_agent (xpath_hints) formats.
        """
        # scraper_agent format
        data_req = inputs.get("data_requirements", {})
        if data_req and "xpath_hints" in data_req:
            hints = data_req["xpath_hints"]
            if isinstance(hints, dict):
                return hints

        # browser_agent format
        hints = inputs.get("xpath_hints", {})
        if isinstance(hints, dict):
            return hints
        elif isinstance(hints, list) and hints:
            return {"target": hints[0]}

        return {}

    def _normalize_xpath(self, xpath: str) -> str:
        """Normalize xpath for comparison

        Handles differences like:
        - Quote style: 'app' vs "app"
        - Index notation: a[1] vs a

        Args:
            xpath: XPath string

        Returns:
            Normalized xpath string
        """
        import re
        # Normalize quotes: replace single quotes with double quotes
        normalized = xpath.replace("'", '"')
        # Remove [1] index (first element selector) as it's often omitted
        normalized = re.sub(r'\[1\]', '', normalized)
        return normalized

    def _find_dom_id_by_xpath_hints(
        self,
        xpath_hints: Dict[str, str],
        intents: List
    ) -> Optional[str]:
        """Find dom_id by matching xpath_hints against Intent operations

        The xpath_hints in workflow steps come from Recording operations' element.xpath.
        We find the matching operation and return its dom_id.

        Args:
            xpath_hints: Field name -> xpath mapping from step
            intents: List of Intent objects or dicts

        Returns:
            dom_id if found, None otherwise
        """
        # Normalize hint xpaths for comparison
        hint_xpaths_normalized = {self._normalize_xpath(x) for x in xpath_hints.values()}
        logger.debug(f"    Looking for normalized xpaths: {list(hint_xpaths_normalized)[:2]}...")

        for intent in intents:
            # Support both Intent objects and dicts
            if isinstance(intent, Intent):
                operations = intent.operations
            elif isinstance(intent, dict):
                operations = intent.get("operations", [])
            else:
                continue

            for op in operations:
                # Support both Operation objects and dicts
                if isinstance(op, dict):
                    element = op.get("element", {})
                    xpath = element.get("xpath") if element else None
                    dom_id = op.get("dom_id")
                else:
                    # Operation object
                    xpath = op.element.xpath if op.element else None
                    dom_id = op.dom_id

                if xpath and dom_id:
                    normalized_xpath = self._normalize_xpath(xpath)
                    if normalized_xpath in hint_xpaths_normalized:
                        logger.debug(f"    Matched xpath={xpath} -> dom_id={dom_id}")
                        return dom_id

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

        # Create working directory - directly in step directory (no hash subdirectory)
        working_dir = workflow_dir / step_id
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
        workflow_dir: Path,
        page_url: Optional[str] = None
    ) -> ScriptGenerationResult:
        """Generate extraction_script.py for scraper_agent step

        Args:
            step_id: Step identifier
            inputs: Step inputs from workflow
            dom_dict: DOM dictionary for script generation
            workflow_dir: Workflow directory to save script
            page_url: Page URL for absolute URL conversion in scripts
        """

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

        # Create working directory - directly in step directory (no hash subdirectory)
        working_dir = workflow_dir / step_id
        working_dir.mkdir(parents=True, exist_ok=True)

        # Generate script
        result = await self.scraper_generator.generate(
            requirement=requirement,
            dom_dict=dom_dict,
            working_dir=working_dir,
            api_key=self.api_key,
            base_url=self.base_url,
            page_url=page_url
        )

        return result
