# Feature 3: Toolkit Event Decorators (@listen_toolkit, @auto_listen_toolkit)

## Current State Analysis

### Eigent Implementation

**Location:** `third-party/eigent/backend/app/utils/listen/toolkit_listen.py` (lines 79-401)

Eigent provides two decorators for automatic toolkit event emission:

#### 1. @listen_toolkit - Method Decorator

```python
def listen_toolkit(
    wrap_method: Callable[..., Any] | None = None,
    inputs: Callable[..., str] | None = None,
    return_msg: Callable[[Any], str] | None = None,
):
    """
    Decorator that wraps toolkit methods to emit activate/deactivate events.

    Args:
        wrap_method: Original method for signature (optional)
        inputs: Custom function to format input args
        return_msg: Custom function to format return value
    """
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            toolkit = args[0]  # self
            task_lock = get_task_lock(toolkit.api_task_id)

            # Format input arguments
            args_str = format_args(args, kwargs, inputs)

            # EMIT ACTIVATION EVENT
            await task_lock.put_queue(ActionActivateToolkitData(
                data={
                    "agent_name": toolkit.agent_name,
                    "toolkit_name": toolkit.toolkit_name(),
                    "method_name": func.__name__,
                    "message": args_str,
                    "process_task_id": process_task.get("")
                }
            ))

            # Execute actual method
            try:
                result = await func(*args, **kwargs)
                error = None
            except Exception as e:
                error = e
                result = None

            # Format result message
            result_msg = format_result(result, error, return_msg)

            # EMIT DEACTIVATION EVENT
            await task_lock.put_queue(ActionDeactivateToolkitData(
                data={
                    "agent_name": toolkit.agent_name,
                    "toolkit_name": toolkit.toolkit_name(),
                    "method_name": func.__name__,
                    "message": result_msg,
                    "process_task_id": process_task.get("")
                }
            ))

            if error:
                raise error
            return result

        return async_wrapper
    return decorator
```

#### 2. @auto_listen_toolkit - Class Decorator

```python
def auto_listen_toolkit(base_toolkit_class: Type[T]) -> Callable[[Type[T]], Type[T]]:
    """
    Class decorator that automatically wraps all public methods from base toolkit.

    Excluded methods:
    - get_tools, get_can_use_tools: Tool enumeration
    - toolkit_name: Metadata getter
    - run_mcp_server: MCP initialization
    - Pydantic methods: model_dump, dict, json, copy, update

    Usage:
        @auto_listen_toolkit(BaseNoteTakingToolkit)
        class NoteTakingToolkit(BaseNoteTakingToolkit, AbstractToolkit):
            agent_name: str = Agents.document_agent
    """
    def class_decorator(cls: Type[T]) -> Type[T]:
        # Get all public methods from base class
        for method_name in dir(base_toolkit_class):
            if method_name.startswith('_') or method_name in EXCLUDED_METHODS:
                continue

            method = getattr(base_toolkit_class, method_name)
            if not callable(method):
                continue

            # Wrap with @listen_toolkit
            decorated = listen_toolkit(method)(create_wrapper(method_name, method))
            setattr(cls, method_name, decorated)

        return cls
    return class_decorator

EXCLUDED_METHODS = {
    'get_tools', 'get_can_use_tools', 'toolkit_name', 'run_mcp_server',
    'model_dump', 'model_dump_json', 'dict', 'json', 'copy', 'update'
}
```

### 2ami Current State

**Location:** `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/`

Current toolkits use **explicit FunctionTool wrapping**, not decorators:

```python
class TerminalToolkit(BaseToolkit):
    def get_tools(self) -> List[FunctionTool]:
        return [
            FunctionTool(
                func=self.execute_command,
                name="terminal_execute_command",
                description="Execute shell command"
            )
        ]

    async def execute_command(self, command: str) -> str:
        # No event emission here
        result = await self._run_command(command)
        return result
```

**Missing:**
- No automatic event emission on tool execution
- No decorator infrastructure
- Events must be manually emitted in each method

---

