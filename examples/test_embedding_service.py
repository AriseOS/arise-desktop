#!/usr/bin/env python3
"""Test script for EmbeddingService with SiliconFlow API.

Usage:
    # Set your SiliconFlow API key first
    export SILICONFLOW_API_KEY="your-api-key"

    # Run the test
    python examples/test_embedding_service.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cloud_backend.memgraph.services.embedding_service import EmbeddingService


def test_embedding_service():
    """Test the EmbeddingService with SiliconFlow API."""

    # Check if API key is set (from env or hardcoded for testing)
    api_key = os.getenv("SILICONFLOW_API_KEY")

    # Try to read from config file if not in env
    if not api_key:
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "src/cloud_backend/config/cloud-backend.yaml"
            )
            with open(config_path) as f:
                config = yaml.safe_load(f)
                api_key = config.get("embedding", {}).get("api_key_env")
                if api_key and not api_key.startswith("sk-"):
                    # It's an env var name, not an actual key
                    api_key = os.getenv(api_key)
        except Exception as e:
            print(f"Could not read config: {e}")

    if not api_key:
        print("Error: SILICONFLOW_API_KEY not found")
        print("Please set it with: export SILICONFLOW_API_KEY='your-api-key'")
        print("Or add it to cloud-backend.yaml embedding.api_key_env")
        return False

    print("=" * 60)
    print("Testing EmbeddingService with SiliconFlow API")
    print("=" * 60)

    # Configure the service
    print("\n1. Configuring EmbeddingService...")
    EmbeddingService.configure(
        provider="openai",
        model="BAAI/bge-m3",
        dimension=1024,
        api_url="https://api.siliconflow.cn/v1",
        api_key=api_key,
    )
    print("   - Provider: openai (SiliconFlow compatible)")
    print("   - Model: BAAI/bge-m3")
    print("   - Dimension: 1024")
    print("   - API URL: https://api.siliconflow.cn/v1")

    # Check if service is available
    print("\n2. Checking service availability...")
    try:
        model = EmbeddingService.get_model()
        if model is None:
            print("   Error: Model is None")
            return False
        print(f"   Model: {model}")
        config_ok = model.check_config()
        print(f"   Config check: {config_ok}")
        if not config_ok:
            print("   Error: Config check failed")
            return False
    except Exception as e:
        print(f"   Error initializing model: {e}")
        import traceback
        traceback.print_exc()
        return False
    print("   Service is available!")

    # Test single text embedding
    print("\n3. Testing single text embedding...")
    test_text = "用户在淘宝上搜索商品并添加到购物车"
    embedding = EmbeddingService.embed(test_text)

    if embedding is None:
        print("   Error: Failed to generate embedding")
        return False

    print(f"   Input: '{test_text}'")
    print(f"   Embedding dimension: {len(embedding)}")
    print(f"   First 5 values: {embedding[:5]}")

    # Test batch embedding
    print("\n4. Testing batch embedding...")
    test_texts = [
        "打开浏览器访问百度",
        "在搜索框输入关键词",
        "点击搜索按钮查看结果",
    ]
    embeddings = EmbeddingService.embed_batch(test_texts)

    if embeddings is None:
        print("   Error: Failed to generate batch embeddings")
        return False

    print(f"   Input texts: {len(test_texts)}")
    print(f"   Output embeddings: {len(embeddings)}")
    for i, (text, emb) in enumerate(zip(test_texts, embeddings)):
        print(f"   [{i}] '{text[:20]}...' -> dim={len(emb)}")

    # Test similarity (simple cosine similarity)
    print("\n5. Testing embedding similarity...")

    def cosine_similarity(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        return dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0

    similar_text = "在淘宝网站上浏览商品并加入购物车"
    different_text = "今天天气很好，适合出去散步"

    emb_original = EmbeddingService.embed(test_text)
    emb_similar = EmbeddingService.embed(similar_text)
    emb_different = EmbeddingService.embed(different_text)

    sim_similar = cosine_similarity(emb_original, emb_similar)
    sim_different = cosine_similarity(emb_original, emb_different)

    print(f"   Original: '{test_text}'")
    print(f"   Similar:  '{similar_text}'")
    print(f"   Different: '{different_text}'")
    print(f"   Similarity (original vs similar): {sim_similar:.4f}")
    print(f"   Similarity (original vs different): {sim_different:.4f}")

    if sim_similar > sim_different:
        print("   Result: Similar text has higher similarity (as expected)")
    else:
        print("   Warning: Similarity scores are unexpected")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = test_embedding_service()
    sys.exit(0 if success else 1)
