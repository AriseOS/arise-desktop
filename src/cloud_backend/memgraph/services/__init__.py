"""Services Layer - Business Logic Services.

This module provides the core business logic and processing services for the system,
including:

- **LLM (Large Language Model) Clients**: Unified interface for interacting with
  various LLM providers (OpenAI, Anthropic Claude, Mock clients for testing)
- **Embedding Models**: Text embedding generation using OpenAI and local BGE models
- **Rerank Models**: Document reranking for improved retrieval quality
- **Prompt Management**: Base classes and templates for prompt engineering

The services layer abstracts away provider-specific details and provides consistent
APIs for all AI/ML operations used throughout the application.

Typical usage example:

    from src.services import (
        create_llm_client,
        create_embedding_model,
        create_rerank_model,
        LLMProvider,
        EmbeddingProvider,
        RerankProvider
    )

    # Create LLM client
    llm_client = create_llm_client(
        provider=LLMProvider.OPENAI,
        api_client=openai_instance,
        model_name="gpt-4"
    )

    # Create embedding model
    embedding_model = create_embedding_model(
        provider=EmbeddingProvider.OPENAI,
        model_name="text-embedding-ada-002"
    )

    # Create rerank model
    rerank_model = create_rerank_model(
        provider=RerankProvider.LOCAL_BGE,
        model_name="BAAI/bge-reranker-base"
    )
"""

# Embedding model classes and utilities
from src.cloud_backend.memgraph.services.embedding_model import (
    ConfigValidationError as EmbeddingConfigValidationError,
)
from src.cloud_backend.memgraph.services.embedding_model import (
    EmbeddingModel,
    EmbeddingModelConfigChecker,
    EmbeddingProvider,
    EmbeddingResponse,
    LocalBGEModel,
    OpenAIEmbedding,
)
from src.cloud_backend.memgraph.services.embedding_model import (
    check_all_env_configs as check_all_embedding_configs,
)
from src.cloud_backend.memgraph.services.embedding_model import create_embedding_model
from src.cloud_backend.memgraph.services.embedding_model import (
    get_available_providers as get_available_embedding_providers,
)

# Core LLM client classes and utilities
from src.cloud_backend.memgraph.services.llm import AnthropicLLMClient, ClaudeLLMClient
from src.cloud_backend.memgraph.services.llm import ConfigValidationError as LLMConfigValidationError
from src.cloud_backend.memgraph.services.llm import (
    LLMClient,
    LLMConfigChecker,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    MockLLMClient,
    OpenAILLMClient,
)
from src.cloud_backend.memgraph.services.llm import check_all_env_configs as check_all_llm_configs
from src.cloud_backend.memgraph.services.llm import create_llm_client

# Prompt management classes
from src.cloud_backend.memgraph.services.prompt_base import (
    BasePrompt,
    PromptInput,
    PromptOutput,
    PromptRegistry,
    PromptTemplate,
    prompt_registry,
)

# Rerank model classes and utilities
from src.cloud_backend.memgraph.services.rerank_model import (
    ConfigValidationError as RerankConfigValidationError,
)
from src.cloud_backend.memgraph.services.rerank_model import (
    LocalBGERerankModel,
    MaaSRerankModel,
    RerankModel,
    RerankModelConfigChecker,
    RerankProvider,
    RerankResponse,
    RerankResult,
)
from src.cloud_backend.memgraph.services.rerank_model import check_all_env_configs as check_all_rerank_configs
from src.cloud_backend.memgraph.services.rerank_model import create_rerank_model
from src.cloud_backend.memgraph.services.rerank_model import (
    get_available_providers as get_available_rerank_providers,
)

__all__ = [
    # LLM Client - Core classes and types
    "LLMClient",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    # LLM Client - Implementations
    "OpenAILLMClient",
    "ClaudeLLMClient",
    "AnthropicLLMClient",
    "MockLLMClient",
    # LLM Client - Factory and utilities
    "create_llm_client",
    "LLMConfigChecker",
    "LLMConfigValidationError",
    "check_all_llm_configs",
    # Embedding Model - Core classes and types
    "EmbeddingModel",
    "EmbeddingProvider",
    "EmbeddingResponse",
    # Embedding Model - Implementations
    "OpenAIEmbedding",
    "LocalBGEModel",
    # Embedding Model - Factory and utilities
    "create_embedding_model",
    "EmbeddingModelConfigChecker",
    "EmbeddingConfigValidationError",
    "check_all_embedding_configs",
    "get_available_embedding_providers",
    # Rerank Model - Core classes and types
    "RerankModel",
    "RerankProvider",
    "RerankResponse",
    "RerankResult",
    # Rerank Model - Implementations
    "LocalBGERerankModel",
    "MaaSRerankModel",
    # Rerank Model - Factory and utilities
    "create_rerank_model",
    "RerankModelConfigChecker",
    "RerankConfigValidationError",
    "check_all_rerank_configs",
    "get_available_rerank_providers",
    # Prompt Management
    "BasePrompt",
    "PromptInput",
    "PromptOutput",
    "PromptRegistry",
    "PromptTemplate",
    "prompt_registry",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
