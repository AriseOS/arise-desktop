"""MaaS Rerank Model.

This module provides an implementation of document reranking using MaaS
(Model as a Service) API. Supports BGE and other reranker models via HTTP API.
"""

import os
from typing import Any, List, Optional

import requests

from src.cloud_backend.memgraph.services.rerank_model.rerank_model import (
    RerankModel,
    RerankProvider,
    RerankResponse,
    RerankResult,
)


class MaaSRerankModel(RerankModel):
    """MaaS reranker model implementation.

    Uses MaaS API to perform document reranking. Supports various reranker
    models hosted on the MaaS platform.

    Attributes:
        model_name: The MaaS model name.
        provider: Set to RerankProvider.MAAS.
        api_key: The MaaS API key.
        base_url: The MaaS API base URL.
        timeout: Request timeout in seconds.
        config: Additional configuration parameters.
    """

    def __init__(
        self,
        model_name: str = "bge-reranker-v2-m3",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initializes the MaaSRerankModel.

        Args:
            model_name: The MaaS reranker model name. Options:
                - "bge-reranker-v2-m3" (recommended)
                - "bge-reranker-base"
                - "bge-reranker-large"
            api_key: MaaS API key (optional, reads from env if not provided).
            base_url: MaaS API base URL (optional, uses default if not provided).
            **kwargs: Additional configuration parameters:
                - timeout: Request timeout in seconds (default: 30)
                - max_retries: Maximum number of retries (default: 3)
        """
        super().__init__(model_name=model_name, **kwargs)
        self.provider = RerankProvider.MAAS

        # Get API credentials
        self.api_key = api_key or os.getenv("MAAS_API_KEY")
        self.base_url = base_url or os.getenv(
            "MAAS_BASE_URL", "https://api.maas.example.com"  # Default placeholder
        )

        # Extract configuration
        self.timeout = kwargs.get("timeout", 30)
        self.max_retries = kwargs.get("max_retries", 3)

    def _make_request(self, endpoint: str, payload: dict) -> dict:
        """Makes an HTTP request to the MaaS API.

        Args:
            endpoint: API endpoint path.
            payload: Request payload.

        Returns:
            Response JSON as dictionary.

        Raises:
            ValueError: If API key is not configured.
            RuntimeError: If the API call fails.
        """
        if not self.api_key:
            raise ValueError(
                "MaaS API key is required. Set MAAS_API_KEY environment "
                "variable or provide api_key parameter."
            )

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"MaaS API request failed: {exc}") from exc

    def rerank(self, query: str, documents: List[str], **kwargs: Any) -> RerankResponse:
        """Reranks documents based on relevance to the query.

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional parameters:
                - top_k: Return only top K results (default: all).

        Returns:
            RerankResponse containing reranked results.

        Raises:
            RuntimeError: If the API call fails.
        """
        # Prepare request payload
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
        }

        # Add optional parameters
        top_k = kwargs.get("top_k", None)
        if top_k is not None:
            payload["top_k"] = top_k

        # Make API request
        response_data = self._make_request("/v1/rerank", payload)

        # Parse response
        results = []
        for item in response_data.get("results", []):
            result = RerankResult(
                index=item["index"],
                document=item.get("document", documents[item["index"]]),
                score=float(item["relevance_score"]),
            )
            results.append(result)

        # Extract usage information
        usage = response_data.get("usage", {})

        return RerankResponse(
            query=query,
            results=results,
            model=self.model_name,
            provider=self.provider.value,
            usage=usage,
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

        Raises:
            ValueError: If number of queries doesn't match documents lists.
            RuntimeError: If the API call fails.
        """
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

        Args:
            query: Query text.
            documents: List of documents to rerank.
            **kwargs: Additional parameters.

        Returns:
            RerankResponse containing reranked results.

        Raises:
            ImportError: If aiohttp is not installed.
            ValueError: If API key is not configured.
            RuntimeError: If the API call fails.
        """
        try:
            # pylint: disable=import-outside-toplevel
            import aiohttp
        except ImportError as exc:
            raise ImportError(
                "aiohttp is required for async operations. "
                "Install it with: pip install aiohttp"
            ) from exc

        if not self.api_key:
            raise ValueError(
                "MaaS API key is required. Set MAAS_API_KEY environment "
                "variable or provide api_key parameter."
            )

        # Prepare request payload
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
        }

        top_k = kwargs.get("top_k", None)
        if top_k is not None:
            payload["top_k"] = top_k

        # Make async API request
        url = f"{self.base_url.rstrip('/')}/v1/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()

        except aiohttp.ClientError as exc:
            raise RuntimeError(f"MaaS async API request failed: {exc}") from exc

        # Parse response
        results = []
        for item in response_data.get("results", []):
            result = RerankResult(
                index=item["index"],
                document=item.get("document", documents[item["index"]]),
                score=float(item["relevance_score"]),
            )
            results.append(result)

        usage = response_data.get("usage", {})

        return RerankResponse(
            query=query,
            results=results,
            model=self.model_name,
            provider=self.provider.value,
            usage=usage,
        )

    async def rerank_batch_async(
        self, queries: List[str], documents_list: List[List[str]], **kwargs: Any
    ) -> List[RerankResponse]:
        """Reranks multiple query-documents pairs (async).

        Args:
            queries: List of query texts.
            documents_list: List of document lists, one per query.
            **kwargs: Additional parameters.

        Returns:
            List of RerankResponse objects, one per query.

        Raises:
            ValueError: If number of queries doesn't match documents lists.
            RuntimeError: If the API call fails.
        """
        if len(queries) != len(documents_list):
            raise ValueError(
                f"Number of queries ({len(queries)}) must match number of "
                f"document lists ({len(documents_list)})"
            )

        # Process each query-documents pair concurrently
        # pylint: disable=import-outside-toplevel
        import asyncio

        tasks = [
            self.rerank_async(query, documents, **kwargs)
            for query, documents in zip(queries, documents_list)
        ]
        responses = await asyncio.gather(*tasks)

        return list(responses)

    def check_config(self) -> bool:
        """Validates the model configuration.

        Checks if the API key is available.

        Returns:
            True if configuration is valid, False otherwise.
        """
        return bool(self.api_key and self.base_url)
