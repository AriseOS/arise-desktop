"""ScraperAgent v4.1 - LLM-based data extraction agent

Design Change (v4.1):
- Code-level snapshot capture (no LLM token limits)
- Code-level notes file writing
- LLM only does data parsing (its strength)
- Large data sets saved in batches via LLM append_note calls

Features:
- Uses EigentStyleBrowserAgent for browser operations
- Code captures page snapshot directly (bypasses LLM output limits)
- LLM reads snapshot from notes and extracts structured data
- Handles large data extraction via batched notes

Input Format (backward compatible):
- data_requirements: What data to extract
- target_path: URL(s) to navigate to
- interaction_steps: Pre-extraction interactions
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..workspace import get_current_manager
from ..tools.eigent_browser.browser_session import HybridBrowserSession

logger = logging.getLogger(__name__)

# Fixed filenames for scraper notes
PAGE_SNAPSHOT_NOTE = "page_snapshot"
EXTRACTED_DATA_NOTE = "workflow_extracted_data"


def _get_browser_data_dir() -> Optional[str]:
    """Get browser data directory."""
    try:
        manager = get_current_manager()
        if manager:
            path = manager.browser_data_dir
        else:
            path = Path.home() / ".ami" / "browser_data_quicktask"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    except Exception as e:
        logger.warning(f"Failed to get browser_data dir: {e}")
        return None


def _get_notes_dir() -> Path:
    """Get notes directory."""
    manager = get_current_manager()
    if manager:
        path = manager.notes_dir
    else:
        path = Path.home() / ".ami" / "notes"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ScraperAgent(BaseStepAgent):
    """ScraperAgent v4.1 - LLM-based data extraction agent

    Code-level snapshot capture + LLM-based data parsing.
    Maintains backward compatibility with v3 input format.
    """

    INPUT_SCHEMA = InputSchema(
        description="Data extraction agent using LLM for intelligent scraping",
        fields={
            "data_requirements": FieldSchema(
                type="dict|str",
                required=True,
                description="Data extraction requirements with output_format defining fields"
            ),
            "target_path": FieldSchema(
                type="str|list",
                required=False,
                description="URL(s) to navigate to before extraction"
            ),
            "interaction_steps": FieldSchema(
                type="list",
                required=False,
                items_type="dict",
                description="Pre-extraction interactions (scroll, click, etc.)"
            ),
            "max_items": FieldSchema(
                type="int",
                required=False,
                default=0,
                description="Maximum items to extract (0 for unlimited)"
            ),
            "max_steps": FieldSchema(
                type="int",
                required=False,
                default=30,
                description="Maximum LLM steps for extraction"
            ),
        },
        examples=[
            {
                "data_requirements": {
                    "user_description": "Extract product information",
                    "output_format": {
                        "name": "Product name",
                        "price": "Product price",
                        "url": "Product URL"
                    }
                },
                "target_path": "https://example.com/products"
            },
            {
                "data_requirements": "Extract all article titles and links",
                "interaction_steps": [
                    {"task": "Scroll down to load more content"}
                ]
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
                name="scraper_agent",
                description="LLM-based data extraction agent"
            )
        super().__init__(metadata)

        self.config_service = config_service
        self._eigent_agent = None
        self._browser_session: Optional[HybridBrowserSession] = None

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize the agent."""
        try:
            self.is_initialized = True
            logger.info("ScraperAgent v4.1 initialized")
            return True
        except Exception as e:
            logger.error(f"ScraperAgent initialization failed: {e}")
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data."""
        if isinstance(input_data, dict):
            return bool(input_data.get("data_requirements"))
        if isinstance(input_data, AgentInput):
            return await self.validate_input(input_data.data)
        return False

    async def _ensure_browser_session(self, context: AgentContext, headless: bool = False) -> HybridBrowserSession:
        """Ensure browser session is initialized.

        Reuses existing session from context if available.
        """
        # Try to get session_id from context for session sharing
        session_id = getattr(context, 'browser_session_id', None) or "scraper_default"

        self._browser_session = HybridBrowserSession(
            headless=headless,
            stealth=True,
            user_data_dir=_get_browser_data_dir(),
            session_id=session_id,
        )
        await self._browser_session.ensure_browser()
        return self._browser_session

    async def _capture_snapshot_to_notes(self, include_links: bool = True) -> str:
        """Capture page snapshot and save directly to notes file.

        This bypasses LLM output token limits by writing directly from code.

        Returns:
            Path to saved notes file
        """
        if not self._browser_session:
            raise RuntimeError("Browser session not initialized")

        # Get snapshot with elements (includes href for links)
        if include_links:
            full_result = await self._browser_session.get_snapshot_with_elements()
            snapshot_text = full_result.get("snapshotText", "")
            elements = full_result.get("elements", {})
            current_url = full_result.get("url", "")

            # Build links section
            links = []
            for ref, elem_info in elements.items():
                href = elem_info.get("href")
                if href:
                    name = elem_info.get("name", "")
                    role = elem_info.get("role", "")
                    links.append(f"- [{ref}] \"{name}\" -> {href}")

            links_section = ""
            if links:
                links_section = "\n\n**Page Links:**\n" + "\n".join(links)

            # Format complete snapshot
            content = f"**Current Page:**\n- URL: {current_url}\n\n"
            content += f"- Page Snapshot\n```yaml\n{snapshot_text}\n```"
            content += links_section
        else:
            snapshot_text = await self._browser_session.get_snapshot()
            page = await self._browser_session.get_page()
            current_url = page.url
            content = f"**Current Page:**\n- URL: {current_url}\n\n{snapshot_text}"

        # Write directly to notes file (bypasses LLM token limits)
        notes_dir = _get_notes_dir()
        note_path = notes_dir / f"{PAGE_SNAPSHOT_NOTE}.md"
        note_path.write_text(content, encoding="utf-8")

        # Also update the .note_register so NoteTakingToolkit can find it
        self._register_note(notes_dir, PAGE_SNAPSHOT_NOTE)

        logger.info(f"[ScraperAgent] Snapshot saved to {note_path} ({len(content)} chars)")
        return str(note_path)

    def _register_note(self, notes_dir: Path, note_name: str) -> None:
        """Register a note in the .note_register file.

        This is needed so NoteTakingToolkit.read_note() can find notes
        that were created directly by code (not via toolkit).
        """
        try:
            registry_file = notes_dir / ".note_register"

            # Load existing registry
            if registry_file.exists():
                registry = registry_file.read_text(encoding="utf-8").strip().split("\n")
                registry = [r for r in registry if r]  # Remove empty lines
            else:
                registry = []

            # Add note if not already registered
            if note_name not in registry:
                registry.append(note_name)
                registry_file.write_text("\n".join(registry), encoding="utf-8")
                logger.debug(f"Registered note: {note_name}")
        except Exception as e:
            logger.warning(f"Failed to register note {note_name}: {e}")

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute data extraction.

        v4.1 Flow:
        1. Code navigates to target URL (if provided)
        2. Code executes interaction steps via LLM (if any)
        3. Code captures snapshot and saves to notes file directly
        4. LLM reads snapshot from notes and extracts structured data

        Args:
            input_data: Input data (AgentInput or dict)
            context: Execution context

        Returns:
            AgentOutput with extracted data
        """
        if not self.is_initialized:
            return AgentOutput(
                success=False,
                message="ScraperAgent not initialized",
                data={}
            )

        # Parse input
        if isinstance(input_data, AgentInput):
            data = input_data.data
        else:
            data = input_data

        data_requirements = data.get("data_requirements", {})
        target_path = data.get("target_path")
        interaction_steps = data.get("interaction_steps", [])
        max_items = data.get("max_items", 0)
        max_steps = data.get("max_steps", 30)
        headless = data.get("headless", False)

        logger.info(f"ScraperAgent v4.1 executing: target={target_path}, max_items={max_items}")

        try:
            # Prepare output data file
            self._prepare_extracted_data_file()

            # Initialize browser session
            await self._ensure_browser_session(context, headless=headless)

            # Step 1: Navigate to target URL (code-level)
            if target_path:
                url = target_path[0] if isinstance(target_path, list) else target_path
                logger.info(f"[ScraperAgent] Step 1a: Navigating to {url}")
                await self._browser_session.navigate(url)

            # Step 1b: Execute interaction steps if any (via LLM)
            if interaction_steps:
                logger.info(f"[ScraperAgent] Step 1b: Executing {len(interaction_steps)} interaction steps")
                await self._execute_interactions(interaction_steps, context, max_steps // 3)

            # Step 2: Capture snapshot and save to notes (code-level, no token limits)
            logger.info("[ScraperAgent] Step 2: Capturing snapshot (code-level)")
            await self._capture_snapshot_to_notes(include_links=True)

            # Step 3: LLM extracts data from snapshot file
            extraction_task = self._build_extraction_task(
                data_requirements=data_requirements,
                max_items=max_items
            )

            logger.info("[ScraperAgent] Step 3: LLM extracting data from snapshot")

            # Create EigentStyleBrowserAgent for LLM extraction
            # It will read the snapshot from notes and output structured data
            from .eigent_style_browser_agent import EigentStyleBrowserAgent
            self._eigent_agent = EigentStyleBrowserAgent()
            await self._eigent_agent.initialize(context)

            # IMPORTANT: Pass the same notes_directory so LLM can read our snapshot
            notes_dir = str(_get_notes_dir())
            result = await self._eigent_agent.execute(
                AgentInput(data={
                    "task": extraction_task,
                    "max_steps": max_steps,
                    "notes_directory": notes_dir,  # Same dir where we saved snapshot
                }),
                context
            )

            if not result.success:
                return AgentOutput(
                    success=False,
                    message=result.message,
                    data={"error": result.message, "extracted_data": []}
                )

            # Validate and get extracted data
            extracted_data, validation_errors = self._validate_extracted_data(data_requirements)

            # If validation failed, ask LLM to fix it
            if validation_errors and len(validation_errors) > 0:
                logger.warning(f"Validation errors: {validation_errors}, attempting fix...")

                fix_result = await self._attempt_fix_extraction(
                    context=context,
                    data_requirements=data_requirements,
                    validation_errors=validation_errors,
                    max_steps=max_steps // 2,
                )

                if fix_result:
                    extracted_data = fix_result

            # Final result
            items_count = len(extracted_data) if extracted_data else 0
            logger.info(f"ScraperAgent extracted {items_count} items")

            return AgentOutput(
                success=items_count > 0,
                message=f"Successfully extracted {items_count} items" if items_count > 0 else "No data extracted",
                data={
                    "extracted_data": extracted_data or [],
                    "items_extracted": items_count,
                    "result": extracted_data or [],
                }
            )

        except Exception as e:
            import traceback
            error_msg = f"ScraperAgent execution failed: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())

            return AgentOutput(
                success=False,
                message=error_msg,
                data={"error": str(e), "extracted_data": []}
            )

    def _prepare_extracted_data_file(self) -> None:
        """Prepare empty extracted data file for LLM to append to.

        This creates an empty note file so LLM can simply use append_note()
        without worrying about create vs append.
        """
        try:
            notes_dir = _get_notes_dir()
            note_path = notes_dir / f"{EXTRACTED_DATA_NOTE}.md"

            # Create empty file (or clear existing)
            note_path.write_text("", encoding="utf-8")
            logger.info(f"Prepared empty data file: {note_path}")
        except Exception as e:
            logger.warning(f"Failed to prepare extracted data file: {e}")

    def _validate_extracted_data(
        self,
        data_requirements: Union[Dict, str]
    ) -> tuple[Optional[List[Dict]], List[str]]:
        """Validate extracted data from notes file.

        Args:
            data_requirements: Expected data format

        Returns:
            Tuple of (extracted_data, validation_errors)
            - extracted_data: List of valid items, or None if file not found
            - validation_errors: List of error messages
        """
        errors = []

        # Read from notes file
        extracted_data = self._read_extracted_data_from_notes()

        if extracted_data is None:
            errors.append("No extracted data file found or file is not valid JSON")
            return None, errors

        if not isinstance(extracted_data, list):
            errors.append(f"Extracted data is not a list: {type(extracted_data)}")
            return None, errors

        if len(extracted_data) == 0:
            errors.append("Extracted data is empty (0 items)")
            return [], errors

        # Validate against expected fields
        if isinstance(data_requirements, dict):
            output_format = data_requirements.get("output_format", {})
            if output_format:
                required_fields = set(output_format.keys())
                valid_items = []
                invalid_count = 0

                for i, item in enumerate(extracted_data):
                    if not isinstance(item, dict):
                        invalid_count += 1
                        continue

                    # Check if item has at least one required field
                    item_fields = set(item.keys())
                    if not item_fields.intersection(required_fields):
                        invalid_count += 1
                        continue

                    valid_items.append(item)

                if invalid_count > 0:
                    errors.append(f"{invalid_count} items don't have required fields: {list(required_fields)}")

                # Check if too many items are invalid
                if len(valid_items) < len(extracted_data) * 0.5:
                    errors.append(f"More than 50% of items are invalid ({len(valid_items)}/{len(extracted_data)})")

                return valid_items, errors

        return extracted_data, errors

    async def _attempt_fix_extraction(
        self,
        context: AgentContext,
        data_requirements: Union[Dict, str],
        validation_errors: List[str],
        max_steps: int = 15,
    ) -> Optional[List[Dict]]:
        """Attempt to fix extraction errors by asking LLM to correct the data.

        Args:
            context: Execution context
            data_requirements: Expected data format
            validation_errors: List of validation errors
            max_steps: Max steps for fix attempt

        Returns:
            Fixed data list or None if fix failed
        """
        try:
            # Build fix task
            fix_task = self._build_fix_task(data_requirements, validation_errors)

            # Reuse the same agent (browser session is still active)
            eigent_input = AgentInput(
                data={
                    "task": fix_task,
                    "max_steps": max_steps,
                }
            )

            result = await self._eigent_agent.execute(eigent_input, context)

            if not result.success:
                logger.warning(f"Fix attempt failed: {result.message}")
                return None

            # Read fixed data
            fixed_data = self._read_extracted_data_from_notes()
            if fixed_data and len(fixed_data) > 0:
                logger.info(f"Fix successful, got {len(fixed_data)} items")
                return fixed_data

            return None

        except Exception as e:
            logger.error(f"Fix attempt error: {e}")
            return None

    def _build_fix_task(
        self,
        data_requirements: Union[Dict, str],
        validation_errors: List[str]
    ) -> str:
        """Build task to fix extraction errors."""
        parts = []

        parts.append("The previous data extraction had validation errors. Please fix them.")
        parts.append("")
        parts.append("Validation errors:")
        for err in validation_errors:
            parts.append(f"  - {err}")
        parts.append("")

        # Show expected format
        if isinstance(data_requirements, dict):
            output_format = data_requirements.get("output_format", {})
            if output_format:
                parts.append("Expected fields for each item:")
                for field, desc in output_format.items():
                    parts.append(f"  - {field}: {desc}")
                parts.append("")

        parts.append("Please:")
        parts.append(f"1. Read the current note file '{EXTRACTED_DATA_NOTE}' to see what was extracted")
        parts.append("2. Fix the JSON format and ensure all items have the required fields")
        parts.append(f"3. Overwrite the note file with corrected data: create_note('{EXTRACTED_DATA_NOTE}', '<valid JSON array>', overwrite=True)")
        parts.append("")
        parts.append("The data must be a valid JSON array with all items having the required fields.")

        return "\n".join(parts)

    async def _execute_interactions(
        self,
        interaction_steps: List[Dict],
        context: AgentContext,
        max_steps: int = 10,
    ) -> bool:
        """Execute interaction steps via LLM.

        Uses EigentStyleBrowserAgent for complex interactions like
        scrolling, clicking, form filling, etc.

        Args:
            interaction_steps: List of interaction step dicts
            context: Execution context
            max_steps: Max LLM steps

        Returns:
            True if all interactions completed successfully
        """
        if not interaction_steps:
            return True

        # Build interaction task
        parts = ["Task: Perform the following page interactions:"]
        parts.append("")
        for i, step in enumerate(interaction_steps, 1):
            task = step.get("task", str(step))
            parts.append(f"{i}. {task}")
        parts.append("")
        parts.append("Complete each interaction in order. Use browser tools as needed.")

        interaction_task = "\n".join(parts)

        # Create agent for interactions
        from .eigent_style_browser_agent import EigentStyleBrowserAgent
        interaction_agent = EigentStyleBrowserAgent()
        await interaction_agent.initialize(context)

        # Share browser session
        interaction_agent._session = self._browser_session

        result = await interaction_agent.execute(
            AgentInput(data={"task": interaction_task, "max_steps": max_steps}),
            context
        )

        return result.success

    def _build_extraction_task(
        self,
        data_requirements: Union[Dict, str],
        max_items: int
    ) -> str:
        """Build task to extract data from saved snapshot file.

        This is Step 2 of the scraper flow:
        1. Read snapshot from note file (use shell commands for partial reads)
        2. Extract required data
        3. Save extracted data to output file (in batches if large)
        """
        # Get the actual notes file path for shell commands
        notes_dir = _get_notes_dir()
        snapshot_file = notes_dir / f"{PAGE_SNAPSHOT_NOTE}.md"
        output_file = notes_dir / f"{EXTRACTED_DATA_NOTE}.md"

        parts = []

        parts.append("Task: Extract data from saved snapshot file")
        parts.append("")

        # File paths for shell commands
        parts.append(f"Snapshot file path: {snapshot_file}")
        parts.append(f"Output file path: {output_file}")
        parts.append("")

        # What to extract
        parts.append("Extract the following data:")
        if isinstance(data_requirements, str):
            parts.append(f"  {data_requirements}")
        elif isinstance(data_requirements, dict):
            user_desc = data_requirements.get("user_description", "")
            if user_desc:
                parts.append(f"  {user_desc}")

            output_format = data_requirements.get("output_format", {})
            if output_format:
                parts.append("  Required fields:")
                for field, desc in output_format.items():
                    parts.append(f"    - {field}: {desc}")

            extraction_hints = data_requirements.get("extraction_hints", "")
            if extraction_hints:
                parts.append(f"  Hints: {extraction_hints}")

        if max_items > 0:
            parts.append(f"  Limit: max {max_items} items")

        parts.append("")

        # How to do it - emphasize shell commands for partial reads
        parts.append("## Extraction Steps")
        parts.append("")
        parts.append("1. First, check total lines in snapshot:")
        parts.append(f"   run_terminal_cmd('wc -l {snapshot_file}')")
        parts.append("")
        parts.append("2. Read the **Page Links** section (usually at the end of file):")
        parts.append(f"   run_terminal_cmd('grep -n \"Page Links\" {snapshot_file}')  # Find where links section starts")
        parts.append(f"   run_terminal_cmd('sed -n \"<start>,<end>p\" {snapshot_file}')  # Read specific line range")
        parts.append("")
        parts.append("3. Parse the links and save to output file")
        parts.append("")

        # Batch processing with shell commands
        parts.append("## CRITICAL - Batch Processing Rules")
        parts.append("")
        parts.append("If there are many items (>50), process in batches:")
        parts.append("")
        parts.append("For EACH batch, you MUST:")
        parts.append("1. Use shell command to read ONLY that batch's lines from snapshot:")
        parts.append(f"   run_terminal_cmd('sed -n \"<start_line>,<end_line>p\" {snapshot_file}')")
        parts.append("2. Parse the data from ONLY those lines")
        parts.append("3. Append to output file:")
        parts.append(f"   append_note('{EXTRACTED_DATA_NOTE}', '<JSON array for this batch>')")
        parts.append("")
        parts.append("Example batch processing:")
        parts.append("- Batch 1: sed -n '100,150p' to read lines 100-150, parse, append")
        parts.append("- Batch 2: sed -n '151,200p' to read lines 151-200, parse, append")
        parts.append("- ... and so on")
        parts.append("")
        parts.append("**DO NOT** rely on memory from previous batches!")
        parts.append("**DO NOT** fabricate data - only extract what you read from the file!")
        parts.append("")
        parts.append("Output format: JSON array, e.g., [{\"name\": \"Product1\", \"url\": \"https://...\"}, ...]")

        return "\n".join(parts)

    def _read_extracted_data_from_notes(self) -> Optional[List[Dict]]:
        """Read extracted data from notes file.

        Handles multiple JSON arrays appended together (from batch writes).
        E.g., '[{...}, {...}][{...}, {...}]' -> merged into one list.

        Returns:
            List of extracted items if successful, None if file not found or invalid JSON.
        """
        try:
            notes_dir = _get_notes_dir()
            note_path = notes_dir / f"{EXTRACTED_DATA_NOTE}.md"

            if not note_path.exists():
                logger.debug(f"Notes file not found: {note_path}")
                return None

            content = note_path.read_text(encoding="utf-8").strip()

            if not content:
                logger.debug("Notes file is empty")
                return None

            # Try to parse as single JSON array first
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    logger.info(f"Successfully read {len(data)} items from notes file")
                    return data
                else:
                    logger.warning(f"Notes file contains non-list JSON: {type(data)}")
                    return None
            except json.JSONDecodeError:
                # Try to handle multiple JSON arrays (from batch writes)
                # E.g., '[{...}][{...}]' or '[{...}]\n[{...}]'
                logger.info("Single JSON parse failed, trying to merge multiple arrays...")
                merged_data = self._merge_json_arrays(content)
                if merged_data is not None:
                    logger.info(f"Successfully merged {len(merged_data)} items from multiple arrays")
                    return merged_data

                # Try to fix common JSON issues
                logger.warning("Merge failed, attempting to fix JSON...")
                fixed_content = self._fix_json_array(content)
                if fixed_content:
                    try:
                        data = json.loads(fixed_content)
                        if isinstance(data, list):
                            logger.info(f"Successfully read {len(data)} items after JSON fix")
                            return data
                    except json.JSONDecodeError:
                        pass
                logger.error("Failed to parse notes file as JSON")
                return None

        except Exception as e:
            logger.error(f"Error reading notes file: {e}")
            return None

    def _merge_json_arrays(self, content: str) -> Optional[List[Dict]]:
        """Merge multiple JSON arrays into one list.

        Handles formats like:
        - '[{...}][{...}]'
        - '[{...}]\n[{...}]'
        - '[{...}], [{...}]'

        Args:
            content: Raw content with potentially multiple JSON arrays

        Returns:
            Merged list or None if parsing fails
        """
        import re

        merged = []

        # Find all JSON arrays in the content
        # Pattern matches [...] with nested brackets handled simply
        array_pattern = r'\[(?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*\]'

        matches = re.findall(array_pattern, content)

        if not matches:
            return None

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list):
                    merged.extend(data)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse array segment: {match[:100]}...")
                continue

        if merged:
            return merged

        return None

    def _fix_json_array(self, content: str) -> Optional[str]:
        """Attempt to fix common JSON array issues.

        Args:
            content: Raw content that might have JSON issues

        Returns:
            Fixed JSON string or None if unfixable
        """
        # Remove trailing commas before ]
        import re
        fixed = re.sub(r',\s*]', ']', content)

        # Ensure it starts with [ and ends with ]
        fixed = fixed.strip()
        if not fixed.startswith('['):
            fixed = '[' + fixed
        if not fixed.endswith(']'):
            fixed = fixed + ']'

        return fixed

    async def cleanup(self, context: AgentContext, close_browser: bool = False):
        """Cleanup resources."""
        # Cleanup EigentStyleBrowserAgent
        if self._eigent_agent:
            try:
                await self._eigent_agent.cleanup(context, close_browser=close_browser)
            except Exception as e:
                logger.warning(f"Failed to cleanup EigentStyleBrowserAgent: {e}")
            self._eigent_agent = None

        # Note: Default behavior avoids closing shared sessions (workflow steps).
        # Use close_browser=True when it's safe to fully close the browser.
        self._browser_session = None