## Implementation Plan

### Step 1: Create Decorator Module

**File:** `src/clients/desktop_app/ami_daemon/base_agent/events/toolkit_listen.py` (NEW)

```python
"""
Toolkit event decorators for automatic activate/deactivate event emission.

Provides:
- @listen_toolkit: Method decorator for individual methods
- @auto_listen_toolkit: Class decorator for all public methods
"""
import asyncio
import json
import threading
from functools import wraps
from inspect import iscoroutinefunction, signature
from typing import Any, Callable, Optional, Type, TypeVar, Set
from contextvars import ContextVar

from .action_types import (
    ActionActivateToolkitData,
    ActionDeactivateToolkitData
)

# Context variable for current process task ID
process_task: ContextVar[str] = ContextVar('process_task', default='')

# Maximum argument string length for events
MAX_ARGS_LENGTH = 500
MAX_RESULT_LENGTH = 500

T = TypeVar('T')


def _format_args(args: tuple, kwargs: dict, custom_formatter: Optional[Callable] = None) -> str:
    """Format function arguments for event message"""
    if custom_formatter is not None:
        try:
            return custom_formatter(*args, **kwargs)
        except Exception:
            pass

    # Default formatting: skip self argument
    filtered_args = args[1:] if len(args) > 0 else []
    args_str = ", ".join(repr(arg) for arg in filtered_args)
    if kwargs:
        kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        args_str = f"{args_str}, {kwargs_str}" if args_str else kwargs_str

    # Truncate if too long
    if len(args_str) > MAX_ARGS_LENGTH:
        args_str = args_str[:MAX_ARGS_LENGTH] + f"... (truncated)"

    return args_str


def _format_result(result: Any, error: Optional[Exception], custom_formatter: Optional[Callable] = None) -> str:
    """Format function result for event message"""
    if error is not None:
        return f"Error: {str(error)}"

    if custom_formatter is not None:
        try:
            return custom_formatter(result)
        except Exception:
            pass

    # Default formatting
    if isinstance(result, str):
        result_str = result
    else:
        try:
            result_str = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            result_str = str(result)

    # Truncate if too long
    if len(result_str) > MAX_RESULT_LENGTH:
        result_str = result_str[:MAX_RESULT_LENGTH] + f"... (truncated)"

    return result_str


async def _emit_activate(toolkit: Any, method_name: str, args_str: str) -> None:
    """Emit toolkit activation event"""
    if not hasattr(toolkit, '_task_state') or toolkit._task_state is None:
        return

    state = toolkit._task_state
    if not hasattr(state, 'emitter') or state.emitter is None:
        return

    await state.emitter.emit(ActionActivateToolkitData(
        data={
            "agent_name": getattr(toolkit, 'agent_name', 'unknown'),
            "toolkit_name": toolkit.toolkit_name() if hasattr(toolkit, 'toolkit_name') else toolkit.__class__.__name__,
            "method_name": method_name.replace("_", " "),
            "message": args_str,
            "process_task_id": process_task.get('')
        }
    ))


async def _emit_deactivate(toolkit: Any, method_name: str, result_msg: str) -> None:
    """Emit toolkit deactivation event"""
    if not hasattr(toolkit, '_task_state') or toolkit._task_state is None:
        return

    state = toolkit._task_state
    if not hasattr(state, 'emitter') or state.emitter is None:
        return

    await state.emitter.emit(ActionDeactivateToolkitData(
        data={
            "agent_name": getattr(toolkit, 'agent_name', 'unknown'),
            "toolkit_name": toolkit.toolkit_name() if hasattr(toolkit, 'toolkit_name') else toolkit.__class__.__name__,
            "method_name": method_name.replace("_", " "),
            "message": result_msg,
            "process_task_id": process_task.get('')
        }
    ))


def _safe_emit(coro) -> None:
    """Safely emit event, handling both sync and async contexts"""
    try:
        loop = asyncio.get_running_loop()
        # In async context, create task
        task = asyncio.create_task(coro)
        task.add_done_callback(lambda t: None if not t.exception() else None)
    except RuntimeError:
        # No running loop, run in new thread
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(coro)
            finally:
                new_loop.close()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()


def listen_toolkit(
    wrap_method: Optional[Callable[..., Any]] = None,
    inputs: Optional[Callable[..., str]] = None,
    return_msg: Optional[Callable[[Any], str]] = None,
    skip_events: bool = False
):
    """
    Decorator that wraps toolkit methods to emit activate/deactivate events.

    Args:
        wrap_method: Original method for signature extraction (optional)
        inputs: Custom function to format input arguments
        return_msg: Custom function to format return value
        skip_events: If True, skip event emission (useful for internal methods)

    Usage:
        class MyToolkit(BaseToolkit):
            @listen_toolkit
            async def my_method(self, arg1: str) -> str:
                return "result"

            @listen_toolkit(inputs=lambda self, cmd: f"Command: {cmd}")
            async def execute(self, command: str) -> str:
                return await self._run(command)
    """
    def decorator(func: Callable[..., Any]):
        wrap = func if wrap_method is None else wrap_method

        if iscoroutinefunction(func):
            # Async function wrapper
            @wraps(wrap)
            async def async_wrapper(*args, **kwargs):
                toolkit = args[0]  # self

                # Skip events if requested or toolkit doesn't support it
                if skip_events or not hasattr(toolkit, '_task_state'):
                    return await func(*args, **kwargs)

                method_name = func.__name__
                args_str = _format_args(args, kwargs, inputs)

                # Emit activation
                await _emit_activate(toolkit, method_name, args_str)

                # Execute method
                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    error = e

                # Format and emit deactivation
                result_msg = _format_result(result, error, return_msg)
                await _emit_deactivate(toolkit, method_name, result_msg)

                if error is not None:
                    raise error
                return result

            return async_wrapper

        else:
            # Sync function wrapper
            @wraps(wrap)
            def sync_wrapper(*args, **kwargs):
                toolkit = args[0]  # self

                if skip_events or not hasattr(toolkit, '_task_state'):
                    return func(*args, **kwargs)

                method_name = func.__name__
                args_str = _format_args(args, kwargs, inputs)

                # Emit activation (safely handles async)
                _safe_emit(_emit_activate(toolkit, method_name, args_str))

                # Execute method
                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    error = e

                # Format and emit deactivation
                result_msg = _format_result(result, error, return_msg)
                _safe_emit(_emit_deactivate(toolkit, method_name, result_msg))

                if error is not None:
                    raise error
                return result

            return sync_wrapper

    # Support both @listen_toolkit and @listen_toolkit()
    if wrap_method is not None and callable(wrap_method) and not isinstance(wrap_method, type):
        # Called as @listen_toolkit (without parens)
        return decorator(wrap_method)

    return decorator


# Methods excluded from auto-decoration
EXCLUDED_METHODS: Set[str] = {
    # Tool enumeration
    'get_tools',
    'get_can_use_tools',

    # Metadata getters
    'toolkit_name',
    'toolkit_description',

    # Initialization
    'run_mcp_server',
    'initialize',
    'setup',
    'cleanup',

    # Pydantic model methods
    'model_dump',
    'model_dump_json',
    'model_validate',
    'model_copy',
    'dict',
    'json',
    'copy',
    'update',

    # Internal methods
    'validate',
    'configure',
}


def auto_listen_toolkit(base_toolkit_class: Type[T]) -> Callable[[Type[T]], Type[T]]:
    """
    Class decorator that automatically wraps all public methods from base toolkit.

    Automatically applies @listen_toolkit to all public methods inherited from
    the base class, excluding utility methods like get_tools, toolkit_name, etc.

    Args:
        base_toolkit_class: The base class whose methods should be wrapped

    Usage:
        @auto_listen_toolkit(BaseTerminalToolkit)
        class TerminalToolkit(BaseTerminalToolkit):
            agent_name: str = "terminal_agent"

            # All inherited methods will emit events automatically
            # Override methods will also emit events
    """
    def class_decorator(cls: Type[T]) -> Type[T]:
        # Collect base class methods to wrap
        base_methods = {}
        for name in dir(base_toolkit_class):
            # Skip private and excluded methods
            if name.startswith('_') or name in EXCLUDED_METHODS:
                continue

            attr = getattr(base_toolkit_class, name)
            if callable(attr) and not isinstance(attr, type):
                base_methods[name] = attr

        # Wrap each method
        for method_name, base_method in base_methods.items():
            # Check if method is overridden in subclass
            if method_name in cls.__dict__:
                overridden = cls.__dict__[method_name]

                # Check if already decorated
                if hasattr(overridden, '__wrapped__'):
                    continue

                # Wrap the overridden method
                decorated = listen_toolkit(base_method)(overridden)
                setattr(cls, method_name, decorated)
            else:
                # Create wrapper that calls super
                sig = signature(base_method)

                if iscoroutinefunction(base_method):
                    async def make_async_wrapper(name):
                        async def wrapper(self, *args, **kwargs):
                            return await getattr(super(cls, self), name)(*args, **kwargs)
                        wrapper.__name__ = name
                        wrapper.__signature__ = sig
                        return wrapper

                    wrapper = asyncio.get_event_loop().run_until_complete(
                        make_async_wrapper(method_name)
                    ) if False else None  # Can't await here

                    # Alternative: create wrapper directly
                    async def async_wrapper(self, *args, _method_name=method_name, **kwargs):
                        return await getattr(super(cls, self), _method_name)(*args, **kwargs)
                    async_wrapper.__name__ = method_name
                    wrapper = async_wrapper
                else:
                    def sync_wrapper(self, *args, _method_name=method_name, **kwargs):
                        return getattr(super(cls, self), _method_name)(*args, **kwargs)
                    sync_wrapper.__name__ = method_name
                    wrapper = sync_wrapper

                # Decorate and set
                decorated = listen_toolkit(base_method)(wrapper)
                setattr(cls, method_name, decorated)

        return cls

    return class_decorator


class set_process_task:
    """
    Context manager for setting process task ID.

    Usage:
        with set_process_task("task_123"):
            await toolkit.execute_command("ls")
    """
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.token = None

    def __enter__(self):
        self.token = process_task.set(self.task_id)
        return self

    def __exit__(self, *args):
        process_task.reset(self.token)
```

