"""
ScreenshotToolkit - Take screenshots for visual analysis.

Wraps CAMEL's ScreenshotToolkit with SSE event support.
Used by Developer Agent for GUI analysis and visual context.
"""

import os
import logging
from typing import Any, List, Optional

from camel.toolkits import ScreenshotToolkit as BaseScreenshotToolkit
from camel.toolkits import FunctionTool

from .base_toolkit import BaseToolkit

logger = logging.getLogger(__name__)


class ScreenshotToolkit(BaseToolkit):
    """
    Screenshot toolkit for taking and analyzing screenshots.

    Capabilities:
    - Take screenshots of the entire screen
    - Take screenshots of specific windows
    - Save screenshots to files for analysis

    Based on CAMEL's ScreenshotToolkit.
    """

    def __init__(
        self,
        working_directory: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize ScreenshotToolkit.

        Args:
            working_directory: Directory to save screenshots.
                              Defaults to ~/Downloads.
            timeout: Timeout for screenshot operations.
        """
        super().__init__()

        if working_directory is None:
            working_directory = os.path.expanduser("~/Downloads")

        self._working_directory = working_directory
        self._timeout = timeout

        # Initialize CAMEL's base toolkit
        self._base_toolkit = BaseScreenshotToolkit(
            working_directory=working_directory,
            timeout=timeout,
        )

        logger.info(
            f"[ScreenshotToolkit] Initialized with working_directory={working_directory}"
        )

    @staticmethod
    def toolkit_name() -> str:
        """Return toolkit name for identification."""
        return "ScreenshotToolkit"

    def get_tools(self) -> List[FunctionTool]:
        """
        Get all tools from this toolkit.

        Returns:
            List of FunctionTool instances.
        """
        # Get tools from CAMEL's base toolkit
        base_tools = self._base_toolkit.get_tools()

        # Wrap each tool to add SSE event support
        wrapped_tools = []
        for tool in base_tools:
            # Create a wrapper that emits events
            wrapped_tool = self._wrap_tool_with_events(tool)
            wrapped_tools.append(wrapped_tool)

        return wrapped_tools

    def _wrap_tool_with_events(self, tool: FunctionTool) -> FunctionTool:
        """
        Wrap a tool to emit SSE events before/after execution.

        Args:
            tool: Original FunctionTool.

        Returns:
            Wrapped FunctionTool with event emission.
        """
        original_func = tool.func
        tool_name = tool.get_function_name()

        def wrapped_func(*args, **kwargs):
            # Emit tool start event
            self._emit_tool_event(tool_name, "start", kwargs)

            try:
                result = original_func(*args, **kwargs)

                # Emit tool success event
                self._emit_tool_event(tool_name, "success", {"result": str(result)[:500]})

                return result
            except Exception as e:
                # Emit tool error event
                self._emit_tool_event(tool_name, "error", {"error": str(e)})
                raise

        # Create new FunctionTool with wrapped function
        return FunctionTool(
            func=wrapped_func,
            name=tool_name,
            description=tool.get_function_description(),
        )

    def _emit_tool_event(self, tool_name: str, status: str, data: dict) -> None:
        """Emit SSE event for tool execution."""
        if self._task_state is None:
            return

        try:
            from ..events import ToolCallData
            from ..events.toolkit_listen import _run_async_safely

            event = ToolCallData(
                tool_name=tool_name,
                status=status,
                data=data,
            )
            _run_async_safely(self._task_state.put_queue(event))
        except Exception as e:
            logger.debug(f"[ScreenshotToolkit] Failed to emit event: {e}")
