"""
Replay Executor - Core engine for replaying recorded operations.

This module executes recorded operations step-by-step, strictly following
the recorded sequence without interpretation or intent extraction.
"""

import logging
from typing import Any, Dict, List, Optional
from playwright.async_api import Page, ElementHandle, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class ReplayExecutor:
    """Executes recorded operations on a browser session."""

    def __init__(self, page: Page):
        """Initialize replay executor.

        Args:
            page: Playwright page instance to execute operations on.
        """
        self.page = page
        self.execution_log: List[Dict[str, Any]] = []
        self.current_operation_index = 0

    async def execute_operation(
        self,
        operation: Dict[str, Any],
        index: int,
        wait_after: float = 0.5
    ) -> Dict[str, Any]:
        """Execute a single recorded operation.

        Args:
            operation: Operation dict from recording.
            index: Operation index in sequence.
            wait_after: Seconds to wait after operation (default 0.5s).

        Returns:
            Execution result dict with status and details.
        """
        self.current_operation_index = index
        op_type = operation.get("type")

        logger.info(f"[{index}] Executing operation: {op_type}")

        result = {
            "index": index,
            "type": op_type,
            "status": "pending",
            "error": None,
            "timestamp": operation.get("timestamp")
        }

        try:
            # Route to appropriate handler
            if op_type == "navigate":
                await self._execute_navigate(operation)
            elif op_type == "click":
                await self._execute_click(operation)
            elif op_type == "input":
                await self._execute_input(operation)
            elif op_type == "select":
                await self._execute_select(operation)
            elif op_type == "scroll":
                await self._execute_scroll(operation)
            elif op_type == "copy_action":
                await self._execute_copy(operation)
            elif op_type == "paste_action":
                await self._execute_paste(operation)
            elif op_type == "dataload":
                await self._execute_dataload(operation)
            elif op_type == "test":
                logger.info("Skipping test operation (binding verification)")
            else:
                logger.warning(f"Unknown operation type: {op_type}")
                result["status"] = "skipped"
                return result

            result["status"] = "success"

            # Wait after successful operation
            if wait_after > 0:
                await self.page.wait_for_timeout(int(wait_after * 1000))

        except Exception as e:
            logger.error(f"Failed to execute operation [{index}] {op_type}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        self.execution_log.append(result)
        return result

    async def _execute_navigate(self, operation: Dict[str, Any]) -> None:
        """Execute navigation operation."""
        target_url = operation.get("data", {}).get("toUrl") or operation.get("url")

        if not target_url:
            raise ValueError("No target URL found in navigate operation")

        logger.info(f"Navigating to: {target_url}")
        await self.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for network idle
        await self.page.wait_for_load_state("networkidle", timeout=10000)

    async def _execute_click(self, operation: Dict[str, Any]) -> None:
        """Execute click operation."""
        element = await self._locate_element(operation)

        if element:
            # Wait for element to be visible and enabled
            await element.wait_for_element_state("visible", timeout=5000)
            await element.click()
            logger.info("Click executed successfully")
        else:
            # Fallback: try clicking by coordinates if available
            data = operation.get("data", {})
            if "clientX" in data and "clientY" in data:
                x, y = data["clientX"], data["clientY"]
                logger.info(f"Fallback: clicking at coordinates ({x}, {y})")
                await self.page.mouse.click(x, y)
            else:
                raise ValueError("Element not found and no coordinates available")

    async def _execute_input(self, operation: Dict[str, Any]) -> None:
        """Execute input operation."""
        element = await self._locate_element(operation)

        if not element:
            raise ValueError("Input element not found")

        data = operation.get("data", {})
        input_value = data.get("actualValue", "")

        logger.info(f"Filling input with: {input_value[:50]}...")

        # Clear existing value and fill
        await element.click()  # Focus the element
        await element.fill("")  # Clear
        await element.type(input_value, delay=50)  # Type with human-like delay

    async def _execute_select(self, operation: Dict[str, Any]) -> None:
        """Execute text selection operation."""
        element = await self._locate_element(operation)

        if not element:
            raise ValueError("Element for selection not found")

        data = operation.get("data", {})
        selected_text = data.get("selectedText", "")

        logger.info(f"Selecting text: {selected_text[:50]}...")

        # Triple-click to select all text in element (common pattern)
        await element.click(click_count=3)

    async def _execute_scroll(self, operation: Dict[str, Any]) -> None:
        """Execute scroll operation."""
        data = operation.get("data", {})
        direction = data.get("direction", "down")
        distance = data.get("distance", 500)

        logger.info(f"Scrolling {direction} by {distance}px")

        # Execute scroll via JavaScript
        scroll_delta = distance if direction == "down" else -distance
        await self.page.evaluate(f"window.scrollBy(0, {scroll_delta})")

        # Wait for scroll to settle
        await self.page.wait_for_timeout(300)

    async def _execute_copy(self, operation: Dict[str, Any]) -> None:
        """Execute copy operation."""
        data = operation.get("data", {})
        text_to_copy = data.get("copiedText", "")

        logger.info(f"Copying text: {text_to_copy[:50]}...")

        # Simulate Ctrl+C / Cmd+C
        modifier = "Meta" if self._is_mac() else "Control"
        await self.page.keyboard.press(f"{modifier}+KeyC")

    async def _execute_paste(self, operation: Dict[str, Any]) -> None:
        """Execute paste operation."""
        data = operation.get("data", {})
        text_to_paste = data.get("pastedText", "")

        logger.info(f"Pasting text: {text_to_paste[:50]}...")

        # First, locate the input element if specified
        element = await self._locate_element(operation)
        if element:
            await element.click()  # Focus

        # Simulate Ctrl+V / Cmd+V
        modifier = "Meta" if self._is_mac() else "Control"
        await self.page.keyboard.press(f"{modifier}+KeyV")

    async def _execute_dataload(self, operation: Dict[str, Any]) -> None:
        """Execute dataload (wait for dynamic content) operation."""
        data = operation.get("data", {})
        added_count = data.get("added_elements_count", 0)

        logger.info(f"Waiting for dynamic content load ({added_count} elements)...")

        # Wait for network idle (indicates content loaded)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeout:
            logger.warning("Timeout waiting for network idle, continuing...")

    async def _locate_element(self, operation: Dict[str, Any]) -> Optional[ElementHandle]:
        """Locate element from operation data.

        Tries multiple strategies in order:
        1. XPath (most reliable)
        2. ID attribute
        3. Name attribute
        4. Text content matching

        Args:
            operation: Operation dict containing element info.

        Returns:
            ElementHandle if found, None otherwise.
        """
        element_info = operation.get("element", {})

        if not element_info:
            return None

        # Strategy 1: XPath (primary)
        xpath = element_info.get("xpath")
        if xpath:
            try:
                element = await self.page.wait_for_selector(
                    f"xpath={xpath}",
                    timeout=5000,
                    state="attached"
                )
                if element:
                    logger.debug(f"Element found by XPath: {xpath}")
                    return element
            except PlaywrightTimeout:
                logger.warning(f"XPath locator timed out: {xpath}")

        # Strategy 2: ID
        element_id = element_info.get("id")
        if element_id:
            try:
                element = await self.page.wait_for_selector(
                    f"#{element_id}",
                    timeout=2000,
                    state="attached"
                )
                if element:
                    logger.debug(f"Element found by ID: {element_id}")
                    return element
            except PlaywrightTimeout:
                pass

        # Strategy 3: Name attribute (for form inputs)
        name = element_info.get("name")
        tag_name = element_info.get("tagName", "").upper()
        if name and tag_name in ["INPUT", "SELECT", "TEXTAREA"]:
            try:
                element = await self.page.wait_for_selector(
                    f"{tag_name.lower()}[name='{name}']",
                    timeout=2000,
                    state="attached"
                )
                if element:
                    logger.debug(f"Element found by name: {name}")
                    return element
            except PlaywrightTimeout:
                pass

        # Strategy 4: Text content (for buttons, links)
        text_content = element_info.get("textContent")
        if text_content and tag_name in ["BUTTON", "A", "SPAN"]:
            try:
                # Use text selector
                element = await self.page.wait_for_selector(
                    f"text={text_content}",
                    timeout=2000,
                    state="attached"
                )
                if element:
                    logger.debug(f"Element found by text: {text_content}")
                    return element
            except PlaywrightTimeout:
                pass

        logger.warning(f"Element not found with any strategy: {element_info}")
        return None

    def _is_mac(self) -> bool:
        """Check if running on macOS."""
        import platform
        return platform.system() == "Darwin"

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of execution results.

        Returns:
            Summary dict with statistics.
        """
        total = len(self.execution_log)
        successful = sum(1 for r in self.execution_log if r["status"] == "success")
        failed = sum(1 for r in self.execution_log if r["status"] == "failed")
        skipped = sum(1 for r in self.execution_log if r["status"] == "skipped")

        return {
            "total_operations": total,
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "success_rate": successful / total if total > 0 else 0,
            "execution_log": self.execution_log
        }
