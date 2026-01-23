"""
Base Toolkit - Foundation for all tool integrations.

Ported from CAMEL-AI/Eigent project for Tool-calling architecture.
Supports both OpenAI and Anthropic tool use formats.

Features:
- Automatic tool definition generation from function signatures
- Support for both OpenAI and Anthropic formats
- Task state integration for event emission via decorators
"""

import inspect
import logging
import re
from abc import ABC
from typing import Any, Callable, Dict, List, Optional, Union, get_type_hints, get_origin, get_args, TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular import - TaskState is only used for type hints
    pass

logger = logging.getLogger(__name__)


def _parse_docstring_params(docstring: str) -> Dict[str, str]:
    """Parse parameter descriptions from docstring.

    Supports Google-style docstrings:
        Args:
            param_name: Description of the parameter.
            param_name (type): Description of the parameter.
    """
    if not docstring:
        return {}

    params = {}
    # Match Args section
    args_match = re.search(r'Args:\s*\n((?:\s+.+\n?)+)', docstring)
    if args_match:
        args_section = args_match.group(1)
        # Match each parameter line
        param_pattern = r'\s+(\w+)(?:\s*\([^)]*\))?:\s*(.+?)(?=\n\s+\w+(?:\s*\([^)]*\))?:|$)'
        for match in re.finditer(param_pattern, args_section, re.DOTALL):
            param_name = match.group(1)
            param_desc = match.group(2).strip().replace('\n', ' ')
            # Clean up multi-line descriptions
            param_desc = re.sub(r'\s+', ' ', param_desc)
            params[param_name] = param_desc

    return params


class FunctionTool:
    """Wrapper for a callable function that can be used as a tool.

    Converts a Python function into a tool definition that can be used
    by LLM function calling (supports both OpenAI and Anthropic formats).
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Initialize a FunctionTool.

        Args:
            func: The callable function to wrap.
            name: Optional override for the tool name (defaults to func.__name__).
            description: Optional override for the description (defaults to func docstring).
        """
        self.func = func
        self.name = name or func.__name__

        # Extract description from docstring (first paragraph only)
        raw_doc = func.__doc__ or ""
        if description:
            self.description = description
        else:
            # Get first paragraph before Args:
            doc_parts = raw_doc.split('\n\n')
            first_para = doc_parts[0].strip() if doc_parts else ""
            # Remove Args: section if present
            if 'Args:' in first_para:
                first_para = first_para.split('Args:')[0].strip()
            self.description = first_para or f"Execute {self.name}"

        # Parse parameter descriptions from docstring
        self._param_descriptions = _parse_docstring_params(raw_doc)

        # Extract parameter info from function signature
        self.parameters = self._extract_parameters()

    def _get_type_string(self, annotation: Any) -> str:
        """Convert Python type annotation to JSON schema type."""
        if annotation == inspect.Parameter.empty:
            return "string"

        # Handle Optional types
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            # Optional[X] is Union[X, None]
            non_none_args = [a for a in args if a is not type(None)]
            if non_none_args:
                return self._get_type_string(non_none_args[0])
            return "string"

        # Handle basic types
        if annotation == int:
            return "integer"
        elif annotation == float:
            return "number"
        elif annotation == bool:
            return "boolean"
        elif annotation == str:
            return "string"
        elif origin in (list, List):
            return "array"
        elif origin in (dict, Dict):
            return "object"
        elif annotation == list:
            return "array"
        elif annotation == dict:
            return "object"

        return "string"

    def _extract_parameters(self) -> Dict[str, Any]:
        """Extract parameter schema from function signature with descriptions."""
        sig = inspect.signature(self.func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Get type
            param_type = self._get_type_string(param.annotation)

            # Build property definition
            prop_def = {"type": param_type}

            # Add description if available
            if param_name in self._param_descriptions:
                prop_def["description"] = self._param_descriptions[param_name]

            # Add default value if present
            if param.default != inspect.Parameter.empty:
                if param.default is not None:
                    prop_def["default"] = param.default
            else:
                # No default means required
                required.append(param_name)

            properties[param_name] = prop_def

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def __call__(self, **kwargs) -> Any:
        """Execute the wrapped function."""
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        return self.func(**kwargs)

    def call_sync(self, **kwargs) -> Any:
        """Execute the wrapped function synchronously.

        Note: This method cannot be called from within an async context
        if the wrapped function is async. Use 'await tool(**kwargs)' instead.
        """
        if inspect.iscoroutinefunction(self.func):
            import asyncio
            try:
                # Check if we're already in an async context
                asyncio.get_running_loop()
                raise RuntimeError(
                    "call_sync() cannot be called from within an async context. "
                    "Use 'await tool(**kwargs)' instead."
                )
            except RuntimeError as e:
                if "no running event loop" in str(e):
                    # No running loop, safe to use asyncio.run()
                    return asyncio.run(self.func(**kwargs))
                raise
        return self.func(**kwargs)

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """Convert to Anthropic tool use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class BaseToolkit(ABC):
    """Base class for all toolkits.

    A toolkit is a collection of related tools that can be used by agents.

    Attributes:
        timeout: Optional timeout for tool operations in seconds.
        agent_name: Name of the agent using this toolkit (for event tracking).
        _task_state: Task state for event emission via decorators.
    """

    # Agent name for event tracking (can be overridden by subclasses)
    agent_name: str = "unknown"

    # Task state for event emission (set by agent before tool execution)
    _task_state: Optional[Any] = None

    def __init__(self, timeout: Optional[float] = None):
        """Initialize the toolkit.

        Args:
            timeout: Optional timeout for tool operations in seconds.
        """
        self.timeout = timeout
        self._task_state = None

    def set_task_state(self, state: Any) -> None:
        """Set task state for event emission.

        This is called by the agent before executing tools to enable
        automatic event emission via @listen_toolkit decorators.

        Args:
            state: TaskState instance with event emitter.
        """
        self._task_state = state

    def get_task_state(self) -> Optional[Any]:
        """Get current task state.

        Returns:
            TaskState instance or None if not set.
        """
        return self._task_state

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects.

        Subclasses should override this to return their specific tools.

        Returns:
            List of FunctionTool objects representing available tools.
        """
        raise NotImplementedError("Subclasses must implement get_tools()")

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit.

        Returns:
            String name of the toolkit (without 'Toolkit' suffix).
        """
        name = cls.__name__
        if name.endswith("Toolkit"):
            name = name[:-7]  # Remove "Toolkit" suffix
        return name
