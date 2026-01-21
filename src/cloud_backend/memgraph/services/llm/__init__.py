"""LLM Client Module.

This module provides base classes for LLM client abstraction.
For actual LLM usage, use src/common/llm/AnthropicProvider directly.

Key Components:
    - LLMClient: Abstract base class (for reference)
    - OpenAILLMClient: OpenAI GPT models client
    - LLMConfigChecker: Configuration validation utilities
"""

# Core LLM client classes and types
from src.cloud_backend.memgraph.services.llm.llm_client import (
    LLMClient,
    LLMMessage,
    LLMProvider,
    LLMResponse,
)

# Configuration validation
from src.cloud_backend.memgraph.services.llm.llm_config_checker import (
    ConfigValidationError,
    LLMConfigChecker,
    check_all_env_configs,
)

# Provider-specific client implementations
from src.cloud_backend.memgraph.services.llm.openai_client import OpenAILLMClient


__all__ = [
    # Core classes and types
    "LLMClient",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    # Client implementations
    "OpenAILLMClient",
    # Configuration validation
    "ConfigValidationError",
    "LLMConfigChecker",
    "check_all_env_configs",
]


__version__ = "1.0.0"
