"""Rerank Model Module.

This module provides a unified interface for document reranking using various
rerank providers including local BGE models, MaaS API, and others. It supports
both synchronous and asynchronous operations, batch processing, and comprehensive
configuration validation.

Key Components:
    - RerankModel: Abstract base class for all rerank models
    - LocalBGERerankModel: Local BGE reranker models
    - MaaSRerankModel: MaaS (Model as a Service) rerank API client
    - RerankModelConfigChecker: Configuration validation utilities
    - create_rerank_model: Factory function for creating models

Example usage:
    from src.services.rerank_model import (
        create_rerank_model,
        RerankProvider,
        RerankResponse
    )

    # Create a rerank model
    model = create_rerank_model(
        provider=RerankProvider.LOCAL_BGE,
        model_name="BAAI/bge-reranker-base"
    )

    # Rerank documents
    query = "What is machine learning?"
    documents = [
        "Machine learning is a subset of AI.",
        "Python is a programming language.",
        "Deep learning uses neural networks."
    ]
    response = model.rerank(query, documents)

    # Get top results
    top_docs = response.get_top_k(2)
    for result in top_docs:
        print(f"Score: {result.score}, Doc: {result.document}")
"""

# Provider-specific model implementations
from src.services.rerank_model.local_bge_rerank_model import LocalBGERerankModel
from src.services.rerank_model.maas_rerank_model import MaaSRerankModel

# Core rerank model classes and types
from src.services.rerank_model.rerank_model import (
    RerankModel,
    RerankProvider,
    RerankResponse,
    RerankResult,
    create_rerank_model,
)

# Configuration validation
from src.services.rerank_model.rerank_model_config_checker import (
    ConfigValidationError,
    RerankModelConfigChecker,
    check_all_env_configs,
    get_available_providers,
)

__all__ = [
    # Core classes and types
    "RerankModel",
    "RerankProvider",
    "RerankResponse",
    "RerankResult",
    # Model implementations
    "LocalBGERerankModel",
    "MaaSRerankModel",
    # Factory function
    "create_rerank_model",
    # Configuration validation
    "ConfigValidationError",
    "RerankModelConfigChecker",
    "check_all_env_configs",
    "get_available_providers",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
