"""
Toolkit Event Decorators for Automatic Event Emission.

Provides:
- @listen_toolkit: Method decorator for individual methods
- @auto_listen_toolkit: Class decorator for all public methods
- set_process_task: Context manager for process task ID

These decorators automatically emit activate/deactivate events when
toolkit methods are called, enabling real-time progress tracking.
"""

import asyncio
import json
import logging
import threading
import time
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction, signature
from typing import Any, Callable, Optional, Set, Type, TypeVar

from .action_types import ActivateToolkitData, DeactivateToolkitData

logger = logging.getLogger(__name__)

# Context variable for current process task ID
process_task: ContextVar[str] = ContextVar('process_task', default='')

# Maximum argument/result string length for events
MAX_ARGS_LENGTH = 500
MAX_RESULT_LENGTH = 500

T = TypeVar('T')


def _format_args(
    args: tuple,
    kwargs: dict,
    custom_formatter: Optional[Callable] = None
) -> str:
    """
    Format function arguments for event message.

    Args:
        args: Positional arguments (first is usually self)
        kwargs: Keyword arguments
        custom_formatter: Optional custom formatting function

    Returns:
        Formatted argument string
    """
    if custom_formatter is not None:
        try:
            return str(custom_formatter(*args, **kwargs))
        except Exception as e:
            logger.debug(f"Custom formatter failed: {e}")

    # Default formatting: skip self argument
    filtered_args = args[1:] if len(args) > 0 else []

    parts = []
    for arg in filtered_args:
        if isinstance(arg, str) and len(arg) > 100:
            parts.append(f"'{arg[:100]}...'")
        else:
            parts.append(repr(arg))

    args_str = ", ".join(parts)

    if kwargs:
        kwargs_parts = []
        for k, v in kwargs.items():
            if isinstance(v, str) and len(v) > 100:
                kwargs_parts.append(f"{k}='{v[:100]}...'")
            else:
                kwargs_parts.append(f"{k}={v!r}")
        kwargs_str = ", ".join(kwargs_parts)
        args_str = f"{args_str}, {kwargs_str}" if args_str else kwargs_str

    # Truncate if too long
    if len(args_str) > MAX_ARGS_LENGTH:
        args_str = args_str[:MAX_ARGS_LENGTH] + "... (truncated)"

    return args_str


def _format_result(
    result: Any,
    error: Optional[Exception],
    custom_formatter: Optional[Callable] = None
) -> str:
    """
    Format function result for event message.

    Args:
        result: Function return value
        error: Exception if any
        custom_formatter: Optional custom formatting function

    Returns:
        Formatted result string
    """
    if error is not None:
        return f"Error: {type(error).__name__}: {str(error)}"

    if custom_formatter is not None:
        try:
            return str(custom_formatter(result))
        except Exception as e:
            logger.debug(f"Custom result formatter failed: {e}")

    # Default formatting
    if result is None:
        return "Done"

    if isinstance(result, str):
        result_str = result
    elif isinstance(result, bool):
        result_str = "Success" if result else "Failed"
    elif isinstance(result, (int, float)):
        result_str = str(result)
    elif isinstance(result, (list, tuple)):
        result_str = f"[{len(result)} items]"
    elif isinstance(result, dict):
        result_str = f"{{{len(result)} keys}}"
    else:
        try:
            result_str = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            result_str = str(result)

    # Truncate if too long
    if len(result_str) > MAX_RESULT_LENGTH:
        result_str = result_str[:MAX_RESULT_LENGTH] + "... (truncated)"

    return result_str


