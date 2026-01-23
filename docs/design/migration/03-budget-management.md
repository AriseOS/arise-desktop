# Budget Management & Token Tracking Migration Guide

## Overview

This document describes how to implement budget management and token tracking capabilities in the 2ami system, based on Eigent's implementation using the CAMEL framework.

## Eigent's Budget Management Architecture

### 1. Budget Tracking in CAMEL

Eigent leverages CAMEL's built-in budget tracking through `ModelProcessingError`:

```python
# From third-party/eigent/backend/app/utils/agent.py

from camel.agents import ChatAgent
from camel.messages import BaseMessage

class ListenChatAgent(ChatAgent):
    def step(self, input_message, response_format=None):
        try:
            # Activate agent event
            asyncio.create_task(task_lock.put_queue(ActionActivateAgentData(...)))

            # Call parent's step method (CAMEL's ChatAgent)
            res = super().step(input_message, response_format)

        except ModelProcessingError as e:
            # CAMEL raises this when budget is exceeded
            if "Budget has been exceeded" in str(e):
                message = "Budget has been exceeded"
                # Emit budget exceeded event
                asyncio.create_task(task_lock.put_queue(ActionBudgetNotEnough()))
            raise

        return res
```

### 2. Token Usage from browser_use

Eigent also uses `browser_use` library which tracks tokens:

```python
# Token tracking structure from browser_use
class TokenUsage:
    cache_creation_tokens: int  # Prompt caching creation
    cache_read_tokens: int      # Cached prompt reads
    input_tokens: int           # Regular input tokens
    output_tokens: int          # Generated output tokens

# Cost calculation
def calculate_cost(usage: TokenUsage, model: str) -> float:
    pricing = MODEL_PRICING.get(model)
    return (
        usage.input_tokens * pricing.input_per_token +
        usage.output_tokens * pricing.output_per_token +
        usage.cache_creation_tokens * pricing.cache_creation_per_token +
        usage.cache_read_tokens * pricing.cache_read_per_token
    )
```

### 3. Budget Event Types

```python
# From third-party/eigent/backend/app/service/task.py

@dataclass
class ActionBudgetNotEnough:
    """Emitted when budget is exceeded."""
    action: Action = Action.budget_not_enough
    data: dict = field(default_factory=dict)
```

---

## Migration Plan for 2ami

### Phase 1: Token Tracking Infrastructure

#### 1.1 Token Usage Data Class

```python
# src/clients/desktop_app/ami_daemon/base_agent/core/token_usage.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class TokenUsage:
    """Tracks token usage for a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_tokens(self) -> int:
        return self.cache_creation_tokens + self.cache_read_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SessionTokenUsage:
    """Aggregated token usage for an entire session/task."""
    task_id: str
    model: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    num_calls: int = 0
    call_history: list = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_usage(self, usage: TokenUsage):
        """Add a new token usage record."""
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_cache_creation_tokens += usage.cache_creation_tokens
        self.total_cache_read_tokens += usage.cache_read_tokens
        self.num_calls += 1
        self.call_history.append(usage)
        self.updated_at = datetime.now()
        if usage.model:
            self.model = usage.model

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def estimated_cost(self) -> float:
        """Estimate cost based on token usage."""
        return calculate_cost(
            self.total_input_tokens,
            self.total_output_tokens,
            self.total_cache_creation_tokens,
            self.total_cache_read_tokens,
            self.model
        )
```

#### 1.2 Cost Calculator

```python
# src/clients/desktop_app/ami_daemon/base_agent/core/cost_calculator.py

from typing import Dict

# Pricing per 1M tokens (as of 2025)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4-5-20250929": {
        "input": 3.00,       # $3 per 1M input tokens
        "output": 15.00,     # $15 per 1M output tokens
        "cache_write": 3.75,  # $3.75 per 1M cache write
        "cache_read": 0.30,   # $0.30 per 1M cache read
    },
    "claude-opus-4-5-20251101": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
    # Add more models as needed
}

def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    model: str = "claude-sonnet-4-5-20250929"
) -> float:
    """Calculate estimated cost for token usage.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_creation_tokens: Number of cache write tokens
        cache_read_tokens: Number of cache read tokens
        model: Model name/ID

    Returns:
        Estimated cost in USD
    """
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Default to Sonnet pricing if model not found
        pricing = MODEL_PRICING["claude-sonnet-4-5-20250929"]

    cost = 0.0
    cost += (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    cost += (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    cost += (cache_read_tokens / 1_000_000) * pricing["cache_read"]

    return round(cost, 6)


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation).

    Uses the approximation of ~4 characters per token for English text.
    This is a rough estimate - actual tokenization varies by model.
    """
    return len(text) // 4
```

