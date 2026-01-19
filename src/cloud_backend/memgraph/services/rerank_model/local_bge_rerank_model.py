"""Local BGE Rerank Model.

This module provides a local implementation of document reranking using the BGE
(BAAI General Embedding) reranker models. Uses sentence-transformers for efficient
local reranking without external API calls.
"""

from typing import Any, List

from src.cloud_backend.memgraph.services.rerank_model.rerank_model import (
    RerankModel,
    RerankProvider,
    RerankResponse,
    RerankResult,
)


class LocalBGERerankModel(RerankModel):
    """Local BGE reranker model implementation.

    Uses the sentence-transformers library with BGE reranker models to perform
    local document reranking. Supports various BGE reranker model sizes.

    Attributes:
        model_name: The BGE reranker model name.
        provider: Set to RerankProvider.LOCAL_BGE.
        model: The loaded sentence-transformers CrossEncoder model.
        device: Device to run the model on ("cpu" or "cuda").
        config: Additional configuration parameters.
    """

    def __init__(
        self, model_name: str = "BAAI/bge-reranker-base", **kwargs: Any
    ) -> None:
        """Initializes the LocalBGERerankModel.

        Args:
            model_name: The BGE reranker model identifier. Common options:
                - "BAAI/bge-reranker-base" (recommended)
                - "BAAI/bge-reranker-large"
                - "BAAI/bge-reranker-v2-m3"
            **kwargs: Additional configuration parameters:
                - device: Device to run on ("cpu", "cuda", or "auto")
                - batch_size: Batch size for encoding (default: 32)
                - max_length: Maximum sequence length (default: 512)
        """
        super().__init__(model_name=model_name, **kwargs)
        self.provider = RerankProvider.LOCAL_BGE

        # Extract configuration
        self.device = kwargs.get("device", "cpu")
        self.batch_size = kwargs.get("batch_size", 32)
        self.max_length = kwargs.get("max_length", 512)

        # Initialize model (lazy loading)
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Loads the sentence-transformers CrossEncoder model.

        Raises:
            ImportError: If sentence-transformers is not installed.
            Exception: If the model cannot be loaded.
        """
        try:
            # pylint: disable=import-outside-toplevel
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for LocalBGERerankModel. "
                "Install it with: pip install sentence-transformers"
            ) from exc

        try:
            self.model = CrossEncoder(
                self.model_name, max_length=self.max_length, device=self.device
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load BGE reranker model '{self.model_name}': {exc}"
            ) from exc

    def rerank(self, query: str, documents: List[str], **kwargs: Any) -> RerankResponse:
        """Reranks documents based on relevance to the query.

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional parameters:
                - top_k: Return only top K results (default: all).
                - return_documents: Whether to include documents in results (default: True).

        Returns:
            RerankResponse containing reranked results.
        """
        if self.model is None:
            self._load_model()

        # Prepare query-document pairs
        pairs = [[query, doc] for doc in documents]

        # Get relevance scores
        scores = self.model.predict(
            pairs, batch_size=self.batch_size, show_progress_bar=False
        )

        # Create results with original indices
        results = []
        for idx, (doc, score) in enumerate(zip(documents, scores)):
            result = RerankResult(index=idx, document=doc, score=float(score))
            results.append(result)

        # Sort by score (descending)
        results.sort(key=lambda x: x.score, reverse=True)

        # Apply top_k filter if specified
        top_k = kwargs.get("top_k", None)
        if top_k is not None and top_k > 0:
            results = results[:top_k]

        return RerankResponse(
            query=query,
            results=results,
            model=self.model_name,
            provider=self.provider.value,
            usage={"num_documents": len(documents)},
        )

    def rerank_batch(
        self, queries: List[str], documents_list: List[List[str]], **kwargs: Any
    ) -> List[RerankResponse]:
        """Reranks multiple query-documents pairs.

        Args:
            queries: List of query texts.
            documents_list: List of document lists, one per query.
            **kwargs: Additional parameters.

        Returns:
            List of RerankResponse objects, one per query.
        """
        if self.model is None:
            self._load_model()

        if len(queries) != len(documents_list):
            raise ValueError(
                f"Number of queries ({len(queries)}) must match number of "
                f"document lists ({len(documents_list)})"
            )

        # Process each query-documents pair
        responses = []
        for query, documents in zip(queries, documents_list):
            response = self.rerank(query, documents, **kwargs)
            responses.append(response)

        return responses

    async def rerank_async(
        self, query: str, documents: List[str], **kwargs: Any
    ) -> RerankResponse:
        """Reranks documents based on relevance to the query (async).

        Note: Currently wraps the synchronous method. For true async support,
        consider using a thread pool executor in production.

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional parameters.

        Returns:
            RerankResponse containing reranked results.
        """
        # For now, just call synchronous version
        # TODO: Implement true async using asyncio.to_thread or similar
        return self.rerank(query, documents, **kwargs)

    async def rerank_batch_async(
        self, queries: List[str], documents_list: List[List[str]], **kwargs: Any
    ) -> List[RerankResponse]:
        """Reranks multiple query-documents pairs (async).

        Note: Currently wraps the synchronous method. For true async support,
        consider using a thread pool executor in production.

        Args:
            queries: List of query texts.
            documents_list: List of document lists, one per query.
            **kwargs: Additional parameters.

        Returns:
            List of RerankResponse objects, one per query.
        """
        # For now, just call synchronous version
        # TODO: Implement true async using asyncio.to_thread or similar
        return self.rerank_batch(queries, documents_list, **kwargs)

    def check_config(self) -> bool:
        """Validates the model configuration.

        Checks if the model can be loaded successfully.

        Returns:
            True if the model is loaded and ready, False otherwise.
        """
        try:
            if self.model is None:
                self._load_model()
            return self.model is not None
        except Exception:
            return False

    def get_model_info(self) -> dict:
        """Returns information about the loaded model.

        Returns:
            Dictionary containing model metadata.
        """
        if self.model is None:
            self._load_model()

        return {
            "model_name": self.model_name,
            "device": str(self.device),
            "max_length": self.max_length,
            "batch_size": self.batch_size,
        }
