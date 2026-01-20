"""OpenAI Embedding Model.

This module provides an implementation of text embeddings using OpenAI's embedding
models, such as text-embedding-ada-002 and text-embedding-3-small/large.
"""

import os
from typing import Any, List, Optional

from src.cloud_backend.memgraph.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingProvider,
    EmbeddingResponse,
)


class OpenAIEmbedding(EmbeddingModel):
    """OpenAI embedding model implementation.

    Uses OpenAI's embedding API to generate high-quality text embeddings.
    Supports various OpenAI embedding models with different capabilities
    and price points.

    Attributes:
        model_name: The OpenAI model name (e.g., "text-embedding-ada-002").
        provider: Set to EmbeddingProvider.OPENAI.
        dimension: The output dimension of embeddings.
        client: The OpenAI client instance.
        api_key: The OpenAI API key.
        config: Additional configuration parameters.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-ada-002",
        dimension: int = 1536,
        api_client: Optional[Any] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initializes the OpenAIEmbedding model.

        Args:
            model_name: The OpenAI embedding model name. Options:
                - "text-embedding-ada-002" (1536 dim, recommended)
                - "text-embedding-3-small" (1536 dim, cost-effective)
                - "text-embedding-3-large" (3072 dim, highest quality)
            dimension: The expected output dimension of embeddings.
            api_client: Pre-initialized OpenAI client instance (optional).
            api_key: OpenAI API key (optional, reads from env if not provided).
            base_url: Custom API base URL for OpenAI-compatible APIs (optional).
                If not provided, uses the default OpenAI API URL.
            **kwargs: Additional configuration parameters:
                - timeout: Request timeout in seconds (default: 60)
                - max_retries: Maximum number of retries (default: 3)
        """
        super().__init__(model_name=model_name, dimension=dimension, **kwargs)
        self.provider = EmbeddingProvider.OPENAI

        # Get API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        # Store base_url for custom API endpoints
        self.base_url = base_url

        # Extract configuration (must be before _initialize_client)
        self.timeout = kwargs.get("timeout", 60)
        self.max_retries = kwargs.get("max_retries", 3)

        # Initialize client
        self.client = api_client
        self.async_client = None  # Will be initialized on first async call

        if self.client is None and self.api_key:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initializes the OpenAI client.

        Raises:
            ImportError: If openai library is not installed.
            ValueError: If API key is not available.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai library is required for OpenAIEmbedding. "
                "Install it with: pip install openai"
            ) from exc

        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment "
                "variable or provide api_key parameter."
            )

        # Build client kwargs
        client_kwargs = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }

        # Add base_url if provided (for OpenAI-compatible APIs)
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = OpenAI(**client_kwargs)

    def embed(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters:
                - user: User identifier for tracking (optional).

        Returns:
            EmbeddingResponse containing the embedding vector.

        Raises:
            RuntimeError: If the API call fails.
        """
        if self.client is None:
            self._initialize_client()

        try:
            # Call OpenAI API
            user = kwargs.get("user", None)
            response = self.client.embeddings.create(
                model=self.model_name, input=text, user=user
            )

            # Extract embedding
            embedding = response.data[0].embedding

            # Extract usage information
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            return EmbeddingResponse(
                embedding=embedding,
                model=self.model_name,
                provider=self.provider.value,
                dimension=len(embedding),
                usage=usage,
            )

        except Exception as exc:
            raise RuntimeError(f"OpenAI embedding API call failed: {exc}") from exc

    def embed_batch(self, texts: List[str], **kwargs: Any) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs.

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters:
                - user: User identifier for tracking (optional).

        Returns:
            List of EmbeddingResponse objects, one per input text.

        Raises:
            RuntimeError: If the API call fails.
        """
        if self.client is None:
            self._initialize_client()

        try:
            # Call OpenAI API with batch
            user = kwargs.get("user", None)
            response = self.client.embeddings.create(
                model=self.model_name, input=texts, user=user
            )

            # Extract embeddings
            responses = []
            for data_item in response.data:
                embedding = data_item.embedding

                # Calculate per-item usage (approximate)
                total_tokens = response.usage.total_tokens
                tokens_per_item = total_tokens // len(texts)

                usage = {
                    "prompt_tokens": tokens_per_item,
                    "total_tokens": tokens_per_item,
                }

                resp = EmbeddingResponse(
                    embedding=embedding,
                    model=self.model_name,
                    provider=self.provider.value,
                    dimension=len(embedding),
                    usage=usage,
                )
                responses.append(resp)

            return responses

        except Exception as exc:
            raise RuntimeError(
                f"OpenAI embedding batch API call failed: {exc}"
            ) from exc

    async def embed_async(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input (async).

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters:
                - user: User identifier for tracking (optional).

        Returns:
            EmbeddingResponse containing the embedding vector.

        Raises:
            RuntimeError: If the API call fails.
        """
        if self.client is None:
            self._initialize_client()

        try:
            # pylint: disable=import-outside-toplevel
            from openai import AsyncOpenAI

            # Create async client if needed
            if self.async_client is None:
                async_client_kwargs = {
                    "api_key": self.api_key,
                    "timeout": self.timeout,
                    "max_retries": self.max_retries,
                }
                if self.base_url:
                    async_client_kwargs["base_url"] = self.base_url
                self.async_client = AsyncOpenAI(**async_client_kwargs)

            # Call OpenAI API (async)
            user = kwargs.get("user", None)
            response = await self.async_client.embeddings.create(
                model=self.model_name, input=text, user=user
            )

            # Extract embedding
            embedding = response.data[0].embedding

            # Extract usage information
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            return EmbeddingResponse(
                embedding=embedding,
                model=self.model_name,
                provider=self.provider.value,
                dimension=len(embedding),
                usage=usage,
            )

        except Exception as exc:
            raise RuntimeError(
                f"OpenAI async embedding API call failed: {exc}"
            ) from exc

    async def embed_batch_async(
        self, texts: List[str], **kwargs: Any
    ) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs (async).

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters:
                - user: User identifier for tracking (optional).

        Returns:
            List of EmbeddingResponse objects, one per input text.

        Raises:
            RuntimeError: If the API call fails.
        """
        if self.client is None:
            self._initialize_client()

        try:
            # pylint: disable=import-outside-toplevel
            from openai import AsyncOpenAI

            # Create async client if needed
            if self.async_client is None:
                self.async_client = AsyncOpenAI(
                    api_key=self.api_key,
                    timeout=self.timeout,
                    max_retries=self.max_retries,
                )

            # Call OpenAI API with batch (async)
            user = kwargs.get("user", None)
            response = await self.async_client.embeddings.create(
                model=self.model_name, input=texts, user=user
            )

            # Extract embeddings
            responses = []
            for data_item in response.data:
                embedding = data_item.embedding

                # Calculate per-item usage (approximate)
                total_tokens = response.usage.total_tokens
                tokens_per_item = total_tokens // len(texts)

                usage = {
                    "prompt_tokens": tokens_per_item,
                    "total_tokens": tokens_per_item,
                }

                resp = EmbeddingResponse(
                    embedding=embedding,
                    model=self.model_name,
                    provider=self.provider.value,
                    dimension=len(embedding),
                    usage=usage,
                )
                responses.append(resp)

            return responses

        except Exception as exc:
            raise RuntimeError(
                f"OpenAI async batch embedding API call failed: {exc}"
            ) from exc

    def check_config(self) -> bool:
        """Validates the model configuration.

        Checks if the API key is available and the client can be initialized.

        Returns:
            True if configuration is valid, False otherwise.
        """
        # pylint: disable=broad-exception-caught
        try:
            if not self.api_key:
                return False

            if self.client is None:
                self._initialize_client()

            return self.client is not None

        except Exception:
            return False