async def _emit_activate(
    toolkit: Any,
    method_name: str,
    args_str: str,
    start_time: float
) -> None:
    """
    Emit toolkit activation event.

    Args:
        toolkit: The toolkit instance
        method_name: Name of the method being called
        args_str: Formatted arguments string
        start_time: Execution start time
    """
    # Check if toolkit has task state for event emission
    if not hasattr(toolkit, '_task_state') or toolkit._task_state is None:
        return

    state = toolkit._task_state
    if not hasattr(state, 'put_event'):
        return

    # Get toolkit metadata
    agent_name = getattr(toolkit, 'agent_name', 'unknown')
    if hasattr(toolkit, 'toolkit_name') and callable(toolkit.toolkit_name):
        toolkit_name = toolkit.toolkit_name()
    else:
        toolkit_name = toolkit.__class__.__name__.replace("Toolkit", "")

    # Human-readable method name
    display_name = method_name.replace("_", " ").title()

    try:
        await state.put_event(ActivateToolkitData(
            task_id=getattr(state, 'task_id', None),
            toolkit_name=toolkit_name,
            method_name=display_name,
            agent_name=agent_name,
            process_task_id=process_task.get(''),
            input_preview=args_str,
            message=f"Executing {display_name}",
        ))
    except Exception as e:
        logger.warning(f"Failed to emit activate event: {e}")


async def _emit_deactivate(
    toolkit: Any,
    method_name: str,
    result_msg: str,
    success: bool,
    start_time: float
) -> None:
    """
    Emit toolkit deactivation event.

    Args:
        toolkit: The toolkit instance
        method_name: Name of the method being called
        result_msg: Formatted result string
        success: Whether execution succeeded
        start_time: Execution start time for duration calculation
    """
    if not hasattr(toolkit, '_task_state') or toolkit._task_state is None:
        return

    state = toolkit._task_state
    if not hasattr(state, 'put_event'):
        return

    # Get toolkit metadata
    agent_name = getattr(toolkit, 'agent_name', 'unknown')
    if hasattr(toolkit, 'toolkit_name') and callable(toolkit.toolkit_name):
        toolkit_name = toolkit.toolkit_name()
    else:
        toolkit_name = toolkit.__class__.__name__.replace("Toolkit", "")

    display_name = method_name.replace("_", " ").title()
    duration_ms = int((time.time() - start_time) * 1000)

    try:
        await state.put_event(DeactivateToolkitData(
            task_id=getattr(state, 'task_id', None),
            toolkit_name=toolkit_name,
            method_name=display_name,
            agent_name=agent_name,
            process_task_id=process_task.get(''),
            output_preview=result_msg,
            success=success,
            duration_ms=duration_ms,
            message=result_msg,
        ))
    except Exception as e:
        logger.warning(f"Failed to emit deactivate event: {e}")


def _run_async_safely(coro, toolkit=None) -> None:
    """
    Run async coroutine safely from sync context.

    Based on Eigent's _safe_put_queue pattern with proper task tracking.

    Args:
        coro: Coroutine to execute
        toolkit: Optional toolkit instance for background task tracking
    """
    try:
        loop = asyncio.get_running_loop()
        # In async context, create task
        task = asyncio.create_task(coro)

        # Track background task if toolkit has task state with tracking
        if toolkit and hasattr(toolkit, '_task_state'):
            state = toolkit._task_state
            if state and hasattr(state, 'add_background_task'):
                state.add_background_task(task)

        # Add done callback to handle any exceptions
        def handle_task_result(t):
            try:
                t.result()
            except asyncio.CancelledError:
                pass  # Task was cancelled, not an error
            except Exception as e:
                logger.warning(f"Event emit task failed: {e}")

        task.add_done_callback(handle_task_result)

    except RuntimeError:
        # No running event loop - run in a separate thread with brief wait
        import queue
        result_queue = queue.Queue()

        def run_in_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(coro)
                    result_queue.put(("success", None))
                except Exception as e:
                    logger.warning(f"Thread event emit failed: {e}")
                    result_queue.put(("error", e))
                finally:
                    new_loop.close()
            except Exception as e:
                logger.warning(f"Thread setup failed: {e}")
                result_queue.put(("error", e))

        # Use daemon=False to ensure event delivery even during shutdown
        thread = threading.Thread(target=run_in_thread, daemon=False)
        thread.start()

        # Wait briefly for completion (based on Eigent's pattern)
        try:
            status, error = result_queue.get(timeout=1.0)
            if status == "error" and error:
                logger.warning(f"Event emit thread error: {error}")
        except queue.Empty:
            # Timeout - thread is still running, log and continue
            logger.debug("Event emit thread timeout after 1s, continuing...")


