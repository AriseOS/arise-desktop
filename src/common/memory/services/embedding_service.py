"""Embedding Service - Non-singleton service for embedding with user API key support.

This module provides a non-singleion service for embedding operations.
Each instance is configured with a specific user's API key for proper cost tracking.
"""

import logging
from typing import Any, List, Optional

from src.common.memory.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingResponse,
)
from src.common.memory.services.embedding_model.local_bge_model import (
    LocalBGEModel,
)
from src.common.memory.services.embedding_model.openai_embedding import (
    OpenAIEmbedding,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Non-singleion service for embedding operations with user API key.

    Each instance must be created with a user's API key to enable proper
    cost tracking and budget management.

    Attributes:
        _model: The embedding model instance.
        _config: Configuration dictionary.
        _initialized: Whether the model has been initialized.
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "BAAI/bge-m3",
        dimension: int = 1024,
        provider: str = "openai",
        **kwargs: Any,
    ):
        """Initialize EmbeddingService with user's API key.

        Args:
            api_key: User's API key for embedding service (required).
            base_url: Custom API base URL for CRS (e.g., https://api.ariseos.com/api).
            model: Model name/identifier.
            dimension: Embedding vector dimension.
            provider: Embedding provider ('openai' or 'local_bge').
            **kwargs: Additional provider-specific configuration.

        Raises:
            ValueError: If api_key is not provided.
        """
        if not api_key:
            raise ValueError("api_key is required for EmbeddingService")

        self._config = {
            "provider": provider,
            "model": model,
            "dimension": dimension,
            "api_url": base_url,
            "api_key": api_key,
            **kwargs,
        }
        self._model: Optional[EmbeddingModel] = None
        self._initialized = False

    def _initialize_model(self) -> None:
        """Initialize the embedding model based on configuration."""
        if self._initialized and self._model is not None:
            return

        provider = self._config.get("provider", "openai")
        model_name = self._config.get("model", "BAAI/bge-m3")
        dimension = self._config.get("dimension", 1024)
        api_key = self._config.get("api_key")

        if not api_key:
            raise RuntimeError("EmbeddingService: api_key not configured")

        if provider == "openai":
            api_url = self._config.get("api_url")
            self._model = OpenAIEmbedding(
                model_name=model_name,
                dimension=dimension,
                api_key=api_key,
                base_url=api_url,
            )
        elif provider == "local_bge":
            self._model = LocalBGEModel(
                model_name=model_name,
                dimension=dimension,
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

        self._initialized = True

    def is_available(self) -> bool:
        """Check if the embedding service is available and configured.

        Returns:
            True if the service is properly configured and can generate embeddings.
        """
        try:
            if not self._initialized:
                self._initialize_model()
            return self._model is not None and self._model.check_config()
        except Exception:
            return False

    def embed(self, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Generate embedding for a single text.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.

        Raises:
            RuntimeError: If service is not properly configured.
        """
        if not self._initialized:
            self._initialize_model()

        if self._model is None:
            raise RuntimeError("EmbeddingService: model not initialized")

        try:
            response = self._model.embed(text, **kwargs)
            return response.to_list()
        except Exception as e:
            logger.error(f"EmbeddingService: error generating embedding: {e}")
            raise

    def encode(self, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Alias for embed() - for compatibility with Reasoner interface.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.
        """
        return self.embed(text, **kwargs)

    async def encode_async(self, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Async alias for embed_async() - for compatibility with Reasoner interface."""
        return await self.embed_async(text, **kwargs)

    def embed_batch(self, texts: List[str], **kwargs: Any) -> Optional[List[List[float]]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            List of embedding vectors, or None if unavailable.

        Raises:
            RuntimeError: If service is not properly configured.
        """
        if not self._initialized:
            self._initialize_model()

        if self._model is None:
            raise RuntimeError("EmbeddingService: model not initialized")

        try:
            responses = self._model.embed_batch(texts, **kwargs)
            return [resp.to_list() for resp in responses]
        except Exception as e:
            logger.error(f"EmbeddingService: error generating batch embeddings: {e}")
            raise

    async def embed_async(self, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Generate embedding for a single text (async).

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.

        Raises:
            RuntimeError: If service is not properly configured.
        """
        if not self._initialized:
            self._initialize_model()

        if self._model is None:
            raise RuntimeError("EmbeddingService: model not initialized")

        try:
            response = await self._model.embed_async(text, **kwargs)
            return response.to_list()
        except Exception as e:
            logger.error(f"EmbeddingService: error generating async embedding: {e}")
            raise

    async def embed_batch_async(
        self, texts: List[str], **kwargs: Any
    ) -> Optional[List[List[float]]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            List of embedding vectors, or None if unavailable.

        Raises:
            RuntimeError: If service is not properly configured.
        """
        if not self._initialized:
            self._initialize_model()

        if self._model is None:
            raise RuntimeError("EmbeddingService: model not initialized")

        try:
            responses = await self._model.embed_batch_async(texts, **kwargs)
            return [resp.to_list() for resp in responses]
        except Exception as e:
            logger.error(f"EmbeddingService: error generating async batch embeddings: {e}")
            raise

    @property
    def dimension(self) -> int:
        """Get the embedding dimension.

        Returns:
            The configured embedding dimension.
        """
        return self._config.get("dimension", 1024)


__all__ = [
    "EmbeddingService",
]