### Step 2: Update Base Toolkit Class

**File:** `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/base_toolkit.py`

Add task state support:

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...services.quick_task_service import TaskState


class BaseToolkit(ABC):
    """Base class for all toolkits"""

    # Task state for event emission
    _task_state: Optional['TaskState'] = None

    # Agent name for event tracking
    agent_name: str = "unknown"

    def set_task_state(self, state: 'TaskState') -> None:
        """Set task state for event emission"""
        self._task_state = state

    def toolkit_name(self) -> str:
        """Return toolkit name for events"""
        return self.__class__.__name__.replace("Toolkit", "")

    @abstractmethod
    def get_tools(self) -> List['FunctionTool']:
        """Return list of tools provided by this toolkit"""
        pass
```

### Step 3: Apply Decorators to Terminal Toolkit

**File:** `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/terminal_toolkit.py`

```python
from ..events.toolkit_listen import listen_toolkit, auto_listen_toolkit
from .base_toolkit import BaseToolkit


class BaseTerminalToolkit(BaseToolkit):
    """Base terminal toolkit with core methods"""

    async def execute_command(self, command: str, timeout: int = 120) -> str:
        """Execute shell command"""
        # Implementation
        pass

    async def read_file(self, path: str) -> str:
        """Read file contents"""
        pass

    async def write_file(self, path: str, content: str) -> str:
        """Write content to file"""
        pass