def listen_toolkit(
    wrap_method: Optional[Callable[..., Any]] = None,
    inputs: Optional[Callable[..., str]] = None,
    return_msg: Optional[Callable[[Any], str]] = None,
    skip_events: bool = False,
):
    """
    Decorator that wraps toolkit methods to emit activate/deactivate events.

    This decorator automatically emits events when a toolkit method is called
    and when it completes (or fails). Events are only emitted if the toolkit
    has a _task_state attribute with an event emitter.

    Args:
        wrap_method: Original method for signature extraction (optional)
        inputs: Custom function to format input arguments
        return_msg: Custom function to format return value
        skip_events: If True, skip event emission (for internal methods)

    Usage:
        class MyToolkit(BaseToolkit):
            @listen_toolkit
            async def my_method(self, arg1: str) -> str:
                return "result"

            @listen_toolkit(inputs=lambda self, cmd: f"$ {cmd}")
            async def execute(self, command: str) -> str:
                return await self._run(command)

            @listen_toolkit(skip_events=True)
            async def _internal_method(self) -> None:
                # No events emitted
                pass
    """
    def decorator(func: Callable[..., Any]):
        wrap = func if wrap_method is None else wrap_method

        if iscoroutinefunction(func):
            # Async function wrapper
            @wraps(wrap)
            async def async_wrapper(*args, **kwargs):
                toolkit = args[0] if args else None

                # Skip events if requested or toolkit doesn't support it
                if skip_events or toolkit is None or not hasattr(toolkit, '_task_state'):
                    return await func(*args, **kwargs)

                method_name = func.__name__
                args_str = _format_args(args, kwargs, inputs)
                start_time = time.time()

                # Emit activation event
                await _emit_activate(toolkit, method_name, args_str, start_time)

                # Execute method
                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    error = e

                # Format and emit deactivation
                result_msg = _format_result(result, error, return_msg)
                await _emit_deactivate(
                    toolkit, method_name, result_msg,
                    success=(error is None), start_time=start_time
                )

                if error is not None:
                    raise error
                return result

            return async_wrapper

        else:
            # Sync function wrapper
            @wraps(wrap)
            def sync_wrapper(*args, **kwargs):
                toolkit = args[0] if args else None

                if skip_events or toolkit is None or not hasattr(toolkit, '_task_state'):
                    return func(*args, **kwargs)

                method_name = func.__name__
                args_str = _format_args(args, kwargs, inputs)
                start_time = time.time()

                # Emit activation (async-safe, with toolkit for task tracking)
                _run_async_safely(
                    _emit_activate(toolkit, method_name, args_str, start_time),
                    toolkit=toolkit
                )

                # Execute method
                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    error = e

                # Format and emit deactivation
                result_msg = _format_result(result, error, return_msg)
                _run_async_safely(
                    _emit_deactivate(
                        toolkit, method_name, result_msg,
                        success=(error is None), start_time=start_time
                    ),
                    toolkit=toolkit
                )

                if error is not None:
                    raise error
                return result

            return sync_wrapper

    # Support both @listen_toolkit and @listen_toolkit()
    if wrap_method is not None and callable(wrap_method) and not isinstance(wrap_method, type):
        # Called as @listen_toolkit without parentheses
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

    # Initialization and lifecycle
    'run_mcp_server',
    'initialize',
    'setup',
    'cleanup',
    'close',

    # Task state management
    'set_task_state',
    'get_task_state',

    # Pydantic model methods
    'model_dump',
    'model_dump_json',
    'model_validate',
    'model_copy',
    'model_fields',
    'model_config',
    'dict',
    'json',
    'copy',
    'update',

    # Internal/utility methods
    'validate',
    'configure',

    # Registry methods
    '_load_registry',
    '_save_registry',
    '_register_note',
}