### Phase 2: Budget Controller

```python
# src/clients/desktop_app/ami_daemon/base_agent/core/budget_controller.py

from dataclasses import dataclass
from typing import Optional, Callable
import asyncio
from enum import Enum

class BudgetExceedAction(str, Enum):
    STOP = "stop"           # Stop execution immediately
    WARN = "warn"           # Continue but emit warning
    CONFIRM = "confirm"     # Ask user for confirmation
    THROTTLE = "throttle"   # Reduce capability (use cheaper model)

@dataclass
class BudgetConfig:
    """Budget configuration for a task/session."""
    # Token limits
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None

    # Cost limits
    max_cost_usd: Optional[float] = None

    # Behavior when limits are reached
    on_exceed: BudgetExceedAction = BudgetExceedAction.WARN

    # Warning thresholds (percentage of limit)
    warn_at_percentage: float = 0.8

    # Cheaper model to fall back to when throttling
    fallback_model: str = "claude-3-5-haiku-20241022"


class BudgetController:
    """Controls and enforces budget limits during task execution."""

    def __init__(
        self,
        config: BudgetConfig,
        task_id: str,
        on_warning: Optional[Callable] = None,
        on_exceeded: Optional[Callable] = None,
    ):
        self.config = config
        self.task_id = task_id
        self._on_warning = on_warning
        self._on_exceeded = on_exceeded
        self._session_usage = SessionTokenUsage(task_id=task_id)
        self._warned = False
        self._exceeded = False

    @property
    def usage(self) -> SessionTokenUsage:
        return self._session_usage

    @property
    def is_exceeded(self) -> bool:
        return self._exceeded

    def record_usage(self, usage: TokenUsage) -> bool:
        """Record token usage and check limits.

        Args:
            usage: Token usage from the latest LLM call

        Returns:
            True if execution can continue, False if should stop
        """
        self._session_usage.add_usage(usage)

        # Check limits
        if self._check_exceeded():
            self._exceeded = True
            return self._handle_exceeded()

        if not self._warned and self._check_warning():
            self._warned = True
            self._handle_warning()

        return True

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

    def _handle_warning(self):
        """Handle warning threshold reached."""
        if self._on_warning:
            asyncio.create_task(self._on_warning({
                "type": "budget_warning",
                "task_id": self.task_id,
                "usage": self._session_usage.to_dict(),
                "percentage_used": self._get_percentage_used(),
            }))

    def _handle_exceeded(self) -> bool:
        """Handle budget exceeded.

        Returns:
            True if execution can continue, False if should stop
        """
        if self._on_exceeded:
            asyncio.create_task(self._on_exceeded({
                "type": "budget_exceeded",
                "task_id": self.task_id,
                "usage": self._session_usage.to_dict(),
                "action": self.config.on_exceed,
            }))

        if self.config.on_exceed == BudgetExceedAction.STOP:
            return False
        elif self.config.on_exceed == BudgetExceedAction.WARN:
            return True
        elif self.config.on_exceed == BudgetExceedAction.THROTTLE:
            # Signal to use fallback model
            return True
        elif self.config.on_exceed == BudgetExceedAction.CONFIRM:
            # Would need async confirmation from user
            return False

        return False

    def _get_percentage_used(self) -> Dict[str, float]:
        """Get percentage of each limit used."""
        cfg = self.config
        usage = self._session_usage
        result = {}

        if cfg.max_total_tokens:
            result["tokens"] = usage.total_tokens / cfg.max_total_tokens
        if cfg.max_cost_usd:
            result["cost"] = usage.estimated_cost / cfg.max_cost_usd

        return result

    def get_remaining_budget(self) -> Dict[str, Any]:
        """Get remaining budget information."""
        cfg = self.config
        usage = self._session_usage

        return {
            "remaining_tokens": (
                cfg.max_total_tokens - usage.total_tokens
                if cfg.max_total_tokens else None
            ),
            "remaining_cost_usd": (
                cfg.max_cost_usd - usage.estimated_cost
                if cfg.max_cost_usd else None
            ),
            "current_usage": usage.to_dict(),
        }

    def should_use_fallback_model(self) -> bool:
        """Check if should switch to fallback model due to throttling."""
        return (
            self._exceeded and
            self.config.on_exceed == BudgetExceedAction.THROTTLE
        )
```

