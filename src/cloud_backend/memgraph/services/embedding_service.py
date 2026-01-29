"""Embedding Service - Singleton service for embedding model management.

This module provides a singleton service for managing embedding models,
supporting configuration-based initialization and lazy loading.
"""

import os
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingResponse,
)
from src.cloud_backend.memgraph.services.embedding_model.local_bge_model import (
    LocalBGEModel,
)
from src.cloud_backend.memgraph.services.embedding_model.openai_embedding import (
    OpenAIEmbedding,
)


class EmbeddingService:
    """Singleton service for embedding model management.

    Provides a centralized service for embedding operations with lazy
    initialization and configuration-based model selection.

    Attributes:
        _instance: Singleton instance.
        _model: The embedding model instance.
        _config: Configuration dictionary.
        _initialized: Whether the service has been initialized.
    """

    _instance: Optional["EmbeddingService"] = None
    _model: Optional[EmbeddingModel] = None
    _config: Dict[str, Any] = {}
    _initialized: bool = False

    def __new__(cls) -> "EmbeddingService":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def configure(
        cls,
        provider: str = "openai",
        model: str = "BAAI/bge-m3",
        dimension: int = 1024,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Configure the embedding service.

        Args:
            provider: Embedding provider ('openai' or 'local_bge').
            model: Model name/identifier.
            dimension: Embedding vector dimension.
            api_url: Custom API base URL (for OpenAI-compatible APIs).
            api_key: API key (optional, can use api_key_env instead).
            api_key_env: Environment variable name for API key.
            **kwargs: Additional provider-specific configuration.
        """
        cls._config = {
            "provider": provider,
            "model": model,
            "dimension": dimension,
            "api_url": api_url,
            "api_key": api_key,
            "api_key_env": api_key_env,
            **kwargs,
        }
        # Reset model to force re-initialization with new config
        cls._model = None
        cls._initialized = False

    @classmethod
    def configure_from_dict(cls, config: Dict[str, Any]) -> None:
        """Configure from a dictionary (e.g., from YAML config).

        Args:
            config: Configuration dictionary with keys:
                - provider: 'openai' or 'local_bge'
                - model: Model name
                - dimension: Vector dimension
                - api_url: Custom API URL (optional)
                - api_key_env: Env var name for API key
        """
        cls.configure(
            provider=config.get("provider", "openai"),
            model=config.get("model", "BAAI/bge-m3"),
            dimension=config.get("dimension", 1024),
            api_url=config.get("api_url"),
            api_key=config.get("api_key"),
            api_key_env=config.get("api_key_env", "SILICONFLOW_API_KEY"),
        )

    @classmethod
    def _initialize_model(cls) -> None:
        """Initialize the embedding model based on configuration."""
        if cls._initialized and cls._model is not None:
            return

        provider = cls._config.get("provider", "openai")
        model_name = cls._config.get("model", "BAAI/bge-m3")
        dimension = cls._config.get("dimension", 1024)

        # Get API key from env if not provided directly
        api_key = cls._config.get("api_key")
        if not api_key:
            api_key_env = cls._config.get("api_key_env", "SILICONFLOW_API_KEY")
            api_key = os.getenv(api_key_env)

        if provider == "openai":
            api_url = cls._config.get("api_url")
            cls._model = OpenAIEmbedding(
                model_name=model_name,
                dimension=dimension,
                api_key=api_key,
                base_url=api_url,
            )
        elif provider == "local_bge":
            cls._model = LocalBGEModel(
                model_name=model_name,
                dimension=dimension,
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

        cls._initialized = True

    @classmethod
    def get_model(cls) -> Optional[EmbeddingModel]:
        """Get the embedding model instance.

        Returns:
            The embedding model instance, or None if not configured.
        """
        if not cls._initialized:
            cls._initialize_model()
        return cls._model

    @classmethod
    def is_available(cls) -> bool:
        """Check if the embedding service is available and configured.

        Returns:
            True if the service is properly configured and can generate embeddings.
        """
        try:
            if not cls._initialized:
                cls._initialize_model()
            return cls._model is not None and cls._model.check_config()
        except Exception:
            return False

    @classmethod
    def embed(cls, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Generate embedding for a single text.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.
        """
        if not cls.is_available():
            return None

        try:
            response = cls._model.embed(text, **kwargs)
            return response.to_list()
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None

    @classmethod
    def encode(cls, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Alias for embed() - for compatibility with Reasoner interface.

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.
        """
        return cls.embed(text, **kwargs)

    @classmethod
    def embed_batch(cls, texts: List[str], **kwargs: Any) -> Optional[List[List[float]]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            List of embedding vectors, or None if unavailable.
        """
        if not cls.is_available():
            return None

        try:
            responses = cls._model.embed_batch(texts, **kwargs)
            return [resp.to_list() for resp in responses]
        except Exception as e:
            print(f"Error generating batch embeddings: {e}")
            return None

    @classmethod
    async def embed_async(cls, text: str, **kwargs: Any) -> Optional[List[float]]:
        """Generate embedding for a single text (async).

        Args:
            text: Input text to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            Embedding vector as a list of floats, or None if unavailable.
        """
        if not cls.is_available():
            return None

        try:
            response = await cls._model.embed_async(text, **kwargs)
            return response.to_list()
        except Exception as e:
            print(f"Error generating async embedding: {e}")
            return None

    @classmethod
    async def embed_batch_async(
        cls, texts: List[str], **kwargs: Any
    ) -> Optional[List[List[float]]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional parameters for the embedding model.

        Returns:
            List of embedding vectors, or None if unavailable.
        """
        if not cls.is_available():
            return None

        try:
            responses = await cls._model.embed_batch_async(texts, **kwargs)
            return [resp.to_list() for resp in responses]
        except Exception as e:
            print(f"Error generating async batch embeddings: {e}")
            return None

    @classmethod
    def get_dimension(cls) -> int:
        """Get the embedding dimension.

        Returns:
            The configured embedding dimension.
        """
        return cls._config.get("dimension", 1024)

    @classmethod
    def reset(cls) -> None:
        """Reset the service to uninitialized state.

        Useful for testing or reconfiguration.
        """
        cls._model = None
        cls._config = {}
        cls._initialized = False


# Convenience functions for direct usage
def get_embedding_service() -> EmbeddingService:
    """Get the EmbeddingService singleton instance.

    Returns:
        The EmbeddingService singleton.
    """
    return EmbeddingService()


def embed_text(text: str) -> Optional[List[float]]:
    """Generate embedding for a single text.

    Args:
        text: Input text to embed.

    Returns:
        Embedding vector as a list of floats, or None if unavailable.
    """
    return EmbeddingService.embed(text)


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings for multiple texts.

    Args:
        texts: List of input texts to embed.

    Returns:
        List of embedding vectors, or None if unavailable.
    """
    return EmbeddingService.embed_batch(texts)


__all__ = [
    "EmbeddingService",
    "get_embedding_service",
    "embed_text",
    "embed_texts",
]
