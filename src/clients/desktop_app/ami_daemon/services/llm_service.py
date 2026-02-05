"""LLMService - Singleton service for managing LLM providers.

Provides centralized management of AnthropicProvider instances with LRU caching
by API key, avoiding redundant provider creation.
"""

import logging
from collections import OrderedDict
from typing import Optional

from src.common.llm import AnthropicProvider
from src.clients.desktop_app.ami_daemon.core.config_service import get_config

logger = logging.getLogger(__name__)

# Maximum number of cached providers
_MAX_CACHED_PROVIDERS = 10


class LLMService:
    """Singleton service for managing LLM providers.

    Caches AnthropicProvider instances by API key using LRU eviction.
    Configuration (model, base_url) comes from app-backend.yaml.

    Usage:
        service = LLMService.get_instance()
        provider = service.get_provider(api_key)
    """

    _instance: Optional["LLMService"] = None
    _providers: OrderedDict[str, AnthropicProvider]

    def __init__(self):
        """Initialize LLMService.

        Use get_instance() instead of direct instantiation.
        """
        self._providers = OrderedDict()
        self._config = get_config()
        logger.info("LLMService initialized")

    @classmethod
    def get_instance(cls) -> "LLMService":
        """Get the singleton LLMService instance.

        Returns:
            LLMService singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_provider(self, api_key: str) -> AnthropicProvider:
        """Get or create an AnthropicProvider for the given API key.

        Uses LRU caching to avoid creating duplicate providers.
        Configuration is read from app-backend.yaml:
        - llm.model: Model name (required)
        - llm.proxy_url: API proxy base URL

        Args:
            api_key: User's API key for authentication

        Returns:
            AnthropicProvider instance configured with the API key

        Raises:
            ValueError: If llm.model is not configured
        """
        # Check cache (and move to end for LRU)
        if api_key in self._providers:
            # Move to end (most recently used)
            self._providers.move_to_end(api_key)
            logger.debug(f"LLMService: reusing cached provider for key {api_key[:10]}...")
            return self._providers[api_key]

        # Create new provider
        model = self._config.get("llm.model")
        if not model:
            raise ValueError("llm.model not configured in app-backend.yaml")
        base_url = self._config.get("llm.proxy_url")

        provider = AnthropicProvider(
            api_key=api_key,
            model_name=model,
            base_url=base_url,
        )

        # Add to cache
        self._providers[api_key] = provider

        # LRU eviction if over limit
        while len(self._providers) > _MAX_CACHED_PROVIDERS:
            evicted_key, _ = self._providers.popitem(last=False)
            logger.debug(f"LLMService: evicted provider for key {evicted_key[:10]}...")

        logger.info(
            f"LLMService: created new provider for key {api_key[:10]}... "
            f"(model={model}, base_url={base_url or 'default'})"
        )
        return provider

    def get_provider_sync(self, api_key: str) -> AnthropicProvider:
        """Synchronous version of get_provider.

        Provided for convenience when calling from non-async code.

        Args:
            api_key: User's API key for authentication

        Returns:
            AnthropicProvider instance configured with the API key
        """
        return self.get_provider(api_key)

    def clear_cache(self) -> int:
        """Clear all cached providers.

        Returns:
            Number of providers cleared
        """
        count = len(self._providers)
        self._providers.clear()
        logger.info(f"LLMService: cleared {count} cached providers")
        return count


def get_llm_service() -> LLMService:
    """Get the singleton LLMService instance.

    Convenience function for easy import.

    Returns:
        LLMService singleton instance
    """
    return LLMService.get_instance()