### Phase 3: Integration with LLM Provider

```python
# src/common/llm/anthropic_provider.py (modifications)

from typing import Optional
from .token_usage import TokenUsage

class AnthropicProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str = None,
        model_name: str = None,
        base_url: str = None,
        budget_controller: Optional[BudgetController] = None,
    ):
        # ... existing init ...
        self._budget_controller = budget_controller
        self._last_usage: Optional[TokenUsage] = None

    def set_budget_controller(self, controller: BudgetController):
        """Set budget controller for tracking."""
        self._budget_controller = controller

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        max_tokens: int = 4096,
    ) -> ToolCallResponse:
        """Generate response with tool calling and budget tracking."""

        # Check if budget already exceeded
        if self._budget_controller and self._budget_controller.is_exceeded:
            if not self._budget_controller.should_use_fallback_model():
                raise BudgetExceededException(
                    f"Budget exceeded for task {self._budget_controller.task_id}"
                )
            # Switch to fallback model
            original_model = self.model_name
            self.model_name = self._budget_controller.config.fallback_model

        try:
            # Make API call
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self.model_name,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

            # Track token usage
            if response.usage:
                usage = TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_creation_tokens=getattr(
                        response.usage, 'cache_creation_input_tokens', 0
                    ),
                    cache_read_tokens=getattr(
                        response.usage, 'cache_read_input_tokens', 0
                    ),
                    model=self.model_name,
                )
                self._last_usage = usage

                if self._budget_controller:
                    can_continue = self._budget_controller.record_usage(usage)
                    if not can_continue:
                        raise BudgetExceededException(
                            f"Budget exceeded after call"
                        )

            return ToolCallResponse(content=response.content, ...)

        finally:
            # Restore original model if we switched
            if 'original_model' in locals():
                self.model_name = original_model

    @property
    def last_usage(self) -> Optional[TokenUsage]:
        return self._last_usage


class BudgetExceededException(Exception):
    """Raised when budget is exceeded."""
    pass
```

### Phase 4: Integration with Agent

```python
# src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py

from ..core.budget_controller import BudgetController, BudgetConfig

class EigentStyleBrowserAgent(BaseStepAgent):
    def __init__(self):
        super().__init__(metadata)
        # ... existing init ...
        self._budget_controller: Optional[BudgetController] = None

    def set_budget_config(self, config: BudgetConfig):
        """Set budget configuration for this agent's execution."""
        self._budget_controller = BudgetController(
            config=config,
            task_id=self._task_id,
            on_warning=self._on_budget_warning,
            on_exceeded=self._on_budget_exceeded,
        )

        # Pass to LLM provider
        if self._llm_provider:
            self._llm_provider.set_budget_controller(self._budget_controller)

    async def _on_budget_warning(self, event: Dict[str, Any]):
        """Handle budget warning."""
        await self._notify_progress("budget_warning", event)
        logger.warning(f"Budget warning: {event}")

    async def _on_budget_exceeded(self, event: Dict[str, Any]):
        """Handle budget exceeded."""
        await self._notify_progress("budget_exceeded", event)
        logger.error(f"Budget exceeded: {event}")

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        # Parse budget config from input
        if isinstance(input_data, dict):
            budget_config = input_data.get("budget_config")
            if budget_config:
                self.set_budget_config(BudgetConfig(**budget_config))

        try:
            # ... existing execution logic ...
            result = await self._run_agent_loop(task, ...)

        except BudgetExceededException as e:
            return AgentOutput(
                success=False,
                message=f"Task stopped: {str(e)}",
                data={
                    "reason": "budget_exceeded",
                    "usage": self._budget_controller.usage.to_dict(),
                }
            )

        # Include usage in output
        usage_data = {}
        if self._budget_controller:
            usage_data = self._budget_controller.usage.to_dict()

        return AgentOutput(
            success=True,
            data={
                "result": result,
                "token_usage": usage_data,
                # ... other data ...
            }
        )
```

### Phase 5: Service Layer Integration

