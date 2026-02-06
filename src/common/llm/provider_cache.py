"""Provider Cache - Unified caching for LLM and Embedding providers.

This module provides a centralized caching mechanism for all provider instances,
avoiding redundant HTTP client creation and SDK initialization.

Cache key format: "{provider_type}:{api_key}:{model}:{base_url}:{dimension}"
- LRU eviction with configurable max size
- Thread-safe operations
- Automatic cache invalidation support

Usage:
    # Get cached AnthropicProvider
    provider = ProviderCache.get_anthropic_provider(
        api_key="sk-...",
        model="claude-sonnet-4-5-20250929",
        base_url="https://api.ariseos.com/api"
    )

    # Get cached EmbeddingService
    embedding_service = ProviderCache.get_embedding_service(
        api_key="sk-...",
        model="BAAI/bge-m3",
        dimension=1024,
        base_url="https://api.ariseos.com/api"
    )
"""

import logging
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Cache configuration
_MAX_CACHE_SIZE = 50  # Maximum number of cached providers


class ProviderCache:
    """Unified cache for all LLM and Embedding providers.

    Uses LRU eviction policy to manage cache size.
    Cache key includes all configuration parameters to ensure correctness.
    """

    # Class-level cache (shared across all instances)
    _cache: OrderedDict[str, Any] = OrderedDict()
    _lock = None  # For thread safety (will be initialized on first use)

    @classmethod
    def _get_lock(cls):
        """Lazy initialize thread lock."""
        if cls._lock is None:
            import threading
            cls._lock = threading.RLock()
        return cls._lock

    @classmethod
    def _generate_cache_key(
        cls,
        provider_type: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> str:
        """Generate cache key from provider configuration.

        Args:
            provider_type: Type of provider (anthropic, openai, embedding)
            api_key: API key for authentication
            model: Model name
            base_url: Custom API base URL
            dimension: Embedding dimension (for embedding services only)

        Returns:
            Cache key string
        """
        # Normalize base_url (None -> empty string)
        base_url = base_url or ""

        # For embedding services, include dimension
        if dimension is not None:
            return f"{provider_type}:{api_key}:{model}:{base_url}:{dimension}"
        else:
            return f"{provider_type}:{api_key}:{model}:{base_url}"

    @classmethod
    def _evict_if_needed(cls) -> None:
        """Evict oldest entries if cache exceeds max size."""
        while len(cls._cache) > _MAX_CACHE_SIZE:
            oldest_key, _ = cls._cache.popitem(last=False)
            logger.debug(f"ProviderCache: evicted {oldest_key}")

    @classmethod
    def get(cls, cache_key: str) -> Optional[Any]:
        """Get provider from cache.

        Args:
            cache_key: Cache key to look up

        Returns:
            Cached provider instance or None if not found
        """
        with cls._get_lock():
            if cache_key in cls._cache:
                # Move to end (most recently used)
                cls._cache.move_to_end(cache_key)
                logger.debug(f"ProviderCache: cache hit for {cache_key[:50]}...")
                return cls._cache[cache_key]
            logger.debug(f"ProviderCache: cache miss for {cache_key[:50]}...")
            return None

    @classmethod
    def put(cls, cache_key: str, provider: Any) -> None:
        """Add provider to cache.

        Args:
            cache_key: Cache key
            provider: Provider instance to cache
        """
        with cls._get_lock():
            cls._cache[cache_key] = provider
            cls._evict_if_needed()
            logger.info(f"ProviderCache: cached {cache_key[:50]}... (total: {len(cls._cache)})")

    @classmethod
    def clear(cls) -> int:
        """Clear all cached providers.

        Returns:
            Number of providers cleared
        """
        with cls._get_lock():
            count = len(cls._cache)
            cls._cache.clear()
            logger.info(f"ProviderCache: cleared {count} cached providers")
            return count

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (size, keys)
        """
        with cls._get_lock():
            return {
                "size": len(cls._cache),
                "keys": list(cls._cache.keys()),
                "max_size": _MAX_CACHE_SIZE,
            }

    # ========================================================================
    # Anthropic Provider
    # ========================================================================

    @classmethod
    def get_anthropic_provider(
        cls,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Get or create AnthropicProvider.

        Args:
            api_key: Anthropic API key
            model: Model name (e.g., 'claude-sonnet-4-5-20250929')
            base_url: Custom API base URL (for proxy)
            **kwargs: Additional arguments passed to AnthropicProvider

        Returns:
            AnthropicProvider instance (cached or newly created)
        """
        from src.common.llm import AnthropicProvider

        cache_key = cls._generate_cache_key(
            provider_type="anthropic",
            api_key=api_key,
            model=model,
            base_url=base_url,
        )

        # Check cache
        cached = cls.get(cache_key)
        if cached is not None:
            return cached

        # Create new provider
        logger.info(
            f"ProviderCache: creating new AnthropicProvider "
            f"(model={model}, base_url={base_url or 'default'})"
        )
        provider = AnthropicProvider(
            api_key=api_key,
            model_name=model,
            base_url=base_url,
            **kwargs,
        )

        # Cache it
        cls.put(cache_key, provider)
        return provider

    # ========================================================================
    # OpenAI Embedding Model (for EmbeddingService)
    # ========================================================================

    @classmethod
    def get_openai_embedding_model(
        cls,
        api_key: str,
        model: str = "text-embedding-ada-002",
        dimension: int = 1536,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Get or create OpenAIEmbedding model instance.

        Note: EmbeddingService wraps this model, so we cache the model
        to avoid creating duplicate OpenAI clients.

        Args:
            api_key: OpenAI API key
            model: Model name (e.g., 'text-embedding-ada-002', 'BAAI/bge-m3')
            dimension: Embedding vector dimension
            base_url: Custom API base URL (for proxy)
            **kwargs: Additional arguments passed to OpenAIEmbedding

        Returns:
            OpenAIEmbedding instance (cached or newly created)
        """
        from src.common.memory.services.embedding_model.openai_embedding import (
            OpenAIEmbedding,
        )

        cache_key = cls._generate_cache_key(
            provider_type="openai_embedding",
            api_key=api_key,
            model=model,
            base_url=base_url,
            dimension=dimension,
        )

        # Check cache
        cached = cls.get(cache_key)
        if cached is not None:
            return cached

        # Create new model
        logger.info(
            f"ProviderCache: creating new OpenAIEmbedding "
            f"(model={model}, dimension={dimension}, base_url={base_url or 'default'})"
        )
        embedding_model = OpenAIEmbedding(
            model_name=model,
            dimension=dimension,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

        # Cache it
        cls.put(cache_key, embedding_model)
        return embedding_model

    # ========================================================================
    # Embedding Service (delegates to cached model)
    # ========================================================================

    @classmethod
    def get_embedding_service(
        cls,
        api_key: str,
        model: str = "BAAI/bge-m3",
        dimension: int = 1024,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs: Any,
    ) -> Any:
        """Get or create EmbeddingService with cached underlying model.

        Note: EmbeddingService itself is lightweight (just a wrapper).
        The heavy OpenAI client is cached at the model level.

        Args:
            api_key: API key for embedding service
            model: Model name (e.g., 'BAAI/bge-m3')
            dimension: Embedding vector dimension
            base_url: Custom API base URL (for proxy)
            provider: Provider type ('openai' or 'local_bge')
            **kwargs: Additional arguments passed to EmbeddingService

        Returns:
            EmbeddingService instance (new wrapper, but with cached model)
        """
        from src.common.memory.services.embedding_service import EmbeddingService

        # For openai provider, use cached model
        if provider == "openai":
            # Get or create cached OpenAIEmbedding model
            embedding_model = cls.get_openai_embedding_model(
                api_key=api_key,
                model=model,
                dimension=dimension,
                base_url=base_url,
                **kwargs,
            )

            # Create lightweight wrapper service
            service = EmbeddingService(
                api_key=api_key,
                model=model,
                dimension=dimension,
                base_url=base_url,
                provider=provider,
                **kwargs,
            )

            # Inject cached model (avoid re-creating OpenAI client)
            service._model = embedding_model
            service._initialized = True

            return service

        # For local_bge, create new service (no HTTP client to cache)
        else:
            logger.info(
                f"ProviderCache: creating new EmbeddingService "
                f"(provider={provider}, model={model}, dimension={dimension})"
            )
            return EmbeddingService(
                api_key=api_key,
                model=model,
                dimension=dimension,
                base_url=base_url,
                provider=provider,
                **kwargs,
            )


# ========================================================================
# Convenience Functions
# ========================================================================


def get_cached_anthropic_provider(
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Convenience function to get cached AnthropicProvider.

    Args:
        api_key: Anthropic API key
        model: Model name
        base_url: Custom API base URL
        **kwargs: Additional arguments

    Returns:
        AnthropicProvider instance
    """
    return ProviderCache.get_anthropic_provider(
        api_key=api_key,
        model=model,
        base_url=base_url,
        **kwargs,
    )


def get_cached_embedding_service(
    api_key: str,
    model: str = "BAAI/bge-m3",
    dimension: int = 1024,
    base_url: Optional[str] = None,
    provider: str = "openai",
    **kwargs: Any,
) -> Any:
    """Convenience function to get cached EmbeddingService.

    Args:
        api_key: API key
        model: Model name
        dimension: Embedding dimension
        base_url: Custom API base URL
        provider: Provider type
        **kwargs: Additional arguments

    Returns:
        EmbeddingService instance
    """
    return ProviderCache.get_embedding_service(
        api_key=api_key,
        model=model,
        dimension=dimension,
        base_url=base_url,
        provider=provider,
        **kwargs,
    )
