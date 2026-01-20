"""Abstract Rerank Model Interface.

This module provides the abstract base class for rerank models, defining a unified
interface for document reranking operations across different providers and implementations.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class RerankProvider(Enum):
    """Enumeration of supported rerank providers.

    Attributes:
        LOCAL_BGE: Local BGE (BAAI General Embedding) rerank models
        MAAS: Model as a Service rerank API
        COHERE: Cohere rerank API
        JINA: Jina rerank API
    """

    LOCAL_BGE = "local_bge"
    MAAS = "maas"
    COHERE = "cohere"
    JINA = "jina"


class RerankResult:
    """Represents a single document reranking result.

    Attributes:
        index: Original index of the document in the input list.
        document: The document text.
        score: Relevance score assigned by the rerank model.
        metadata: Optional additional metadata.
    """

    def __init__(
        self,
        index: int,
        document: str,
        score: float,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes a RerankResult.

        Args:
            index: Original index of the document.
            document: The document text.
            score: Relevance score.
            metadata: Optional metadata.
        """
        self.index = index
        self.document = document
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Converts the result to a dictionary.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "index": self.index,
            "document": self.document,
            "score": self.score,
            "metadata": self.metadata,
        }


class RerankResponse:
    """Represents a response from a rerank model.

    Attributes:
        query: The query text used for reranking.
        results: List of reranked results, sorted by relevance score.
        model: The model name used for reranking.
        provider: The provider name (e.g., "local_bge", "maas").
        usage: Optional usage information.
        metadata: Optional additional response metadata.
    """

    def __init__(
        self,
        query: str,
        results: List[RerankResult],
        *,
        model: str = "",
        provider: str = "",
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes a RerankResponse.

        Args:
            query: The query text.
            results: List of rerank results.
            model: The model name used.
            provider: The provider name.
            usage: Optional usage information.
            metadata: Optional metadata.
        """
        self.query = query
        self.results = results
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.metadata = metadata or {}

    def get_top_k(self, top_k: int) -> List[RerankResult]:
        """Returns the top K results.

        Args:
            top_k: Number of top results to return.

        Returns:
            List of top K rerank results.
        """
        return self.results[:top_k]

    def get_scores(self) -> List[float]:
        """Extracts all relevance scores.

        Returns:
            List of scores in the same order as results.
        """
        return [result.score for result in self.results]

    def get_documents(self) -> List[str]:
        """Extracts all reranked documents.

        Returns:
            List of documents in the reranked order.
        """
        return [result.document for result in self.results]

    def to_dict(self) -> Dict[str, Any]:
        """Converts the response to a dictionary.

        Returns:
            Dictionary representation of the response.
        """
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "metadata": self.metadata,
        }


class RerankModel(ABC):
    """Abstract base class for rerank models.

    This class defines the interface that all rerank model implementations must follow,
    supporting both single and batch reranking operations, with optional async support.

    Attributes:
        model_name: The name of the rerank model to use.
        provider: The rerank provider type.
        config: Additional configuration parameters.
    """

    def __init__(self, model_name: str = "default", **kwargs: Any) -> None:
        """Initializes a RerankModel.

        Args:
            model_name: The name of the rerank model to use.
            **kwargs: Additional configuration parameters.
        """
        self.model_name = model_name
        self.provider = RerankProvider.LOCAL_BGE  # Default provider
        self.config = kwargs

    def __call__(
        self, query: str, documents: List[str], **kwargs: Any
    ) -> RerankResponse:
        """Allows the model to be called directly as a function.

        This method provides a convenient shorthand for the rerank() method,
        allowing models to be used as callables.

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional provider-specific parameters.

        Returns:
            RerankResponse object containing reranked results.
        """
        return self.rerank(query, documents, **kwargs)

    @abstractmethod
    def rerank(self, query: str, documents: List[str], **kwargs: Any) -> RerankResponse:
        """Reranks documents based on relevance to the query (synchronous).

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional provider-specific parameters:
                - top_k: Return only top K results.

        Returns:
            RerankResponse object containing reranked results.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement rerank()")

    @abstractmethod
    def rerank_batch(
        self, queries: List[str], documents_list: List[List[str]], **kwargs: Any
    ) -> List[RerankResponse]:
        """Reranks multiple query-documents pairs (synchronous batch).

        Args:
            queries: List of query texts.
            documents_list: List of document lists, one per query.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of RerankResponse objects, one per query.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement rerank_batch()")

    @abstractmethod
    async def rerank_async(
        self, query: str, documents: List[str], **kwargs: Any
    ) -> RerankResponse:
        """Reranks documents based on relevance to the query (asynchronous).

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional provider-specific parameters.

        Returns:
            RerankResponse object containing reranked results.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement rerank_async()")

    @abstractmethod
    async def rerank_batch_async(
        self, queries: List[str], documents_list: List[List[str]], **kwargs: Any
    ) -> List[RerankResponse]:
        """Reranks multiple query-documents pairs (asynchronous batch).

        Args:
            queries: List of query texts.
            documents_list: List of document lists, one per query.
            **kwargs: Additional provider-specific parameters.

        Returns:
            List of RerankResponse objects, one per query.

        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclass must implement rerank_batch_async()")

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


def create_rerank_model(
    provider: Union[str, RerankProvider],
    model_name: Optional[str] = None,
    **kwargs: Any,
) -> "RerankModel":
    """Factory function for creating rerank models.

    Args:
        provider: The rerank provider (string or RerankProvider enum).
        model_name: The model name to use. If None, uses provider default.
        **kwargs: Additional configuration parameters.

    Returns:
        An instance of the appropriate rerank model.

    Raises:
        ValueError: If the provider is not supported.
    """
    # Import here to avoid circular dependencies
    # pylint: disable=import-outside-toplevel
    from src.services.rerank_model.local_bge_rerank_model import LocalBGERerankModel
    from src.services.rerank_model.maas_rerank_model import MaaSRerankModel

    if isinstance(provider, str):
        provider = RerankProvider(provider)

    if provider == RerankProvider.LOCAL_BGE:
        model_name = model_name or "BAAI/bge-reranker-base"
        return LocalBGERerankModel(model_name=model_name, **kwargs)

    if provider == RerankProvider.MAAS:
        model_name = model_name or "bge-reranker-v2-m3"
        return MaaSRerankModel(model_name=model_name, **kwargs)

    raise ValueError(f"Unsupported rerank provider: {provider}")