```python
# src/clients/desktop_app/ami_daemon/services/quick_task_service.py

from ..base_agent.core.budget_controller import BudgetConfig

async def execute_quick_task(
    task: str,
    user_id: str,
    budget_config: Optional[Dict[str, Any]] = None,
    ...
) -> Dict[str, Any]:
    """Execute a quick task with optional budget limits."""

    # Parse budget config
    if budget_config:
        config = BudgetConfig(
            max_total_tokens=budget_config.get("max_tokens"),
            max_cost_usd=budget_config.get("max_cost_usd"),
            on_exceed=BudgetExceedAction(
                budget_config.get("on_exceed", "warn")
            ),
        )
    else:
        # Default budget: $1 per task
        config = BudgetConfig(max_cost_usd=1.0)

    agent = EigentStyleBrowserAgent()
    agent.set_budget_config(config)

    # ... rest of execution ...
```

---

## API Endpoints for Budget Management

### Set Task Budget

```python
# POST /api/v1/task/{task_id}/budget
{
    "max_tokens": 100000,
    "max_cost_usd": 5.00,
    "on_exceed": "warn"  // "stop", "warn", "confirm", "throttle"
}
```

### Get Task Usage

```python
# GET /api/v1/task/{task_id}/usage
# Response:
{
    "task_id": "xxx",
    "total_input_tokens": 45000,
    "total_output_tokens": 12000,
    "total_tokens": 57000,
    "estimated_cost_usd": 0.24,
    "num_calls": 15,
    "model": "claude-sonnet-4-5-20250929"
}
```

### Get User Usage Summary

```python
# GET /api/v1/user/{user_id}/usage?period=month
# Response:
{
    "user_id": "xxx",
    "period": "2025-01",
    "total_tokens": 1250000,
    "total_cost_usd": 12.50,
    "tasks_executed": 45,
    "breakdown_by_model": {
        "claude-sonnet-4-5-20250929": {"tokens": 1000000, "cost": 10.00},
        "claude-3-5-haiku-20241022": {"tokens": 250000, "cost": 2.50}
    }
}
```

---

## Frontend Integration

### Progress Events

The agent emits progress events for budget tracking:

```typescript
// Event types
type BudgetEvent = {
  type: "budget_warning" | "budget_exceeded";
  task_id: string;
  usage: {
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    estimated_cost: number;
    num_calls: number;
  };
  percentage_used?: {
    tokens?: number;
    cost?: number;
  };
  action?: "stop" | "warn" | "confirm" | "throttle";
};

// React component
function TaskBudgetIndicator({ taskId }: { taskId: string }) {
  const [usage, setUsage] = useState<BudgetUsage | null>(null);

  useEffect(() => {
    const handler = (event: BudgetEvent) => {
      setUsage(event.usage);
    };
    taskEventEmitter.on("budget_warning", handler);
    taskEventEmitter.on("budget_exceeded", handler);
    return () => {
      taskEventEmitter.off("budget_warning", handler);
      taskEventEmitter.off("budget_exceeded", handler);
    };
  }, [taskId]);

  if (!usage) return null;

  return (
    <div className="budget-indicator">
      <span>Tokens: {usage.total_tokens.toLocaleString()}</span>
      <span>Cost: ${usage.estimated_cost.toFixed(4)}</span>
    </div>
  );
}
```

---

## File Structure

```
src/clients/desktop_app/ami_daemon/base_agent/core/
├── token_usage.py           # NEW: Token usage tracking
├── cost_calculator.py       # NEW: Cost calculation
├── budget_controller.py     # NEW: Budget enforcement
└── schemas.py               # Existing

src/common/llm/
├── anthropic_provider.py    # MODIFY: Add budget tracking
└── base_provider.py         # MODIFY: Add usage property
```

---

## Configuration

### Environment Variables

```bash
# Default budget limits
DEFAULT_MAX_TOKENS_PER_TASK=100000
DEFAULT_MAX_COST_PER_TASK=1.00

# Model for throttling fallback
BUDGET_FALLBACK_MODEL=claude-3-5-haiku-20241022
```

---

## References

- Anthropic Pricing: https://www.anthropic.com/api#pricing
- CAMEL Budget: https://github.com/camel-ai/camel/blob/master/camel/utils/budget.py
- Eigent implementation: `third-party/eigent/backend/app/utils/agent.py`
