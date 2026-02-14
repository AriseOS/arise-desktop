"""
Token Usage Tracking Module

Tracks token usage for LLM calls and aggregates usage across sessions.
Based on Eigent's browser_use token tracking and CAMEL framework patterns.

References:
- Eigent: third-party/eigent/backend/app/utils/agent.py
- CAMEL: https://github.com/camel-ai/camel/blob/master/camel/utils/budget.py
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .cost_calculator import calculate_cost


@dataclass
class TokenUsage:
    """Tracks token usage for a single LLM call.

    Based on browser_use's token tracking structure with support for
    Anthropic's prompt caching feature.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0  # Prompt caching creation
    cache_read_tokens: int = 0      # Cached prompt reads
    timestamp: datetime = field(default_factory=datetime.now)
    model: str = ""

    # Optional metadata for tracking context
    call_id: Optional[str] = None
    agent_id: Optional[str] = None
    tool_name: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens

    @property
    def cache_tokens(self) -> int:
        """Total cache-related tokens."""
        return self.cache_creation_tokens + self.cache_read_tokens

    @property
    def cost(self) -> float:
        """Calculate cost for this single usage."""
        return calculate_cost(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens,
            model=self.model
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cache_tokens": self.cache_tokens,
            "cost": self.cost,
            "model": self.model,
            "timestamp": self.timestamp.isoformat(),
            "call_id": self.call_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenUsage":
        """Create TokenUsage from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_creation_tokens=data.get("cache_creation_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            timestamp=timestamp,
            model=data.get("model", ""),
            call_id=data.get("call_id"),
            agent_id=data.get("agent_id"),
            tool_name=data.get("tool_name"),
        )

    @classmethod
    def from_anthropic_response(cls, usage, model: str = "") -> "TokenUsage":
        """Create TokenUsage from Anthropic API response usage object.

        Args:
            usage: Anthropic response.usage object
            model: Model name/ID
        """
        return cls(
            input_tokens=getattr(usage, 'input_tokens', 0),
            output_tokens=getattr(usage, 'output_tokens', 0),
            cache_creation_tokens=getattr(usage, 'cache_creation_input_tokens', 0),
            cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0),
            model=model,
        )


@dataclass
class SessionTokenUsage:
    """Aggregated token usage for an entire session/task.

    Tracks cumulative token usage across multiple LLM calls within
    a single task or session, enabling budget enforcement.
    """
    task_id: str
    model: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    num_calls: int = 0
    call_history: List[TokenUsage] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Track by model for mixed-model usage
    usage_by_model: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add_usage(self, usage: TokenUsage) -> None:
        """Add a new token usage record.

        Args:
            usage: TokenUsage from the latest LLM call
        """
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_cache_creation_tokens += usage.cache_creation_tokens
        self.total_cache_read_tokens += usage.cache_read_tokens
        self.num_calls += 1
        self.call_history.append(usage)
        self.updated_at = datetime.now()

        # Update model tracking
        if usage.model:
            self.model = usage.model  # Track most recent model
            if usage.model not in self.usage_by_model:
                self.usage_by_model[usage.model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_tokens": 0,
                    "cache_read_tokens": 0,
                    "num_calls": 0,
                }
            self.usage_by_model[usage.model]["input_tokens"] += usage.input_tokens
            self.usage_by_model[usage.model]["output_tokens"] += usage.output_tokens
            self.usage_by_model[usage.model]["cache_creation_tokens"] += usage.cache_creation_tokens
            self.usage_by_model[usage.model]["cache_read_tokens"] += usage.cache_read_tokens
            self.usage_by_model[usage.model]["num_calls"] += 1

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all calls."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cache_tokens(self) -> int:
        """Total cache-related tokens."""
        return self.total_cache_creation_tokens + self.total_cache_read_tokens

    @property
    def estimated_cost(self) -> float:
        """Estimate total cost based on token usage.

        For mixed-model usage, calculates cost per model and sums.
        """
        if self.usage_by_model:
            total_cost = 0.0
            for model, usage in self.usage_by_model.items():
                total_cost += calculate_cost(
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_creation_tokens=usage["cache_creation_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                    model=model
                )
            return total_cost
        else:
            return calculate_cost(
                input_tokens=self.total_input_tokens,
                output_tokens=self.total_output_tokens,
                cache_creation_tokens=self.total_cache_creation_tokens,
                cache_read_tokens=self.total_cache_read_tokens,
                model=self.model
            )

    @property
    def average_tokens_per_call(self) -> float:
        """Average tokens per LLM call."""
        if self.num_calls == 0:
            return 0.0
        return self.total_tokens / self.num_calls

    @property
    def duration_seconds(self) -> float:
        """Duration from start to last update."""
        return (self.updated_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "model": self.model,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_tokens": self.total_tokens,
            "total_cache_tokens": self.total_cache_tokens,
            "estimated_cost": self.estimated_cost,
            "num_calls": self.num_calls,
            "average_tokens_per_call": self.average_tokens_per_call,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "usage_by_model": self.usage_by_model,
            # Don't include full call_history by default (can be large)
            "call_history_count": len(self.call_history),
        }

    def to_dict_with_history(self) -> Dict[str, Any]:
        """Convert to dictionary including full call history."""
        result = self.to_dict()
        result["call_history"] = [u.to_dict() for u in self.call_history]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionTokenUsage":
        """Create SessionTokenUsage from dictionary."""
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elif started_at is None:
            started_at = datetime.now()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()

        instance = cls(
            task_id=data.get("task_id", ""),
            model=data.get("model", ""),
            total_input_tokens=data.get("total_input_tokens", 0),
            total_output_tokens=data.get("total_output_tokens", 0),
            total_cache_creation_tokens=data.get("total_cache_creation_tokens", 0),
            total_cache_read_tokens=data.get("total_cache_read_tokens", 0),
            num_calls=data.get("num_calls", 0),
            started_at=started_at,
            updated_at=updated_at,
            usage_by_model=data.get("usage_by_model", {}),
        )

        # Restore call history if present
        if "call_history" in data:
            instance.call_history = [
                TokenUsage.from_dict(u) for u in data["call_history"]
            ]

        return instance

    def reset(self) -> None:
        """Reset all usage counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self.num_calls = 0
        self.call_history.clear()
        self.usage_by_model.clear()
        self.started_at = datetime.now()
        self.updated_at = datetime.now()
