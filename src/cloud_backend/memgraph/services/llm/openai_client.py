"""OpenAI LLM Client Implementation.

This module provides the OpenAI-specific implementation of the LLM client interface,
supporting GPT models with both synchronous and asynchronous operations.
"""

import asyncio
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.services.llm.llm_client import LLMClient, LLMMessage, LLMProvider, LLMResponse


class OpenAILLMClient(LLMClient):
    """OpenAI LLM client implementation.

    This class wraps the OpenAI API to provide a unified interface for generating
    responses from GPT models. It supports both synchronous and asynchronous
    operations, batch processing, and JSON mode.

    Attributes:
        client: The OpenAI API client instance.
        model_name: The name of the GPT model to use.
        provider: Set to LLMProvider.OPENAI.
        chat: Exposed for backward compatibility with existing code.
    """

    def __init__(
        self, api_client: Any, model_name: str = "gpt-4", **kwargs: Any
    ) -> None:
        """Initializes the OpenAI LLM client.

        Args:
            api_client: The OpenAI API client instance.
            model_name: The name of the GPT model to use (default: "gpt-4").
            **kwargs: Additional configuration parameters.
        """
        super().__init__(model_name, **kwargs)
        self.client = api_client
        self.provider = LLMProvider.OPENAI

        # Expose chat interface for backward compatibility
        self.chat = api_client.chat if hasattr(api_client, "chat") else None

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
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional OpenAI-specific parameters.

        Returns:
            LLMResponse object containing the generated content.
        """
        return self.generate(messages, temperature, max_tokens, **kwargs)

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a response from OpenAI GPT models (synchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional parameters:
                - json_mode (bool): Enable JSON response format (GPT-4/3.5 only).
                - response_format (dict): Custom response format specification.
                - Additional OpenAI API parameters.

        Returns:
            LLMResponse object with generated content and metadata.

        Raises:
            Exception: If the API call fails.
        """
        message_dicts = [msg.to_dict() for msg in messages]

        # Build API request parameters
        api_params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": message_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add JSON mode support for GPT-4 and GPT-3.5 models
        if "gpt-4" in self.model_name or "gpt-3.5" in self.model_name:
            if kwargs.get("json_mode", False):
                api_params["response_format"] = {"type": "json_object"}
            elif "response_format" in kwargs:
                api_params["response_format"] = kwargs.pop("response_format")

        # Add any additional parameters
        api_params.update({k: v for k, v in kwargs.items() if k not in ["json_mode"]})

        # Call OpenAI API
        response = self.client.chat.completions.create(**api_params)

        # Extract usage information
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=response.choices[0].message.content,
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
        """Generates a response from OpenAI GPT models (asynchronous).

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional parameters (same as generate()).

        Returns:
            LLMResponse object with generated content and metadata.

        Raises:
            Exception: If the API call fails.
        """
        # If client has async support, use it
        if hasattr(self.client, "async_client"):
            # Use async client directly
            return await self._generate_async_native(
                messages, temperature, max_tokens, **kwargs
            )
        else:
            # Fall back to running sync method in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.generate, messages, temperature, max_tokens, kwargs
            )

    async def _generate_async_native(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> LLMResponse:
        """Native async generation using OpenAI async client.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters.

        Returns:
            LLMResponse object.
        """
        message_dicts = [msg.to_dict() for msg in messages]

        api_params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": message_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add JSON mode support
        if "gpt-4" in self.model_name or "gpt-3.5" in self.model_name:
            if kwargs.get("json_mode", False):
                api_params["response_format"] = {"type": "json_object"}
            elif "response_format" in kwargs:
                api_params["response_format"] = kwargs.pop("response_format")

        api_params.update({k: v for k, v in kwargs.items() if k not in ["json_mode"]})

        # Call async OpenAI API
        async_client = self.client.async_client
        response = await async_client.chat.completions.create(**api_params)

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=response.choices[0].message.content,
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
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional OpenAI-specific parameters.

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
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum number of tokens to generate.
            **kwargs: Additional OpenAI-specific parameters.

        Returns:
            List of LLMResponse objects, one for each input message list.
        """
        tasks = [
            self.generate_async(messages, temperature, max_tokens, **kwargs)
            for messages in batch_messages
        ]
        return await asyncio.gather(*tasks)

    def check_config(self) -> bool:
        """Validates the OpenAI client configuration.

        Checks whether the client is properly configured with a valid API client
        and required attributes.

        Returns:
            True if configuration is valid, False otherwise.
        """
        if not self.client:
            return False

        # Check if client has required chat.completions interface
        if not hasattr(self.client, "chat"):
            return False

        if not hasattr(self.client.chat, "completions"):
            return False

        # Check if model name is set
        if not self.model_name:
            return False

        return True
