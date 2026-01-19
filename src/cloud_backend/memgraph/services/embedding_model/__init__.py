"""Embedding Model Module.

This module provides a unified interface for text embeddings using various
embedding providers including OpenAI, local BGE models, and others. It supports
both synchronous and asynchronous operations, batch processing, and comprehensive
configuration validation.

Key Components:
    - EmbeddingModel: Abstract base class for all embedding models
    - OpenAIEmbedding: OpenAI embedding models client
    - LocalBGEModel: Local BGE (BAAI General Embedding) models
    - EmbeddingModelConfigChecker: Configuration validation utilities
    - create_embedding_model: Factory function for creating models

Example usage:
    from src.services.embedding_model import (
        create_embedding_model,
        EmbeddingProvider,
        EmbeddingResponse
    )

    # Create an embedding model
    model = create_embedding_model(
        provider=EmbeddingProvider.OPENAI,
        api_key="your-api-key",
        model_name="text-embedding-ada-002"
    )

    # Generate an embedding
    response = model.embed("Hello, world!")
    print(response.embedding)
    print(response.dimension)
"""

# Core embedding model classes and types
from src.cloud_backend.memgraph.services.embedding_model.embedding_model import (
    EmbeddingModel,
    EmbeddingProvider,
    EmbeddingResponse,
    create_embedding_model,
)

# Configuration validation
from src.cloud_backend.memgraph.services.embedding_model.embedding_model_config_checker import (
    ConfigValidationError,
    EmbeddingModelConfigChecker,
    check_all_env_configs,
    get_available_providers,
)

# Provider-specific model implementations
from src.cloud_backend.memgraph.services.embedding_model.local_bge_model import LocalBGEModel
from src.cloud_backend.memgraph.services.embedding_model.openai_embedding import OpenAIEmbedding

__all__ = [
    # Core classes and types
    "EmbeddingModel",
    "EmbeddingProvider",
    "EmbeddingResponse",
    # Model implementations
    "OpenAIEmbedding",
    "LocalBGEModel",
    # Factory function
    "create_embedding_model",
    # Configuration validation
    "ConfigValidationError",
    "EmbeddingModelConfigChecker",
    "check_all_env_configs",
    "get_available_providers",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
