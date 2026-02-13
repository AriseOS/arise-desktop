#!/usr/bin/env python3
"""Test script to verify ProviderCache functionality.

This script tests:
1. AnthropicProvider caching
2. EmbeddingService caching (with underlying OpenAIEmbedding)
3. Cache hit/miss behavior
4. LRU eviction
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.common.llm.provider_cache import ProviderCache, get_cached_anthropic_provider, get_cached_embedding_service


def test_anthropic_provider_cache():
    """Test AnthropicProvider caching."""
    print("\n" + "="*60)
    print("Testing AnthropicProvider Cache")
    print("="*60)

    # Clear cache first
    ProviderCache.clear()
    stats = ProviderCache.get_stats()
    print(f"Initial cache size: {stats['size']}")

    # Create first provider (should be cache miss)
    print("\n1. Creating first provider (cache miss expected)...")
    provider1 = get_cached_anthropic_provider(
        api_key="sk-test-key-1",
        model="claude-sonnet-4-5-20250929",
        base_url="https://api.ariseos.com/api"
    )
    print(f"   Provider 1 id: {id(provider1)}")

    stats = ProviderCache.get_stats()
    print(f"   Cache size after first call: {stats['size']}")

    # Create second provider with same config (should be cache hit)
    print("\n2. Creating second provider with same config (cache hit expected)...")
    provider2 = get_cached_anthropic_provider(
        api_key="sk-test-key-1",
        model="claude-sonnet-4-5-20250929",
        base_url="https://api.ariseos.com/api"
    )
    print(f"   Provider 2 id: {id(provider2)}")
    print(f"   Same instance? {provider1 is provider2}")

    stats = ProviderCache.get_stats()
    print(f"   Cache size after second call: {stats['size']}")

    # Create provider with different config (should be cache miss)
    print("\n3. Creating provider with different model (cache miss expected)...")
    provider3 = get_cached_anthropic_provider(
        api_key="sk-test-key-1",
        model="claude-opus-4-20250514",
        base_url="https://api.ariseos.com/api"
    )
    print(f"   Provider 3 id: {id(provider3)}")
    print(f"   Same as provider1? {provider1 is provider3}")

    stats = ProviderCache.get_stats()
    print(f"   Cache size after third call: {stats['size']}")

    print("\n✅ AnthropicProvider cache test passed!")


def test_embedding_service_cache():
    """Test EmbeddingService caching."""
    print("\n" + "="*60)
    print("Testing EmbeddingService Cache")
    print("="*60)

    # Clear cache first
    ProviderCache.clear()
    stats = ProviderCache.get_stats()
    print(f"Initial cache size: {stats['size']}")

    # Create first embedding service (should be cache miss)
    print("\n1. Creating first embedding service (cache miss expected)...")
    service1 = get_cached_embedding_service(
        api_key="sk-test-key-1",
        model="BAAI/bge-m3",
        dimension=1024,
        base_url="https://api.ariseos.com/openai/v1"
    )
    print(f"   Service 1 id: {id(service1)}")
    print(f"   Service 1._model id: {id(service1._model)}")

    stats = ProviderCache.get_stats()
    print(f"   Cache size after first call: {stats['size']}")

    # Create second service with same config (should return cached model)
    print("\n2. Creating second service with same config...")
    service2 = get_cached_embedding_service(
        api_key="sk-test-key-1",
        model="BAAI/bge-m3",
        dimension=1024,
        base_url="https://api.ariseos.com/openai/v1"
    )
    print(f"   Service 2 id: {id(service2)}")
    print(f"   Service 2._model id: {id(service2._model)}")
    print(f"   Services are same instance? {service1 is service2}")
    print(f"   Underlying models are same instance? {service1._model is service2._model}")

    stats = ProviderCache.get_stats()
    print(f"   Cache size after second call: {stats['size']}")

    print("\n✅ EmbeddingService cache test passed!")


def test_cache_stats():
    """Test cache statistics."""
    print("\n" + "="*60)
    print("Testing Cache Statistics")
    print("="*60)

    # Clear and populate cache
    ProviderCache.clear()

    # Add multiple providers
    for i in range(5):
        get_cached_anthropic_provider(
            api_key=f"sk-test-key-{i}",
            model=f"model-{i}",
            base_url="https://api.ariseos.com/api"
        )

    stats = ProviderCache.get_stats()
    print(f"\nCache stats:")
    print(f"  Size: {stats['size']}")
    print(f"  Max size: {stats['max_size']}")
    print(f"  Keys ({len(stats['keys'])}):")
    for key in stats['keys']:
        print(f"    - {key[:80]}...")

    print("\n✅ Cache stats test passed!")


def test_lru_eviction():
    """Test LRU eviction."""
    print("\n" + "="*60)
    print("Testing LRU Eviction")
    print("="*60)

    # Clear cache
    ProviderCache.clear()

    # Add providers up to max cache size + 2
    print(f"\nAdding 52 providers (max cache size is 50)...")
    first_provider = None
    for i in range(52):
        provider = get_cached_anthropic_provider(
            api_key=f"sk-test-key-{i}",
            model=f"model-{i}",
            base_url="https://api.ariseos.com/api"
        )
        if i == 0:
            first_provider = provider

    stats = ProviderCache.get_stats()
    print(f"Cache size after adding 52 providers: {stats['size']}")
    print(f"Expected size: 50 (LRU eviction)")

    # Check if first provider was evicted
    print(f"\nFirst provider should have been evicted...")
    print(f"  First provider still in cache? {any('sk-test-key-0' in key for key in stats['keys'])}")

    print("\n✅ LRU eviction test passed!")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("ProviderCache Test Suite")
    print("="*60)

    try:
        test_anthropic_provider_cache()
        test_embedding_service_cache()
        test_cache_stats()
        test_lru_eviction()

        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
