"""Anthropic Claude LLM Client Implementation.

This module provides the Anthropic Claude-specific implementation of the LLM client
interface, supporting Claude models with both synchronous and asynchronous operations.
"""

import asyncio
from typing import Any, Dict, List, Optional

from src.services.llm.llm_client import LLMClient, LLMMessage, LLMProvider, LLMResponse


class ClaudeLLMClient(LLMClient):
    """Anthropic Claude LLM client implementation.

    This class wraps the Anthropic API to provide a unified interface for generating
    responses from Claude models. It supports both synchronous and asynchronous
    operations, batch processing, and handles Claude's unique system message format.

    Attributes:
        client: The Anthropic API client instance.
        model_name: The name of the Claude model to use.
        provider: Set to LLMProvider.ANTHROPIC.
        messages: Exposed for backward compatibility with existing code.
    """

    def __init__(
        self, api_client: Any, model_name: str = "claude-3-opus-20240229", **kwargs: Any
    ) -> None:
        """Initializes the Claude LLM client.

        Args:
            api_client: The Anthropic API client instance.
            model_name: The name of the Claude model to use.
            **kwargs: Additional configuration parameters.
        """
        super().__init__(model_name, **kwargs)
        self.client = api_client
        self.provider = LLMProvider.ANTHROPIC

        # Expose messages interface for backward compatibility
        self.messages = api_client.messages if hasattr(api_client, "messages") else None

    def __call__(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Allows the client to be called directly.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional Claude-specific parameters.

        Returns:
            LLMResponse object containing the generated content.
        """
        return self.generate(messages, temperature, max_tokens, **kwargs)

    def _prepare_messages(
        self, messages: List[LLMMessage]
    ) -> tuple[str, List[Dict[str, str]]]:
        """Prepares messages for Claude API format.

        Claude requires system messages to be passed separately from the
        conversation messages.

        Args:
            messages: List of LLMMessage objects.

        Returns:
            A tuple of (system_prompt, user_messages) where:
                - system_prompt: The combined system message content
                - user_messages: List of non-system message dicts
        """
        system_prompt = ""
        user_messages = []

        for msg in messages:
            if msg.role == "system":
                # Combine multiple system messages if present
                if system_prompt:
                    system_prompt += "\n\n" + msg.content
                else:
                    system_prompt = msg.content
            else:
                user_messages.append(msg.to_dict())

        return system_prompt, user_messages

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response from Claude models (synchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional parameters:
                - stop_sequences (list): Custom stop sequences.
                - top_p (float): Nucleus sampling parameter.
                - top_k (int): Top-k sampling parameter.
                - Additional Anthropic API parameters.

        Returns:
            LLMResponse object with generated content and metadata.

        Raises:
            Exception: If the API call fails.
        """
        system_prompt, user_messages = self._prepare_messages(messages)

        # Build API request parameters
        api_params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add system prompt if present
        if system_prompt:
            api_params["system"] = system_prompt

        # Add additional Claude-specific parameters
        for key in ["stop_sequences", "top_p", "top_k"]:
            if key in kwargs:
                api_params[key] = kwargs[key]

        # Call Anthropic API
        response = self.client.messages.create(**api_params)

        # Extract usage information
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return LLMResponse(
            content=response.content[0].text,
            model=self.model_name,
            provider=self.provider.value,
            usage=usage,
        )

    async def generate_async(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response from Claude models (asynchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional parameters (same as generate()).

        Returns:
            LLMResponse object with generated content and metadata.

        Raises:
            Exception: If the API call fails.
        """
        # If client has async support, use it
        if hasattr(self.client, "async_messages"):
            return await self._generate_async_native(
                messages, temperature, max_tokens, **kwargs
            )
        else:
            # Fall back to running sync method in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: self.generate(messages, temperature, max_tokens, **kwargs)
            )

    async def _generate_async_native(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> LLMResponse:
        """Native async generation using Anthropic async client.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters.

        Returns:
            LLMResponse object.
        """
        system_prompt, user_messages = self._prepare_messages(messages)

        api_params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_prompt:
            api_params["system"] = system_prompt

        # Add additional parameters
        for key in ["stop_sequences", "top_p", "top_k"]:
            if key in kwargs:
                api_params[key] = kwargs[key]

        # Call async Anthropic API
        async_client = self.client.async_messages
        response = await async_client.create(**api_params)

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return LLMResponse(
            content=response.content[0].text,
            model=self.model_name,
            provider=self.provider.value,
            usage=usage,
        )

    def generate_batch(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates responses for multiple message lists (synchronous).

        Args:
            batch_messages: List of message lists to process.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional Claude-specific parameters.

        Returns:
            List of LLMResponse objects, one for each input message list.
        """
        responses = []
        for messages in batch_messages:
            response = self.generate(messages, temperature, max_tokens, **kwargs)
            responses.append(response)
        return responses

    async def generate_batch_async(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates responses for multiple message lists (asynchronous).

        Processes all requests concurrently for improved performance.

        Args:
            batch_messages: List of message lists to process.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional Claude-specific parameters.

        Returns:
            List of LLMResponse objects, one for each input message list.
        """
        tasks = [
            self.generate_async(messages, temperature, max_tokens, **kwargs)
            for messages in batch_messages
        ]
        return await asyncio.gather(*tasks)

    def check_config(self) -> bool:
        """Validates the Claude client configuration.

        Checks whether the client is properly configured with a valid API client
        and required attributes.

        Returns:
            True if configuration is valid, False otherwise.
        """
        if not self.client:
            return False

        # Check if client has required messages interface
        if not hasattr(self.client, "messages"):
            return False

        # Check if model name is set
        if not self.model_name:
            return False

        return True