@auto_listen_toolkit(BaseTerminalToolkit)
class TerminalToolkit(BaseTerminalToolkit):
    """Terminal toolkit with automatic event emission"""

    agent_name: str = "terminal_agent"

    # All inherited methods (execute_command, read_file, write_file)
    # will automatically emit activate/deactivate events

    # Custom method with explicit decorator
    @listen_toolkit(
        inputs=lambda self, cmd, **kw: f"$ {cmd}",
        return_msg=lambda r: r[:200] if len(r) > 200 else r
    )
    async def execute_command(self, command: str, timeout: int = 120) -> str:
        """Execute command with custom event formatting"""
        return await super().execute_command(command, timeout)
```

### Step 4: Apply to Browser Toolkit

**File:** `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/browser_toolkit.py`

```python
from ..events.toolkit_listen import listen_toolkit


class BrowserToolkit(BaseToolkit):
    agent_name: str = "browser_agent"

    @listen_toolkit(
        inputs=lambda self, selector: f"Click: {selector}",
        return_msg=lambda r: "Clicked successfully" if r else "Click failed"
    )
    async def click(self, selector: str) -> bool:
        """Click element by selector"""
        pass

    @listen_toolkit(
        inputs=lambda self, selector, text: f"Type '{text}' into {selector}"
    )
    async def type_text(self, selector: str, text: str) -> bool:
        """Type text into element"""
        pass

    @listen_toolkit(
        inputs=lambda self, url: f"Navigate to: {url}"
    )
    async def navigate(self, url: str) -> bool:
        """Navigate to URL"""
        pass

    @listen_toolkit(skip_events=True)  # Internal method, no events
    async def _get_page_snapshot(self) -> str:
        """Get page DOM snapshot (internal)"""
        pass
