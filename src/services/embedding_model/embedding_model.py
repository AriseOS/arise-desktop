"""Abstract Embedding Model Interface.

This module provides the abstract base class for embedding models, defining a unified
interface for text embedding operations across different providers and implementations.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import numpy as np


class EmbeddingProvider(Enum):
    """Enumeration of supported embedding providers.

    Attributes:
        OPENAI: OpenAI embedding models (text-embedding-ada-002, etc.)
        LOCAL_BGE: Local BGE (BAAI General Embedding) models
        HUGGINGFACE: HuggingFace transformer models
        SENTENCE_TRANSFORMERS: Sentence-BERT models
    """

    OPENAI = "openai"
    LOCAL_BGE = "local_bge"
    HUGGINGFACE = "huggingface"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class EmbeddingResponse:
    """Represents a response from an embedding model.

    Attributes:
        embedding: The embedding vector(s) as numpy array.
        model: The model name used for embedding generation.
        provider: The provider name (e.g., "openai", "local_bge").
        dimension: The dimensionality of the embedding vector.
        usage: Optional token/input usage information.
        metadata: Optional additional response metadata.
    """

    def __init__(
        self,
        embedding: Union[np.ndarray, List[float]],
        *,
        model: str = "",
        provider: str = "",
        dimension: Optional[int] = None,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes an EmbeddingResponse.

        Args:
            embedding: The embedding vector(s) as numpy array or list.
            model: The model name used for embedding generation.
            provider: The provider name.
            dimension: The dimensionality of the embedding. Auto-computed if None.
            usage: Optional usage information (e.g., tokens).
            metadata: Optional additional response metadata.
        """
        # Convert to numpy array if needed
        if isinstance(embedding, list):
            self.embedding = np.array(embedding)
        else:
            self.embedding = embedding

        self.model = model
        self.provider = provider

        # Determine dimension
        if dimension is not None:
            self.dimension = dimension
        else:
            # Auto-compute dimension
            if len(self.embedding.shape) == 1:
                self.dimension = self.embedding.shape[0]
            elif len(self.embedding.shape) == 2:
                self.dimension = self.embedding.shape[1]
            else:
                self.dimension = 0

        self.usage = usage or {}
        self.metadata = metadata or {}

    def to_list(self) -> List[float]:
        """Converts the embedding to a Python list.

        Returns:
            The embedding vector as a list of floats.
        """
        return self.embedding.tolist()

    def normalize(self) -> None:
        """Normalizes the embedding vector to unit length (L2 norm).

        Modifies the embedding in-place.
        """
        if len(self.embedding.shape) == 1:
            norm = np.linalg.norm(self.embedding)
            if norm > 0:
                self.embedding = self.embedding / norm
        elif len(self.embedding.shape) == 2:
            norms = np.linalg.norm(self.embedding, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
            self.embedding = self.embedding / norms


class EmbeddingModel(ABC):
    """Abstract base class for embedding models.

    This class defines the interface that all embedding model implementations must follow,
    supporting both single and batch text embedding operations, with optional async support.

    Attributes:
        model_name: The name of the embedding model to use.
        provider: The embedding provider type.
        dimension: The output dimension of embeddings.
        config: Additional configuration parameters.
    """

    def __init__(
        self, model_name: str = "default", dimension: int = 768, **kwargs: Any
    ) -> None:
        """Initializes an EmbeddingModel.

        Args:
            model_name: The name of the embedding model to use.
            dimension: The output dimension of embeddings.
            **kwargs: Additional configuration parameters.
        """
        self.model_name = model_name
        self.provider = EmbeddingProvider.LOCAL_BGE  # Default provider
        self.dimension = dimension
        self.config = kwargs

    def __call__(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Allows the model to be called directly as a function.

        This method provides a convenient shorthand for the embed() method,
        allowing models to be used as callables.

        Args:
            text: Input text to embed.
            **kwargs: Additional provider-specific parameters.

        Returns:
            EmbeddingResponse object containing the embedding vector.
        """
        return self.embed(text, **kwargs)

    @abstractmethod
    def embed(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input (synchronous).

        Args:
            text: Input text to embed.
            **kwargs: Additional provider-specific parameters.

        Returns:
            EmbeddingResponse object containing the embedding vector.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement embed()")

    @abstractmethod
    def embed_batch(self, texts: List[str], **kwargs: Any) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs (synchronous batch).

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of EmbeddingResponse objects, one per input text.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement embed_batch()")

    @abstractmethod
    async def embed_async(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        """Generates an embedding for a single text input (asynchronous).

        Args:
            text: Input text to embed.
            **kwargs: Additional provider-specific parameters.

        Returns:
            EmbeddingResponse object containing the embedding vector.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement embed_async()")

    @abstractmethod
    async def embed_batch_async(
        self, texts: List[str], **kwargs: Any
    ) -> List[EmbeddingResponse]:
        """Generates embeddings for multiple text inputs (asynchronous batch).

        Args:
            texts: List of input texts to embed.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of EmbeddingResponse objects, one per input text.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement embed_batch_async()")

    @abstractmethod
    def check_config(self) -> bool:
        """Validates the model configuration.

        Checks whether the model is properly configured with valid settings,
        API keys (if required), and other necessary parameters.

        Returns:
            True if configuration is valid, False otherwise.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement check_config()")

    def compute_similarity(
        self,
        embedding1: Union[EmbeddingResponse, np.ndarray],
        embedding2: Union[EmbeddingResponse, np.ndarray],
        metric: str = "cosine",
    ) -> float:
        """Computes similarity between two embeddings.

        Args:
            embedding1: First embedding (EmbeddingResponse or numpy array).
            embedding2: Second embedding (EmbeddingResponse or numpy array).
            metric: Similarity metric to use ("cosine", "euclidean", "dot").

        Returns:
            Similarity score as a float.

        Raises:
            ValueError: If the metric is not supported.
        """
        # Extract numpy arrays
        vec1 = (
            embedding1.embedding
            if isinstance(embedding1, EmbeddingResponse)
            else embedding1
        )
        vec2 = (
            embedding2.embedding
            if isinstance(embedding2, EmbeddingResponse)
            else embedding2
        )

        # Ensure 1D vectors
        vec1 = vec1.flatten()
        vec2 = vec2.flatten()

        if metric == "cosine":
            # Cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(dot_product / (norm1 * norm2))

        if metric == "euclidean":
            # Negative Euclidean distance (higher is more similar)
            return float(-np.linalg.norm(vec1 - vec2))

        if metric == "dot":
            # Dot product
            return float(np.dot(vec1, vec2))

        raise ValueError(f"Unsupported similarity metric: {metric}")


def create_embedding_model(
    provider: Union[str, EmbeddingProvider],
    model_name: Optional[str] = None,
    dimension: Optional[int] = None,
    **kwargs: Any,
) -> "EmbeddingModel":
    """Factory function for creating embedding models.

    Args:
        provider: The embedding provider (string or EmbeddingProvider enum).
        model_name: The model name to use. If None, uses provider default.
        dimension: The embedding dimension. If None, uses provider default.
        **kwargs: Additional configuration parameters.

    Returns:
        An instance of the appropriate embedding model.

    Raises:
        ValueError: If the provider is not supported.
    """
    # Import here to avoid circular dependencies
    # pylint: disable=import-outside-toplevel
    from src.services.embedding_model.local_bge_model import LocalBGEModel
    from src.services.embedding_model.openai_embedding import OpenAIEmbedding

    if isinstance(provider, str):
        provider = EmbeddingProvider(provider)

    if provider == EmbeddingProvider.OPENAI:
        model_name = model_name or "text-embedding-ada-002"
        dimension = dimension or 1536
        return OpenAIEmbedding(model_name=model_name, dimension=dimension, **kwargs)

    if provider == EmbeddingProvider.LOCAL_BGE:
        model_name = model_name or "BAAI/bge-base-en-v1.5"
        dimension = dimension or 768
        return LocalBGEModel(model_name=model_name, dimension=dimension, **kwargs)

    raise ValueError(f"Unsupported embedding provider: {provider}")
