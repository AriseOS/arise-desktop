"""LLM Client Module.

This module provides a unified interface for interacting with various Large Language
Model (LLM) providers including OpenAI, Anthropic Claude, and others. It supports
both synchronous and asynchronous operations, batch processing, and comprehensive
configuration validation.

Key Components:
    - BaseLLMClient: Abstract base class for all LLM clients
    - OpenAILLMClient: OpenAI GPT models client
    - ClaudeLLMClient: Anthropic Claude models client
    - MockLLMClient: Mock client for testing
    - LLMConfigChecker: Configuration validation utilities
    - create_llm_client: Factory function for creating clients

Example usage:
    from src.services.llm import create_llm_client, LLMProvider, LLMMessage

    # Create a client
    client = create_llm_client(
        provider=LLMProvider.OPENAI,
        api_client=openai_api_instance,
        model_name="gpt-4"
    )

    # Generate a response
    messages = [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content="Hello!")
    ]
    response = client.generate(messages)
    print(response.content)
"""

from src.services.llm.claude_client import ClaudeLLMClient

# Core LLM client classes and types
from src.services.llm.llm_client import (
    LLMClient,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    create_llm_client,
)

# Configuration validation
from src.services.llm.llm_config_checker import (
    ConfigValidationError,
    LLMConfigChecker,
    check_all_env_configs,
)
from src.services.llm.mock_client import MockLLMClient

# Provider-specific client implementations
from src.services.llm.openai_client import OpenAILLMClient

# Maintain backward compatibility with old import names
AnthropicLLMClient = ClaudeLLMClient


__all__ = [
    # Core classes and types
    "LLMClient",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    # Client implementations
    "OpenAILLMClient",
    "ClaudeLLMClient",
    "AnthropicLLMClient",  # Backward compatibility alias
    "MockLLMClient",
    # Factory function
    "create_llm_client",
    # Configuration validation
    "ConfigValidationError",
    "LLMConfigChecker",
    "check_all_env_configs",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
