"""
Budget Controller Module

Controls and enforces budget limits during task execution.
Based on Eigent's budget tracking via CAMEL's ModelProcessingError pattern.

References:
- Eigent: third-party/eigent/backend/app/utils/agent.py
- CAMEL: https://github.com/camel-ai/camel/blob/master/camel/utils/budget.py
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .cost_calculator import get_cheaper_model
from .token_usage import SessionTokenUsage, TokenUsage

logger = logging.getLogger(__name__)


class BudgetExceedAction(str, Enum):
    """Action to take when budget is exceeded."""
    STOP = "stop"           # Stop execution immediately
    WARN = "warn"           # Continue but emit warning
    CONFIRM = "confirm"     # Ask user for confirmation
    THROTTLE = "throttle"   # Reduce capability (use cheaper model)


class BudgetExceededException(Exception):
    """Raised when budget is exceeded and action is STOP.

    Similar to CAMEL's ModelProcessingError for budget tracking.
    """

    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.task_id = task_id
        self.usage = usage or {}


@dataclass
class BudgetConfig:
    """Budget configuration for a task/session.

    Supports both token-based and cost-based limits with configurable
    warning thresholds and exceed actions.
    """
    # Token limits
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None

    # Cost limits (in USD)
    max_cost_usd: Optional[float] = None

    # Per-call limits
    max_tokens_per_call: Optional[int] = None

    # Behavior when limits are reached
    on_exceed: BudgetExceedAction = BudgetExceedAction.WARN

    # Warning thresholds (percentage of limit, 0.0-1.0)
    warn_at_percentage: float = 0.8

    # Cheaper model to fall back to when throttling
    fallback_model: str = "claude-3-5-haiku-20241022"

    # Auto-switch to fallback model when cost exceeds threshold
    auto_throttle_at_percentage: Optional[float] = None  # e.g., 0.9

    def __post_init__(self):
        """Validate configuration."""
        if self.warn_at_percentage < 0 or self.warn_at_percentage > 1:
            raise ValueError("warn_at_percentage must be between 0 and 1")
        if self.auto_throttle_at_percentage is not None:
            if self.auto_throttle_at_percentage < 0 or self.auto_throttle_at_percentage > 1:
                raise ValueError("auto_throttle_at_percentage must be between 0 and 1")

    @classmethod
    def default(cls) -> "BudgetConfig":
        """Create default budget configuration.

        Default: $1 per task, warn at 80%.
        """
        return cls(max_cost_usd=1.0, on_exceed=BudgetExceedAction.WARN)

    @classmethod
    def unlimited(cls) -> "BudgetConfig":
        """Create unlimited budget configuration (no limits)."""
        return cls()

    @classmethod
    def strict(cls, max_cost: float = 0.5) -> "BudgetConfig":
        """Create strict budget configuration.

        Stops execution when limit is reached.
        """
        return cls(
            max_cost_usd=max_cost,
            on_exceed=BudgetExceedAction.STOP,
            warn_at_percentage=0.7
        )

    @classmethod
    def with_throttle(cls, max_cost: float = 1.0) -> "BudgetConfig":
        """Create budget configuration with automatic throttling.

        Switches to cheaper model when cost exceeds 80%.
        """
        return cls(
            max_cost_usd=max_cost,
            on_exceed=BudgetExceedAction.THROTTLE,
            auto_throttle_at_percentage=0.8
        )


@dataclass
class BudgetState:
    """Internal state tracking for budget controller."""
    warned: bool = False
    exceeded: bool = False
    throttled: bool = False
    original_model: Optional[str] = None
    exceed_time: Optional[datetime] = None
    warn_time: Optional[datetime] = None


def _run_async_safely(coro) -> None:
    """Run async coroutine safely from sync context."""
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(coro)
    except RuntimeError:
        # No event loop running
        pass


class BudgetController:
    """Controls and enforces budget limits during task execution.

    Based on Eigent's pattern of catching CAMEL's ModelProcessingError
    and emitting budget events.

    Usage:
        config = BudgetConfig(max_cost_usd=1.0)
        controller = BudgetController(config, task_id="task-123")

        # After each LLM call
        usage = TokenUsage(input_tokens=1000, output_tokens=500, model="claude-sonnet-4.5")
        can_continue = controller.record_usage(usage)
        if not can_continue:
            # Budget exceeded, stop execution
            break
    """

    def __init__(
        self,
        config: BudgetConfig,
        task_id: str,
        on_warning: Optional[Callable] = None,
        on_exceeded: Optional[Callable] = None,
        on_throttle: Optional[Callable] = None,
    ):
        """Initialize budget controller.

        Args:
            config: Budget configuration
            task_id: Task/session identifier
            on_warning: Async callback when warning threshold reached
            on_exceeded: Async callback when budget exceeded
            on_throttle: Async callback when switching to cheaper model
        """
        self.config = config
        self.task_id = task_id
        self._on_warning = on_warning
        self._on_exceeded = on_exceeded
        self._on_throttle = on_throttle
        self._session_usage = SessionTokenUsage(task_id=task_id)
        self._state = BudgetState()
        self._lock = asyncio.Lock()

    @property
    def usage(self) -> SessionTokenUsage:
        """Get current session usage."""
        return self._session_usage

    @property
    def is_exceeded(self) -> bool:
        """Check if budget has been exceeded."""
        return self._state.exceeded

    @property
    def is_warned(self) -> bool:
        """Check if warning has been triggered."""
        return self._state.warned

    @property
    def is_throttled(self) -> bool:
        """Check if currently using fallback model."""
        return self._state.throttled

    def record_usage(self, usage: TokenUsage) -> bool:
        """Record token usage and check limits.

        Args:
            usage: Token usage from the latest LLM call

        Returns:
            True if execution can continue, False if should stop

        Raises:
            BudgetExceededException: If budget exceeded and on_exceed is STOP
        """
        self._session_usage.add_usage(usage)

        # Check if budget exceeded
        if self._check_exceeded():
            self._state.exceeded = True
            self._state.exceed_time = datetime.now()
            return self._handle_exceeded()

        # Check auto-throttle threshold
        if self._should_auto_throttle():
            self._trigger_throttle()

        # Check warning threshold
        if not self._state.warned and self._check_warning():
            self._state.warned = True
            self._state.warn_time = datetime.now()
            self._handle_warning()

        return True

    async def record_usage_async(self, usage: TokenUsage) -> bool:
        """Async version of record_usage with lock protection.

        Args:
            usage: Token usage from the latest LLM call

        Returns:
            True if execution can continue, False if should stop
        """
        async with self._lock:
            return self.record_usage(usage)

    def _check_exceeded(self) -> bool:
        """Check if any budget limit is exceeded."""
        cfg = self.config
        usage = self._session_usage

        if cfg.max_total_tokens and usage.total_tokens >= cfg.max_total_tokens:
            return True
        if cfg.max_input_tokens and usage.total_input_tokens >= cfg.max_input_tokens:
            return True
        if cfg.max_output_tokens and usage.total_output_tokens >= cfg.max_output_tokens:
            return True
        if cfg.max_cost_usd and usage.estimated_cost >= cfg.max_cost_usd:
            return True

        return False

    def _check_warning(self) -> bool:
        """Check if warning threshold is reached."""
        cfg = self.config
        usage = self._session_usage
        warn_pct = cfg.warn_at_percentage

        if cfg.max_total_tokens:
            if usage.total_tokens >= cfg.max_total_tokens * warn_pct:
                return True
        if cfg.max_cost_usd:
            if usage.estimated_cost >= cfg.max_cost_usd * warn_pct:
                return True

        return False

    def _should_auto_throttle(self) -> bool:
        """Check if should auto-switch to cheaper model."""
        if self._state.throttled:
            return False  # Already throttled

        cfg = self.config
        if cfg.auto_throttle_at_percentage is None:
            return False

        usage = self._session_usage
        if cfg.max_cost_usd:
            return usage.estimated_cost >= cfg.max_cost_usd * cfg.auto_throttle_at_percentage

        return False

    def _handle_warning(self) -> None:
        """Handle warning threshold reached."""
        event = {
            "type": "budget_warning",
            "task_id": self.task_id,
            "usage": self._session_usage.to_dict(),
            "percentage_used": self._get_percentage_used(),
            "timestamp": datetime.now().isoformat(),
        }

        logger.warning(f"Budget warning for task {self.task_id}: {event}")

        if self._on_warning:
            self._emit_async(self._on_warning, event)

    def _handle_exceeded(self) -> bool:
        """Handle budget exceeded.

        Returns:
            True if execution can continue, False if should stop
        """
        event = {
            "type": "budget_exceeded",
            "task_id": self.task_id,
            "usage": self._session_usage.to_dict(),
            "action": self.config.on_exceed.value,
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(f"Budget exceeded for task {self.task_id}: {event}")

        if self._on_exceeded:
            self._emit_async(self._on_exceeded, event)

        action = self.config.on_exceed

        if action == BudgetExceedAction.STOP:
            raise BudgetExceededException(
                f"Budget exceeded for task {self.task_id}",
                task_id=self.task_id,
                usage=self._session_usage.to_dict()
            )

        elif action == BudgetExceedAction.WARN:
            return True  # Continue execution

        elif action == BudgetExceedAction.THROTTLE:
            self._trigger_throttle()
            return True  # Continue with cheaper model

        elif action == BudgetExceedAction.CONFIRM:
            # Would need async confirmation from user
            # For now, stop execution (caller should handle confirmation)
            return False

        return False

    def _trigger_throttle(self) -> None:
        """Switch to cheaper fallback model."""
        if self._state.throttled:
            return  # Already throttled

        self._state.throttled = True

        event = {
            "type": "budget_throttle",
            "task_id": self.task_id,
            "fallback_model": self.config.fallback_model,
            "usage": self._session_usage.to_dict(),
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(f"Budget throttle for task {self.task_id}: switching to {self.config.fallback_model}")

        if self._on_throttle:
            self._emit_async(self._on_throttle, event)

    def _emit_async(self, callback: Callable, event: Dict[str, Any]) -> None:
        """Emit event via callback (handles both sync and async)."""
        if asyncio.iscoroutinefunction(callback):
            _run_async_safely(callback(event))
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon(lambda: callback(event))
            except RuntimeError:
                # No event loop running, call directly
                callback(event)

    def _get_percentage_used(self) -> Dict[str, float]:
        """Get percentage of each limit used."""
        cfg = self.config
        usage = self._session_usage
        result = {}

        if cfg.max_total_tokens:
            result["tokens"] = round(usage.total_tokens / cfg.max_total_tokens, 4)
        if cfg.max_input_tokens:
            result["input_tokens"] = round(usage.total_input_tokens / cfg.max_input_tokens, 4)
        if cfg.max_output_tokens:
            result["output_tokens"] = round(usage.total_output_tokens / cfg.max_output_tokens, 4)
        if cfg.max_cost_usd:
            result["cost"] = round(usage.estimated_cost / cfg.max_cost_usd, 4)

        return result

    def get_remaining_budget(self) -> Dict[str, Any]:
        """Get remaining budget information."""
        cfg = self.config
        usage = self._session_usage

        result = {
            "current_usage": usage.to_dict(),
            "is_exceeded": self._state.exceeded,
            "is_warned": self._state.warned,
            "is_throttled": self._state.throttled,
        }

        if cfg.max_total_tokens:
            result["remaining_tokens"] = max(0, cfg.max_total_tokens - usage.total_tokens)
        if cfg.max_input_tokens:
            result["remaining_input_tokens"] = max(0, cfg.max_input_tokens - usage.total_input_tokens)
        if cfg.max_output_tokens:
            result["remaining_output_tokens"] = max(0, cfg.max_output_tokens - usage.total_output_tokens)
        if cfg.max_cost_usd:
            result["remaining_cost_usd"] = round(max(0, cfg.max_cost_usd - usage.estimated_cost), 6)

        return result

    def should_use_fallback_model(self) -> bool:
        """Check if should switch to fallback model due to throttling."""
        return self._state.throttled

    def get_current_model(self, original_model: str) -> str:
        """Get the model to use (original or fallback if throttled).

        Args:
            original_model: The originally configured model

        Returns:
            Model to use for the next call
        """
        if self._state.throttled:
            return self.config.fallback_model
        return original_model

    def get_fallback_model(self, current_model: str) -> Optional[str]:
        """Get a cheaper alternative to the current model.

        Args:
            current_model: Current model name

        Returns:
            Cheaper alternative model name, or None if already cheapest
        """
        return get_cheaper_model(current_model)

    def reset(self) -> None:
        """Reset the budget controller state."""
        self._session_usage.reset()
        self._state = BudgetState()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize controller state to dictionary."""
        return {
            "task_id": self.task_id,
            "config": {
                "max_input_tokens": self.config.max_input_tokens,
                "max_output_tokens": self.config.max_output_tokens,
                "max_total_tokens": self.config.max_total_tokens,
                "max_cost_usd": self.config.max_cost_usd,
                "on_exceed": self.config.on_exceed.value,
                "warn_at_percentage": self.config.warn_at_percentage,
                "fallback_model": self.config.fallback_model,
            },
            "state": {
                "warned": self._state.warned,
                "exceeded": self._state.exceeded,
                "throttled": self._state.throttled,
                "warn_time": self._state.warn_time.isoformat() if self._state.warn_time else None,
                "exceed_time": self._state.exceed_time.isoformat() if self._state.exceed_time else None,
            },
            "usage": self._session_usage.to_dict(),
            "remaining": self.get_remaining_budget(),
        }
