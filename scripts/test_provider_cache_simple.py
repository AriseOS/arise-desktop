#!/usr/bin/env python3
"""Simple test to verify ProviderCache logic without external dependencies.

Tests the caching mechanism itself (LRU, cache keys, etc.).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_cache_key_generation():
    """Test cache key generation."""
    print("\n" + "="*60)
    print("Testing Cache Key Generation")
    print("="*60)

    from src.common.llm.provider_cache import ProviderCache

    # Test basic key generation
    key1 = ProviderCache._generate_cache_key(
        provider_type="anthropic",
        api_key="sk-test-123",
        model="claude-sonnet-4-5",
        base_url="https://api.ariseos.com/api"
    )
    print(f"\nKey 1: {key1}")
    assert key1 == "anthropic:sk-test-123:claude-sonnet-4-5:https://api.ariseos.com/api"

    # Test with None base_url
    key2 = ProviderCache._generate_cache_key(
        provider_type="anthropic",
        api_key="sk-test-123",
        model="claude-sonnet-4-5",
        base_url=None
    )
    print(f"Key 2 (None base_url): {key2}")
    assert key2 == "anthropic:sk-test-123:claude-sonnet-4-5:"

    # Test with dimension
    key3 = ProviderCache._generate_cache_key(
        provider_type="openai_embedding",
        api_key="sk-test-123",
        model="BAAI/bge-m3",
        base_url="https://api.ariseos.com/openai/v1",
        dimension=1024
    )
    print(f"Key 3 (with dimension): {key3}")
    assert key3 == "openai_embedding:sk-test-123:BAAI/bge-m3:https://api.ariseos.com/openai/v1:1024"

    print("\n✅ Cache key generation test passed!")


def test_cache_basic_operations():
    """Test basic cache operations (get, put, clear)."""
    print("\n" + "="*60)
    print("Testing Basic Cache Operations")
    print("="*60)

    from src.common.llm.provider_cache import ProviderCache

    # Clear cache
    ProviderCache.clear()
    assert ProviderCache.get_stats()['size'] == 0

    # Test cache miss
    result = ProviderCache.get("nonexistent_key")
    assert result is None
    print("✓ Cache miss returns None")

    # Test put and get
    test_obj = {"data": "test"}
    ProviderCache.put("test_key", test_obj)
    assert ProviderCache.get_stats()['size'] == 1
    print("✓ Put increases cache size")

    retrieved = ProviderCache.get("test_key")
    assert retrieved is test_obj
    print("✓ Get returns cached object")

    # Test clear
    count = ProviderCache.clear()
    assert count == 1
    assert ProviderCache.get_stats()['size'] == 0
    print("✓ Clear empties cache")

    print("\n✅ Basic cache operations test passed!")


def test_lru_behavior():
    """Test LRU eviction behavior."""
    print("\n" + "="*60)
    print("Testing LRU Eviction Behavior")
    print("="*60)

    from src.common.llm.provider_cache import ProviderCache

    # Clear cache
    ProviderCache.clear()

    # Add items up to max size (50)
    max_size = ProviderCache.get_stats()['max_size']
    print(f"Max cache size: {max_size}")

    for i in range(max_size):
        ProviderCache.put(f"key_{i}", f"value_{i}")

    stats = ProviderCache.get_stats()
    assert stats['size'] == max_size
    print(f"✓ Cache filled to max size: {stats['size']}")

    # Access first item (make it recently used)
    ProviderCache.get("key_0")
    ProviderCache.get("key_1")

    # Add one more item (should evict key_2, not key_0 or key_1)
    ProviderCache.put(f"key_{max_size}", f"value_{max_size}")

    stats = ProviderCache.get_stats()
    assert stats['size'] == max_size
    print(f"✓ Cache size remains at max: {stats['size']}")

    # Check which keys exist
    keys = stats['keys']
    assert "key_0" in keys
    assert "key_1" in keys
    assert "key_2" not in keys  # This should have been evicted
    assert f"key_{max_size}" in keys
    print("✓ LRU eviction works correctly (oldest unused key evicted)")

    print("\n✅ LRU behavior test passed!")


def test_thread_safety():
    """Test that cache has thread lock."""
    print("\n" + "="*60)
    print("Testing Thread Safety")
    print("="*60)

    from src.common.llm.provider_cache import ProviderCache

    # Get lock (should initialize it)
    lock = ProviderCache._get_lock()
    assert lock is not None
    print("✓ Thread lock initialized")

    # Test lock acquisition
    with lock:
        ProviderCache.put("test", "value")
    print("✓ Lock can be acquired and released")

    print("\n✅ Thread safety test passed!")


def test_cache_stats():
    """Test cache statistics."""
    print("\n" + "="*60)
    print("Testing Cache Statistics")
    print("="*60)

    from src.common.llm.provider_cache import ProviderCache

    ProviderCache.clear()

    # Add some items
    for i in range(5):
        ProviderCache.put(f"key_{i}", f"value_{i}")

    stats = ProviderCache.get_stats()
    assert stats['size'] == 5
    assert stats['max_size'] == 50
    assert len(stats['keys']) == 5
    assert 'key_0' in stats['keys']
    assert 'key_4' in stats['keys']

    print(f"✓ Stats correct: size={stats['size']}, max_size={stats['max_size']}")
    print(f"✓ Keys: {stats['keys']}")

    print("\n✅ Cache stats test passed!")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("ProviderCache Logic Test Suite (No External Dependencies)")
    print("="*60)

    try:
        test_cache_key_generation()
        test_cache_basic_operations()
        test_lru_behavior()
        test_thread_safety()
        test_cache_stats()

        print("\n" + "="*60)
        print("✅ All logic tests passed!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
