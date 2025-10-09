"""
AgentCrafter Source Code

Directory structure:
- common/: Shared utilities and services (LLM providers, etc.)
- base_app/: BaseAgent framework
- intent_builder/: Intent-based workflow generation
- agent_builder/: AI-assisted agent development
- Memory System: Graph-Based User Behavior Memory System.

This is a comprehensive memory system based on graph structure, designed to capture,
process, and reason about user behaviors in web/app interactions. The system
implements a four-level modeling architecture and five-layer system design.

Four-Level Modeling Architecture:
    Level 1 - Atomic Intents: Basic user operations (ClickElement, TypeText, etc.)
    Level 2 - Semantic States: Meaningful behavioral states composed of intents
                              (graph nodes: InspectProductPrice, SelectProduct)
    Level 3 - Cognitive Phases: High-level workflow patterns for aggregation
                               (Browsing, Information Extraction)
    Level 4 - User Goals/Tasks: Task-level understanding for intelligent retrieval
                               (Compare Coffee Products, Find Best Deal)

Five-Layer System Design:
    1. Data Capture Layer: Event parsing and atomic intent extraction
    2. Semantic Abstraction: Semantic state construction from intents
    3. Memory Graph Layer: Core graph structure for state storage and relationships
    4. Goal Index/Search: Task-level retrieval and recommendation
    5. Replay & Visualization: Behavior path reconstruction and analysis

Core Features:
    - Graph-based semantic state storage
    - Goal-oriented intelligent retrieval
    - Behavior replay and recommendation
    - Cognitive phrase-based aggregation and analysis
    - Multi-provider LLM/embedding/rerank support

Project Structure:
    - ontology: Core data models (Intent, State, Action, CognitivePhrase)
    - memory: Memory management interfaces and implementations
    - graphstore: Graph storage backends (NetworkX, etc.)
    - services: AI/ML services (LLM, Embedding, Rerank, Prompt)
    - thinker: Workflow processing and semantic extraction
    - reasoner: Intelligent reasoning, retrieval, and goal decomposition

Typical usage example:

    from src import (
        Intent, State, Action, CognitivePhrase,
        WorkflowMemory, NetworkXGraphStorage,
        WorkflowProcessor, Reasoner
    )

    # Initialize memory system
    graph_storage = NetworkXGraphStorage()
    memory = WorkflowMemory(graph_storage)

    # Process workflow
    processor = WorkflowProcessor(memory)
    processor.process_user_workflow(workflow_data)

    # Query and reason
    reasoner = Reasoner(memory)
    results = reasoner.retrieve_similar_workflows(query)
"""

# Graph storage components
from src.graphstore import GraphStore, MemoryGraph, NetworkXGraphStorage

# Memory management components
from src.memory import (
    ActionManager,
    CognitivePhraseManager,
    GraphActionManager,
    GraphStateManager,
    InMemoryCognitivePhraseManager,
    Memory,
    StateManager,
    WorkflowMemory,
)

# Ontology definitions (core data models)
from src.ontology import (
    Action,
    AtomicIntent,
    AtomicIntentType,
    CognitivePhrase,
    Intent,
    IntentType,
    SemanticState,
    SemanticStateType,
    State,
    StateType,
    TransitionEdge,
)

# Reasoning and retrieval components
from src.reasoner import (
    CognitivePhraseChecker,
    Reasoner,
    RetrievalResult,
    RetrievalTool,
    TaskDAG,
    TaskTool,
    ToolResult,
    WorkflowConverter,
    WorkflowResult,
)

# Services layer (LLM, Embedding, Rerank)
from src.services import (
    AnthropicLLMClient,
    BasePrompt,
    ClaudeLLMClient,
    EmbeddingConfigValidationError,
    EmbeddingModel,
    EmbeddingModelConfigChecker,
    EmbeddingProvider,
    EmbeddingResponse,
    LLMClient,
    LLMConfigChecker,
    LLMConfigValidationError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LocalBGEModel,
    LocalBGERerankModel,
    MaaSRerankModel,
    MockLLMClient,
    OpenAIEmbedding,
    OpenAILLMClient,
    PromptInput,
    PromptOutput,
    PromptRegistry,
    PromptTemplate,
    RerankConfigValidationError,
    RerankModel,
    RerankModelConfigChecker,
    RerankProvider,
    RerankResponse,
    RerankResult,
    check_all_embedding_configs,
    check_all_llm_configs,
    check_all_rerank_configs,
    create_embedding_model,
    create_llm_client,
    create_rerank_model,
    get_available_embedding_providers,
    get_available_rerank_providers,
    prompt_registry,
)

# Workflow processing and semantic extraction
from src.thinker import (
    CognitivePhraseGenerator,
    IntentDAGBuilder,
    StateGenerator,
    WorkflowProcessor,
)

__all__ = [
    # Ontology - Core data models
    "Intent",
    "IntentType",
    "AtomicIntent",
    "AtomicIntentType",
    "State",
    "StateType",
    "SemanticState",
    "SemanticStateType",
    "Action",
    "TransitionEdge",
    "CognitivePhrase",
    # Memory - Memory management
    "StateManager",
    "ActionManager",
    "CognitivePhraseManager",
    "Memory",
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "WorkflowMemory",
    # Graphstore - Graph storage
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraphStorage",
    # Reasoner - Reasoning and retrieval
    "Reasoner",
    "RetrievalResult",
    "WorkflowResult",
    "TaskDAG",
    "CognitivePhraseChecker",
    "WorkflowConverter",
    "TaskTool",
    "ToolResult",
    "RetrievalTool",
    # Thinker - Workflow processing
    "IntentDAGBuilder",
    "StateGenerator",
    "CognitivePhraseGenerator",
    "WorkflowProcessor",
    # Services - LLM clients
    "LLMClient",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "OpenAILLMClient",
    "ClaudeLLMClient",
    "AnthropicLLMClient",
    "MockLLMClient",
    "create_llm_client",
    "LLMConfigChecker",
    "LLMConfigValidationError",
    "check_all_llm_configs",
    # Services - Embedding models
    "EmbeddingModel",
    "EmbeddingProvider",
    "EmbeddingResponse",
    "OpenAIEmbedding",
    "LocalBGEModel",
    "create_embedding_model",
    "EmbeddingModelConfigChecker",
    "EmbeddingConfigValidationError",
    "check_all_embedding_configs",
    "get_available_embedding_providers",
    # Services - Rerank models
    "RerankModel",
    "RerankProvider",
    "RerankResponse",
    "RerankResult",
    "LocalBGERerankModel",
    "MaaSRerankModel",
    "create_rerank_model",
    "RerankModelConfigChecker",
    "RerankConfigValidationError",
    "check_all_rerank_configs",
    "get_available_rerank_providers",
    # Services - Prompt management
    "BasePrompt",
    "PromptInput",
    "PromptOutput",
    "PromptRegistry",
    "PromptTemplate",
    "prompt_registry",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