```

### Step 5: Integration in Agent

**File:** `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py`

```python
from ..events.toolkit_listen import set_process_task

class EigentStyleBrowserAgent:

    async def _execute_tool(self, tool_call: dict) -> str:
        """Execute tool call with event emission"""
        tool_name = tool_call['name']
        tool_args = tool_call['arguments']

        # Get toolkit and method
        toolkit, method = self._get_tool_method(tool_name)

        # Set task state on toolkit for event emission
        if hasattr(toolkit, 'set_task_state'):
            toolkit.set_task_state(self._task_state)

        # Execute with process task context
        with set_process_task(self._current_step_id):
            if asyncio.iscoroutinefunction(method):
                result = await method(**tool_args)
            else:
                result = method(**tool_args)

        return result
```

---

## Migration Checklist

- [ ] Create `events/toolkit_listen.py` module
- [ ] Implement `@listen_toolkit` decorator (async + sync)
- [ ] Implement `@auto_listen_toolkit` class decorator
- [ ] Implement `set_process_task` context manager
- [ ] Update `BaseToolkit` with `_task_state` and `set_task_state()`
- [ ] Apply decorators to `TerminalToolkit`
- [ ] Apply decorators to `BrowserToolkit`
- [ ] Apply decorators to `NoteTakingToolkit`
- [ ] Apply decorators to `SearchToolkit`
- [ ] Apply decorators to `HumanToolkit`
- [ ] Update agent to set task state on toolkits
- [ ] Add unit tests for decorator behavior
- [ ] Add integration tests for event emission

---

## Decorator Decision Tree

```
Is method internal/utility?
├── Yes → @listen_toolkit(skip_events=True) or no decorator
└── No → Does class inherit from base toolkit?
         ├── Yes → Use @auto_listen_toolkit on class
         │         └── Override specific methods with @listen_toolkit if needed
         └── No → Use @listen_toolkit on each method

Need custom message formatting?
├── Yes → @listen_toolkit(inputs=..., return_msg=...)
└── No → @listen_toolkit (default formatting)
```

---

## Testing Strategy

1. **Unit Tests:**
   - Test decorator with async/sync functions
   - Test event emission format
   - Test custom formatters
   - Test `skip_events` flag

2. **Integration Tests:**
   - Test full toolkit execution with events
   - Test event ordering (activate before deactivate)
   - Test error handling (deactivate still emitted on error)

3. **Manual Testing:**
   - Execute tool and verify events in SSE stream
   - Verify method_name is human-readable
   - Verify args/result truncation works
