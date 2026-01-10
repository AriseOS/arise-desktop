"""
Scraper Context Service - Generate diagnostic context for workflow modification sessions.

This service pre-computes context information to help Claude efficiently diagnose
and fix scraper extraction issues without unnecessary exploration.

Context includes:
1. Directory structure with scraper script locations
2. Requirement.json content for each scraper step
3. Pre-run script output (optional)
4. URL index mapping steps to pages
"""

import json
import logging
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScraperStepInfo:
    """Information about a single scraper step."""
    step_id: str
    step_name: str
    script_dir: str  # Relative path like "step_id/scraper_script_xxx"
    url_pattern: Optional[str] = None

    # From requirement.json
    user_description: Optional[str] = None
    output_format: Optional[Dict[str, str]] = None
    xpath_hints: Optional[Dict[str, str]] = None

    # Pre-run results
    script_status: Optional[str] = None  # "success", "error", "empty"
    script_output_preview: Optional[List[Dict]] = None  # First 3 items
    script_output_count: Optional[int] = None
    script_error: Optional[str] = None

    # DOM info
    has_dom_data: bool = False
    dom_file_size: Optional[int] = None


@dataclass
class ScraperContext:
    """Complete context for scraper modification session."""
    workflow_name: str
    scraper_steps: List[ScraperStepInfo] = field(default_factory=list)
    url_index: List[Dict[str, str]] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Generate markdown context for injection into system prompt."""
        lines = []

        # Header
        lines.append("## Workflow Context (Pre-computed)")
        lines.append("")
        lines.append(f"**Workflow**: {self.workflow_name}")
        lines.append("")

        # Directory structure
        lines.append("### Directory Structure")
        lines.append("")
        lines.append("```")
        lines.append("./")
        lines.append("├── workflow.yaml")
        lines.append("├── metadata.json")

        for step in self.scraper_steps:
            lines.append(f"└── {step.step_id}/")
            lines.append(f"    └── {step.script_dir.split('/')[-1]}/")
            lines.append(f"        ├── extraction_script.py")
            lines.append(f"        ├── dom_tools.py")
            lines.append(f"        ├── requirement.json")
            if step.has_dom_data:
                lines.append(f"        └── dom_data.json ({_format_size(step.dom_file_size)})")

        lines.append("```")
        lines.append("")

        # Scraper steps detail
        lines.append("### Scraper Steps")
        lines.append("")

        for i, step in enumerate(self.scraper_steps, 1):
            lines.append(f"#### Step {i}: {step.step_name}")
            lines.append(f"- **Step ID**: `{step.step_id}`")
            lines.append(f"- **Script Directory**: `{step.script_dir}`")
            if step.url_pattern:
                lines.append(f"- **URL Pattern**: `{step.url_pattern}`")
            lines.append("")

            # Requirement info
            if step.user_description:
                lines.append(f"**Requirement**: {step.user_description}")
                lines.append("")

            if step.output_format:
                lines.append("**Expected Output Format**:")
                lines.append("```json")
                lines.append(json.dumps(step.output_format, indent=2, ensure_ascii=False))
                lines.append("```")
                lines.append("")

            if step.xpath_hints:
                lines.append("**XPath Hints** (from recording, may be outdated - verify with dom_data.json):")
                lines.append("```json")
                lines.append(json.dumps(step.xpath_hints, indent=2, ensure_ascii=False))
                lines.append("```")
                lines.append("")

            # Script status
            if step.script_status:
                if step.script_status == "success":
                    lines.append(f"**Current Script Output**: ✅ Success ({step.script_output_count} items)")
                    if step.script_output_preview:
                        lines.append("```json")
                        lines.append(json.dumps(step.script_output_preview[:2], indent=2, ensure_ascii=False))
                        if step.script_output_count > 2:
                            lines.append(f"// ... and {step.script_output_count - 2} more items")
                        lines.append("```")
                elif step.script_status == "empty":
                    lines.append(f"**Current Script Output**: ⚠️ Empty list `[]`")
                elif step.script_status == "error":
                    lines.append(f"**Current Script Output**: ❌ Error")
                    if step.script_error:
                        lines.append(f"```")
                        lines.append(step.script_error[:500])
                        lines.append(f"```")
                lines.append("")

            lines.append("---")
            lines.append("")

        # URL Index
        if self.url_index:
            lines.append("### URL Index")
            lines.append("")
            lines.append("| Step ID | Step Name | URL Pattern |")
            lines.append("|---------|-----------|-------------|")
            for entry in self.url_index:
                lines.append(f"| {entry['step_id']} | {entry['step_name']} | {entry.get('url_pattern', 'N/A')} |")
            lines.append("")

        return "\n".join(lines)


def _format_size(size_bytes: Optional[int]) -> str:
    """Format file size in human readable format."""
    if size_bytes is None:
        return "N/A"
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


class ScraperContextService:
    """Service to generate scraper diagnostic context."""

    def __init__(self, dom_snapshots_dir: Optional[Path] = None):
        """
        Initialize the service.

        Args:
            dom_snapshots_dir: Directory containing DOM snapshots for pre-running scripts.
                              If None, scripts won't be pre-run.
        """
        self.dom_snapshots_dir = dom_snapshots_dir

    def generate_context(
        self,
        session_dir: Path,
        workflow_yaml: str,
        pre_run_scripts: bool = True,
        dom_snapshots: Optional[Dict[str, Dict]] = None
    ) -> ScraperContext:
        """
        Generate complete scraper context for a modification session.

        Args:
            session_dir: Path to the session working directory
            workflow_yaml: The workflow YAML content
            pre_run_scripts: Whether to pre-run scripts to get current output
            dom_snapshots: Optional dict of URL -> DOM dict for pre-running

        Returns:
            ScraperContext with all diagnostic information
        """
        try:
            workflow = yaml.safe_load(workflow_yaml)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse workflow YAML: {e}")
            return ScraperContext(workflow_name="Unknown")

        workflow_name = workflow.get("metadata", {}).get("name", "Unknown")
        steps = workflow.get("steps", [])

        context = ScraperContext(workflow_name=workflow_name)

        # Process each step
        for step in steps:
            step_id = step.get("id", "")
            step_name = step.get("name", "")
            agent_type = step.get("agent_type", "")

            # Only process scraper_agent steps
            if agent_type != "scraper_agent":
                continue

            # Find script directory
            step_dir = session_dir / step_id
            script_dir = self._find_script_dir(step_dir)

            if not script_dir:
                logger.warning(f"No script directory found for step {step_id}")
                continue

            # Create step info
            step_info = ScraperStepInfo(
                step_id=step_id,
                step_name=step_name,
                script_dir=f"{step_id}/{script_dir.name}"
            )

            # Extract URL pattern from step config
            step_info.url_pattern = self._extract_url_pattern(step)

            # Read requirement.json
            self._load_requirement(script_dir, step_info)

            # Check DOM data
            dom_data_file = script_dir / "dom_data.json"
            if dom_data_file.exists():
                step_info.has_dom_data = True
                step_info.dom_file_size = dom_data_file.stat().st_size

            # Pre-run script if requested
            if pre_run_scripts:
                self._pre_run_script(script_dir, step_info, dom_snapshots)

            context.scraper_steps.append(step_info)

            # Add to URL index
            context.url_index.append({
                "step_id": step_id,
                "step_name": step_name,
                "url_pattern": step_info.url_pattern or "N/A"
            })

        return context

    def _find_script_dir(self, step_dir: Path) -> Optional[Path]:
        """Find scraper_script_xxx directory in step directory."""
        if not step_dir.exists():
            return None

        for child in step_dir.iterdir():
            if child.is_dir() and child.name.startswith("scraper_script_"):
                return child

        return None

    def _extract_url_pattern(self, step: Dict) -> Optional[str]:
        """Extract URL pattern from step configuration."""
        # Try different places where URL might be stored
        params = step.get("params", {})

        # Direct URL
        if "url" in params:
            return params["url"]

        # Target URL
        if "target_url" in params:
            return params["target_url"]

        # From data_requirements
        data_req = params.get("data_requirements", {})
        if "source_url" in data_req:
            return data_req["source_url"]

        return None

    def _load_requirement(self, script_dir: Path, step_info: ScraperStepInfo):
        """Load requirement.json content into step info."""
        req_file = script_dir / "requirement.json"
        if not req_file.exists():
            return

        try:
            with open(req_file, 'r', encoding='utf-8') as f:
                req = json.load(f)

            step_info.user_description = req.get("user_description")
            step_info.output_format = req.get("output_format")
            step_info.xpath_hints = req.get("xpath_hints")

        except Exception as e:
            logger.warning(f"Failed to load requirement.json: {e}")

    def _pre_run_script(
        self,
        script_dir: Path,
        step_info: ScraperStepInfo,
        dom_snapshots: Optional[Dict[str, Dict]] = None
    ):
        """Pre-run extraction script and capture output.

        Args:
            script_dir: Path to the script directory
            step_info: Step info to update with results
            dom_snapshots: Optional URL -> DOM dict mapping
        """
        script_file = script_dir / "extraction_script.py"
        dom_data_file = script_dir / "dom_data.json"

        if not script_file.exists():
            step_info.script_status = "error"
            step_info.script_error = "extraction_script.py not found"
            return

        # Check if we have DOM data
        # Priority: 1) Existing dom_data.json 2) Provided dom_snapshots
        has_dom = dom_data_file.exists()
        temp_dom_file = None

        if not has_dom and dom_snapshots:
            # Try to find matching DOM snapshot by URL pattern
            dom_dict = self._find_matching_dom(step_info.url_pattern, dom_snapshots)
            if dom_dict:
                # Write temporary dom_data.json
                try:
                    with open(dom_data_file, 'w', encoding='utf-8') as f:
                        json.dump(dom_dict, f, ensure_ascii=False)
                    temp_dom_file = dom_data_file
                    has_dom = True
                except Exception as e:
                    logger.warning(f"Failed to write temp DOM data: {e}")

        if not has_dom:
            step_info.script_status = "error"
            step_info.script_error = "No DOM data available (dom_data.json not found)"
            return

        try:
            # Run the script
            result = subprocess.run(
                [sys.executable, str(script_file)],
                cwd=str(script_dir),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                step_info.script_status = "error"
                step_info.script_error = result.stderr[:500] if result.stderr else "Unknown error"
                return

            # Parse output
            try:
                output = json.loads(result.stdout)
                if isinstance(output, list):
                    if len(output) == 0:
                        step_info.script_status = "empty"
                        step_info.script_output_count = 0
                    else:
                        step_info.script_status = "success"
                        step_info.script_output_count = len(output)
                        step_info.script_output_preview = output[:3]
                else:
                    step_info.script_status = "success"
                    step_info.script_output_count = 1
                    step_info.script_output_preview = [output]

            except json.JSONDecodeError:
                step_info.script_status = "error"
                step_info.script_error = f"Invalid JSON output: {result.stdout[:200]}"

        except subprocess.TimeoutExpired:
            step_info.script_status = "error"
            step_info.script_error = "Script execution timed out (30s)"
        except Exception as e:
            step_info.script_status = "error"
            step_info.script_error = str(e)
        finally:
            # Clean up temp DOM file
            if temp_dom_file and temp_dom_file.exists():
                # Don't delete - keep it for Claude to use
                pass

    def _find_matching_dom(
        self,
        url_pattern: Optional[str],
        dom_snapshots: Dict[str, Dict]
    ) -> Optional[Dict]:
        """Find DOM snapshot matching the URL pattern."""
        if not url_pattern or not dom_snapshots:
            return None

        # Try exact match first
        if url_pattern in dom_snapshots:
            return dom_snapshots[url_pattern]

        # Try partial match
        for url, dom in dom_snapshots.items():
            if url_pattern in url or url in url_pattern:
                return dom

        # Return first available as fallback
        if dom_snapshots:
            return next(iter(dom_snapshots.values()))

        return None


def generate_scraper_context_markdown(
    session_dir: Path,
    workflow_yaml: str,
    pre_run_scripts: bool = True,
    dom_snapshots: Optional[Dict[str, Dict]] = None
) -> str:
    """
    Convenience function to generate context markdown.

    Args:
        session_dir: Session working directory
        workflow_yaml: Workflow YAML content
        pre_run_scripts: Whether to pre-run scripts
        dom_snapshots: Optional URL -> DOM dict for pre-running

    Returns:
        Markdown string for injection into system prompt
    """
    service = ScraperContextService()
    context = service.generate_context(
        session_dir=session_dir,
        workflow_yaml=workflow_yaml,
        pre_run_scripts=pre_run_scripts,
        dom_snapshots=dom_snapshots
    )
    return context.to_markdown()