def auto_listen_toolkit(base_toolkit_class: Type[T]) -> Callable[[Type[T]], Type[T]]:
    """
    Class decorator that automatically wraps all public methods from base toolkit.

    Automatically applies @listen_toolkit to all public methods defined in
    the base class, excluding utility methods like get_tools, toolkit_name, etc.

    Args:
        base_toolkit_class: The base class whose methods should be wrapped

    Usage:
        class BaseTerminalToolkit:
            async def execute_command(self, cmd: str) -> str:
                pass

        @auto_listen_toolkit(BaseTerminalToolkit)
        class TerminalToolkit(BaseTerminalToolkit):
            agent_name = "terminal_agent"

            # execute_command will automatically emit events
            # Override with @listen_toolkit for custom formatting:

            @listen_toolkit(inputs=lambda self, cmd: f"$ {cmd}")
            async def execute_command(self, cmd: str) -> str:
                return await super().execute_command(cmd)
    """
    def class_decorator(cls: Type[T]) -> Type[T]:
        # Collect base class methods to wrap
        base_methods = {}
        for name in dir(base_toolkit_class):
            # Skip private/dunder and excluded methods
            if name.startswith('_') or name in EXCLUDED_METHODS:
                continue

            attr = getattr(base_toolkit_class, name, None)
            if attr is None:
                continue

            # Only wrap callable methods (not properties or class attributes)
            if callable(attr) and not isinstance(attr, type):
                base_methods[name] = attr

        # Wrap each method
        for method_name, base_method in base_methods.items():
            # Check if method is overridden in subclass
            if method_name in cls.__dict__:
                overridden = cls.__dict__[method_name]

                # Skip if already decorated (has __wrapped__)
                if hasattr(overridden, '__wrapped__'):
                    continue

                # Skip if it's a property or classmethod
                if isinstance(overridden, (property, classmethod, staticmethod)):
                    continue

                # Wrap the overridden method
                decorated = listen_toolkit(base_method)(overridden)
                setattr(cls, method_name, decorated)
            else:
                # Method not overridden - create a wrapper that calls super
                if iscoroutinefunction(base_method):
                    # Async wrapper
                    def make_async_wrapper(name):
                        async def wrapper(self, *args, **kwargs):
                            parent_method = getattr(super(cls, self), name)
                            return await parent_method(*args, **kwargs)
                        wrapper.__name__ = name
                        wrapper.__doc__ = getattr(base_method, '__doc__', None)
                        return wrapper

                    wrapper = make_async_wrapper(method_name)
                else:
                    # Sync wrapper
                    def make_sync_wrapper(name):
                        def wrapper(self, *args, **kwargs):
                            parent_method = getattr(super(cls, self), name)
                            return parent_method(*args, **kwargs)
                        wrapper.__name__ = name
                        wrapper.__doc__ = getattr(base_method, '__doc__', None)
                        return wrapper

                    wrapper = make_sync_wrapper(method_name)

                # Decorate and set
                decorated = listen_toolkit(base_method)(wrapper)
                setattr(cls, method_name, decorated)

        return cls

    return class_decorator


class set_process_task:
    """
    Context manager for setting the current process task ID.

    This sets a context variable that decorators use to include
    the process task ID in emitted events.

    Usage:
        with set_process_task("task_123"):
            await toolkit.execute_command("ls")
            # Events will include process_task_id="task_123"

    Can also be used as an async context manager:
        async with set_process_task("task_123"):
            await toolkit.execute_command("ls")
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.token = None

    def __enter__(self):
        self.token = process_task.set(self.task_id)
        return self

    def __exit__(self, *args):
        if self.token is not None:
            process_task.reset(self.token)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)
