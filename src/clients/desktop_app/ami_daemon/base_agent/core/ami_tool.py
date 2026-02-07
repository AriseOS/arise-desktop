"""
AMI Tool - Lightweight tool wrapper that generates Anthropic-native schemas.

Replaces CAMEL's FunctionTool with a simpler implementation that:
- Generates JSON Schema from Python type hints directly
- Outputs Anthropic tool format (no OpenAI intermediate)
- Supports sync and async callables
- Backward compatible API (get_function_name, set_function_name, etc.)
"""

import asyncio
import inspect
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import docstring_parser

logger = logging.getLogger(__name__)


def _python_type_to_json_schema(annotation: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to JSON Schema.

    Handles: str, int, float, bool, List, Dict, Optional, Union, Literal, Any.
    """
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[X] is Union[X, None]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Optional[X] → schema for X, nullable
            schema = _python_type_to_json_schema(non_none[0])
            if "type" in schema:
                current = schema["type"]
                if isinstance(current, list):
                    if "null" not in current:
                        current.append("null")
                else:
                    schema["type"] = [current, "null"]
            return schema
        else:
            # Union[X, Y, ...] → anyOf
            return {"anyOf": [_python_type_to_json_schema(a) for a in non_none]}

    # Literal["a", "b", "c"]
    if origin is Literal:
        values = list(args)
        if all(isinstance(v, str) for v in values):
            return {"type": "string", "enum": values}
        elif all(isinstance(v, int) for v in values):
            return {"type": "integer", "enum": values}
        return {"enum": values}

    # List[X]
    if origin is list:
        if args:
            return {"type": "array", "items": _python_type_to_json_schema(args[0])}
        return {"type": "array"}

    # Dict[K, V]
    if origin is dict:
        return {"type": "object"}

    # Basic types
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}

    # Enum subclass
    if isinstance(annotation, type) and issubclass(annotation, __import__("enum").Enum):
        values = [e.value for e in annotation]
        return {"enum": values}

    # Fallback
    return {"type": "string"}


class AMITool:
    """Lightweight tool wrapper for AMI agents.

    Wraps a callable (sync or async) and generates Anthropic-native tool schema
    from type hints and docstrings.

    Usage:
        tool = AMITool(self.search_google)
        schema = tool.to_anthropic_schema()
        result = await tool.acall(query="AI trends")
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Initialize AMITool.

        Args:
            func: The callable to wrap (sync or async, bound method or function).
            name: Override function name. If None, uses func.__name__.
            description: Override description. If None, parsed from docstring.
        """
        self.func = func
        self.is_async = asyncio.iscoroutinefunction(func)

        # Name and description
        self._name = name or getattr(func, "__name__", "unknown_tool")
        self._description = description

        # Schema cache (built lazily)
        self._schema_cache: Optional[Dict[str, Any]] = None
        self._input_schema_override: Optional[Dict[str, Any]] = None

        # Build the OpenAI-compatible schema dict for backward compatibility
        # MCP toolkits directly manipulate this structure
        self._openai_compat_schema = self._build_openai_compat_schema()

    @property
    def openai_tool_schema(self) -> Dict[str, Any]:
        """Backward compatible access to OpenAI-format tool schema.

        Used by MCP toolkits that directly set parameters:
            tool.openai_tool_schema["function"]["parameters"] = mcp_schema
        """
        return self._openai_compat_schema

    @openai_tool_schema.setter
    def openai_tool_schema(self, value: Dict[str, Any]) -> None:
        self._openai_compat_schema = value
        self._schema_cache = None  # Invalidate Anthropic cache

    def get_function_name(self) -> str:
        """Get the tool function name."""
        return self._openai_compat_schema["function"]["name"]

    def set_function_name(self, name: str) -> None:
        """Set the tool function name."""
        self._name = name
        self._openai_compat_schema["function"]["name"] = name
        self._schema_cache = None

    def get_function_description(self) -> str:
        """Get the tool function description."""
        return self._openai_compat_schema["function"]["description"]

    def set_function_description(self, description: str) -> None:
        """Set the tool function description."""
        self._description = description
        self._openai_compat_schema["function"]["description"] = description
        self._schema_cache = None

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Generate Anthropic-native tool schema.

        Returns:
            {"name": str, "description": str, "input_schema": {...}}
        """
        if self._schema_cache is not None:
            return self._schema_cache

        # Get parameters from the openai_compat_schema (single source of truth)
        params = self._openai_compat_schema["function"]["parameters"]

        self._schema_cache = {
            "name": self.get_function_name(),
            "description": self.get_function_description(),
            "input_schema": params,
        }
        return self._schema_cache

    def _build_openai_compat_schema(self) -> Dict[str, Any]:
        """Build OpenAI-compatible schema from function signature.

        This is the single source of truth for parameter schema.
        to_anthropic_schema() reads from this.
        MCP toolkits can override parameters directly on this dict.
        """
        description = self._description or self._parse_description()
        input_schema = self._build_input_schema()

        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": description,
                "parameters": input_schema,
            },
        }

    def _parse_description(self) -> str:
        """Parse function description from docstring."""
        doc = inspect.getdoc(self.func)
        if not doc:
            return f"Function {self._name}"

        try:
            parsed = docstring_parser.parse(doc)
            # Use short + long description
            parts = []
            if parsed.short_description:
                parts.append(parsed.short_description)
            if parsed.long_description:
                parts.append(parsed.long_description)
            return "\n".join(parts) if parts else doc.split("\n")[0]
        except Exception:
            return doc.split("\n")[0]

    def _build_input_schema(self) -> Dict[str, Any]:
        """Build JSON Schema for function parameters from type hints."""
        sig = inspect.signature(self.func)
        try:
            hints = get_type_hints(self.func)
        except Exception:
            hints = {}

        # Parse parameter descriptions from docstring
        param_docs = self._parse_param_docs()

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in sig.parameters.items():
            # Skip 'self', 'cls', 'return'
            if param_name in ("self", "cls"):
                continue

            # Get type annotation
            annotation = hints.get(param_name, param.annotation)
            prop_schema = _python_type_to_json_schema(annotation)

            # Add description from docstring
            if param_name in param_docs:
                prop_schema["description"] = param_docs[param_name]

            properties[param_name] = prop_schema

            # Determine if required
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                # Has default value → optional, make nullable
                if "type" in prop_schema:
                    current = prop_schema["type"]
                    if isinstance(current, list):
                        if "null" not in current:
                            current.append("null")
                    else:
                        prop_schema["type"] = [current, "null"]
                # Still add to required for strict mode compliance
                required.append(param_name)

        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

        return schema

    def _parse_param_docs(self) -> Dict[str, str]:
        """Parse parameter descriptions from docstring."""
        doc = inspect.getdoc(self.func)
        if not doc:
            return {}

        try:
            parsed = docstring_parser.parse(doc)
            return {
                p.arg_name: p.description
                for p in parsed.params
                if p.description
            }
        except Exception:
            return {}

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function synchronously.

        If the function is async, runs it in a new event loop.
        """
        try:
            result = self.func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                # Async function called synchronously
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    # Already in async context — use thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, result)
                        return future.result()
                else:
                    return asyncio.run(result)
            return result
        except Exception as e:
            logger.error(f"[AMITool] Error calling {self._name}: {e}")
            raise

    async def acall(self, *args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function asynchronously.

        If the function is sync, runs it in a thread executor.
        """
        if self.is_async:
            return await self.func(*args, **kwargs)
        else:
            return await asyncio.to_thread(self.func, *args, **kwargs)
