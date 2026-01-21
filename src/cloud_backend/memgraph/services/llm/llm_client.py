"""Abstract LLM Client Interface.

This module provides the abstract base class for LLM clients, defining a unified
interface for synchronous, asynchronous, and batch operations across different
LLM providers.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class LLMProvider(Enum):
    """Enumeration of supported LLM providers.

    Attributes:
        OPENAI: OpenAI GPT models (gpt-4, gpt-3.5-turbo, etc.)
        ANTHROPIC: Anthropic Claude models (claude-3-opus, etc.)
        GOOGLE: Google Gemini models
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class LLMMessage:
    """Represents a message in an LLM conversation.

    Attributes:
        role: The role of the message sender (e.g., "system", "user", "assistant").
        content: The text content of the message.
    """

    def __init__(self, role: str, content: str) -> None:
        """Initializes an LLMMessage.

        Args:
            role: The role of the message sender.
            content: The text content of the message.
        """
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        """Converts the message to a dictionary format.

        Returns:
            A dictionary with 'role' and 'content' keys.
        """
        return {"role": self.role, "content": self.content}


class LLMResponse:
    """Represents a response from an LLM.

    Attributes:
        content: The generated text content.
        model: The model name used for generation.
        provider: The provider name (e.g., "openai", "anthropic").
        usage: Optional token usage information.
        metadata: Optional additional response metadata.
    """

    def __init__(
        self,
        content: str,
        model: str = "",
        provider: str = "",
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes an LLMResponse.

        Args:
            content: The generated text content.
            model: The model name used for generation.
            provider: The provider name.
            usage: Optional token usage information (e.g., prompt_tokens, completion_tokens).
            metadata: Optional additional response metadata.
        """
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.metadata = metadata or {}


class LLMClient(ABC):
    """Abstract base class for LLM clients.

    This class defines the interface that all LLM client implementations must follow,
    supporting both synchronous and asynchronous operations, batch processing, and
    configuration validation.

    Attributes:
        model_name: The name of the LLM model to use.
        provider: The LLM provider type.
        config: Additional configuration parameters.
    """

    def __init__(self, model_name: str = "default", **kwargs: Any) -> None:
        """Initializes an LLMClient.

        Args:
            model_name: The name of the LLM model to use.
            **kwargs: Additional configuration parameters.
        """
        self.model_name = model_name
        self.provider = LLMProvider.OPENAI  # Default provider
        self.config = kwargs

    def __call__(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Allows the client to be called directly as a function.

        This method provides a convenient shorthand for the generate() method,
        allowing clients to be used as callables.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse object containing the generated content.
        """
        return self.generate(messages, temperature, max_tokens, **kwargs)

    @abstractmethod
    def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response from the LLM (synchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse object containing the generated content.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement generate()")

    @abstractmethod
    async def generate_async(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response from the LLM (asynchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse object containing the generated content.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement generate_async()")

    @abstractmethod
    def generate_batch(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates responses for a batch of message lists (synchronous).

        Args:
            batch_messages: List of message lists to process in batch.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of LLMResponse objects.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement generate_batch()")

    @abstractmethod
    async def generate_batch_async(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates responses for a batch of message lists (asynchronous).

        Args:
            batch_messages: List of message lists to process in batch.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of LLMResponse objects.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement generate_batch_async()")

    def generate_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response using system and user prompts (synchronous).

        This is a convenience method that constructs messages from system and user
        prompts and calls generate().

        Args:
            system_prompt: The system prompt to set context.
            user_prompt: The user's input prompt.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse object containing the generated content.
        """
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        return self.generate(messages, temperature, max_tokens, **kwargs)

    async def generate_with_system_async(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response using system and user prompts (asynchronous).

        This is a convenience method that constructs messages from system and user
        prompts and calls generate_async().

        Args:
            system_prompt: The system prompt to set context.
            user_prompt: The user's input prompt.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse object containing the generated content.
        """
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        return await self.generate_async(messages, temperature, max_tokens, **kwargs)

    @abstractmethod
    def check_config(self) -> bool:
        """Validates the client configuration.

        Checks whether the client is properly configured with valid API keys,
        endpoints, and other required settings.

        Returns:
            True if configuration is valid, False otherwise.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement check_config()")


