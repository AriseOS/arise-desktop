"""Mock LLM Client Implementation.

This module provides a mock implementation of the LLM client interface for testing
and development purposes. It returns predefined responses without making actual
API calls.
"""

import asyncio
from typing import Any, List

from src.cloud_backend.memgraph.services.llm.llm_client import LLMClient, LLMMessage, LLMProvider, LLMResponse


class MockLLMClient(LLMClient):
    """Mock LLM client for testing and development.

    This client simulates LLM behavior without making actual API calls. It returns
    predefined responses and can be configured to simulate different scenarios.

    Attributes:
        model_name: The mock model name.
        provider: Set to LLMProvider.MOCK.
        response_text: The default response text to return.
        chat: Mock OpenAI-style chat interface.
        messages: Mock Anthropic-style messages interface.
    """

    def __init__(self, model_name: str = "mock-model", **kwargs: Any) -> None:
        """Initializes the mock LLM client.

        Args:
            model_name: The mock model name (default: "mock-model").
            **kwargs: Additional configuration parameters:
                - response_text (str): Custom response text to return.
        """
        super().__init__(model_name, **kwargs)
        self.provider = LLMProvider.MOCK
        self.response_text = kwargs.get("response_text", "Mock LLM response")

        # Provide backward-compatible API interfaces
        self.chat = self._MockChat(self)
        self.messages = self._MockMessages(self)

    class _MockChat:
        """Mock OpenAI chat interface for backward compatibility."""

        def __init__(self, parent: "MockLLMClient") -> None:
            """Initializes the mock chat interface.

            Args:
                parent: The parent MockLLMClient instance.
            """
            self.parent = parent
            self.completions = self._MockCompletions(parent)

        class _MockCompletions:
            """Mock OpenAI completions interface."""

            def __init__(self, parent: "MockLLMClient") -> None:
                """Initializes the mock completions interface.

                Args:
                    parent: The parent MockLLMClient instance.
                """
                self.parent = parent

            def create(self, **kwargs: Any) -> Any:
                """Simulates OpenAI completions.create() method.

                Args:
                    **kwargs: API parameters (ignored).

                Returns:
                    A mock response object mimicking OpenAI's response format.
                """

                class MockResponse:
                    """Mock response object."""

                    def __init__(self, content: str) -> None:
                        self.choices = [
                            type(
                                "obj",
                                (object,),
                                {
                                    "message": type(
                                        "obj", (object,), {"content": content}
                                    )()
                                },
                            )()
                        ]
                        self.usage = type(
                            "obj",
                            (object,),
                            {
                                "prompt_tokens": 10,
                                "completion_tokens": 20,
                                "total_tokens": 30,
                            },
                        )()

                return MockResponse(self.parent.response_text)

    class _MockMessages:
        """Mock Anthropic messages interface for backward compatibility."""

        def __init__(self, parent: "MockLLMClient") -> None:
            """Initializes the mock messages interface.

            Args:
                parent: The parent MockLLMClient instance.
            """
            self.parent = parent

        def create(self, **kwargs: Any) -> Any:
            """Simulates Anthropic messages.create() method.

            Args:
                **kwargs: API parameters (ignored).

            Returns:
                A mock response object mimicking Anthropic's response format.
            """

            class MockResponse:
                """Mock response object."""

                def __init__(self, content: str) -> None:
                    self.content = [type("obj", (object,), {"text": content})()]
                    self.usage = type(
                        "obj", (object,), {"input_tokens": 10, "output_tokens": 20}
                    )()

            return MockResponse(self.parent.response_text)

    def __call__(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Allows the client to be called directly.

        Args:
            messages: List of conversation messages (ignored).
            temperature: Sampling temperature (ignored).
            max_tokens: Maximum number of tokens (ignored).
            **kwargs: Additional parameters (ignored).

        Returns:
            LLMResponse object with mock content.
        """
        return self.generate(messages, temperature, max_tokens, **kwargs)

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a mock response (synchronous).

        Args:
            messages: List of conversation messages (ignored).
            temperature: Sampling temperature (ignored).
            max_tokens: Maximum number of tokens (ignored).
            **kwargs: Additional parameters (ignored).

        Returns:
            LLMResponse object with predefined mock content.
        """
        return LLMResponse(
            content=self.response_text,
            model=self.model_name,
            provider=self.provider.value,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    async def generate_async(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generates a mock response (asynchronous).

        Args:
            messages: List of conversation messages (ignored).
            temperature: Sampling temperature (ignored).
            max_tokens: Maximum number of tokens (ignored).
            **kwargs: Additional parameters (ignored).

        Returns:
            LLMResponse object with predefined mock content.
        """
        # Simulate async delay
        await asyncio.sleep(0.01)
        return self.generate(messages, temperature, max_tokens, **kwargs)

    def generate_batch(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates mock responses for a batch (synchronous).

        Args:
            batch_messages: List of message lists to process.
            temperature: Sampling temperature (ignored).
            max_tokens: Maximum number of tokens (ignored).
            **kwargs: Additional parameters (ignored).

        Returns:
            List of LLMResponse objects with mock content.
        """
        return [
            self.generate(messages, temperature, max_tokens, **kwargs)
            for messages in batch_messages
        ]

    async def generate_batch_async(
        self,
        batch_messages: List[List[LLMMessage]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Generates mock responses for a batch (asynchronous).

        Args:
            batch_messages: List of message lists to process.
            temperature: Sampling temperature (ignored).
            max_tokens: Maximum number of tokens (ignored).
            **kwargs: Additional parameters (ignored).

        Returns:
            List of LLMResponse objects with mock content.
        """
        tasks = [
            self.generate_async(messages, temperature, max_tokens, **kwargs)
            for messages in batch_messages
        ]
        return await asyncio.gather(*tasks)

    def check_config(self) -> bool:
        """Validates the mock client configuration.

        The mock client is always considered valid since it doesn't require
        actual API credentials.

        Returns:
            Always True for mock clients.
        """
        return True
