"""
Cost Calculator Module

Calculates estimated costs for LLM API usage based on token counts.
Based on Anthropic pricing as of 2025.

References:
- Anthropic Pricing: https://www.anthropic.com/api#pricing
- Eigent: third-party/eigent/backend/app/utils/agent.py
"""

from typing import Dict, Optional


# Pricing per 1M tokens (as of January 2025)
# Source: https://www.anthropic.com/api#pricing
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Claude 4.5 models
    "claude-opus-4-5-20251101": {
        "input": 15.00,       # $15 per 1M input tokens
        "output": 75.00,      # $75 per 1M output tokens
        "cache_write": 18.75, # $18.75 per 1M cache write tokens
        "cache_read": 1.50,   # $1.50 per 1M cache read tokens
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.00,        # $3 per 1M input tokens
        "output": 15.00,      # $15 per 1M output tokens
        "cache_write": 3.75,  # $3.75 per 1M cache write tokens
        "cache_read": 0.30,   # $0.30 per 1M cache read tokens
    },

    # Claude 3.5 models
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.80,        # $0.80 per 1M input tokens
        "output": 4.00,       # $4 per 1M output tokens
        "cache_write": 1.00,  # $1 per 1M cache write tokens
        "cache_read": 0.08,   # $0.08 per 1M cache read tokens
    },

    # Claude 3 models (legacy)
    "claude-3-opus-20240229": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-3-sonnet-20240229": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03,
    },
}

# Model aliases for convenience
MODEL_ALIASES: Dict[str, str] = {
    # Short names
    "opus-4.5": "claude-opus-4-5-20251101",
    "sonnet-4.5": "claude-sonnet-4-5-20250929",
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
    "haiku-3.5": "claude-3-5-haiku-20241022",
    "opus-3": "claude-3-opus-20240229",
    "sonnet-3": "claude-3-sonnet-20240229",
    "haiku-3": "claude-3-haiku-20240307",

    # Common variations
    "claude-opus-4.5": "claude-opus-4-5-20251101",
    "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
    "claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3.5-haiku": "claude-3-5-haiku-20241022",
}

# Default model for fallback
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


def resolve_model_name(model: str) -> str:
    """Resolve model alias to full model name.

    Args:
        model: Model name or alias

    Returns:
        Full model name
    """
    if not model:
        return DEFAULT_MODEL

    # Check direct match first
    if model in MODEL_PRICING:
        return model

    # Check aliases
    if model in MODEL_ALIASES:
        return MODEL_ALIASES[model]

    # Try case-insensitive match
    model_lower = model.lower()
    for alias, full_name in MODEL_ALIASES.items():
        if alias.lower() == model_lower:
            return full_name

    # Default if not found
    return DEFAULT_MODEL


def get_pricing(model: str) -> Dict[str, float]:
    """Get pricing for a model.

    Args:
        model: Model name or alias

    Returns:
        Pricing dictionary with input/output/cache_write/cache_read rates
    """
    resolved = resolve_model_name(model)
    return MODEL_PRICING.get(resolved, MODEL_PRICING[DEFAULT_MODEL])


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    model: str = DEFAULT_MODEL
) -> float:
    """Calculate estimated cost for token usage.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_creation_tokens: Number of cache write tokens (prompt caching)
        cache_read_tokens: Number of cache read tokens (prompt caching)
        model: Model name/ID (supports aliases)

    Returns:
        Estimated cost in USD
    """
    pricing = get_pricing(model)

    cost = 0.0
    cost += (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    cost += (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    cost += (cache_read_tokens / 1_000_000) * pricing["cache_read"]

    return round(cost, 6)


def calculate_cost_breakdown(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    model: str = DEFAULT_MODEL
) -> Dict[str, float]:
    """Calculate detailed cost breakdown for token usage.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_creation_tokens: Number of cache write tokens
        cache_read_tokens: Number of cache read tokens
        model: Model name/ID

    Returns:
        Dictionary with cost breakdown by category
    """
    pricing = get_pricing(model)

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    cache_write_cost = (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    cache_read_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read"]

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cache_write_cost": round(cache_write_cost, 6),
        "cache_read_cost": round(cache_read_cost, 6),
        "total_cost": round(input_cost + output_cost + cache_write_cost + cache_read_cost, 6),
        "model": resolve_model_name(model),
        "pricing": pricing,
    }


def estimate_tokens(text: str, method: str = "chars") -> int:
    """Estimate token count for text (rough approximation).

    Args:
        text: Text to estimate
        method: Estimation method
            - "chars": ~4 characters per token (English text)
            - "words": ~1.3 tokens per word (English text)

    Returns:
        Estimated token count

    Note:
        This is a rough estimate. Actual tokenization varies by model.
        For accurate counts, use the Anthropic tokenizer.
    """
    if not text:
        return 0

    if method == "words":
        # Rough estimate: ~1.3 tokens per word
        word_count = len(text.split())
        return int(word_count * 1.3)
    else:  # default: chars
        # Rough estimate: ~4 characters per token for English
        return len(text) // 4


def estimate_cost_for_text(
    prompt: str,
    expected_response_length: int = 1000,
    model: str = DEFAULT_MODEL
) -> Dict[str, float]:
    """Estimate cost for a text prompt and expected response.

    Args:
        prompt: Input prompt text
        expected_response_length: Expected output token count
        model: Model name/ID

    Returns:
        Cost estimate dictionary
    """
    input_tokens = estimate_tokens(prompt)

    return {
        "estimated_input_tokens": input_tokens,
        "expected_output_tokens": expected_response_length,
        "estimated_cost": calculate_cost(
            input_tokens=input_tokens,
            output_tokens=expected_response_length,
            model=model
        ),
        "model": resolve_model_name(model),
    }


def get_model_tier(model: str) -> str:
    """Get the pricing tier for a model.

    Args:
        model: Model name/ID

    Returns:
        Tier name: "premium", "standard", or "economy"
    """
    resolved = resolve_model_name(model)
    pricing = get_pricing(resolved)

    if pricing["input"] >= 10.0:
        return "premium"  # Opus-class models
    elif pricing["input"] >= 1.0:
        return "standard"  # Sonnet-class models
    else:
        return "economy"  # Haiku-class models


def get_cheaper_model(model: str) -> Optional[str]:
    """Get a cheaper alternative model.

    Args:
        model: Current model name/ID

    Returns:
        Cheaper alternative model name, or None if already cheapest
    """
    resolved = resolve_model_name(model)
    tier = get_model_tier(resolved)

    if tier == "premium":
        return "claude-sonnet-4-5-20250929"
    elif tier == "standard":
        return "claude-3-5-haiku-20241022"
    else:
        return None  # Already at cheapest tier
